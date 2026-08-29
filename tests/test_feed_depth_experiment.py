from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import ProbeContext, ProbeKind, ProbePage, ProbeRunStatus
from yandex_analytics_reaper.experiments import (
    FeedDepthEligibilityError,
    FeedDepthExperiment,
    FeedDepthTrialObservation,
    RejectedFeedDepthTrial,
    evaluate_feed_depth_trials,
)
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, SQLiteProbeRunStore


def _trial(
    run_id: str,
    started_at: datetime,
    *,
    depth_1: int,
    depth_3: int,
    depth_5: int,
    depth_10: int = 10,
) -> FeedDepthTrialObservation:
    full = tuple(range(1, depth_10 + 1))
    return FeedDepthTrialObservation(
        run_id=run_id,
        started_at=started_at,
        organic_rankings={
            1: full[:depth_1],
            3: full[:depth_3],
            5: full[:depth_5],
            10: full,
        },
    )


def test_report_refuses_recommendation_until_sample_is_sufficient() -> None:
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    report = evaluate_feed_depth_trials(
        [
            _trial("run-1", base, depth_1=9, depth_3=10, depth_5=10),
            _trial(
                "run-2",
                base + timedelta(hours=1),
                depth_1=9,
                depth_3=10,
                depth_5=10,
            ),
        ]
    )

    assert report.sample_sufficient is False
    assert report.recommended_depth is None
    assert report.eligible_trial_count == 2
    assert report.hour_buckets_utc == (
        "2026-08-29T08:00:00Z",
        "2026-08-29T09:00:00Z",
    )
    assert any("eligible trials=2" in reason for reason in report.decision_reasons)


def test_policy_selects_smallest_depth_that_passes_all_frozen_thresholds() -> None:
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    trials = [
        _trial(
            f"run-{index}",
            base + timedelta(hours=index),
            depth_1=9,
            depth_3=10,
            depth_5=10,
        )
        for index in range(8)
    ]

    report = evaluate_feed_depth_trials(trials)

    assert report.sample_sufficient is True
    assert report.recommended_depth == 1
    depth_one = next(metric for metric in report.metrics if metric.depth == 1)
    assert depth_one.median_coverage_vs_10 == pytest.approx(0.9)
    assert depth_one.p25_coverage_vs_10 == pytest.approx(0.9)
    assert depth_one.median_marginal_gain_to_next == pytest.approx(0.1)
    assert depth_one.median_pairwise_ranked_overlap == pytest.approx(1.0)


def test_policy_skips_failed_shallower_candidate_and_can_choose_three_pages() -> None:
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    trials = [
        _trial(
            f"run-{index}",
            base + timedelta(hours=index),
            depth_1=8,
            depth_3=9,
            depth_5=10,
        )
        for index in range(8)
    ]

    report = evaluate_feed_depth_trials(trials)

    assert report.sample_sufficient is True
    assert report.recommended_depth == 3


def test_rank_stability_threshold_can_reject_good_depth_one_coverage() -> None:
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    group_a = tuple(range(1, 10))
    group_b = tuple(range(11, 20))
    trials: list[FeedDepthTrialObservation] = []
    for index in range(8):
        prefix = group_a if index < 4 else group_b
        full = prefix + (100,)
        trials.append(
            FeedDepthTrialObservation(
                run_id=f"run-{index}",
                started_at=base + timedelta(hours=index),
                organic_rankings={
                    1: prefix,
                    3: full,
                    5: full,
                    10: full,
                },
            )
        )

    report = evaluate_feed_depth_trials(trials)
    depth_one = next(metric for metric in report.metrics if metric.depth == 1)
    depth_ten = next(metric for metric in report.metrics if metric.depth == 10)

    assert depth_one.median_coverage_vs_10 == pytest.approx(0.9)
    assert depth_one.median_marginal_gain_to_next == pytest.approx(0.1)
    assert depth_one.median_pairwise_ranked_overlap is not None
    assert depth_ten.median_pairwise_ranked_overlap is not None
    assert (
        depth_one.median_pairwise_ranked_overlap
        < depth_ten.median_pairwise_ranked_overlap - 0.03
    )
    assert report.recommended_depth == 3


def test_evaluator_rejects_inconsistent_submitted_trial_identity() -> None:
    base = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    eligible = _trial("eligible", base, depth_1=9, depth_3=10, depth_5=10)
    rejected = RejectedFeedDepthTrial(run_id="rejected", reason="fixture rejection")

    with pytest.raises(ValueError, match="exactly match"):
        evaluate_feed_depth_trials(
            [eligible],
            submitted_run_ids=["eligible", "different"],
            rejected_trials=[rejected],
        )


def _persist_feed_trial(
    tmp_path: Path,
    *,
    page_size: int = 20,
    page_count: int = 10,
) -> tuple[str, FilesystemRawSnapshotStore, SQLiteProbeRunStore]:
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    probe_store = SQLiteProbeRunStore(tmp_path / "market.sqlite3")
    context = ProbeContext(profile_age_days=0)
    started = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    run = probe_store.create_run(
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context=context,
        requested_page_limit=10,
        started_at=started,
    )

    for index in range(page_count):
        has_next = index < page_count - 1
        next_page_id = f"page-{index + 1}" if has_next else None
        next_rtx = f"req-{index + 1}" if has_next else None
        payload = {
            "feed": [
                {
                    "items": [
                        {"appID": 100 + index},
                        {"appID": 900 + index, "source": "direct"},
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
            "games_count": page_size,
            "with_promos": "false",
            "lang": "ru",
            "device-type": "desktop",
            "platform": "desktop_other",
        }
        if index > 0:
            params["page_id"] = f"page-{index}"
            params["rtx-reqid"] = f"req-{index}"
        response = CollectedResponse(
            source_id="yandex_public",
            request_key="catalogue.feed",
            method="GET",
            url="https://yandex.ru/games/api/catalogue/v2/feed/",
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode(),
            retrieved_at=started + timedelta(seconds=index + 1),
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
                request_page_id=(None if index == 0 else f"page-{index}"),
                request_rtx_reqid=(None if index == 0 else f"req-{index}"),
                response_next_page_id=next_page_id,
                response_rtx_reqid=next_rtx,
                has_next_page=has_next,
            )
        )

    probe_store.finish_run(
        run.id,
        status=ProbeRunStatus.COMPLETED,
        completed_at=started + timedelta(seconds=20),
    )
    return run.id, raw_store, probe_store


def test_replay_builds_prefix_rankings_and_excludes_sponsored_cards(tmp_path: Path) -> None:
    run_id, raw_store, probe_store = _persist_feed_trial(tmp_path)
    experiment = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store)

    trial = experiment.load_trial(run_id)

    assert trial.organic_rankings[1] == (100,)
    assert trial.organic_rankings[3] == (100, 101, 102)
    assert trial.organic_rankings[5] == (100, 101, 102, 103, 104)
    assert trial.organic_rankings[10] == tuple(range(100, 110))
    assert all(app_id < 900 for app_id in trial.organic_rankings[10])


def test_source_exhaustion_saturates_deeper_candidate_rankings(tmp_path: Path) -> None:
    run_id, raw_store, probe_store = _persist_feed_trial(tmp_path, page_count=2)
    experiment = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store)

    trial = experiment.load_trial(run_id)

    assert trial.organic_rankings[1] == (100,)
    assert trial.organic_rankings[3] == (100, 101)
    assert trial.organic_rankings[5] == (100, 101)
    assert trial.organic_rankings[10] == (100, 101)


def test_replay_rejects_trial_with_wrong_page_size(tmp_path: Path) -> None:
    run_id, raw_store, probe_store = _persist_feed_trial(tmp_path, page_size=10)
    experiment = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store)

    with pytest.raises(FeedDepthEligibilityError, match="games_count=20"):
        experiment.load_trial(run_id)


def test_replay_rejects_stored_page_linkage_that_disagrees_with_raw(tmp_path: Path) -> None:
    run_id, raw_store, probe_store = _persist_feed_trial(tmp_path)
    with probe_store.database.connect() as connection:
        connection.execute(
            """
            UPDATE probe_pages
            SET response_next_page_id = ?
            WHERE run_id = ? AND page_index = 0
            """,
            ("tampered-cursor", run_id),
        )

    experiment = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store)
    with pytest.raises(FeedDepthEligibilityError, match="does not match stored page linkage"):
        experiment.load_trial(run_id)


def test_broken_raw_trial_is_reported_as_rejected_instead_of_aborting(tmp_path: Path) -> None:
    run_id, raw_store, probe_store = _persist_feed_trial(tmp_path)
    record = probe_store.get_run(run_id)
    assert record is not None
    first_page = record.pages[0]
    metadata = raw_store.get_metadata(record.run.source_id, first_page.raw_snapshot_id)
    (raw_store.root / metadata.content_path).write_bytes(b"tampered")

    report = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store).analyze([run_id])

    assert report.eligible_run_ids == ()
    assert report.eligible_trial_count == 0
    assert len(report.rejected_trials) == 1
    assert report.rejected_trials[0].run_id == run_id
    assert "raw replay failed" in report.rejected_trials[0].reason
    assert report.sample_sufficient is False
    assert report.recommended_depth is None
