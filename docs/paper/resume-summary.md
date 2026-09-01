# Pregame Pitcher Strikeout Projection - Resume Project Summary

**Cameron Kaplinger** - AI Engineer (Data Science background) - Portfolio artifact (updated Aug 2026)

Primary project link: [GitHub repository](https://github.com/Cbkaplinger/MLB-Props)  
Secondary long-form write-up: [Technical manuscript](https://github.com/Cbkaplinger/MLB-Props/blob/main/docs/paper/manuscript.md)

---

## Goal

Estimate a starter’s strikeout rate before first pitch, project how many batters that starter will face, and convert the pair into expected strikeouts and P(K ≥ L) for common prop lines L—using only information available before first pitch:

<div class="equation">k<sub>rate</sub> × TBF → E[K] → P(K ≥ L)</div>

## Professional positioning

This project demonstrates a blended profile across:

- **AI/ML engineering:** end-to-end feature pipelines, freeze discipline, and reproducible deployment artifacts.
- **Applied statistics:** chronological validation, calibration diagnostics, and leakage-safe modeling controls.
- **Quant decisioning:** market-skill ranking, policy-floor governance, and risk-aware deployment gates.

---

## Models and headline metrics

| Component | Model | Role |
|---|---|---|
| Strikeout rate (live) | Weighted 3-model LightGBM blend | Active production scorer (`live_krate_ensemble.json`) |
| Batters faced (TBF) | Ridge (thin bullpen, 24 features) | Projected exposure |
| Counts / lines | Binomial / Poisson on projected TBF | Expected K and P(K ≥ L) |

**Active deployment profile (frozen `KING_PROFILE_AUG2026`, 2026-08-21):** blend `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58`, edge floor `0.12`.  
**Policy-search diagnostics (pre-freeze `n=26`, 2026-07-30–08-17; not post-freeze OOS):** ROI `0.4363`, PnL `1208.55`, Sharpe `0.4438`, Sortino `0.4277`, max drawdown `0.1905`, market-skill deltas `+0.2069` (Brier) / `+0.1551` (LogLoss). Audit 2026-09-01: these ROI/Sharpe figures are **selection-window evidence**, not validated deployment edge.  
**Post-freeze KING-floor lane (2026-08-22–08-31, `n=74`):** ROI `−1.55%`, win rate `48.6%`, CLV mean `+1.59`pp (beat-close `58.6%` on `n_clv=29`); overs `n=45` / `−24.6%` ROI vs unders `n=29` / `+29.3%` ROI. Honest OOS sample — larger than n=26, still underpowered, **not** a claimed edge.

---

## Full-stack evaluation (production)

| Evaluation gate | Result |
|---|---|
| Estimator tuning | Keep baseline LightGBM defaults; Ridge α tuned and persisted |
| Calibration + probability quality | Production isotonic path; Brier `0.2090`, LogLoss `0.6087`, ECE `0.0639`, MCE `0.1353` |
| Population policy | Metrics conditional on PA ≥ 9 (~3.5% of first pitchers excluded) |
| Exogenous-exit governance | Source-tagged anomaly overrides + training mask are shipped; current walk-forward A/B effect is neutral under low historical tag density |

---

## Current governance winners

High-signal results from current artifacts:

- Open-universe deduped sweep winner (`ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv`):
  - blend `0.05 sparse72 / 0.45 sparse72_monotone / 0.50 final58`
  - ROI `0.6612`, Sharpe `0.9468`, Sortino `0.6954`, bets `35`
  - Brier/LogLoss skill vs market: `+0.0825 / +0.0645`
- Active deployment king (`open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`):
  - blend `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58` (frozen 2026-08-21)
  - **policy-search** ROI `0.4363`, PnL `1208.55`, Sharpe `0.4438`, Sortino `0.4277`, max DD `0.1905` on pre-freeze `n=26` (2026-07-30–08-17) — not post-freeze OOS
  - Brier/LogLoss skill vs market: `+0.2069 / +0.1551`
- Duplicate-ticket diagnostics explicitly tracked: `123` duplicate groups, `246` duplicate tickets in manual-set audits.

---

## Resume-ready takeaway

Leakage-safe Statcast -> rate x exposure stack with nested chronological
selection, then scaled into a quant-governed production system with open-market
replay, deduped fairness controls, transfer calibration, and live ensemble
deployment. The stack shows positive market-skill deltas in current governance lanes, and runs under
explicit CI/gate discipline without overstating unresolved live-edge evidence.

**Portfolio claim:** production-minded ML engineering under a strict information constraint, strengthened by statistical rigor and quant-style decision governance.

## Copy/Paste resume bullets

- Built a leakage-safe MLB forecasting pipeline over pitch-level Statcast data (Polars + Python), enforcing chronological splits and pregame-only features, then wired it into a governed live decision system.
- Designed and deployed a two-stage prediction stack (`k-rate × projected TBF`) with isotonic-calibrated line probabilities and artifact-backed governance diagnostics in production.
- Productionized a governed decision engine with isotonic calibration, board-to-ledger parity locks, and execution freshness/coverage gates; hardened daily run reliability with explicit fail-fast controls.
- Led model-selection governance using open-universe counterfactual replay and deduped one-opportunity-one-bet evaluation; froze production blend/floor/isotonic under `KING_PROFILE_AUG2026` and documented that the oft-cited 26-bet ROI/Sharpe window is pre-freeze policy-search evidence (not post-freeze OOS), while reporting positive market-skill deltas (`Brier +0.2069`, `LogLoss +0.1551`) as search-window diagnostics.

## Interview framing (30 seconds)

I built a production-first sports forecasting system where the hard part was not
just model accuracy, but controlling leakage, calibration drift, and execution
quality. The final stack combines a frozen LightGBM ensemble with a projected
exposure model, then governs decisions with chronological testing and explicit
risk gates so we can operate daily without over-claiming edge.

---

*Code first:* [GitHub repository](https://github.com/Cbkaplinger/MLB-Props) · *Paper:* [manuscript PDF](https://github.com/Cbkaplinger/MLB-Props/blob/main/docs/paper/manuscript.pdf)
