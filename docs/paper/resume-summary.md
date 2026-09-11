# Pregame Pitcher Strikeout Projection - Resume Project Summary

**Cameron Kaplinger** - AI Engineer (Data Science background) - Portfolio artifact (updated 2026-09-10)

> **Repo work queue (not this resume):** live approvals / next steps live in [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md). This page is a portfolio summary only.

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
- **Quant decisioning:** market-skill ranking vs book closes, policy-floor governance, and risk-aware deployment gates.

---

## Models and headline metrics

| Component | Model | Role |
|---|---|---|
| Strikeout rate (live) | Weighted 3-model LightGBM blend | Active production scorer (`live_krate_ensemble.json`) |
| Batters faced (TBF) | Ridge (thin bullpen, 24 features) | Projected exposure |
| Counts / lines | **Poisson** on projected TBF (binomial one-line revert) | Expected K and P(K ≥ L) |
| Line maps (live) | Per-line Platt (WS1c), shipped 2026-09-10 | Replaces August isotonic pointer |

**Active deployment profile (frozen `KING_PROFILE_AUG2026`, 2026-08-21):** blend `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58`, juiced edge floor `0.12`. Live overlays: 4.5-over hard veto, 2.5/3.5-over probation floor `0.18`, postseason HOLD after `2026-09-27`. Offset cap, stacker overlay, and morning edge-cap are researched and **not live**.

**Policy-search diagnostics (pre-freeze `n=26`, 2026-07-30–08-17; not post-freeze OOS):** ROI `0.4363`, PnL `1208.55`, Sharpe `0.4438`, Sortino `0.4277`, max drawdown `0.1905`, market-skill deltas `+0.2069` (Brier) / `+0.1551` (LogLoss). Audit 2026-09-01: these ROI/Sharpe figures are **selection-window evidence**, not validated deployment edge.

**Universe close skill (live Poisson + WS1c, 2026-09-10, `n=19,533`):** Brier `0.2204` vs book `0.2162` (skill **`−0.0043`**); ECE `0.021` vs book `0.009`; MCE `0.088` vs `0.019`. Skill negative on all eight lines. Same starts **beat friend opens** (skill `+0.044` at ≈ −12h) and trail by morning. **Not a betting-edge claim.**

**Paper money track (deduped through 2026-09-09, `n=973`):** PnL `+$611`, mean CLV `+0.59`pp on `n_clv=545` — paper prices, not fills. ≥50 real fills remain the money-truth gate.

---

## Full-stack evaluation (production)

| Evaluation gate | Result |
|---|---|
| Estimator tuning | Keep baseline LightGBM defaults; Ridge α tuned and persisted |
| Calibration + probability quality | Live WS1c Platt + Poisson; universe ECE `0.021` / MCE `0.088` on `n=19,533` (book `0.009` / `0.019`). Search-lane ECE `0.0639` on `n=26` is labeled, not live. |
| Population policy | Metrics conditional on PA ≥ 9 (~3.5% of first pitchers excluded) |
| Exogenous-exit governance | Source-tagged anomaly overrides + training mask are shipped; current walk-forward A/B effect is neutral under low historical tag density |

---

## Current governance winners

High-signal results from current artifacts:

- Universe close-matched panel (`rescore_cal_report.json`): live config skill `−0.0043` Brier vs book; ships closed ~27% of the frozen-config gap.
- Open-universe deduped sweep winner (`ensemble_sweep_ranked_ensemble_full_aug21_deduped.csv`) — **search lane, not live quality:**
  - blend `0.05 sparse72 / 0.45 sparse72_monotone / 0.50 final58`
  - ROI `0.6612`, Sharpe `0.9468`, Sortino `0.6954`, bets `35`
  - Brier/LogLoss skill vs market: `+0.0825 / +0.0645`
- Active deployment king (`open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json`):
  - blend `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58` (frozen 2026-08-21)
  - **policy-search** ROI `0.4363`, PnL `1208.55`, Sharpe `0.4438`, Sortino `0.4277`, max DD `0.1905` on pre-freeze `n=26` (2026-07-30–08-17) — not post-freeze OOS
- Duplicate-ticket diagnostics explicitly tracked: `123` duplicate groups, `246` duplicate tickets in manual-set audits.

---

## Resume-ready takeaway

Leakage-safe Statcast -> rate x exposure stack with nested chronological
selection, then scaled into a quant-governed production system with open-market
replay, deduped fairness controls, per-line Platt calibration, Poisson counts,
and live ensemble deployment. Universe-scale skill vs book closes is slightly
negative after the 2026-09-10 ships; timing (beat the open) and selection
filters are the remaining levers. No persistent betting-edge claim.

**Portfolio claim:** production-minded ML engineering under a strict information constraint, strengthened by statistical rigor and quant-style decision governance.

## Copy/Paste resume bullets

- Built a leakage-safe MLB forecasting pipeline over pitch-level Statcast data (Polars + Python), enforcing chronological splits and pregame-only features, then wired it into a governed live decision system.
- Designed and deployed a two-stage prediction stack (`k-rate × projected TBF`) with Poisson line probabilities, per-line Platt (WS1c) calibration, and artifact-backed governance diagnostics in production.
- Productionized a governed decision engine with board-to-ledger parity locks, a 4.5-over hard veto, and execution freshness/coverage gates; hardened daily run reliability with explicit fail-fast controls.
- Measured market skill on a close-matched universe (`n=19,533`): live Brier `0.2204` vs book `0.2162` (skill `−0.0043`), ECE `0.021` vs `0.009`; documented that the oft-cited 26-bet ROI/Sharpe window is pre-freeze policy-search evidence, not post-freeze OOS.

## Interview framing (30 seconds)

I built a production-first sports forecasting system where the hard part was not
just model accuracy, but controlling leakage, calibration drift, and execution
quality. The final stack combines a frozen LightGBM ensemble with a projected
exposure model, then governs decisions with chronological testing and explicit
risk gates so we can operate daily without over-claiming edge.

---

*Code first:* [GitHub repository](https://github.com/Cbkaplinger/MLB-Props) · *Paper:* [manuscript PDF](https://github.com/Cbkaplinger/MLB-Props/blob/main/docs/paper/manuscript.pdf)
