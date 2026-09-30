# Pitcher-prior experiment — plain-language report (Phase 6)

Question: can the noisy season-reset pitcher input be replaced by a better pregame prior?

Answer: YES. P3 = pooled empirical-Bayes (K_prior_season + K_curr + 100*lg) / (PA_prior_season + PA_curr + 100),
strength m=100 selected on 2023 folds ONLY (never on 2024), is the best arm in both registered blocks, in both
pitcher-only and log5-with-batter forms, and is promoted as the transparent development baseline.

Headline (E1/E2 = 2024 chronological blocks, n=55,815/50,252):
- Pitcher-only logloss: P3 beats P0 by -0.00742 (E1, 100% of bootstrap replicates) and -0.00208 (E2, 100%).
- Log5 form beats the ORIGINAL M2 by -0.00736 (E1) and -0.00205 (E2), both CIs exclude zero, 100% fav.
- Calibration slope improves from 0.27/0.55 (P0) to ~0.92 both blocks; ECE roughly halves.
- P1 (prior-season only) fixes E1 but not E2; P2 (current EB m=100) fixes E2 strongly; P3 combines both.

Gate A corrections logged in deviations.md: zero split PAs ever entered the PA table (Phase 5 measurement artifact);
all modeled pitchers are official starters; 4,711/4,711 starts reconcile exactly to official BF.
Frozen comparator: STOPPED for 2024 primary (train/selection overlap; see ../pa1b_oracle_xk/frozen_comparator_validity.json).
