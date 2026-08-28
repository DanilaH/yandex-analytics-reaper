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
```

Production burden is not part of market taxonomy.

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

`other` means the game is genuinely outside the current registry. `unknown` means available evidence is insufficient to classify it reliably.

A classifier must be allowed to return `unknown`; it must not guess merely to satisfy the schema.

## Controlled dimensions

Use versioned label registries for dimensions that drive aggregation:

```text
mechanics[]
objectives[]
meta_systems[]
session_model
replayability_sources[]
tone[]
social_mode
presentation dimensions
```

Do not use arbitrary free strings for these dimensions in production classification. New labels require a taxonomy-version change/review.

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

Track independent presentation dimensions such as:

```text
dimension: 2d / 2_5d / 3d / unknown
camera: top_down / side / first_person / third_person / isometric / fixed_board / ui_primary / unknown
art_style: versioned controlled registry
```

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
