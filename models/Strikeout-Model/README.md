# Strikeout-rate model

`train.py` is the canonical training entry point for the current production
lineage.

`train.ipynb` is a visual audit companion that imports the production trainer;
it is not a second implementation.

```powershell
# Build model-ready data first
python -c "from Python.pipeline import run_all; run_all()"

# Benchmarks (unweighted baseline)
python models/Strikeout-Model/train.py --model mean
python models/Strikeout-Model/train.py --model ridge

# LightGBM (active production and challenger registries)
python models/Strikeout-Model/train.py --model lightgbm
python models/Strikeout-Model/train.py --model lightgbm --feature-set step10_180
python models/Strikeout-Model/train.py --model lightgbm --feature-set step7_185
python models/Strikeout-Model/train.py --model lightgbm --feature-set production_final58_consensus

# Step 5 PA-weighted diagnostic arm (same features; PA is weight only)
python models/Strikeout-Model/train.py --model ridge --sample-weight pa
python models/Strikeout-Model/train.py --model lightgbm --sample-weight pa

# Count layer: expected_K = k_rate × projected_tbf (+ line probs)
python models/Strikeout-Model/score_count_layer.py

# Post-hoc calibration on p_over_* (chrono CV; does not retrain rate/TBF)
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

Current live deployment is ensemble-based, selected from the deduped manual
transfer governance lane:

- `0.00 production_sparse72 + 0.60 production_sparse72_monotone + 0.40 production_final58_consensus`
- config: `production/ops/live_krate_ensemble.json`
- runtime: `src/Python/live_assembly.py`

Single-model registries remain available for comparison/challenger analysis.

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
