from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .registries import (
    ControlledLabelDimension,
    DEFAULT_TAXONOMY_LABEL_REGISTRY_VERSION,
    get_taxonomy_label_registry,
    normalize_taxonomy_label,
)


class PrimaryGameplayArchetype(StrEnum):
    MERGE = "merge"
    MATCH = "match"
    SORT = "sort"
    LOGIC_PUZZLE = "logic_puzzle"
    HIDDEN_OBJECT = "hidden_object"
    WORD_TRIVIA = "word_trivia"
    BOARD_CARD = "board_card"
    IDLE_INCREMENTAL = "idle_incremental"
    MANAGEMENT_TYCOON = "management_tycoon"
    CRAFTING_ECONOMY = "crafting_economy"
    PLATFORMER_OBBY = "platformer_obby"
    RUNNER = "runner"
    DRIVING_RACING = "driving_racing"
    SHOOTER = "shooter"
    MELEE_COMBAT = "melee_combat"
    SURVIVAL = "survival"
    BASE_DEFENSE = "base_defense"
    SANDBOX_SIMULATION = "sandbox_simulation"
    STORY_ADVENTURE = "story_adventure"
    CUSTOMIZATION = "customization"
    OTHER = "other"
    UNKNOWN = "unknown"


class SessionModel(StrEnum):
    MICRO_ROUND = "micro_round"
    LEVEL_BASED = "level_based"
    RUN_BASED = "run_based"
    ENDLESS = "endless"
    PERSISTENT = "persistent"
    SANDBOX = "sandbox"
    IDLE_RETURN = "idle_return"
    SOCIAL_SESSION = "social_session"


class SocialMode(StrEnum):
    SINGLEPLAYER = "singleplayer"
    ASYNCHRONOUS_SOCIAL = "asynchronous_social"
    LEADERBOARD_COMPETITIVE = "leaderboard_competitive"
    REAL_TIME_COMPETITIVE = "real_time_competitive"
    REAL_TIME_COOP = "real_time_coop"
    SHARED_WORLD = "shared_world"
    UNKNOWN = "unknown"


class PresentationDimensions(BaseModel):
    """Explicit presentation axes; controlled value registries are added separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str | None = None
    camera: str | None = None
    art_style: str | None = None

    @field_validator("dimension", "camera", "art_style")
    @classmethod
    def validate_optional_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_taxonomy_label(value)


class ControlledTaxonomyDimensions(BaseModel):
    """Stable axes validated against one explicit controlled-label registry version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label_registry_version: int = Field(
        default=DEFAULT_TAXONOMY_LABEL_REGISTRY_VERSION,
        ge=1,
    )
    mechanics: tuple[str, ...] = ()
    objectives: tuple[str, ...] = ()
    meta_systems: tuple[str, ...] = ()
    session_model: SessionModel | None = None
    replayability_sources: tuple[str, ...] = ()
    tones: tuple[str, ...] = ()
    social_mode: SocialMode = SocialMode.UNKNOWN
    presentation: PresentationDimensions = Field(default_factory=PresentationDimensions)

    @field_validator(
        "mechanics",
        "objectives",
        "meta_systems",
        "replayability_sources",
        "tones",
    )
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_taxonomy_label(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("controlled taxonomy dimension labels must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_registry_membership(self) -> Self:
        registry = get_taxonomy_label_registry(self.label_registry_version)
        registry.validate_membership(ControlledLabelDimension.MECHANICS, self.mechanics)
        registry.validate_membership(ControlledLabelDimension.OBJECTIVES, self.objectives)
        registry.validate_membership(
            ControlledLabelDimension.META_SYSTEMS,
            self.meta_systems,
        )
        registry.validate_membership(ControlledLabelDimension.TONES, self.tones)
        if "none" in self.meta_systems and len(self.meta_systems) != 1:
            raise ValueError("meta_systems label 'none' cannot be combined with other labels")
        return self


class GameTaxonomyDraft(BaseModel):
    """Draft market taxonomy; gold-set validation is still pending."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_archetype: PrimaryGameplayArchetype
    dimensions: ControlledTaxonomyDimensions = Field(
        default_factory=ControlledTaxonomyDimensions
    )
    themes: tuple[str, ...] = ()
    trend_layers: tuple[str, ...] = ()
    observed_monetization: dict[str, bool | None] = Field(default_factory=dict)

    @field_validator("themes", "trend_layers")
    @classmethod
    def validate_open_entities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_taxonomy_label(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("taxonomy entity labels must be unique")
        return normalized
