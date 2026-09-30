# Phase 7 — regularized logistic PA challenger: plain-language report

Question: does learned context add signal beyond the promoted P3-log5 transparent baseline?

Answer: YES - and the value is in the context features, not the recalibration.

Ladder (fit on 2023 folds only; ONE 2024 E1/E2 evaluation; identical rows; B=2000 seed=0 date-clustered CIs):
- L1a (intercept-only recalibration): ~zero effect (-0.0001).
- L1b (alpha+beta recalibration): tiny (-0.0003 E1 fav 99%; -0.0002 E2 fav 89%, CI crosses zero).
- L2 (P3-logit + 6 pre-registered families): -0.00167 E1 / -0.00159 E2, both fav 100%; beats L1b in both (100%).
- L3 (L2 + trip dummies + PA index): BEST: -0.00256 E1 / -0.00214 E2, both fav 100%; calibration beta 0.95-1.01.
- Aggregation (4,711 exact official starts): L2-L0 MAE -0.027 (E1) / -0.018 (E2); L3-L0 MAE -0.0275 / -0.0212,
  all fav >=99.9%. L1b aggregation gain does NOT survive (CIs cross zero) - the context features carry the
  aggregated improvement.

Family evidence (2023 folds): F2 batter discipline dominates (ablation +0.0008 both folds, permutation +0.0029);
F3 pitcher discipline modest (+0.001 perm); F1 platoon small (+0.0004); F4 history + F5 park small; F6 rest ~zero.
Fold coefficient sign agreement 19/20. C selected: L2=0.03, L3=0.01 (2023 folds only).

Month slices: L3 beats L0 in 6/7 months (March slightly worse, n=2,224) - stable, not slice-driven.

Verdicts: LOGISTIC RE-CALIBRATION ADDS VALUE: marginal only. CONTEXT FEATURES ADD VALUE BEYOND P3: YES.
TRAINED PA SIGNAL SURVIVES AGGREGATION: YES (L2/L3). L3 promoted as development challenger; no production or
betting claim; 2025 validation is the next chronology-safe gate.
