# Feature pipeline reference

This is the current implementation reference for the MLB pitcher strikeout
project. Historical notebook scores and the former Longleaf workflow were
removed because they were produced before the leakage-safe pipeline and are not
valid evidence of current model quality.

## Objective and leakage boundary

The pitcher model predicts a starter's game-level strikeout rate:

```text
k_rate = strikeouts / batters faced
```

Every feature must be known before first pitch. Same-game `K`, `PA`, and `Outs`
remain in the final frame only as labels/evaluation fields and must be excluded
from model inputs. All player-form features lag the current game.

## Three data levels

Paths are defined in `src/Python/config.py` and default to
`Data/processed/`.

| Level | Builder | Pitcher artifact | Batter artifact |
|---|---|---|---|
| 1: game | `pipeline/games.py` | `pitcher_games.parquet` | `batter_games.parquet` |
| 2: rolling | `pipeline/rolling.py` | `pitcher_rolling.parquet` | `batter_rolling.parquet` |
| 3: training | `pipeline/training.py` | `pitcher_training.parquet` | `batter_training.parquet` |

Level 1 also writes `pitch_type_games.parquet` at
starter/game/canonical-pitch-type grain for denominator-aware pitch-type
research.

Run all stages:

```powershell
python -c "from Python.pipeline import run_all; run_all()"
```

Or run `python -m Python.pipeline.games`, `.rolling`, and `.training`
individually.

### Level 1: Savant to game tables

`statcast.py` loads regular-season parquet exports and defines shared event,
wOBA/xwOBA, and plate-discipline primitives. Level 1 verifies every requested
season's local game IDs against MLB's official regular-season schedule before
building outputs; `verify_schedule=False` is an explicit offline-only escape
hatch. It also loads the immediately preceding season as prior-only HR/FB
context. Thus a 2023-2025 build uses 2022 Statcast for the early-2023 xFIP
prior without creating 2022 model rows.

`pitcher_features.py` produces one row per true starter/game:

- default minimum of nine batters faced removes openers and very early exits;
- foul tips count as whiffs;
- fly balls include Statcast `fly_ball` and `popup`;
- wOBA/xwOBA use Savant's `woba_value`, `woba_denom`, and
  `estimated_woba_using_speedangle`;
- outs include batting, caught-stealing, and pickoff outs;
- FIP uses published FanGraphs season constants; xFIP uses league HR/FB
  available before each game date, regressed toward the previous season;
- pitch-type physics, usage by batter hand, wOBA/xwOBA, extension, mean release
  point, and release-point standard deviation are retained.

`batter_features.py` produces one row per batter/game with overall outcomes,
vs-LHP/vs-RHP strikeout counts, discipline counts/rates, Savant wOBA/xwOBA, and
the static game context (`game_date`, home/away teams, batting/opponent team,
home flag, batter hand).

### Level 2: game tables to pregame player form

`pitcher_rolling.py` creates lagged, denominator-weighted rates and rolling means.
Defaults are 5/10/20 starts for rates and 3/5/10 starts for physics, mechanics,
usage, and expected metrics. Season-to-date rates reset each season. All games
on the current calendar date are excluded, and duplicate pitcher-game keys fail
loudly. Rolling FIP/xFIP are calculated from summed prior-start
HR/BB/HBP/K/FB/outs rather than averaging per-start ratios. xFIP applies the
league HR/FB known before the projected date, with a 1,000-fly-ball prior based
on the previous loaded season. Under the pipeline's `fly_ball + popup`
definition, the sourced 2022 prior for 2023 is 0.12815157.

`batter_rolling.py` creates:

- season-to-date overall and handedness-split K%;
- lagged 5/10/20-game K%;
- empirical-Bayes season K% shrinkage toward league K% through the previous
  date only (the first date uses the exact-definition previous-season league
  rate; 2023 uses 2022's `0.22381258`);
- season-to-date whiff and chase rates.

Batter rolling features likewise exclude every same-date game, reject duplicate
batter-game keys, and allow partial early-history windows (`P20` means up to the
last 20 games, with at least one prior game by default).

`pipeline/rolling.py` keeps static keys/context, Level 2 features, and pitcher
labels. It drops raw same-game feature columns by default. Use `keep_raw=True`
only for diagnostics, never as the model input artifact.

Denominator-aware stabilization has been run on the current Level 1 data. It
proposed candidate neighborhoods but did not by itself justify changing the
default 5/10/20 rate windows or 3/5/10 physics windows. Validate nearby choices
with chronological CV and grouped ablation before changing constants in the
rolling modules; do not recreate windows in notebooks.

### Level 3: model-ready joins

`pipeline/training.py` joins:

- pitcher rolling form;
- the opposing batters' pregame overall/handed K%, Whiff%
  (`Whiffs/Swings`), SwStr% (`Whiffs/Pitches`), and chase%;
- the season/stadium park factor.

The historical lineup proxy uses the first nine distinct batters to appear for
each team, ordered by first plate appearance. This removes bullpen-only pinch
hitters from the feature membership and Level 3 requires exactly nine matched
batters. Live inference must still use the announced lineup.

Season-opening games, including early neutral-site openers, intentionally have
null opponent-lineup rates. Every batter has zero prior season-to-date PA before
their first game, so a leakage-safe rate does not yet exist. These nulls must be
handled by model-native missing-value support or preprocessing fitted on the
training split; they must not be backfilled from same-game outcomes.

The batter training frame does not yet include opposing-starter features and is
therefore not feature-complete for a production batter-side model.

### Daily lineup adapter

`Python.daily_lineups` ingests the current RotoGrinders DraftKings MLB page,
preserving batting order and projected/confirmed status. It joins each game to
the official MLB schedule, resolves scraped players only within the matching
MLB active/40-man roster, and returns numeric `batter`/`pitcher` IDs. Name-only
or forward-filled joins are forbidden. Validation requires nine unique
resolved batters per team; `--require-confirmed` additionally rejects
projected lineups.

The adapter writes dated batter and starter inputs under `Data/processed/`.
RotoGrinders supplies the earlier prediction surface; MLB schedule, roster,
probable-pitcher, and person endpoints remain the canonical identity/game
surface. The HTML source is external and must be monitored for markup or usage
policy changes.

### Preserved future-target foundations

Level 1 intentionally retains `Hits`, `BB`, `Runs`, `Pitches`, `Outs`, and
`PA`/batters faced even when they are not inputs to the K/PA model. These
outcomes and the denominator plans in `reliability.py` are foundations for
future hit, walk, runs-allowed, pitches, outs, and workload models; they are not
dead columns or dead research code. Level 2 currently promotes only the active
pitcher labels needed by this model, so future targets should rebuild from
Level 1 or explicitly extend the label-retention policy without weakening the
pregame leakage gate.

`Models/Strikeout-Model/train.py` reads `PITCHER_TRAINING_PATH` and supports
LightGBM, Ridge, and mean baselines without rebuilding Level 1 or Level 2.
Feature selection accepts only explicitly approved context fields and lagged
rolling/season-to-date columns; an unexpected numeric column fails loudly.
The approximate 70/15/15 chronological split keeps each calendar date wholly
inside one partition.

The frozen audit-corrected baseline has 227 features: training ends
2025-04-14, validation is 2025-04-15 through 2025-07-05, and testing starts
2025-07-06. Test RMSE / R² are 0.1076 / -0.0001 (Mean), 0.1003 / 0.1313
(Ridge), and 0.0994 / 0.1459 (LightGBM). Later research frames contain
214 core, 219 compact, 227 preferred-raw, or 232 all-candidate features and
must not be conflated with that frozen baseline. The frozen registry includes
`opp_lineup_whiff`, while `opp_lineup_swstr` is a later candidate.

## Park factors and future intangibles

`park_factors.parquet` is a dimension table keyed by `(season, home_team)`.
For season `Y`, its factor uses only seasons before `Y`. The preceding
prior-only Statcast season supplies the first model season's history, so 2023
uses 2022 rather than receiving neutral factors. A 2023-2025 build also writes
the 2026 lookup. This avoids using future park outcomes in earlier training
rows.

Venue resolution is date-aware where a team code spans multiple physical
parks. In particular, `TB` home games in 2025 resolve to Steinbrenner Field;
the override ends on December 31, 2025 because the Rays returned to Tropicana
Field in 2026. Statcast already distinguishes the Athletics' Sacramento era
as `ATH` from the pre-2025 Oakland code `OAK`.

Neutral-site and international games (including the Mexico City, Seoul, and
London series, Field of Dreams, and the Little League Classic) are not
currently filtered. They remain grouped under Statcast's listed home-team
code and can slightly contaminate that venue's factor.

Future catcher, weather, travel, or other context belongs in separate keyed
dimension tables and is joined at Level 3. It does not belong in player rolling
files unless the feature itself represents lagged player form.

## Stabilization and feature selection

`reliability.py` contains:

- game-count split-half reliability;
- enhanced reliability/ICC/year-over-year summaries;
- denominator-aware split-half curves for pitch-, swing-, zone-, and
  plate-appearance-denominated statistics.

Use the denominator where reliability reaches the chosen threshold (commonly
`r ≈ 0.5`), translate it to starts, then compare nearby windows with
chronological cross-validation and grouped ablation. Stabilization chooses
plausible windows; it does not prove predictive value.

## FIP constant maintenance

Completed-season constants in `FANGRAPHS_FIP_CONSTANT` are fixed. Refresh the
current season from FanGraphs Guts before rebuilding, pass an override to
`add_fip_xfip`, or set `include_constant=False` when only the FIP core is needed.
A season-level additive constant has no within-season tree-model signal.

## Current limitations

- Projected batters faced and an end-to-end strikeout-count backtest are not
  complete.
- Daily lineup ingestion exists, but scheduling, retries, source-status
  monitoring, and downstream prediction-frame assembly are not automated.
- Full batter-by-pitch-type arsenal/lineup interactions are not implemented;
  current lineup discipline features are lineup averages.
- Weather, travel/rest, catcher, and market features are not integrated.
- Neutral-site/international games can contaminate team-keyed park factors.
- Existing feature-family ablations predate denominator-weighted expected-stat
  and splitter propagation corrections and require a rebuilt-frame rerun.

## Validation

Unit tests cover Statcast flags, pitcher/batter game aggregation, rolling
leakage boundaries, FIP/xFIP, park factors, lineup joins, stabilization, safety
rules, and parquet stage boundaries. Run:

```powershell
python -m pytest
```
