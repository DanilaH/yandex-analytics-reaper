from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CoreLoop(StrEnum):
    MERGE = "merge"
    MATCH = "match"
    SORT = "sort"
    LOGIC_SOLVE = "logic_solve"
    HIDDEN_OBJECT = "hidden_object"
    WORD_ANSWER = "word_answer"
    BOARD_TURN = "board_turn"
    CARD_PLAY = "card_play"
    IDLE_GROWTH = "idle_growth"
    MANAGEMENT = "management"
    ECONOMY_TRADE = "economy_trade"
    CRAFT = "craft"
    MOVE_PLATFORM = "move_platform"
    RUN_DODGE = "run_dodge"
    DRIVE = "drive"
    RACE = "race"
    SHOOT = "shoot"
    MELEE_FIGHT = "melee_fight"
    DEFEND = "defend"
    SURVIVE = "survive"
    BUILD_PLACE = "build_place"
    SANDBOX_INTERACT = "sandbox_interact"
    COLLECT = "collect"
    STORY_CHOICE = "story_choice"
    CUSTOMIZE = "customize"
    EXPLORE = "explore"
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


class GameTaxonomyDraft(BaseModel):
    """Draft taxonomy model. Labels are not considered validated until gold-set review."""

    model_config = ConfigDict(frozen=True)

    primary_core_loop: CoreLoop
    secondary_mechanics: tuple[str, ...] = ()
    objectives: tuple[str, ...] = ()
    meta_systems: tuple[str, ...] = ()
    session_model: SessionModel | None = None
    themes: tuple[str, ...] = ()
    tones: tuple[str, ...] = ()
    trend_layers: tuple[str, ...] = ()
    social_mode: SocialMode = SocialMode.UNKNOWN
    presentation: dict[str, str] = Field(default_factory=dict)
    observed_monetization: dict[str, bool | None] = Field(default_factory=dict)
