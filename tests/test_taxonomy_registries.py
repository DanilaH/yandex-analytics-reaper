from __future__ import annotations

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.taxonomy import (
    DEFAULT_TAXONOMY_LABEL_REGISTRY_VERSION,
    ControlledLabelDimension,
    ControlledTaxonomyDimensions,
    TaxonomyLabelRegistry,
    get_taxonomy_label_registry,
)


def test_v1_registry_bundle_defines_each_controlled_dimension_once() -> None:
    bundle = get_taxonomy_label_registry(DEFAULT_TAXONOMY_LABEL_REGISTRY_VERSION)

    assert bundle.version == 1
    assert {registry.dimension for registry in bundle.registries} == set(
        ControlledLabelDimension
    )
    assert bundle.registry_for(ControlledLabelDimension.MECHANICS).version == 1
    assert "collect" in bundle.registry_for(ControlledLabelDimension.MECHANICS).labels
    assert "horror" in bundle.registry_for(ControlledLabelDimension.TONES).labels


def test_dimensions_record_registry_version_and_accept_declared_labels() -> None:
    dimensions = ControlledTaxonomyDimensions(
        mechanics=("collect", "shoot"),
        objectives=("survive",),
        meta_systems=("linear_levels",),
        tones=("horror", "tense"),
    )

    assert dimensions.label_registry_version == 1
    assert dimensions.model_dump(mode="json")["label_registry_version"] == 1


def test_dimensions_reject_label_missing_from_selected_registry() -> None:
    with pytest.raises(ValidationError, match="unsupported mechanics label"):
        ControlledTaxonomyDimensions(mechanics=("teleport",))

    with pytest.raises(ValidationError, match="unsupported tones label"):
        ControlledTaxonomyDimensions(tones=("nostalgic",))


def test_dimensions_reject_unknown_registry_version() -> None:
    with pytest.raises(ValidationError, match="unsupported taxonomy label registry version"):
        ControlledTaxonomyDimensions(label_registry_version=999)


def test_meta_system_none_cannot_be_combined_with_other_labels() -> None:
    with pytest.raises(ValidationError, match="cannot be combined"):
        ControlledTaxonomyDimensions(meta_systems=("none", "linear_levels"))

    dimensions = ControlledTaxonomyDimensions(meta_systems=("none",))
    assert dimensions.meta_systems == ("none",)


def test_registry_declaration_rejects_duplicate_labels() -> None:
    with pytest.raises(ValidationError, match="duplicate labels"):
        TaxonomyLabelRegistry(
            dimension=ControlledLabelDimension.MECHANICS,
            version=2,
            labels=("collect", "collect"),
        )
