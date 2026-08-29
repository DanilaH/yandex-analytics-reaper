from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_TAXONOMY_LABEL_REGISTRY_VERSION = 1
TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH = (
    "38cea47878b053ffc34dbfb270d4344ffcf94a05a04f19ffcff394257715d49f"
)


class ControlledLabelDimension(StrEnum):
    MECHANICS = "mechanics"
    OBJECTIVES = "objectives"
    META_SYSTEMS = "meta_systems"
    TONES = "tones"


class TaxonomyLabelRegistry(BaseModel):
    """Immutable labels for one controlled taxonomy dimension/version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: ControlledLabelDimension
    version: int = Field(ge=1)
    labels: tuple[str, ...] = Field(min_length=1)

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_taxonomy_label(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("taxonomy label registry cannot contain duplicate labels")
        return normalized


class TaxonomyLabelRegistryBundle(BaseModel):
    """One coherent immutable version across the controlled free-string dimensions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(ge=1)
    registries: tuple[TaxonomyLabelRegistry, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        expected = set(ControlledLabelDimension)
        actual = {registry.dimension for registry in self.registries}
        if actual != expected:
            raise ValueError("taxonomy registry bundle must define every controlled dimension once")
        if any(registry.version != self.version for registry in self.registries):
            raise ValueError("taxonomy registry bundle versions must match")
        return self

    def registry_for(self, dimension: ControlledLabelDimension) -> TaxonomyLabelRegistry:
        for registry in self.registries:
            if registry.dimension == dimension:
                return registry
        raise RuntimeError(f"taxonomy registry missing dimension: {dimension.value}")

    def validate_membership(
        self,
        dimension: ControlledLabelDimension,
        labels: tuple[str, ...],
    ) -> None:
        allowed = set(self.registry_for(dimension).labels)
        invalid = tuple(label for label in labels if label not in allowed)
        if invalid:
            rendered = ", ".join(invalid)
            raise ValueError(
                f"unsupported {dimension.value} label(s) for registry v{self.version}: "
                f"{rendered}"
            )


def normalize_taxonomy_label(value: str) -> str:
    if not value:
        raise ValueError("taxonomy labels cannot be blank")
    if value != value.strip():
        raise ValueError("taxonomy labels must already be trimmed")
    if value != value.lower():
        raise ValueError("taxonomy labels must be lowercase")
    if any(character.isspace() for character in value):
        raise ValueError("taxonomy labels cannot contain whitespace")
    return value


def taxonomy_label_registry_content_hash(bundle: TaxonomyLabelRegistryBundle) -> str:
    payload = bundle.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_REGISTRY_V1 = TaxonomyLabelRegistryBundle(
    version=1,
    registries=(
        TaxonomyLabelRegistry(
            dimension=ControlledLabelDimension.MECHANICS,
            version=1,
            labels=(
                "tap",
                "timing",
                "drag",
                "swipe",
                "aim",
                "shoot",
                "steer",
                "move_avatar",
                "jump",
                "dodge",
                "fight",
                "collect",
                "merge",
                "match",
                "sort",
                "stack",
                "place",
                "build",
                "craft",
                "upgrade",
                "manage",
                "trade",
                "search_hidden",
                "solve_logic",
                "answer",
                "idle_wait",
                "physics",
                "destroy",
            ),
        ),
        TaxonomyLabelRegistry(
            dimension=ControlledLabelDimension.OBJECTIVES,
            version=1,
            labels=(
                "reach_finish",
                "survive",
                "escape",
                "maximize_score",
                "solve",
                "defeat_opponents",
                "build",
                "expand",
                "earn_currency",
                "collect",
                "unlock",
                "complete_story",
                "create_customize",
                "explore",
            ),
        ),
        TaxonomyLabelRegistry(
            dimension=ControlledLabelDimension.META_SYSTEMS,
            version=1,
            labels=(
                "none",
                "linear_levels",
                "chapter_progression",
                "player_level",
                "equipment_upgrade",
                "character_upgrade",
                "base_upgrade",
                "economy_expansion",
                "collection",
                "unlock_tree",
                "cosmetics",
                "quests",
                "daily_rewards",
                "streaks",
                "achievements",
                "leaderboard",
                "prestige_reset",
                "idle_return",
                "liveops_events",
            ),
        ),
        TaxonomyLabelRegistry(
            dimension=ControlledLabelDimension.TONES,
            version=1,
            labels=(
                "absurd",
                "comedic",
                "cozy",
                "dark",
                "dramatic",
                "horror",
                "relaxing",
                "tense",
                "wholesome",
            ),
        ),
    ),
)

if (
    taxonomy_label_registry_content_hash(_REGISTRY_V1)
    != TAXONOMY_LABEL_REGISTRY_V1_CONTENT_HASH
):
    raise RuntimeError(
        "taxonomy label registry v1 changed without a new version/content identity"
    )

_REGISTRY_BUNDLES = (_REGISTRY_V1,)


def get_taxonomy_label_registry(version: int) -> TaxonomyLabelRegistryBundle:
    for bundle in _REGISTRY_BUNDLES:
        if bundle.version == version:
            return bundle
    raise ValueError(f"unsupported taxonomy label registry version: {version}")
