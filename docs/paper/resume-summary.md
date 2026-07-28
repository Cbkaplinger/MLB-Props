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
| Strikeout rate | Unweighted LightGBM (180 features) | Frozen production rate model |
| Batters faced (TBF) | Ridge (thin bullpen, 24 features) | Projected exposure |
| Counts / lines | Binomial / Poisson on projected TBF | Expected K and P(K ≥ L) |

**Frozen rate model** (2023–2024 fit; chronological test from 2024-08-06): MAE / RMSE / R² ≈ **0.0787 / 0.0987 / 0.147** (~15% of game-level rate variance). Same test: train-mean MAE ≈ **0.0854**; Marcel-lite talent baseline MAE ≈ **0.0826**.

**Count layer** (same test partition, projected-TBF exposure): expected-K MAE / RMSE / R² ≈ **1.790 / 2.213 / 0.168**; line Briers roughly **0.12–0.22** (lines 3.5–7.5).

---

## Full-stack evaluation

| Evaluation gate | Result |
|---|---|
| Estimator tuning | Keep baseline LightGBM defaults; Ridge α tuned and persisted |
| Walk-forward stack backtest | Mean expected-K MAE ≈ **1.778** (3 expanding 2024 windows; σ ≈ 0.036) |
| Calibration | Mean ECE ≈ **0.024** (internal chronological calibration; no sportsbook or public-projection benchmark) |
| Population policy | Metrics conditional on PA ≥ 9 (~3.5% of first pitchers excluded) |

---

## Takeaway

Built and validated a leakage-safe Statcast → features → rate × exposure stack with nested chronological selection and automated leakage tests. Predictive power is modest (rate R² ≈ 0.15) but clears a Marcel-lite season-talent floor on the same chronological test. Leave-family-out results are reported per outer fold: lineup is both-fold positive for both models; several other mean deltas flip sign. The portfolio claim is ML engineering discipline under a hard pregame constraint—not a strong or market-beating predictor. Next: pregame role labels, post-freeze holdout, closing-line evaluation if practical value is the goal.

---

*Full write-up: `docs/paper/manuscript.pdf`*
