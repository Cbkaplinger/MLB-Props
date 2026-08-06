# Pregame Pitcher Strikeout Projection — Project Summary

**Cameron Kaplinger** · Independent Researcher · Portfolio artifact (July 2026)

Companion to the full technical manuscript in `docs/paper/manuscript.md`.

---

## Goal

Estimate a starter’s strikeout rate before first pitch, project how many batters that starter will face, and convert the pair into expected strikeouts and P(K ≥ L) for common prop lines L—using only information available before first pitch:

<div class="equation">k<sub>rate</sub> × TBF → E[K] → P(K ≥ L)</div>

---

## Models and headline metrics

| Component | Model | Role |
|---|---|---|
| Strikeout rate | Unweighted LightGBM (184 features) | Frozen production rate model |
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
| **Live market pilot (exploratory)** | Paper-traded vs. real DK/FD lines, quarter-Kelly sizing off an 8% edge floor. Pre-registered gate: n≥100 CLV samples + bootstrap CI excluding 0. **Current status: inconclusive** — directionally positive mean CLV (~+0.7pp) at n≈85–90, below the pre-registered sample threshold. Not a claim of market edge. |

---

## Takeaway

Leakage-safe Statcast → rate × exposure stack with nested chronological selection. Clears a Marcel-lite talent floor on chronological test; opponent lineup is the only leave-family-out family with both-fold within-fold bootstrap support. Absolute R² remains limited (~0.15). A live closing-line-value pilot against real sportsbook markets is running under a pre-registered statistical gate — currently inconclusive, to be updated once the sample resolves. Portfolio claim: ML engineering under a hard pregame constraint, extended with production deployment and live-market monitoring discipline.

---

*Full write-up: `docs/paper/manuscript.pdf`*
