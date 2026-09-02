from datetime import timedelta

from test_thesis_traction import _NOW, _current_evidence, _prior_evidence, _suite
from yandex_analytics_reaper.thesis_traction import build_traction_features


def test_no_change_prior_observation_is_explicit_zero_velocity() -> None:
    prior = _prior_evidence(
        artifact_hash="4" * 64,
        snapshot_time=_NOW - timedelta(days=2),
        rating_count=50,
        rating_observed_at=_NOW - timedelta(days=1, minutes=2),
        observation_id="obs:no-change",
        run_id="no-change",
    )

    report = build_traction_features(
        _suite(),
        current=_current_evidence(),
        priors=(prior,),
    )
    delta = report.theses[0].rows[0].longitudinal

    assert delta.status == "observed"
    assert delta.previous_rating_count == 50
    assert delta.current_rating_count == 50
    assert delta.rating_count_delta == 0
    assert delta.observed_rating_delta_per_day == 0.0
