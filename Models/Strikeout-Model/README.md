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
python Models/Strikeout-Model/train.py --model mean
python Models/Strikeout-Model/train.py --model ridge

# LightGBM (default: production 184)
python Models/Strikeout-Model/train.py --model lightgbm
python Models/Strikeout-Model/train.py --model lightgbm --feature-set step10_180
python Models/Strikeout-Model/train.py --model lightgbm --feature-set step7_185

# Step 5 PA-weighted diagnostic arm (same features; PA is weight only)
python Models/Strikeout-Model/train.py --model ridge --sample-weight pa
python Models/Strikeout-Model/train.py --model lightgbm --sample-weight pa

# Count layer: expected_K = k_rate × projected_tbf (+ line probs)
python Models/Strikeout-Model/score_count_layer.py

# Post-hoc Platt/isotonic on p_over_* (chrono CV; does not retrain rate/TBF)
python Models/Strikeout-Model/research/fit_prob_calibration.py --method both
python Models/Strikeout-Model/research/fit_prob_calibration.py --method both --set-production

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

The frozen production gate is **184 features** (`--feature-set production`;
Step 10 P1 spine + Step 11 lineup-discipline lift). Locked artifact:
`artifacts/models/lightgbm_krate_20260803_155401.*` (test MAE / RMSE / R² ≈
0.0780 / 0.0982 / 0.156). See `docs/research/step11_discipline_registry_freeze.md`.
Companion `step10_180` retains the prior 180-feature freeze; `step7_185` and
`pre_freeze_248` remain comparison-only.

Phase 11 model quality (tune / walk-forward / calibrate) is **done** —
`docs/research/phase11_model_quality_gates.md`. Daily scoring + paper-trading
CLV live under `production/` (`production/README.md`,
`docs/reference/market_clv_gates.md`). Count lines: **2.5…9.5**.

TBF + count layer: `Models/TBF-Model/train.py` and `score_count_layer.py`
(`docs/research/tbf_first_model_findings.md`, `docs/research/count_layer_findings.md`).

The `research/` notebooks and runners read Level 1 artifacts for
distribution, stabilization, and feature-ablation work. They are not training
entry points.
