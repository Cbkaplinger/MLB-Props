# PA-1B-O oracle aggregation — plain-language report (Phase 6)

Question: does PA-level probability improvement survive summing PAs into start-level expected K?

Answer: YES — twice over. On 4,711 official-starter starts (100% exact BF reconciliation, zero split PAs,
actual K = sum of included is_k rows verified):

1. Batter signal survives aggregation (Outcome A): M2 vs M1 MAE -0.0372 (E1, CI [-0.0462,-0.0282], 100% fav)
   and -0.0506 (E2, 100% fav); RMSE consistent; game_pk-clustered sensitivity agrees.
2. Cold-start repair survives aggregation (Outcome C): P3 log5 vs original M2 MAE -0.1443 (E1) and -0.0419 (E2),
   both 100% fav; P3 is the best arm in every block (E1 MAE 1.735 vs M0 1.880; E2 1.706 vs 1.856).
3. M2 vs M0 mirrors PA-1A: inconclusive in E1, clear in E2.
4. Frozen comparator: DESCRIPTIVE_TRAIN_OVERLAP ONLY for 2024 (members fit through 2024-06-08; weights selected
   2026-08-21; WS1c fit_cutoff 2026-09-03; no 2024 OOF predictions exist) - STOPPED for primary; the clean
   frozen comparison is deferred to 2025 validation.

Residual diagnostics (PA-level, M2): ICC by start 0.020, pitcher 0.012, batter 0.018, team 0.001, month 0.0002,
trip 0.002 - small within-cluster correlation; no dominant hidden cluster effect. Mean experiment only: no
Poisson-binomial, no frozen TBF, no projected lineups, no calibration, no betting.
