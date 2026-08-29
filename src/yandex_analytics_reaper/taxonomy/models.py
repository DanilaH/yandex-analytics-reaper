from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        return _normalized_label(value)


class ControlledTaxonomyDimensions(BaseModel):
    """Stable taxonomy axes whose concrete label registries are versioned separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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
        normalized = tuple(_normalized_label(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("controlled taxonomy dimension labels must be unique")
        return normalized


class GameTaxonomyDraft(BaseModel):
    """Draft market taxonomy; label registries and gold-set validation are still pending."""

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
        normalized = tuple(_normalized_label(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("taxonomy entity labels must be unique")
        return normalized


def _normalized_label(value: str) -> str:
    if not value:
        raise ValueError("taxonomy labels cannot be blank")
    if value != value.strip():
        raise ValueError("taxonomy labels must already be trimmed")
    if value != value.lower():
        raise ValueError("taxonomy labels must be lowercase")
    if any(character.isspace() for character in value):
        raise ValueError("taxonomy labels cannot contain whitespace")
    return value
