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

# Benchmarks
python Models/Strikeout-Model/train.py --model mean
python Models/Strikeout-Model/train.py --model ridge

# LightGBM
python Models/Strikeout-Model/train.py --model lightgbm
```

LightGBM handles missing feature values natively. Ridge imputes medians and
standardizes inside a scikit-learn pipeline fitted only on training rows.

LightGBM models and adjacent JSON metadata (feature names and evaluation
results) are written to `artifacts/models/` by default. Generated models are
ignored by Git.

The current production gate contains 248 features. The latest date-disjoint
2023-2024 LightGBM development evaluation has internal-test RMSE `0.0983` and
R² `0.1546`; its model and metadata are
`artifacts/models/lightgbm_krate_20260724_165215.*`. The 227-feature
2025-consulting run remains a historical benchmark, not a pristine final test.
The invalid overlapping-date snapshot is archived under
`docs/archive/leaky-baseline-2026-07-23/`.

The `Strikeout-EDA/` notebooks and runners read Level 1 artifacts for
distribution, stabilization, and feature-ablation work. They are not training
entry points.
