from __future__ import annotations

from yandex_analytics_reaper.taxonomy import CoreLoop, GameTaxonomyDraft, SessionModel


def test_taxonomy_keeps_theme_and_objective_out_of_core_loop() -> None:
    taxonomy = GameTaxonomyDraft(
        primary_core_loop=CoreLoop.EXPLORE,
        objectives=("escape",),
        themes=("school",),
        tones=("horror",),
        session_model=SessionModel.LEVEL_BASED,
    )

    assert taxonomy.primary_core_loop is CoreLoop.EXPLORE
    assert taxonomy.objectives == ("escape",)
    assert taxonomy.tones == ("horror",)
