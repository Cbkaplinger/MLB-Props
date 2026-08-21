# Strikeout-rate model

`train.py` is the canonical training entry point. It reads the Level 3
`PITCHER_TRAINING_PATH`, derives the safe numeric feature list through
`Python.features.model_feature_names`, and uses a chronological 70/15/15
split. Boundary dates are assigned wholly to the later partition, so train,
validation, and test never share a calendar date.

`train.ipynb` is a visual audit companion that imports the production trainer;
it is not a second implementation.

```powershell
# Build model-ready data first
python -c "from Python.pipeline import run_all; run_all()"

# Benchmarks (unweighted baseline)
python models/Strikeout-Model/train.py --model mean
python models/Strikeout-Model/train.py --model ridge

# LightGBM (default registry may evolve with documented freezes)
python models/Strikeout-Model/train.py --model lightgbm
python models/Strikeout-Model/train.py --model lightgbm --feature-set step10_180
python models/Strikeout-Model/train.py --model lightgbm --feature-set step7_185
python models/Strikeout-Model/train.py --model lightgbm --feature-set production_final58_consensus

# Step 5 PA-weighted diagnostic arm (same features; PA is weight only)
python models/Strikeout-Model/train.py --model ridge --sample-weight pa
python models/Strikeout-Model/train.py --model lightgbm --sample-weight pa

# Count layer: expected_K = k_rate × projected_tbf (+ line probs)
python models/Strikeout-Model/score_count_layer.py

# Post-hoc Platt/isotonic on p_over_* (chrono CV; does not retrain rate/TBF)
python models/Strikeout-Model/research/fit_prob_calibration.py --method both
python models/Strikeout-Model/research/fit_prob_calibration.py --method both --set-production

# Historical research runners (feature freeze is closed)
python models/Strikeout-Model/research/step8_keep_drop.py
```

LightGBM handles missing feature values natively. Ridge imputes medians and
standardizes inside a scikit-learn pipeline fitted only on training rows.
`--sample-weight pa` keeps the unweighted baseline available and reports both
unweighted and PA-weighted holdout metrics.

LightGBM models and adjacent JSON metadata (feature names and evaluation
results) are written to `artifacts/models/` by default. Generated models are
ignored by Git.

Current MAE-first freeze candidate is `production_final58_consensus` (58
features) from the consensus chunk-merge feature search; see
`docs/research/final58_consensus_freeze_2026-08-20.md`. Money-facing governance
replay still favors `production_oof72_monotone`, so keep both candidates in
comparison tables until tuned LightGBM + risk-adjusted policy gates finalize.
`production`, `step10_180`, `step7_185`, and `pre_freeze_248` remain available
for historical comparisons.

Daily production operation and diagnostics run under `production/`:
- `production/INDEX.md`
- `production/RUNBOOK.md`

Phase 11 model quality (tune / walk-forward / calibrate) is **done** —
`docs/research/phase11_model_quality_gates.md`. Daily scoring + paper-trading
CLV live under `production/` (`production/README.md`,
`docs/reference/market_clv_gates.md`). Count lines: **2.5…9.5**.

TBF + count layer: `models/TBF-Model/train.py` and `score_count_layer.py`
(`docs/research/tbf_first_model_findings.md`, `docs/research/count_layer_findings.md`).

The `research/` notebooks and runners read Level 1 artifacts for
distribution, stabilization, and feature-ablation work. They are not training
entry points.
