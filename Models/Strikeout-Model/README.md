# Strikeout-rate model

`train.py` is the canonical training entry point. It reads the Level 3
`PITCHER_TRAINING_PATH`, derives the safe numeric feature list through
`Python.features.model_feature_names`, and uses a chronological 70/15/15
split. Boundary dates are assigned wholly to the later partition, so train,
validation, and test never share a calendar date.

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

The `Strikeout-EDA/` notebook reads Level 1 pitcher games for distribution and
stabilization work. It is not a training entry point.
