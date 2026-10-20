# Data-contract and schema inventory — 2026-10-16 (Chat 3, report-first)

Scope: the Parquet/JSON/manifest schemas flowing between pipeline stages, from
literal `write_parquet`/`read_parquet` pairs (21 targets, 31 sources in tracked
code) + known manifest conventions. Base `origin/main` @ `1927c8c…`. Confidence:
HIGH on producer/consumer edges, MEDIUM on field-level claims (schemas not
dumped — data lives in ignored dirs/lake; this is an edge-level inventory, per
assignment). **Nothing modified.**

## Core contracts (producer → consumers, evidence-verified)

| Contract | Producer (tracked) | Consumers (tracked) | Key / grain | Validation coverage | Storage | Breakage risk |
|---|---|---|---|---|---|---|
| `pa_table.parquet` | `p1_harness/scripts/build_pa_table.py` | `build_features.py`, `fit_models.py`, (test) | PA grain; (game_pk, at_bat_number, pitcher) | `test_feature_contract` (harness) + sha manifest + EXPECTED_ARTIFACTS guards | local artifacts (ignored) | **Medium — naming drift** (see finding 1) |
| `features.parquet` | `build_features.py` | `fit_models.py`, harness test | per-PA features | same harness guards | same | Low (guarded) |
| `eval_predictions.parquet` / `dev_predictions.parquet` | `fit_models.py` | BF cohort enumeration, harness test | per-PA predictions | eval-identity hash (harness) | artifacts | Low |
| `pa_table_2023_2024.parquet` | (lake-generated predecessor; no tracked producer) | `logistic_pa/bundle/build_bundle.py`, `run_phase7.py` | PA grain, 2-season slice | card/hashes.json | lake/artifacts | **Medium — generation code not tracked** (see finding 1) |
| `per_pa.parquet` | `run_pa1a.py` | `run_pa1b_o.py`, `run_pitcher_prior.py` | PA rows + attribution | experiment manifest | experiment dir | Low |
| `ledger.parquet` (artifacts/odds_log) | ledger append path (`odds_ledger.py` — code writes via API, not literal path) | market_research analyses, notebooks | (start, line, side, book) ticket grain; dedupe key | pre-commit trio (`test_odds_ledger`) | artifacts (ignored) | Low (strongest-tested contract in repo) |
| `bf_pmfs.parquet` / `kc_pmfs.parquet` | `tests/test_i3_runner.py` (synthetic) | i3 runner internals | BF/count PMFs | test fixtures | tmp | Low |
| `book_lines_pitcher.parquet`, `graded.parquet` | **none tracked (lake/env-sourced)** | market_research harnesses | book/line grain | none in-tree | lake | **Medium — undocumented import** (finding 2) |
| `cohort_rows_metadata.parquet` | `run_bf_2026_cohort_enumeration.py` | (receipt only) | cohort rows | manifest | lake | Low |
| `daily_lineups_*.parquet` | production builder (path built dynamically) | pregame capture adapter | (game_pk, doubleheader, batter, slot) | adapter tests (6 green) | data/processed (ignored) | Low |

### Manifest contracts (JSON)

| Contract | Shape owner | Convention |
|---|---|---|
| `run_manifest.json` | research runs (B1 closeout pattern) | config/input/artifact hashes, timestamps, schema version — write-once |
| `metrics.json` / `bootstrap.json` | experiment cards | metric payload + `card_sha256` chain |
| `hashes.json` | experiments | `card_sha256` + inputs[] (path, sha256) |
| `results_index.{md,csv}` (PR #8) | generator | CI-staleness-guarded |

## Findings

1. **Naming drift across generations:** `pa_table.parquet` (p1-harness, tracked
   producer) vs `pa_table_2023_2024.parquet` (consumed by the L3/logistic_pa
   lane, producer not tracked — generated during a frozen run). Same logical
   dataset, two names, one without tracked generation code. Action: owner/
   Chat 1 confirm the second is lake-immutable evidence; then annotate in the
   results index — do NOT rename (frozen lineage).
2. **Undocumented lake-imported contracts:** `graded.parquet`,
   `book_lines_pitcher.parquet` (and similar market_research inputs) are
   consumed by tracked code but produced outside the tree. They work because
   local env state exists — the classic hidden-assumption class. Action: a
   one-line provenance note per file in the consuming script's header
   (producer: lake path / generating run), owner-approved.
3. **Date/time + null conventions:** uniformly game_date-based partitioning and
   explicit null/missing semantics in the harness lane (validated); the
   market_research inputs carry no in-tree validation — the observability
   slices (O-1..O-4) cover the operational side; a contract-validation slice
   for market_research inputs would be its own owner-gated PR.
4. **Versioning:** manifests carry schema/version only in the newest convention
   (run_manifest schema_version); older experiment packets rely on card
   timestamps + hashes — acceptable for frozen evidence, do not retrofit.

## Smallest safe follow-up

Finding-2 provenance notes (3-5 header lines, owner-approved) — everything else
is annotation via the results index once PR #8 lands.

## Spec compliance

- **Base SHA (exact):** `1927c8c8c8a4ae72af5be848dea865ce59bd5866` (origin/main).
  **Head at authoring:** branch tip `543fb50036220934948b4fd81ddfe88d4b927d7f`;
  committed as its own increment on top.
- **Inspected paths:** all tracked `.py` for `write_parquet`/`read_parquet` pairs
  (21 targets, 31 sources); manifest conventions from research experiment cards;
  machine-readable companion `data_contract_edges_2026-10-16.csv` (13 contract
  rows mirroring the core-contracts table above).
- **Owner:** repo owner (Cbkaplinger) — provenance-note edits touch script
  headers, several in protected paths; owner-approved PR only.
- **Validation command (re-run the parquet-edge scan):**
  `git grep -n "read_parquet\|write_parquet" -- "*.py"` and diff the
  producer/consumer columns against the CSV.
- **Confidence:** HIGH on producer/consumer edges; MEDIUM on field-level claims
  (schemas not dumped — data lives in ignored dirs/lake; edge-level inventory
  per assignment).
- **Risk:** Medium undocumented-import risk (finding 2) — market_research
  depends on lake state that has no in-tree producer; breakage would be
  environment-shaped and late.
- **Smallest follow-up PR:** finding-2 provenance headers (3-5 comment lines in
  consuming scripts' headers, naming lake path + generating run).
