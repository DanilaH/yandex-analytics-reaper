# Game Market Taxonomy

Status: **draft** until the gold-set validation phase is complete.

## Principle

The taxonomy is pragmatic market classification, not a claim that every axis is mathematically orthogonal.

Each listing gets:

```text
one primary gameplay archetype
+
controlled multi-label dimensions
+
open normalized theme entities
+
separate fast-changing trend/cultural entities
```

Production burden is not part of market taxonomy.

The primary archetype answers **what broad gameplay pattern should this listing aggregate with?**
Controlled dimensions answer **which mechanics, objectives, meta/session/social and presentation traits does it have?**
Themes/trends answer **what is the game about or culturally attached to?**

These layers must not be collapsed into one free-form genre/tag bag.

## Draft implementation shape

The Phase 3 draft model is intentionally split into a coarse primary bucket and explicit axes:

```text
GameTaxonomyDraft
  primary_archetype
  dimensions
    mechanics[]
    objectives[]
    meta_systems[]
    session_model
    replayability_sources[]
    tones[]
    social_mode
    presentation
      dimension
      camera
      art_style
  themes[]
  trend_layers[]
  observed_monetization
```

`ControlledTaxonomyDimensions` controls the **shape of the axes** now. Concrete versioned label registries for mechanics/objectives/meta/tone and related controlled values are a separate roadmap task and must not be silently invented in this structural refactor.

Open theme/trend entities intentionally remain outside `ControlledTaxonomyDimensions` because their vocabulary must evolve independently of durable aggregation axes.

## Primary gameplay archetype

The primary archetype is the single bucket used for broad comparative market aggregation. It describes the dominant gameplay pattern and may overlap conceptually with lower-level mechanics/objectives.

Draft registry:

```text
merge
match
sort
logic_puzzle
hidden_object
word_trivia
board_card
idle_incremental
management_tycoon
crafting_economy
platformer_obby
runner
driving_racing
shooter
melee_combat
survival
base_defense
sandbox_simulation
story_adventure
customization
other
unknown
```

This registry deliberately uses market-level buckets rather than low-level actions. For example:

```text
primary archetype = shooter
mechanic = shoot / aim

primary archetype = story_adventure
mechanic = move_avatar / search_hidden
objective = escape / complete_story
```

Do not create primary buckets such as `shoot`, `collect`, `build_place`, or `explore` merely because those actions are present in gameplay.

`other` means the game is genuinely outside the current registry. `unknown` means available evidence is insufficient to classify it reliably. These are distinct first-class values and must never be collapsed.

A classifier must be allowed to return `unknown`; it must not guess merely to satisfy the schema. `other` is valid only when the evidence is sufficient to conclude that the dominant gameplay pattern genuinely falls outside the current registry.

## Controlled dimensions

Use versioned label registries for dimensions that drive aggregation:

```text
mechanics[]
objectives[]
meta_systems[]
session_model
replayability_sources[]
tones[]
social_mode
presentation dimensions
```

The structural model already forbids undeclared axes and arbitrary presentation keys. The concrete label registries are not frozen yet. Their definition/versioning belongs to the dedicated Phase 3 registry task.

### Mechanics examples

```text
tap
timing
drag
swipe
aim
shoot
steer
move_avatar
jump
dodge
fight
collect
merge
match
sort
stack
place
build
craft
upgrade
manage
trade
search_hidden
solve_logic
answer
idle_wait
physics
destroy
```

### Objectives examples

```text
reach_finish
survive
escape
maximize_score
solve
defeat_opponents
build
expand
earn_currency
collect
unlock
complete_story
create_customize
explore
```

### Meta examples

```text
none
linear_levels
chapter_progression
player_level
equipment_upgrade
character_upgrade
base_upgrade
economy_expansion
collection
unlock_tree
cosmetics
quests
daily_rewards
streaks
achievements
leaderboard
prestige_reset
idle_return
liveops_events
```

## Theme / setting

Theme is an open normalized entity layer because themes/trends evolve continuously.

Store:

```text
theme_id
canonical_name
aliases[]
language aliases
trend_terms[]
```

Examples include school, prison, supermarket, hotel, airport, cars, zombies, military, food, animals, fashion, fantasy, sci-fi, crime, sports, relationships.

## Trend/cultural entities

Fast-changing cultural signals such as memes, viral characters, brainrot/anime/Roblox-like references are modeled separately from durable theme entities. Specific trend entities are versioned/dated rather than permanently baked into the core taxonomy.

## Social/network mode

Controlled values:

```text
singleplayer
asynchronous_social
leaderboard_competitive
real_time_competitive
real_time_coop
shared_world
unknown
```

## Presentation

Presentation is an explicit structured dimension rather than a free-form dictionary:

```text
dimension
camera
art_style
```

Target controlled values include:

```text
dimension: 2d / 2_5d / 3d / unknown
camera: top_down / side / first_person / third_person / isometric / fixed_board / ui_primary / unknown
art_style: versioned controlled registry
```

The concrete registries are not frozen in this structural task.

## Monetization taxonomy

Observed source values and inferred design semantics remain separate.

Observed examples:

```text
rewarded_ads
fullscreen_ads
sticky_ads
purchases_enabled
has_products
```

Inferred examples can include rewarded use cases or IAP types, with explicit evidence/confidence.

## Classification evidence

Evidence priority can include title, source categories/tags, description, instructions, screenshots/video/media, and external descriptions.

Every classification stores:

```text
taxonomy_version
classifier_version
classified_at
input_snapshot_ids[]
labels
confidence/evidence
review_status
```

Historical classifications are immutable.

## Validation before freeze

Before taxonomy status becomes `frozen`:

1. build a diverse 100–200 game gold set;
2. manually classify it;
3. measure confusion matrix, per-class precision/recall, low-confidence rate and human agreement;
4. merge/redefine repeatedly confused labels;
5. verify explicit `unknown` behavior;
6. freeze a version only after review.

Initial targets:

```text
primary gameplay archetype agreement >= 90%
high-value controlled dimensions >= 90%
theme canonicalization >= 95%
```
