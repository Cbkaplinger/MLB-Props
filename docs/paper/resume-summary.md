# Pregame Pitcher Strikeout Projection - Resume Project Summary

**Cameron Kaplinger** - Portfolio artifact (updated 2026-09-11)

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

**Live policy (promoted 2026-09-11 from a 2025-lock selection):** line floors + 4.5-over veto + 2.5/3.5 probation + morning edge cap `0.24` + under-lean premium `+0.04` on overs + DK+FD-only universe + offset clip `±0.02` + 1/16-Kelly + postseason HOLD. A same-day robust-refusal arm was measured and reverted (2025 −0.2% vs base +4.2%).

**Policy-search diagnostics (pre-freeze `n=26`, 2026-07-30–08-17; historical):** ROI `0.4363`, Sharpe `0.4438`. Audit 2026-09-01: **selection-window evidence**, not validated deployment edge. Superseded by the replay era below.

**Universe close skill (live Poisson + WS1c, `n=19,533`):** Brier `0.2204` vs book `0.2162` (skill **`−0.0043`**); ECE `0.021` vs book `0.009`. Skill negative on all eight lines. Same starts **beat friend opens** (skill `+0.044` at ≈ −12h) and trail by morning.

**Juiced replay (frozen probs at executable prices, rejects kept, `n=2,077`):** flat-1u ROI **+7.3%** all-books / **+12.3%** DK+FD-only; 2025 +4.2% / 2026 +12.6% confirmatory. Fills unmodeled.

**2025-lock champion (promoted with disclosed 2026 peek):** 36-config family scored on 2025 only → floor `0.12` / cap `0.24` / under-lean / DK+FD: 2025 `n=558` ROI **+15.5%** WR `0.60` LCB **+7.4%**; White-lite p<0.0005; exclusions ≥+12.9%; 2026 one-look repeat `n=485` ROI **+15.6%**.

**Paper money track (deduped 36 days, `n=317`):** PnL `+$611` (+2.7% ROI), mean CLV `+0.75`pp on `n_clv=195`; veto lane +6.5% (`n=258`) — paper prices, not fills. ≥50 real fills remain the money-truth gate.

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

Leakage-safe Statcast → rate × exposure stack with nested chronological
selection, scaled into a quant-governed production system: frozen-model
replay at executable prices, pre-registered 2025-lock policy selection
(36 configs, White-checked, disclosed-peek judged), per-line Platt
calibration, Poisson counts, and a live board governed by regression pins.
Universe skill trails books on probabilities (−0.0043); the money comes
from choice — clock, tickets, books — and the ledger proves each choice:
veto, lean, cap, DK+FD-only. A same-day arm that didn't validate
(robust-refusal, 2025 −0.2%) was reverted within hours with the evidence
cited. No fills-gated money claim.

**Portfolio claim:** production-minded ML engineering under a strict information constraint, strengthened by statistical rigor and quant-style decision governance — including the discipline to revert your own morning shipment by afternoon.

## Copy/Paste resume bullets

- Built a leakage-safe MLB forecasting pipeline over pitch-level Statcast data (Polars + Python, 340+ pytest guards), enforcing chronological splits and pregame-only features, then wired it into a governed live decision system that scores a daily board, logs a paper ledger, and pages on failure.
- Designed a two-stage prediction stack (`k-rate × projected TBF`) with Poisson line probabilities and per-line Platt calibration; measured it against book closes at universe scale (`n=19,533`: Brier `0.2204` vs `0.2162`) and at executable juiced prices with rejects retained (flat-1u `+7.3%` all-books / `+12.3%` DK+FD).
- Ran a pre-registered 36-config policy selection on 2025 data (slate-clustered LCB champion: floor `0.12` / cap `0.24` / under-lean / DK+FD-only, ROI `+15.5%`), stress-checked it (White-lite p<0.0005, exclusions ≥+12.9%), confirmed on a disclosed 2026 peek (`+15.6%`), and promoted it to production behind regression pins — reverting a same-day arm the data rejected.
- Productionized execution hygiene: atomic ledger writes, settle hard-guards, shared API fetch, failure-banner alerting, and a reproducibility contract (raw JSON + frozen hashes + policy version reconstruct every ticket).

## Interview framing (30 seconds)

I built a production-first sports forecasting system where the hard part was not
model accuracy — books beat us on probabilities at every line — but turning a
frozen model into executable edge: bet earlier (we beat the opener by +0.044),
filter harder (a pre-registered 36-policy selection with White-checked
significance picked floor/cap/lean/DK+FD-only for +15.5% on 2025, repeated
+15.6% on 2026), and report honestly (rejected tickets kept, peeks disclosed,
a same-day shipment reverted when selection-year data rejected it).

---

*Code first:* [GitHub repository](https://github.com/Cbkaplinger/MLB-Props) · *Paper:* [manuscript PDF](https://github.com/Cbkaplinger/MLB-Props/blob/main/docs/paper/manuscript.pdf)
