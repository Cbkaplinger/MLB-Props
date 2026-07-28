# Strikeout model research runners

Exploratory analysis and nested-selection runners for the pregame pitcher
strikeout-rate model. Trainers live one level up (`../train.py`).

## Contents

- `strikeout-eda.ipynb` — target distribution, correlations, skew/null audits,
  physics-vs-K scatter, stat stabilization curves, and a per-stat reliability
  table (split-half, ICC, year-over-year, SEM, regression slope, feature tiers).
- `stabilization.ipynb` — denominator-aware audit companion for candidate
  rolling windows.
- `run_stabilization.py` — reusable overall pitcher/batter stabilization run.
- `run_pitch_type_stabilization.py` — denominator-aware pitch-type
  stabilization run.
- `run_batter_discipline_stabilization.py` — focused stabilization for
  Z-Swing%, Swing%, Z-Contact%, and BB%.
- `run_batter_quality_stabilization.py` — focused stabilization for expected
  stats, contact quality, batted-ball shape, and batter run value.
- `pa_weight_nested_compare.py` — Step 5 nested none-vs-pa sample-weight
  comparison on the production feature allow-list.
- `beta_binomial_nested_compare.py` — Step 5 two-stage beta-binomial challenger
  with binomial/BB NLL scoring across mean models.
- Nested CV / ablation / walk-forward / Marcel / Section 6.1 check runners —
  see filenames in this directory; findings live under `docs/research/`.

Canonical training entry point: `../train.py`.
