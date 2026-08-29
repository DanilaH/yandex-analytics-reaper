from __future__ import annotations

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.taxonomy import (
    ControlledTaxonomyDimensions,
    GameTaxonomyDraft,
    PresentationDimensions,
    PrimaryGameplayArchetype,
    SessionModel,
)


def test_taxonomy_keeps_archetype_separate_from_mechanics_and_theme() -> None:
    taxonomy = GameTaxonomyDraft(
        primary_archetype=PrimaryGameplayArchetype.STORY_ADVENTURE,
        dimensions=ControlledTaxonomyDimensions(
            mechanics=("move_avatar", "search_hidden"),
            objectives=("escape",),
            session_model=SessionModel.LEVEL_BASED,
            tones=("horror",),
            presentation=PresentationDimensions(
                dimension="3d",
                camera="third_person",
            ),
        ),
        themes=("school",),
    )

    assert taxonomy.primary_archetype is PrimaryGameplayArchetype.STORY_ADVENTURE
    assert taxonomy.dimensions.mechanics == ("move_avatar", "search_hidden")
    assert taxonomy.dimensions.objectives == ("escape",)
    assert taxonomy.dimensions.tones == ("horror",)
    assert taxonomy.themes == ("school",)


def test_primary_archetype_registry_uses_market_buckets_not_low_level_actions() -> None:
    values = {item.value for item in PrimaryGameplayArchetype}

    assert "shooter" in values
    assert "story_adventure" in values
    assert "shoot" not in values
    assert "collect" not in values
    assert "build_place" not in values


def test_controlled_dimensions_reject_undeclared_axes() -> None:
    with pytest.raises(ValidationError, match="extra"):
        ControlledTaxonomyDimensions.model_validate(
            {
                "mechanics": ["collect"],
                "theme": "school",
            }
        )


def test_presentation_rejects_arbitrary_unstructured_keys() -> None:
    with pytest.raises(ValidationError, match="extra"):
        PresentationDimensions.model_validate(
            {
                "dimension": "3d",
                "camera": "third_person",
                "lighting": "dark",
            }
        )


def test_dimension_labels_are_normalized_and_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ControlledTaxonomyDimensions(mechanics=("collect", "collect"))

    with pytest.raises(ValidationError, match="lowercase"):
        ControlledTaxonomyDimensions(mechanics=("Collect",))

    with pytest.raises(ValidationError, match="whitespace"):
        ControlledTaxonomyDimensions(mechanics=("hidden object",))
