# Post-hoc `p_over_*` calibration (Platt / isotonic)

**Status:** research complete; **production pointer set to isotonic** (2026-08-21)  
**Code:** `src/Python/prob_calibration.py`  
**Fit / CV:** `models/Strikeout-Model/research/fit_prob_calibration.py`  
**Artifacts:** `artifacts/models/prob_calibration_isotonic_20260821_160723.{joblib,json}`  
**Pointer:** `artifacts/models/prob_calibration_production.json`  
**Report:** `artifacts/model_quality/prob_calibration/fit_report_isotonic_20260821_160723.json`

## Verdict

| Layer | Conclusion |
|---|---|
| Baseball truth (K-rate / TBF / expected_K) | **Unchanged** — calibrator does not touch means |
| Probability calibration | **Isotonic promoted in production** for current governance lock; raw and calibrated streams both retained |
| Betting product (8% floor / Kelly / sides) | **Unchanged** — not selected on ROI |

Phase 11.C already reported mean ECE ≈ 0.024 and did **not** require recalibration under its soft bar. This track is a **follow-on honesty layer** motivated by live mid-bin overconfidence (50–70%) and line 3.5/4.5 heat on graded starts — not a claim that 11.C failed.

## What this is / is not

```text
p_raw (binomial count layer)  →  p_cal (isotonic monotone map)
```

- Fits **only** on Phase 11.B walk-forward OOS predictions (`K` labels + `p_over_3_5…7_5`).
- Expanding-window CV: train on earlier WF windows → test on later.
- Production map: refit chosen method on **all** WF OOS rows through **2024-09-30** after CV selection (refit metrics are descriptive; CV deltas are the leakage-safe claim).
- Does **not** retrain LightGBM or Ridge.
- Does **not** use paper tickets / ROI for selection.
- Keeps raw `p_over_*`; writes `p_over_*_cal` + `calibration_version`.

## Method selection (chrono CV)

| Method | Mean ΔBrier (cal − raw) | Mean ΔECE (cal − raw) |
|---|---:|---:|
| **Platt** | **−0.00047** | **−0.0079** |
| Isotonic | +0.00065 | −0.0019 |

**Current production choice: isotonic.** Historical chrono CV favored Platt on the 2024 WF panel, but production governance now locks isotonic for alignment with the current full-universe ranking lane and deployment policy. Both raw and calibrated outputs remain available for ongoing monitoring.

Fold detail (historical Platt reference):

| Test window | Pooled raw ECE | Pooled cal ECE | Line 3.5 raw→cal ECE |
|---|---:|---:|---:|
| `wf_2024_jun_jul` | 0.022 | 0.016 | 0.066 → 0.050 |
| `wf_2024_aug_sep` | 0.022 | 0.011 | 0.041 → 0.018 |

AUC / ranking: essentially preserved (monotone-in-logit map). Expected-K MAE: unchanged by construction.

## Production apply

`live_assembly.score_frame` (default):

1. `attach_count_predictions` → raw `p_over_*`
2. Load `prob_calibration_production.json` → apply → `p_over_*_cal`
3. `fair_amer_*` from calibrated probs when present
4. `odds_board.p_model_over_for_line` prefers `*_cal`

Fallback hierarchy at apply time:

```text
line-specific map (3.5…7.5)
  → nearest trained line (2.5→3.5, 8.5/9.5→7.5)
  → global map
  → identity
```

Disable with `score_frame(..., calibration_path=False)`.

## Ops

```powershell
# Re-fit + CV report (does not move production pointer unless flagged)
python models/Strikeout-Model/research/fit_prob_calibration.py --method both

# Promote chosen artifact
python models/Strikeout-Model/research/fit_prob_calibration.py --method both --set-production
```

Tests: `tests/test_prob_calibration.py`, `tests/test_odds_board_lines.py` (cal preference).

## Still open / not claimed

- Live 2026+ mid-bin behavior after isotonic apply still needs monitoring on graded logs (n still small).
- Count-distribution challengers (NB / mixture-over-TBF) remain the structural alternative if ECE regresses.
- Do **not** retune the 8% edge floor from calibrator-induced edge shrinkage.
- Historical odds purchase still deferred to the clean CLV gate.

## Related

- `docs/research/phase11_model_quality_gates.md` (11.C diagnose-only)
- `docs/research/count_layer_findings.md`
- `docs/reference/model-card.md`
- `docs/reference/market_clv_gates.md` (product layer unchanged)
