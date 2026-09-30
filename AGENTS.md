# Agent instructions (this repo)

**Master file for what to do next:** [`docs/EXECUTION_BACKLOG.md`](docs/EXECUTION_BACKLOG.md)

That backlog is the single holy work-state file (APPROVED / BLOCKED / waiting / parked / deferred, plus PAST / PRESENT / FORWARD / DEFERRED). Open it first; update the Session Snapshot every turn that changes work state. Do not create parallel backlogs.

| Role | Path |
| --- | --- |
| Work queue & approvals | `docs/EXECUTION_BACKLOG.md` |
| Domain language | `CONTEXT.md` (glossary + lifecycle + grains + paths) |
| Decisions | `docs/adr/` (template + accepted only with repo evidence) |
| **OpenCode / Cursor paste brief** | [`docs/reference/opencode_handoff.md`](docs/reference/opencode_handoff.md) -- coworker briefing 2026-09-11; pack #113 built; juiced #123 measured; Dashboard parked |
| Frozen-model Odds API replay spec | [`docs/reference/oddsapi_replay_architecture.md`](docs/reference/oddsapi_replay_architecture.md) -- not a queue; freeze/work/product |
| Technical research constraints | `docs/reference/research_assistant_instructions.md` (not a todo list) |
| Daily ops commands | `production/README.md`, `production/INDEX.md`, `production/RUNBOOK.md` |
| Dated evidence reports | `docs/reference/reports/` (point-in-time; not the live plan) |
| Paper / portfolio summary | `docs/paper/manuscript.md`, `docs/paper/resume-summary.md` |
| Skill provenance/catalog/evals | `docs/agent/skills-provenance.md`, `docs/agent/skills-catalog.md`, `docs/agent/skills-evaluations.md` |
| Ops contracts (Checkpoint A) | `docs/reference/reports/ops_contracts_2026-09-30.md` | Settlement + dashboard contracts, OPS-1/OPS-2 cards; remote deployment UNVERIFIED |

Also always-on: prefer Polars (`.cursor/rules/use-polars.mdc`); never `git push` (`.cursor/rules/git-push-policy.mdc`).

## Operating rules

- **Purpose:** personal MLB pitcher-strikeout prop desk. Frozen model + policy/market/execution work. Retrain path is closed; dashboard is parked.
- **Start here, in order:** `docs/EXECUTION_BACKLOG.md` -> `CONTEXT.md` -> `docs/reference/repo_canonical_map.md` -> this file.
- **Environment:** Python >=3.11, `.venv` active. `py -3.11 -m venv .venv` then `pip install -e ".[research,dev]"`. Raw Savant via `MLB_PROPS_SAVANT_DATA_DIR` / `MLB_PROPS_DATA_DIR` when not under `data/`.
- **Tests:** `python -m pytest` (full); pre-commit hook runs `tests/test_odds_ledger.py tests/test_real_bets.py tests/test_registries.py`. Prefer Polars; pandas only at plot/sklearn/LightGBM boundaries.
- **Lint:** no separate linter configured; keep ASCII-only in research scripts (cp1252 consoles), use `pl` patterns from `use-polars.mdc`.
- **Safe read-only commands:** `python production/odds/grade_odds_ledger.py --status --curve`, `python scripts/check_notebook_artifacts.py`, `python -m pytest -q`, `git status --short`, `git diff --stat`.
- **Protected production paths (need explicit owner order to change):** `production/ops/kpi_policy.json`, `production/ops/line_floor_policy.json`, `production/ops/live_krate_ensemble.json`, `production/odds/odds_board.py`, `production/odds/poll_odds.py`, `src/Python/market.py`, `src/Python/count_layer.py`, `src/Python/live_assembly.py`, `src/Python/odds_ledger.py`, model artifacts under `artifacts/models/`, Modal schedules/crons, ledger/pointers.
- **Generated/ignored (never commit, never "discover" by globbing):** `data/`, `artifacts/`, `.venv/`, `.hypothesis/`, `.pytest_cache/`.
- **Experiment outputs:** research writes under `research/offseason_2026/experiments/<card>/` with card + manifest + deviations; never overwrite a prior card. Cite n, Brier/skill, ECE, ROI/WR, CLV to a file or report key.
- **Doc conventions:** lowercase hyphenated markdown names; `docs/EXECUTION_BACKLOG.md` wins over all subordinate "next steps"; reports are dated and say SUPERSEDED when replaced; ADRs need repo evidence (else `PROPOSED-*.md`).
- **No-2026-tuning:** do not retune floors, veto, Kelly, WS1c, Poisson, or champion from 2026 paper or juiced 2026 slices. 2026 is locked retrospective / confirmatory only. Clean 2025-select / 2026-judge once, post-9/27, pre-registered.
- **Git:** `git status` before and after writes; never `git push` (give the owner the command); never commit unless asked; end every turn listing files created/modified.
- **Research != production:** research never edits live scorers, policy JSONs, schedules, or ledgers. Shadow columns beside live, zero live-path change, until gated promotion with revert path.
- **Skills:** project skills live in `.cursor/skills/<name>/SKILL.md`. Ignore `/helios-*` in this repo (user-global Helios skills, not for mlb-props). Skill docs: `docs/agent/`.
- **Where things live:** ADRs in `docs/adr/`; architecture in `docs/diagrams/` + `docs/reference/`; experiment cards in `research/offseason_2026/experiments/`; historical reports in `docs/reference/reports/`.

## Cheap-agent / Mac handoff (2026-09-02)

- Context excludes: `.cursorignore`, `.clineignore` (same rules), `.cursorindexingignore`
- Always-on rule: `.cursor/rules/agent-context.mdc` -> backlog + `docs/reference/repo_canonical_map.md`
- Historical CLV API research: `docs/reference/reports/historical_clv_odds_apis_2026-09-02.md`
- Live odds remain SharpAPI (`SHARPAPI_KEY`); do not confuse with historical backfill vendors
