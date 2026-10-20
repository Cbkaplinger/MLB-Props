# Entrypoint and operations audit — 2026-10-16 (Chat 3, report-first)

Scope/method: inventory of all **294 `__main__` entry points** by family,
scheduled/deployment surfaces, and external-service touchpoints at
`origin/main` @ `1927c8c…`; ownership/idempotence/write-path spot checks on the
daily chain. Confidence: HIGH on inventory, MEDIUM on behavioral claims (no
execution). Report-only.

## Entry-point inventory (294, by family)

| Family | Entry points | Nature | Ownership |
|---|---|---|---|
| `production/**` | 149 | daily chain (ingest → features → serve → close → settle), watchers, backfills, builders, market research | Chat 1 + owner (protected paths) |
| `models/**` | 68 | trainers + research ablations/tuners (frozen-era) | Chat 1 |
| `research/offseason_2026/**` | 43 | one-shot experiment runners (frozen evidence pattern) | Chat 1 / Chat 2 review |
| `scripts/**` | 20 | repo tooling (prune, checks, generators) | Chat 3 |
| `src/**`, `.agents`, `docs`, `playground` | 14 | misc/paper/skill | per path |

## Scheduled / deployment surfaces

| Surface | Mechanism | Evidence | Notes |
|---|---|---|---|
| Morning/day chain | `run_morning_workflow.ps1`, `run_daily_operator_flow.ps1` | `production/ops/` | operator flow has the Issue #5 defect (dead notebook step, conditional) |
| Settle/eod | `run_end_of_day_settle.ps1` | `production/ops/` | hosts grading + drift steps |
| Cloud cadence | `production/cloud/modal_app.py` (imports `modal` — **undeclared dep**, see dependency audit) | static scan | scheduled jobs per canonical map (Modal UTC-vs-EDT gap G-OPS-1 recorded in pipeline registry) |
| CI | `.github/workflows/ci.yml` | single workflow | audited separately |
| Notifications | ntfy plumbing (canonical map) | code refs | no issues surfaced this pass |

## External-service touchpoints (documented + code-verified)

SharpAPI (live odds, `SHARPAPI_KEY` env — no hardcoded value found in the
secret scan), The Odds API (historical lake pulls via `requests` — undeclared
dep), Kalshi keyless endpoints, RotoGrinders lineup capture (production
builder), Baseball Savant (pybaseball/raw CSVs). All key material is
environment-sourced; the secrets audit (separate report) found **zero
committed credentials**.

## Findings

| # | Finding | Evidence | Risk | Follow-up |
|---|---|---|---|---|
| 1 | **Undocumented entry points**: many of the 149 production scripts appear in no README/INDEX section (e.g. `build_ab_board_diff.py`, `build_book_quality_scorecard.py`) | cross-ref vs `production/INDEX.md` coverage | Low-Med | INDEX completeness pass (bounded slice; Chat 3 with owner sign-off) |
| 2 | **Dead/duplicate operational paths**: `prune_artifacts.py` dual implementation (canonical map points at `scripts/` copy); `odds_board.py` naming collision (distinct tools, verified) | earlier diff report | Medium | T7 owner ruling |
| 3 | **Missing idempotence signals**: write paths in daily-chain scripts are write-once/run-dir based where inspected (projections, ledgers use append-with-dedupe); watcher scripts carry sweep guards per pipeline registry | spot checks + registry | Info | no action; registry gaps G-OPS-1/G-OBS-1 already tracked |
| 4 | **Unsafe write paths**: none found in the daily chain spot checks (no raw `Remove-Item -Recurse -Force` on variable paths; destructive ops live behind the artifact-prune utility's dry-run default) | pattern scan | Low | keep the dry-run-default convention |
| 5 | **Dead scripts**: only 1 true zero-reference orphan file repo-wide (dead-code audit); no dead `.ps1` found | orphan census | Low | single-file owner decision |
| 6 | **Operator flow executes a deleted notebook** (`results_gate_policy`) — conditional step | Issue #5 | Medium | T8, authorization pending |

## Smallest safe follow-ups

INDEX completeness slice (finding 1) is the highest-value low-risk ops-docs
improvement; everything else is already ticketed (T7/T8) or informational.
