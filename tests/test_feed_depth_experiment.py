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
            _trial("run-2", base + timedelta(hours=1), depth_1=9, depth_3=10, depth_5=10),
        ]
    )

    assert report.sample_sufficient is False
    assert report.recommended_depth is None
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


def _persist_ten_page_trial(
    tmp_path: Path,
    *,
    page_size: int = 20,
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

    for index in range(10):
        has_next = index < 9
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
    run_id, raw_store, probe_store = _persist_ten_page_trial(tmp_path)
    experiment = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store)

    trial = experiment.load_trial(run_id)

    assert trial.organic_rankings[1] == (100,)
    assert trial.organic_rankings[3] == (100, 101, 102)
    assert trial.organic_rankings[5] == (100, 101, 102, 103, 104)
    assert trial.organic_rankings[10] == tuple(range(100, 110))
    assert all(app_id < 900 for app_id in trial.organic_rankings[10])


def test_replay_rejects_trial_with_wrong_page_size(tmp_path: Path) -> None:
    run_id, raw_store, probe_store = _persist_ten_page_trial(tmp_path, page_size=10)
    experiment = FeedDepthExperiment(raw_store=raw_store, probe_store=probe_store)

    with pytest.raises(FeedDepthEligibilityError, match="games_count=20"):
        experiment.load_trial(run_id)
