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

Paths are defined in `src/mlb_props/config.py` and default to
`Data/processed/`.

| Level | Builder | Pitcher artifact | Batter artifact |
|---|---|---|---|
| 1: game | `pipeline/games.py` | `pitcher_games.parquet` | `batter_games.parquet` |
| 2: rolling | `pipeline/rolling.py` | `pitcher_rolling.parquet` | `batter_rolling.parquet` |
| 3: training | `pipeline/training.py` | `pitcher_training.parquet` | `batter_training.parquet` |

Run all stages:

```powershell
python -c "from mlb_props.pipeline import run_all; run_all()"
```

Or run `python -m mlb_props.pipeline.games`, `.rolling`, and `.training`
individually.

### Level 1: Savant to game tables

`statcast.py` loads regular-season parquet exports and defines shared event,
wOBA/xwOBA, and plate-discipline primitives.

`pitcher_features.py` produces one row per true starter/game:

- default minimum of nine batters faced removes openers and very early exits;
- foul tips count as whiffs;
- fly balls include Statcast `fly_ball` and `popup`;
- wOBA/xwOBA use Savant's `woba_value`, `woba_denom`, and
  `estimated_woba_using_speedangle`;
- outs include batting, caught-stealing, and pickoff outs;
- FIP uses published FanGraphs season constants; xFIP uses league HR/FB from
  all loaded pitches;
- pitch-type physics, usage by batter hand, wOBA/xwOBA, extension, mean release
  point, and release-point standard deviation are retained.

`batter_features.py` produces one row per batter/game with overall outcomes,
vs-LHP/vs-RHP strikeout counts, discipline counts/rates, Savant wOBA/xwOBA, and
the static game context (`game_date`, home/away teams, batting/opponent team,
home flag, batter hand).

### Level 2: game tables to pregame player form

`pitcher_rolling.py` creates lagged, denominator-weighted rates and rolling means.
Defaults are 5/10/20 starts for rates and 3/5/10 starts for physics, mechanics,
usage, and expected metrics. Season-to-date rates reset each season.

`batter_rolling.py` creates:

- season-to-date overall and handedness-split K%;
- lagged 5/10/20-game K%;
- empirical-Bayes season K% shrinkage toward league K% through the previous
  date only (a fixed fallback is used before any history exists);
- season-to-date whiff and chase rates.

`pipeline/rolling.py` keeps static keys/context, Level 2 features, and pitcher
labels. It drops raw same-game feature columns by default. Use `keep_raw=True`
only for diagnostics, never as the model input artifact.

The default windows are provisional until denominator-aware stabilization is
run on the current Level 1 data. Change window constants in the rolling modules
after that analysis; do not recreate windows in notebooks.

### Level 3: model-ready joins

`pipeline/training.py` joins:

- pitcher rolling form;
- the opposing batters' pregame overall/handed K%, whiff%, and chase%;
- the season/stadium park factor.

The historical lineup currently uses batters who appeared in the game. Live
inference must use the announced lineup. Pinch hitters in the historical source
are a known approximation.

`Models/Strikeout-Model/train.py` reads `PITCHER_TRAINING_PATH` and supports
LightGBM, Ridge, and mean baselines without rebuilding Level 1 or Level 2.

## Park factors and future intangibles

`park_factors.parquet` is a dimension table keyed by `(season, home_team)`.
For season `Y`, its factor uses only seasons before `Y`; the first available
season receives a neutral `1.0`. A 2023-2025 build also writes the 2026 lookup.
This avoids using future park outcomes in earlier training rows.

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
chronological cross-validation and SHAP. Stabilization chooses plausible
windows; it does not prove predictive value.

## FIP constant maintenance

Completed-season constants in `FANGRAPHS_FIP_CONSTANT` are fixed. Refresh the
current season from FanGraphs Guts before rebuilding, pass an override to
`add_fip_xfip`, or set `include_constant=False` when only the FIP core is needed.
A season-level additive constant has no within-season tree-model signal.

## Current limitations

- No leakage-free model score has been recorded from the Level 3 artifact.
- Projected batters faced and an end-to-end strikeout-count backtest are not
  complete.
- Announced-lineup ingestion is not implemented.
- Full batter-by-pitch-type arsenal/lineup interactions are not implemented;
  current lineup whiff/chase features are lineup averages.
- Weather, travel/rest, catcher, and market features are not integrated.

## Validation

Unit tests cover Statcast flags, pitcher/batter game aggregation, rolling
leakage boundaries, FIP/xFIP, park factors, lineup joins, stabilization, safety
rules, and parquet stage boundaries. Run:

```powershell
python -m pytest
```
