# External research digest 2026-09-28: nfelo market regression, gbnet, Sloan DRL

Owner-prompted deep read (2026-09-28). Verdicts below are mapped to OUR
repo reality (paths, artifacts, prior kills) — not generic summaries.
Companion backlog entry holds the decisions; this file holds the reasoning.

## 1. nfelo — market regression (ADOPT, highest value)

Source: nfeloapp.com NFL study. Findings:
- Markets beat the model alone; **model + market blended beats either**
  (optimal ~65% market weight by Brier).
- Dynamic version: regress LESS where the model's trailing error beats the
  market's (exponential-average squared errors per team), more where not.
- Brier-vs-ATS distinction: volatile margins can beat ATS while losing Brier.

Mapping to us:
- We already own both ingredients: model probs (ws1c-calibrated) + market
  fair (paid consensus closes, Kalshi fairs, DK/FD devigged).
- Our Kalshi-overlay experiment independently found the same shape:
  halfway-to-sharp +0.0263 (52x bar), ~80% of it generic shrinkage.
- Build: `market_blend` columns (flat-weight fit on 2025-26 to minimize
  Brier) + error-weighted dynamic version (trailing model-vs-market error
  per pitcher/team). Compare vs ws1c on the showdown harness. Paper only.
- Caution carried over: blend weight fit on 2026 is development-adjacent
  (2026 = locked retrospective, not pristine) — freeze the weight, confirm
  on 2027 spring.

## 2. gbnet — GBM-in-PyTorch (ADOPT NARROWLY)

Source: mthorrell/gbnet (JOSS 2025). What it is: XGBoost/LightGBM as torch
Modules (autograd gradients), plus ordinal-regression and survival models.

Mapping to us:
- **Ordinal rung model**: our rung probs come from Poisson CDF. A GBM
  ordinal model (P(K≤k) thresholds) is the natural ladder-pricing upgrade —
  directly serves the paper ladder tracker. October candidate.
- **Survival hook model**: time-to-pull as survival (hazard backbone) beats
  our flat pull_prob and uncalibrated hook table — serves v4/TBF honestly.
- Cost flag: needs PyTorch (NOT in our stack; sklearn LightGBM is).
  Evaluate dependency weight before adopting; a sklearn-only ordinal
  fallback exists if torch is refused.
- Forecasting module: irrelevant (no time-series target here).

## 3. Sloan DRL (NBA valuation) — CONCEPTS ONLY, no machinery

Findings: TD win-prob + distributional outcomes (+23% margin RMSE),
neural Shapley attribution (127 synergies), context leverage (+40%
clutch variance), beats BPM/RAPM.
Mapping to us:
- Validates what we already do: distributional > point (Poisson + sims),
  outcome-based learning (CLV/edge framework).
- Synergy/interaction analogue: our reusable compatibility cross-features
  (pitch-mix × whiff profile etc.) — same idea, tabular form. Keep.
- Context leverage is a LIVE-betting concept (we are pregame-only by owner
  order) — park it with live betting, do not model it now.
- Full DRL agent: wrong tool (no sequential pregame decisions, tiny
  samples vs NBA possessions). Declined with reason.

## 4. Batter-K% aggregation architecture (owner direction — APPROVED SHAPE)

Owner: project K% per batter, aggregate — instead of whole-lineup means.
Resolution of the earlier debate:
- Pair-level memorization: still NO (2–3 PA/yr noise, Glicko lesson stands).
- Slot-vector matchup: YES — 9-vector of (batter rate, hand, slot) blended
  per-PA by log5 with pitcher rate (v4 core, tested), aggregated by
  Poisson-binomial over TBF (per the offseason doc's mixture math).
- Implementable WITHOUT retraining: the ensemble keeps emitting
  pitcher-level rates; slot blending happens downstream in live_assembly
  as a post-processing challenger (new columns, policy-gated, paper-first).
- Training mix when rebuilt: PA rows carrying pitcher-trailing +
  batter-trailing + context (Savant pitch rows exist: 674k 2026 with
  count/inning/score), logistic/GLMM loss, chrono splits, game-clustered
  folds. No exact pair IDs, ever.

## 5. Backtest framing (locked terminology)

- 2023–2024: development training (fit parameters, trailing estimators).
- 2025: validation/policy (architecture, calibrator, gates, thresholds).
- 2026: LOCKED retrospective benchmark (compare frozen challengers;
  prior exposure disclosed — never "pristine"/"never-seen").
- 2027: prospective external confirmation (final promotion evidence).
- Rolling-origin folds within 2023–2025; game-day clustered uncertainty.

## 6. Consolidated October plan (concise, precise)

1. Ship batch (family rule + flips + stake-sync + sims + diagram) — image.
2. Market-blend columns (flat, then error-weighted) vs ws1c on showdown.
3. Paper ladder tracker price-aware (panels compounding) + maker-vs-taker.
4. Slot-vector matchup challenger (post-processing, paper) + GLMM PA model.
5. Outs board v1 (TBF distribution) — paper all winter.
6. Novig key/stages; dawn verdict; frozen preseason cuts.
7. Consolidation + spring checklist (one deploy).
Gates: paper ROI before money; Brier+logloss+ECE+season-slices before board;
2027 spring before promotion. Kill list honored (Glicko, Kalshi overlay,
unpooled pairs, full-Kelly, live rungs, market making, uv-September).
