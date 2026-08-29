from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import (
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
    SessionProfile,
)
from yandex_analytics_reaper.experiments import (
    SessionProfileBlockObservation,
    SessionProfileBlockOrder,
    SessionProfileCohortError,
    SessionProfileDepthClassification,
    SessionProfileRunObservation,
    SessionProfileStabilityExperiment,
    evaluate_session_profile_blocks,
)
from yandex_analytics_reaper.experiments import session_profile_stability as stability
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore

_SESSION_ID = "session:0123456789abcdef0123456789abcdef"


def _run_observation(
    run_id: str,
    started_at: datetime,
    *,
    profile: SessionProfile,
    ranking: tuple[int, ...],
    session_instance_id: str = _SESSION_ID,
) -> SessionProfileRunObservation:
    return SessionProfileRunObservation(
        run_id=run_id,
        started_at=started_at,
        session_profile=profile,
        session_instance_id=(
            None if profile is SessionProfile.CLEAN_ANONYMOUS else session_instance_id
        ),
        organic_rankings={depth: ranking for depth in (1, 3, 5, 10)},
    )


def _block(
    block_id: str,
    started_at: datetime,
    *,
    order: SessionProfileBlockOrder,
    clean_rankings: tuple[tuple[int, ...], tuple[int, ...]],
    persistent_rankings: tuple[tuple[int, ...], tuple[int, ...]],
    session_instance_id: str = _SESSION_ID,
) -> SessionProfileBlockObservation:
    starts = [started_at + timedelta(minutes=index) for index in range(4)]
    if order is SessionProfileBlockOrder.CLEAN_OUTER:
        profiles = (
            SessionProfile.CLEAN_ANONYMOUS,
            SessionProfile.PERSISTENT_ANONYMOUS,
            SessionProfile.PERSISTENT_ANONYMOUS,
            SessionProfile.CLEAN_ANONYMOUS,
        )
        rankings = (
            clean_rankings[0],
            persistent_rankings[0],
            persistent_rankings[1],
            clean_rankings[1],
        )
    else:
        profiles = (
            SessionProfile.PERSISTENT_ANONYMOUS,
            SessionProfile.CLEAN_ANONYMOUS,
            SessionProfile.CLEAN_ANONYMOUS,
            SessionProfile.PERSISTENT_ANONYMOUS,
        )
        rankings = (
            persistent_rankings[0],
            clean_rankings[0],
            clean_rankings[1],
            persistent_rankings[1],
        )

    runs = tuple(
        _run_observation(
            f"{block_id}-{index}",
            starts[index],
            profile=profiles[index],
            ranking=rankings[index],
            session_instance_id=session_instance_id,
        )
        for index in range(4)
    )
    clean = tuple(run for run in runs if run.session_profile is SessionProfile.CLEAN_ANONYMOUS)
    persistent = tuple(
        run for run in runs if run.session_profile is SessionProfile.PERSISTENT_ANONYMOUS
    )
    assert len(clean) == 2 and len(persistent) == 2
    return SessionProfileBlockObservation(
        run_ids=(runs[0].run_id, runs[1].run_id, runs[2].run_id, runs[3].run_id),
        started_at=runs[0].started_at,
        order=order,
        persistent_session_instance_id=session_instance_id,
        clean_runs=(clean[0], clean[1]),
        persistent_runs=(persistent[0], persistent[1]),
    )


def _sample_blocks(
    *,
    clean_rankings: tuple[tuple[int, ...], tuple[int, ...]],
    persistent_rankings: tuple[tuple[int, ...], tuple[int, ...]],
) -> list[SessionProfileBlockObservation]:
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    hours = (0, 1, 2, 4, 5, 6)
    return [
        _block(
            f"block-{index}",
            base + timedelta(hours=hour),
            order=(
                SessionProfileBlockOrder.CLEAN_OUTER
                if index % 2 == 0
                else SessionProfileBlockOrder.PERSISTENT_OUTER
            ),
            clean_rankings=clean_rankings,
            persistent_rankings=persistent_rankings,
        )
        for index, hour in enumerate(hours)
    ]


def test_report_refuses_classification_until_matched_sample_is_sufficient() -> None:
    ranking = (1, 2, 3, 4)
    blocks = _sample_blocks(
        clean_rankings=(ranking, ranking),
        persistent_rankings=(ranking, ranking),
    )[:2]

    report = evaluate_session_profile_blocks(blocks)

    assert report.sample_sufficient is False
    assert report.eligible_block_count == 2
    assert all(metric.classification is None for metric in report.metrics)
    assert any("eligible blocks=2" in reason for reason in report.decision_reasons)


def test_stable_classification_requires_cross_profile_similarity_within_tolerances() -> None:
    ranking = (1, 2, 3, 4)
    report = evaluate_session_profile_blocks(
        _sample_blocks(
            clean_rankings=(ranking, ranking),
            persistent_rankings=(ranking, ranking),
        )
    )

    assert report.sample_sufficient is True
    assert report.clean_outer_block_count == 3
    assert report.persistent_outer_block_count == 3
    assert report.persistent_session_instance_id == _SESSION_ID
    assert all(
        metric.classification is SessionProfileDepthClassification.STABLE
        for metric in report.metrics
    )
    assert all(metric.median_jaccard_profile_gap == 0.0 for metric in report.metrics)


def test_material_difference_when_cross_profile_gap_exceeds_frozen_tolerance() -> None:
    report = evaluate_session_profile_blocks(
        _sample_blocks(
            clean_rankings=((1, 2, 3, 4), (1, 2, 3, 4)),
            persistent_rankings=((10, 11, 12, 13), (10, 11, 12, 13)),
        )
    )

    assert report.sample_sufficient is True
    assert all(
        metric.classification is SessionProfileDepthClassification.MATERIAL_DIFFERENCE
        for metric in report.metrics
    )
    assert all(metric.median_jaccard_profile_gap == pytest.approx(1.0) for metric in report.metrics)


def test_inconclusive_when_same_profile_repeatability_is_below_floor() -> None:
    report = evaluate_session_profile_blocks(
        _sample_blocks(
            clean_rankings=((1, 2, 3, 4), (5, 6, 7, 8)),
            persistent_rankings=((1, 2, 3, 4), (1, 2, 3, 4)),
        )
    )

    assert report.sample_sufficient is True
    assert all(
        metric.classification is SessionProfileDepthClassification.INCONCLUSIVE
        for metric in report.metrics
    )
    assert all(
        metric.median_within_baseline_jaccard == pytest.approx(0.0)
        for metric in report.metrics
    )


def test_evaluator_rejects_mixed_persistent_session_instances() -> None:
    first = _block(
        "first",
        datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        order=SessionProfileBlockOrder.CLEAN_OUTER,
        clean_rankings=((1,), (1,)),
        persistent_rankings=((1,), (1,)),
    )
    second = _block(
        "second",
        datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        order=SessionProfileBlockOrder.PERSISTENT_OUTER,
        clean_rankings=((1,), (1,)),
        persistent_rankings=((1,), (1,)),
        session_instance_id="session:fedcba9876543210fedcba9876543210",
    )

    with pytest.raises(SessionProfileCohortError, match="multiple persistent session instances"):
        evaluate_session_profile_blocks([first, second])


def test_evaluator_rejects_one_run_reused_across_distinct_blocks() -> None:
    first = _block(
        "first",
        datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        order=SessionProfileBlockOrder.CLEAN_OUTER,
        clean_rankings=((1,), (1,)),
        persistent_rankings=((1,), (1,)),
    )
    shared_clean = first.clean_runs[0]
    persistent_one = _run_observation(
        "second-p1",
        shared_clean.started_at + timedelta(minutes=1),
        profile=SessionProfile.PERSISTENT_ANONYMOUS,
        ranking=(1,),
    )
    persistent_two = _run_observation(
        "second-p2",
        shared_clean.started_at + timedelta(minutes=2),
        profile=SessionProfile.PERSISTENT_ANONYMOUS,
        ranking=(1,),
    )
    clean_two = _run_observation(
        "second-c2",
        shared_clean.started_at + timedelta(minutes=3),
        profile=SessionProfile.CLEAN_ANONYMOUS,
        ranking=(1,),
    )
    second = SessionProfileBlockObservation(
        run_ids=(
            shared_clean.run_id,
            persistent_one.run_id,
            persistent_two.run_id,
            clean_two.run_id,
        ),
        started_at=shared_clean.started_at,
        order=SessionProfileBlockOrder.CLEAN_OUTER,
        persistent_session_instance_id=_SESSION_ID,
        clean_runs=(shared_clean, clean_two),
        persistent_runs=(persistent_one, persistent_two),
    )

    with pytest.raises(ValueError, match="cannot be reused across blocks"):
        evaluate_session_profile_blocks([first, second])


def test_p75_and_ranked_overlap_match_frozen_math() -> None:
    assert stability._percentile([0.0, 0.4, 0.8, 1.0], 0.75) == pytest.approx(0.85)
    assert stability._ranked_prefix_overlap((1,), (1, 2), persistence=0.9) == pytest.approx(0.55)


def _persist_feed_run(
    *,
    raw_store: FilesystemRawSnapshotStore,
    probe_store: SQLiteProbeRunStore,
    started_at: datetime,
    profile: SessionProfile,
    app_offset: int,
    session_instance_id: str = _SESSION_ID,
) -> str:
    context = (
        ProbeContext(session_profile=SessionProfile.CLEAN_ANONYMOUS, profile_age_days=0)
        if profile is SessionProfile.CLEAN_ANONYMOUS
        else ProbeContext(
            session_profile=SessionProfile.PERSISTENT_ANONYMOUS,
            session_instance_id=session_instance_id,
            cookie_state_hash="a" * 64,
            profile_age_days=0,
        )
    )
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=10,
        started_at=started_at,
    )

    for index in range(2):
        has_next = index == 0
        next_page_id = "page-1" if has_next else None
        next_rtx = "req-1" if has_next else None
        payload = {
            "feed": [
                {
                    "items": [
                        {"appID": app_offset + index},
                        {"appID": 9000 + app_offset + index, "source": "direct"},
                    ]
                }
            ],
            "pageInfo": {
                "hasNextPage": has_next,
                "nextPageId": next_page_id,
                "rtxReqId": next_rtx,
            },
        }
        params: dict[str, object] = {
            "games_count": 20,
            "with_promos": "false",
            "lang": "ru",
            "device-type": "desktop",
            "platform": "desktop_other",
        }
        if index == 1:
            params["page_id"] = "page-1"
            params["rtx-reqid"] = "req-1"
        response = CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.feed",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/feed/",
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode(),
            retrieved_at=started_at + timedelta(seconds=index + 1),
            request_context={
                "probe_context": context.model_dump(mode="json"),
                "params": params,
            },
        )
        metadata = raw_store.persist(response)
        probe_store.append_page(
            ProbePage(
                run_id=run.id,
                page_index=index,
                raw_snapshot_id=metadata.id,
                retrieved_at=metadata.retrieved_at,
                request_page_id=(None if index == 0 else "page-1"),
                request_rtx_reqid=(None if index == 0 else "req-1"),
                response_next_page_id=next_page_id,
                response_rtx_reqid=next_rtx,
                has_next_page=has_next,
            )
        )

    probe_store.finish_run(
        run.id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=started_at + timedelta(seconds=5),
    )
    return run.id


def _persist_matched_block(
    tmp_path: Path,
) -> tuple[
    tuple[str, str, str, str],
    FilesystemRawSnapshotStore,
    SQLiteProbeRunStore,
]:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    profiles = (
        SessionProfile.CLEAN_ANONYMOUS,
        SessionProfile.PERSISTENT_ANONYMOUS,
        SessionProfile.PERSISTENT_ANONYMOUS,
        SessionProfile.CLEAN_ANONYMOUS,
    )
    run_ids = tuple(
        _persist_feed_run(
            raw_store=raw_store,
            probe_store=probe_store,
            started_at=base + timedelta(minutes=index),
            profile=profile,
            app_offset=100,
        )
        for index, profile in enumerate(profiles)
    )
    return (run_ids[0], run_ids[1], run_ids[2], run_ids[3]), raw_store, probe_store


def test_replay_loads_matched_block_and_saturates_after_source_exhaustion(
    tmp_path: Path,
) -> None:
    run_ids, raw_store, probe_store = _persist_matched_block(tmp_path)
    experiment = SessionProfileStabilityExperiment(
        raw_store=raw_store,
        probe_store=probe_store,
    )

    block = experiment.load_block(run_ids)

    assert block.order is SessionProfileBlockOrder.CLEAN_OUTER
    assert block.persistent_session_instance_id == _SESSION_ID
    first_clean = block.clean_runs[0]
    assert first_clean.organic_rankings[1] == (100,)
    assert first_clean.organic_rankings[3] == (100, 101)
    assert first_clean.organic_rankings[5] == (100, 101)
    assert first_clean.organic_rankings[10] == (100, 101)
    assert all(app_id < 9000 for app_id in first_clean.organic_rankings[10])


def test_broken_raw_run_rejects_whole_block_without_aborting_report(tmp_path: Path) -> None:
    run_ids, raw_store, probe_store = _persist_matched_block(tmp_path)
    record = probe_store.get_run(run_ids[0])
    assert record is not None
    metadata = raw_store.get_metadata(record.run.source_id, record.pages[0].raw_snapshot_id)
    (raw_store.root / metadata.content_path).write_bytes(b"tampered")

    report = SessionProfileStabilityExperiment(
        raw_store=raw_store,
        probe_store=probe_store,
    ).analyze([run_ids])

    assert report.eligible_block_count == 0
    assert report.eligible_blocks == ()
    assert len(report.rejected_blocks) == 1
    assert "raw replay failed" in report.rejected_blocks[0].reason
    assert report.sample_sufficient is False
    assert all(metric.classification is None for metric in report.metrics)
