# Step 5 findings — PA-weighted regression arm

**Status:** complete (diagnostic closed)  
**Date:** 2026-07-27  
**Local artifacts (gitignored):** `artifacts/feature_research/step5_pa_weight/`  
**Runner:** `models/Strikeout-Model/research/pa_weight_nested_compare.py`

## Verdict

On the protected nested 2023–2024 folds, **PA sample-weighting does not beat
unweighted** Ridge or LightGBM on game-level (unweighted) MAE/RMSE. Keep the
unweighted regression baseline; treat PA-weighting as a finished diagnostic.

| Model | Arm | Mean unweighted MAE | Mean unweighted RMSE | Mean unweighted R² |
|---|---|---:|---:|---:|
| LightGBM | none | **0.0789** | **0.0996** | **0.1010** |
| LightGBM | pa | 0.0793 | 0.0999 | 0.0946 |
| Ridge | none | **0.0838** | **0.1057** | −0.0207 |
| Ridge | pa | 0.0854 | 0.1081 | −0.0712 |

## Protocol notes

- Same `nested_research_folds` and 248-feature production allow-list
- `PA` used only as `sample_weight`, never as a feature
- LightGBM research protocol: fixed 800 trees, no early stopping (ablation
  convention). Production `train.py` early-stopped gate remains ~RMSE 0.0983.
  Prior Optuna artifacts were purged; this compare intentionally holds LGBM
  hyperparameters fixed so arms differ only by weighting.

## Pickup

Re-run locally:

```powershell
python models/Strikeout-Model/research/pa_weight_nested_compare.py
```

Next Step 5 arms (binomial / beta-binomial) are complete — keep unweighted
LightGBM. Feature freeze later landed at **184** (Step 11; prior spine 180).
Remaining critical path after this arm was Phase 11 model quality
(`docs/research/phase11_model_quality_gates.md`), then Phase D / pristine
post-freeze eval.

## Artifact consolidation note

The generated `artifacts/feature_research/step5_pa_weight/SUMMARY.md`
duplicated the protocol, headline metrics, and unweighted-vs-PA decision
already written here and in `PAPER_NOTES.md`. Removed on 2026-07-28; keep
`inner_results.csv`, `outer_results.csv`, `aggregate.csv`,
`pa_minus_none_deltas.csv`, and `metadata.json`.
