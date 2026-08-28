# Game Market Taxonomy v2

## 1. Principle

Market taxonomy describes **what the game is**. Production assessment describes **how hard it is for us to build**. Do not mix them.

Every game is represented by independent axes.

## 2. Core loop

Exactly one dominant primary core loop:

```text
merge
match
sort
logic_solve
hidden_object
word_answer
board_turn
card_play
idle_growth
management
economy_trade
craft
move_platform
run_dodge
drive
race
shoot
melee_fight
defend
survive
build_place
sandbox_interact
collect
story_choice
customize
explore
other
```

The primary core loop answers: what action structure is repeated most often during normal play?

## 3. Secondary mechanics

Multi-select examples:

```text
tap timing drag swipe draw aim shoot steer move_avatar jump dodge fight collect merge match sort stack place build craft upgrade manage trade search_hidden solve_logic answer memorize idle_wait physics destroy escape race survive
```

## 4. Player objective

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

This allows "horror escape" to be represented as core loop + objective + tone rather than a pseudo-genre.

## 5. Meta systems

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

## 6. Session model

```text
micro_round
level_based
run_based
endless
persistent
sandbox
idle_return
social_session
```

Additional fields: restart friction and estimated session band.

## 7. Replayability source

```text
score_improvement
randomization
skill_mastery
progression
collection
economy_growth
new_content
opponents
social
daily_rewards
leaderboard
procedural_content
sandbox_expression
```

## 8. Theme / setting

Theme is an open normalized entity system, e.g. school, prison, supermarket, hotel, airport, cars, zombies, military, food, animals, fashion, home_design, business, fantasy, sci_fi, crime, sports, relationships.

Use theme + aliases + language + trend terms. No schema migration should be required to add a new theme.

## 9. Tone

Separate from theme:

```text
horror cozy comedy serious competitive relaxing chaotic absurd dramatic
```

## 10. Cultural/trend layer

Separate from theme because it changes quickly:

```text
meme brainrot anime_inspired roblox_like viral_character internet_challenge current_event none
```

Store specific trend entities separately.

## 11. Social/network mode

```text
singleplayer
asynchronous_social
leaderboard_competitive
real_time_competitive
real_time_coop
shared_world
unknown
```

## 12. Presentation

Track dimension, camera, and art style as separate dimensions.

## 13. Device/input

Track input modes, mobile fit, desktop fit, and orientation. Observed and inferred suitability remain separate.

## 14. Monetization taxonomy

Observed fields include rewarded/fullscreen/sticky ads and purchase/product flags. Inferred fields may describe rewarded use cases, IAP types, and monetization intrusiveness.

## 15. Classification evidence

Classifier input priority: title, platform categories/tags, description, instructions, screenshots, video, media metadata, external descriptions.

Output must be structured, confidence-bearing, and evidence-backed.

## 16. Validation before freeze

Build a gold set of 100–200 diverse Yandex games. Measure confusion matrix, per-class precision/recall, low-confidence rate, human agreement, and Cohen's kappa where useful.

Targets:

```text
primary_core_loop human agreement >= 90%
high-value mechanic labels >= 90%
theme canonicalization >= 95%
```

If a class repeatedly confuses with another class, merge/redefine it before freeze.

## 17. Versioning

Store taxonomy version, classifier version, classified_at, input snapshot IDs, labels, confidence, evidence, and review status. Historical classifications are immutable.
