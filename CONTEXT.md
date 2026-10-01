# MLB-Props Context

Shared domain language for agents. Read this before any model, experiment, or architecture work. Numbers below are pointers, not claims -- cite `docs/reference/golden_metrics.md` and its JSON sources for current values.

## Glossary

| Term | Meaning |
|---|---|
| PA | Plate appearance. Binary PA-level K target is conditional on the PA occurring. |
| AB | At-bat (PA minus walks, HBP, sacrifices, interference). |
| BF / TBF | Batters faced. Projected TBF is a frozen Ridge prediction; actual same-game TBF is label/oracle only, never a feature. |
| K / k-rate | Strikeouts / `K / PA` at game level for qualifying starters. Frozen LightGBM ensemble predicts pregame k-rate. |
| xK / expected_K | `k_rate_hat * tbf_hat` on projected TBF only. |
| Count layer | Poisson (live) mapping of expected_K to `P(K >= line)` at lines 2.5-9.5. |
| WS1c | Per-line Platt calibrator, live since 2026-09-10. Isotonic is retired/lineage only. |
| Frozen champion | Live stack: ensemble `0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58` + Ridge TBF + Poisson + WS1c. Policy KING_AUG2026 / 2025-lock champion (floor 0.12, cap 0.24, under-lean +0.04, DK+FD-only). |
| Challenger | Any candidate judged against the frozen champion under `champion_challenger_protocol.md` + `experiment_sop.md`. Never promoted without gates + sign-off. |
| Edge | Juiced two-way multiplicative de-vig edge (`src/Python/market.py`). Live floors speak juiced. |
| CLV | Close-minus-bet on devigged pairs only (`clv_pp`). Headline is same-book (fillable); consensus is secondary. |
| Ledger | `artifacts/odds_log/ledger.parquet`. Canonical money = `dedupe_ledger_props` (one slip per signal at best edge). |
| Board | `production/odds/odds_board.py` output (`recommendations.parquet`). Open polling is parity-locked via `--from-recommendations`. |
| Open / close / morning | Friend open (commence -12h/-6h, ends 2026-07-10) / paid morning (commence -5h request, vendor ts governs) / paid close (commence -5min request). Live = SharpAPI; historical lake = Odds API. Never mix. |
| PA overhaul | 2026 offseason program rebuilding the K signal at PA grain: PA-1A (batter tendency) -> P3-log5 promoted baseline -> L3 ridge logistic = frozen development PA baseline -> tree challenger KILLED (ties L3; stop rule applied, 2026-09-30). Verified: full feature lineage in `docs/reference/reports/phase8_5_truth_sync_2026-09-30.md`. Next frontier: count-distribution experiment (Poisson-binomial vs Poisson), then 2025 validation lanes A-D. |
| 2023-24 / 2025 / 2026 locked / 2027 | Train seasons (2023-24 only) / historical benchmark, never pristine / locked retrospective, never tuned / future free-forward set (SharpAPI + Kalshi keyless + Novig). |

## Lifecycle

```
Statcast L1 games -> L2 rolling -> L3 training -> k-rate ensemble x TBF ridge
-> Poisson count layer -> WS1c -> policy filter -> size (flat $50u; 1/16-Kelly anchor)
-> SharpAPI board -> poll -> ledger -> grade -> drift
```

Research lane (frozen inference, never a re-spin): `score_historical_range.py` -> `join_universe.py` -> `universe_panel_live.parquet` -> cells/gates -> `juiced_replay_ledger.py`.

## Grains

- **Pitch**: raw Savant rows. Never a model grain.
- **PA**: binary K target work (PA overhaul). Attribution: K credited to the pitcher who threw the third-strike pitch; PA charged to the completing pitcher; split PAs flagged (`split_pa_flag`).
- **Game/start**: canonical production grain. Qualifying starter = first pitcher with PA >= 9 (postgame cohort filter; ~3.5% excluded). Pregame role labels still open for pristine v1.
- **Slate/ticket**: board -> ledger rows at (start, line, side, book). One slip per signal after dedupe.

## Canonical packages and paths

- `src/Python/` -- pipeline + model assembly (Polars-first): `statcast.py`, `pitcher_features.py`, `batter_features.py`, `pitcher_rolling.py`, `batter_rolling.py`, `ballpark.py`, `bullpen.py`, `tbf.py`, `count_layer.py`, `features.py` (safety gate), `market.py` (devig/edge/Kelly/CLV), `live_assembly.py`, `odds_ledger.py`, `daily_lineups.py`, `pipeline/games.py`, `pipeline/rolling.py`, `pipeline/training.py`.
- `production/` -- live ops: `ops/run_daily.py`, `ops/live_krate_ensemble.json`, `ops/kpi_policy.json`, `odds/odds_board.py`, `odds/poll_odds.py`, `odds/grade_odds_ledger.py`, `INDEX.md`, `RUNBOOK.md`, `README.md`.
- `models/` -- trainers: `models/Strikeout-Model/train.py`, `models/TBF-Model/train.py`.
- `research/offseason_2026/` -- bounded offseason work (datasets, experiments, specs). No new top-level folders.
- `docs/` -- `EXECUTION_BACKLOG.md` (master queue, wins all fights), `reference/` (living standards), `paper/manuscript.md`, `adr/` (decisions), `agent/` (skill provenance/catalog/evaluations), `diagrams/`, `archive/` (history only).
- Generated/ignored: `data/processed/`, `artifacts/`, `.venv/`. Never commit; never glob parquet to "discover" the repo.

## PA-overhaul status (2026-09-29 record)

PA-1A supports one narrow claim: shrunk batter tendency improved PA logloss/Brier over pitcher-only M1 in both 2024 chrono blocks (E1/E2), game-date-clustered CIs exclude zero. M1 as constructed is weaker than the league constant in E1 (cold-start problem). Not tested: aggregation, pregame xK, count distributions, calibrators, frozen-stack comparison, odds/policy. Open: PA-1B-O reconciliation spec, pitcher-prior card, frozen-comparator replay contract, PA-1B-P projected-lineup lane. Source: `docs/reference/reports/pa_overhaul_phase4_5_record_2026-09-29.md`.

## Links

- Queue: `docs/EXECUTION_BACKLOG.md`
- Ops: `production/README.md`, `production/INDEX.md`, `production/RUNBOOK.md`
- Standards: `docs/reference/repo_canonical_map.md`, `docs/reference/golden_metrics.md`, `docs/reference/model-card.md`
- Process: `docs/reference/experiment_sop.md`, `docs/reference/champion_challenger_protocol.md`, `docs/reference/research_assistant_instructions.md`, `docs/reference/market_clv_gates.md`
- Replay: `docs/reference/oddsapi_replay_architecture.md`, `docs/reference/opencode_handoff.md`
- Overhaul: `docs/reference/offseason_overhaul_plan_2026-09-28.md`, `docs/reference/offseason_2026_choice_log.md`
- Ops contracts: `docs/reference/reports/ops_contracts_2026-09-30.md` (settlement + dashboard contracts, OPS-1/OPS-2 cards; Checkpoint A)
