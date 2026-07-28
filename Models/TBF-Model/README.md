# TBF Model

Projected batters-faced (`PA`) for starter props.

**Frozen spine (paper):** Ridge + `workload_context_bullpen` (thin bullpen).  
**Downstream:** count layer `expected_K` + line probs
(`docs/research/count_layer_findings.md`).

```powershell
python Models/TBF-Model/train.py
python Models/TBF-Model/train.py --model ridge --feature-set workload_context_bullpen
python Models/TBF-Model/train.py --model ridge --feature-set workload_context_bullpen_rich
python Models/Strikeout-Model/score_count_layer.py
```

See `docs/research/tbf_first_model_findings.md`. **Next for the stack:** Phase 11
estimator tune (including persist Ridge α / joblib) → walk-forward backtest →
calibration (`docs/research/phase11_model_quality_gates.md`). Live assembly is deferred
until those gates.
