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

# LightGBM (default: production 180)
python Models/Strikeout-Model/train.py --model lightgbm
python Models/Strikeout-Model/train.py --model lightgbm --feature-set step7_185

# Step 5 PA-weighted diagnostic arm (same features; PA is weight only)
python Models/Strikeout-Model/train.py --model ridge --sample-weight pa
python Models/Strikeout-Model/train.py --model lightgbm --sample-weight pa

# Count layer: expected_K = k_rate × projected_tbf (+ line probs)
python Models/Strikeout-Model/score_count_layer.py

# Historical research runners (feature freeze is closed)
python Models/Strikeout-Model/Strikeout-EDA/step8_keep_drop.py
```

LightGBM handles missing feature values natively. Ridge imputes medians and
standardizes inside a scikit-learn pipeline fitted only on training rows.
`--sample-weight pa` keeps the unweighted baseline available and reports both
unweighted and PA-weighted holdout metrics.

LightGBM models and adjacent JSON metadata (feature names and evaluation
results) are written to `artifacts/models/` by default. Generated models are
ignored by Git.

The frozen production gate is **180 features** (`--feature-set production`;
Step 10 P1 physics swap). Locked artifact:
`artifacts/models/lightgbm_krate_20260728_033241.*` (test MAE / RMSE / R² ≈
0.0787 / 0.0987 / 0.147). See `docs/step10_p1_registry_freeze.md`. Companion
`step7_185` retains the pre-P1 freeze. `pre_freeze_248` is comparison-only.

**Next (not more features):** Phase 11 model quality — nested tune, walk-forward
stack backtest, calibration (`docs/phase11_model_quality_gates.md`). Live
assembly is deferred until those gates pass.

TBF + count layer: `Models/TBF-Model/train.py` and `score_count_layer.py`
(`docs/tbf_first_model_findings.md`, `docs/count_layer_findings.md`).

The `Strikeout-EDA/` notebooks and runners read Level 1 artifacts for
distribution, stabilization, and feature-ablation work. They are not training
entry points.
