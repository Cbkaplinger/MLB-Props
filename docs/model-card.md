# Pitcher strikeout-rate model card

## Intended use

Estimate a starting pitcher's pregame strikeout rate. A separate projected
batters-faced model will convert the rate to an expected strikeout count:

```text
expected strikeouts = predicted strikeout rate × projected batters faced
```

This repository is research code, not a validated betting system.

## Data and target

- Source: Baseball Savant pitch-level regular-season data.
- Level 1 unit: one row per qualifying starter/game.
- Target: `k_rate = K / PA`.
- Training, validation, and internal test seasons: 2023-2024 only.
- Historical holdout season: 2025. The trainer excludes it before any split or
  preprocessing fit. Earlier baseline work already consulted 2025, so it is a
  historical benchmark rather than a pristine final test.
- Evaluation: chronological train/validation/test splits only; calendar dates
  are never divided across partitions.
- Primary rate metrics: MAE, RMSE, and R² on future starts.
- Prop evaluation must use projected, never actual same-game, batters faced.

The current date-disjoint 2023-2024 baseline uses 248 approved features after
deterministic Contact% and CSW% identities are excluded. Internal test results
are Mean RMSE 0.1070 / R² -0.0010, Ridge RMSE 0.0993 / R² 0.1378, and
LightGBM RMSE 0.0983 / R² 0.1546. Training ends 2024-06-08, validation runs
from 2024-06-09 through 2024-08-05, and internal testing starts 2024-08-06.
These are development results, not a new independent final evaluation.
Historical corrected-frame feature-research artifacts used pre-pruning
238/240/243/251/256-feature configurations and remain process evidence rather
than the current trainer feature count.

## Leakage policy

Every feature must be available before first pitch. Forbidden model inputs
include same-game `K`, `PA`, `Outs`, actual TBF, and any statistic containing
the game being predicted. Level 2 uses prior games only. `K`, `PA`, `Outs`, and
`k_rate` are retained in Level 3 solely as labels/evaluation fields.

`src/Python/features.py` is a safety gate: it accepts only approved
lagged-feature families and context columns, and unknown numeric columns fail
rather than silently entering training. It also enforces the 248-feature
production allow-list by excluding expanded research candidates unless
`include_experimental=True` is requested explicitly.

## Feature pipeline

1. `pipeline/games.py`: raw Savant to pitcher-game, batter-game, and park
   dimension tables.
2. `pipeline/rolling.py`: game tables to lagged rolling/season-to-date player
   features while retaining static game context.
3. `pipeline/training.py`: pitcher form + opponent lineup + prior-season park
   factor to the model-ready frame.

Important definitions:

- true starts require at least nine batters faced by default;
- foul tips are whiffs;
- fly balls include popups;
- wOBA/xwOBA use Savant values and denominators;
- pitcher outs include recorded caught-stealing and pickoff outs;
- release extension and horizontal/vertical release-point consistency are
  included;
- research-only candidates include P2 arsenal presence/usage, BIP/BABIP,
  count-state rates, arm angle, fixed-formula SIERA, and run-expectancy value;
  none cleared nested promotion, so they are not production inputs;
- opposing-lineup Z-Swing%, Swing%, Z-Contact%, and BB% season-to-date and
  rolling candidates are generated, but remain research-only pending an
  explicit registry freeze;
- Rolling FIP/xFIP use summed prior-start counts. xFIP uses league HR/FB
  available before the game date, regressed toward the previous season with a
  1,000-fly-ball prior. The 2023 boundary uses 2022 Statcast context calculated
  under the same fly-ball definition; 2022 itself does not enter model rows.

## Context features

Opponent features aggregate each hitter's pregame overall/handed K%,
Whiff% (`Whiffs/Swings`), SwStr% (`Whiffs/Pitches`), and chase%. Research-only
lineup columns additionally cover discipline, wOBA/xwOBA/xBA, BABIP, contact
quality, batted-ball shape, and run value over season-to-date and P5/P10/P20
histories. They are represented as flat means, prior-date batting-order
opportunity weighted means, and weighted lineup dispersion. Historical
membership uses the first nine distinct batters by first plate appearance and
requires complete nine-player coverage. The current 248-feature production
baseline retains only the established lineup context columns. Live
projections substitute the RotoGrinders projected/confirmed lineup through
`Python.daily_lineups`; every scraped name must resolve to an official
team-roster MLB ID.

Park factors are keyed by `(season, home_team)` and use prior seasons only.
The prior-only 2022 source supplies 2023 park history without entering model
rows. This prevents future park outcomes from entering earlier rows.

## Evaluation requirements

Before publishing performance or using probabilities:

- run the complete Level 1-3 pipeline;
- choose rolling windows with denominator-aware stabilization, then validate
  nearby choices with chronological CV and grouped ablation;
- train without label/identifier columns;
- compare against a mean baseline and a regularized linear baseline;
- assess calibration and proper scoring rules for prop probabilities;
- use projected TBF in all strikeout-count evaluation;
- freeze the data window, feature list, parameters, and model artifact.
- retain 2023-2025 in `PIPELINE_SEASONS` for holdout/projection artifacts, but
  enforce `TRAIN_SEASONS = (2023, 2024)` in trainer loading; no 2025 row may
  enter training, validation, preprocessing, or internal testing;
- perform feature/window/hyperparameter selection in inner chronological folds
  and confirm the procedure in distinct outer folds. The 2025 holdout was
  already scored by historical baselines, so it must not drive further model
  decisions or be described as pristine; the next honest final test requires
  genuinely future post-freeze games.
- account for K/PA heteroskedasticity by comparing ordinary regression with
  PA-weighted and binomial/beta-binomial formulations before declaring the
  rate model statistically final.
- derive `P(K >= n)` from a calibrated count distribution, with
  beta-binomial and negative-binomial candidates compared against a Poisson
  baseline. This work is contingent on a stable projected-TBF model.

## Current limitations

- TBF projection and end-to-end prop backtesting are incomplete.
- Daily lineup ingestion exists, but its scheduler, retry/monitoring layer, and
  downstream production prediction assembly are not implemented.
- Batter-by-pitch-type run value remains research-only: no detailed or coarse
  pitch family cleared the lower-bootstrap-CI reliability gate.
- Weather, travel/rest, catcher, and market inputs are not integrated.
- Neutral-site/international games can contaminate team-keyed park factors.
- The production LightGBM gate remains the 248-feature deterministic-pruned
  baseline; explicit Step 7 registry freeze has not occurred. The current
  563-feature research design has 315 research-only candidates. The qualified
  batter quality weighted-dispersion family improved both LightGBM outer folds
  but worsened Ridge MAE in both, so it is not a model-agnostic promotion.
  Ridge has a separate 165-feature VIF-reduced interpretation proposal. The
  historical 2025 benchmark cannot serve as a pristine final test.
