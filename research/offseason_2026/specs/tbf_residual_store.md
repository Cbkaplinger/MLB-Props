# Out-of-fold TBF residual store (experiment-ready spec, no code — audit §AE)

Purpose: feed distribution arm D3 (TBF-mixture PB) without touching the frozen
Ridge point model. No in-sample residuals. No 2026-selected buckets.

Store (built later, workspace `datasets/`): `tbf_oof_residuals.parquet` keyed by
`(game_date, pitcher, game_pk)` with columns: `projected_tbf` (frozen Ridge),
`actual_pa`, `residual`, bucket keys (role, workload band, month, lineup-strength
band — pre-registered from ≤2025 or §AD OOF, never 2026 peek), `fit_cutoff`
(model-fit max date `< game_date`), `artifact_hash`.

Build rule: residual for date d uses a Ridge fit on dates `< d` (OOF); expanding
or rolling-origin per §AD Option A. Residuals never feed back into k-rate or TBF
fits. Mixer consumes read-only; preserves ridge mean or declares shift.

Inputs that exist read-only: `projection_log/graded.parquet` residuals,
`historical_scores_2025_2026.parquet` panel, `hook_pull_table` + EB rates,
TBF feature columns (workload P5/P10/P20, rest/debut, context, thin bullpen).
Unbuilt: this versioned store + mixer API (spec only in this phase).

Audit on build: residual coverage by bucket + PIT of the TBF law + bucket-n
floors (G4 minima apply to bucket claims).
