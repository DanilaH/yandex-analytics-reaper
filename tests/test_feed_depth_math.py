from __future__ import annotations

import pytest

from yandex_analytics_reaper.experiments.feed_depth import (
    _percentile,
    _ranked_prefix_overlap,
)


def test_feed_depth_percentile_uses_declared_linear_interpolation() -> None:
    assert _percentile([0.0, 0.4, 0.8, 1.0], 0.25) == pytest.approx(0.3)


def test_ranked_prefix_overlap_is_one_for_identical_rankings() -> None:
    assert _ranked_prefix_overlap([1, 2, 3], [1, 2, 3], persistence=0.9) == pytest.approx(1.0)


def test_ranked_prefix_overlap_penalizes_missing_tail_without_inventing_items() -> None:
    score = _ranked_prefix_overlap([1], [1, 2], persistence=0.9)

    assert score == pytest.approx(0.55)
    assert 0.0 < score < 1.0
