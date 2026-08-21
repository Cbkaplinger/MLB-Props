# Pregame Pitcher Strikeout Projection - Resume Project Summary

**Cameron Kaplinger** - AI Engineer (Data Science background) - Portfolio artifact (updated Aug 2026)

Companion to the full technical manuscript in `docs/paper/manuscript.md`.

---

## Goal

Estimate a starter’s strikeout rate before first pitch, project how many batters that starter will face, and convert the pair into expected strikeouts and P(K ≥ L) for common prop lines L—using only information available before first pitch:

<div class="equation">k<sub>rate</sub> × TBF → E[K] → P(K ≥ L)</div>

## Professional positioning

This project demonstrates a blended profile across:

- **AI/ML engineering:** end-to-end feature pipeline design, model freeze discipline, reproducible artifact/version controls, and production monitoring hooks.
- **Applied statistics:** chronological validation, bootstrap uncertainty intervals, calibration diagnostics, and explicit leakage audits.
- **Quant decisioning:** de-vig edge construction, CLV-based pre-registered decision gates, and policy-threshold governance under uncertainty.

---

## Models and headline metrics

| Component | Model | Role |
|---|---|---|
| Strikeout rate (single-model baseline) | Unweighted LightGBM (184 features) | Prior frozen production baseline |
| Strikeout rate (live) | Weighted 3-model LightGBM blend | Active production scorer (`live_krate_ensemble.json`) |
| Batters faced (TBF) | Ridge (thin bullpen, 24 features) | Projected exposure |
| Counts / lines | Binomial / Poisson on projected TBF | Expected K and P(K ≥ L) |

**Frozen rate model** (2023–2024 chronological test): MAE / RMSE / R² ≈ **0.0787 / 0.0987 / 0.147**. Same test: Marcel-lite MAE ≈ **0.0826**; train-mean MAE ≈ **0.0854**.

**Count layer** (projected-TBF exposure): expected-K MAE / RMSE / R² ≈ **1.790 / 2.213 / 0.168**; line Briers roughly **0.12–0.22** (lines 3.5–7.5).

---

## Full-stack evaluation

| Evaluation gate | Result |
|---|---|
| Estimator tuning | Keep baseline LightGBM defaults; Ridge α tuned and persisted |
| Walk-forward stack backtest | Mean expected-K MAE ≈ **1.778** (3 expanding 2024 windows; σ ≈ 0.036) |
| Calibration | Mean ECE ≈ **0.024** (11.C diagnose); production **Platt** post-hoc on `p_over_*` (chrono CV ΔECE ≈ −0.008; raw retained). Fit on 2024 walk-forward OOS predictions; not yet refit on 2026 conditions. |
| Population policy | Metrics conditional on PA ≥ 9 (~3.5% of first pitchers excluded) |
| Exogenous-exit governance | Source-tagged anomaly overrides + training mask + confidence-aware rolling contamination policy are shipped; current walk-forward A/B effect is neutral under low historical tag density |
| **Live market pilot (exploratory)** | Paper-traded vs. real DK/FD lines with conservative policy gating. Active decision gate uses CLV sample size and CI checks per `docs/reference/market_clv_gates.md` (current checkpoint: `n_clv >= 150` plus CI test). **Current status: inconclusive** — mean CLV is positive, but CI still crosses 0 at the current snapshot; not a claim of market edge. |

---

## Aug 2026 quant-governance expansion (new)

This project moved beyond a single freeze-vs-baseline comparison into a
portfolio-style governance framework with strict fairness controls:

- full open-universe replay lane,
- segment-aware calibration correction,
- deduped one-opportunity-one-bet robustness checks,
- open-to-manual calibration transfer for top ensembles,
- live production wiring to the best current manual-lane blend.

**High-signal results from current artifacts**

- Deduped full sweep winner (`ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv`):
  - blend `0.05 sparse72 / 0.45 sparse72_monotone / 0.50 final58`
  - ROI `0.6612`, Sharpe `0.9468`, Sortino `0.6954`, bets `35`
  - Brier/LogLoss skill vs market: `+0.0825 / +0.0645`
- Manual transfer winner (`open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`):
  - blend `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58`
  - ROI `0.4363`, PnL `1208.55`, Sharpe `0.4438`, Sortino `0.4277`, max DD `0.1905`
  - Brier/LogLoss skill vs market: `+0.2069 / +0.1551`
- Duplicate-ticket diagnostics explicitly tracked: `123` duplicate groups, `246` duplicate tickets in manual-set audits.

**What this signals professionally**

- I can move from model building to production governance with explicit
  reproducibility and policy controls.
- I treat ranking metrics, realized PnL/risk, calibration, and execution quality
  as separate but connected decision layers.
- I maintain audit trails through exported artifacts, overlap tables, and
  config-driven deployment.

---

## Resume-ready takeaway

Leakage-safe Statcast -> rate x exposure stack with nested chronological
selection, then scaled into a quant-governed production system with open-market
replay, deduped fairness controls, transfer calibration, and live ensemble
deployment. The stack clears a Marcel-lite talent floor on chronological test,
shows positive market-skill deltas in current governance lanes, and runs under
explicit CI/gate discipline without overstating unresolved live-edge evidence.

**Portfolio claim:** production-minded ML engineering under a strict information constraint, strengthened by statistical rigor and quant-style decision governance.

---

*Full write-up: `docs/paper/manuscript.pdf`*
