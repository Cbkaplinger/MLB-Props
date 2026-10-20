# Repository hygiene automation design — 2026-10-16 (Chat 3, DESIGN ONLY)

Local-only, non-destructive hygiene checks consolidating the audit scripts this
program has already built (all currently one-off scripts in the Chat 3 session
temp dir). **Nothing implemented yet; this is the implementation spec.** Base
`origin/main` @ `1927c8c…`.

## Proposed tool

`scripts/repo_hygiene_check.py` — single entry point, stdlib-only, read-only,
runnable locally; emits `--json` and human output; every check has an advisory
default and an explicit `--enforce` (or CI-only) classification. No writes
outside stdout/temp.

## Checks (existing audit code, re-homed)

| Check | Provenance (already run) | Advisory/enforcement | False-positive risks | Owner gate |
|---|---|---|---|---|
| exact-duplicate blobs | 2026-10-15/16 scans (7 groups found) | advisory | intentional mirrors (`.cursorignore`/`.clineignore`), fixture families → allowlist file | add allowlist entries only via reviewed PR |
| near-duplicate text (shingle-Jaccard) | duplication audit (6 prereg pairs found) | advisory | intentional fixture families; boilerplate frontmatter → threshold + allowlist | yes (threshold changes) |
| broken relative links (md) | 2 full scans, 0 broken | **enforcement-ready** (CI candidate) | links into generated dirs that exist only locally → resolve against tracked tree only | CI inclusion = owner |
| dead notebook references | 7 truly-dead found | advisory | bare-name refs that resolve unrooted → basename-resolve first | for the RUNBOOK-type fixes |
| oversized tracked files | inventory (max 212 KB — healthy) | advisory with threshold (e.g. >1 MB) | legitimate PDFs/parquets → threshold + allowlist | threshold change |
| ignored-but-tracked files | 1 intentional negation found | advisory + allowlist | deliberate `!` negations → allowlist | allowlist edits |
| orphan worktrees / branch status | this program's worktree list reviews | advisory (parse `git worktree list` + ahead/behind) | parked-but-owned branches (e.g. `paextwt`) → report-only, never auto-remove | removal = owner (standing rule) |
| secrets patterns | 0 credential hits | **enforcement-ready** (secret-assignment/bearer regexes; report file:line, never values) | docstring/examples containing fake keys → allowlist | CI inclusion = owner |
| dependency/import mismatch | 8 undeclared found | advisory until S-B lands → then enforcement against declared set | dynamic imports, `__main__`-only tooling | pyproject edits = owner |
| default-CI collection gaps | 5 excluded files enumerated | advisory (re-computed each run) | new suites added intentionally outside `tests/` → expected-list | expected-list edits reviewed |
| untracked generated outputs | notebook-artifact census | advisory (git status parse vs expected-ignored map) | local scratch files → expected-map | expected-map edits |
| results-index staleness | already enforced via `tests/test_results_index.py --check` (PR #8) | enforcement (exists) | — | — |

## Design rules

1. Every check is **pure/read-only** against the working tree + git metadata;
   no network, no installs.
2. Allowlists live in one committed file (`scripts/hygiene_allowlist.json`)
   with reasons — the audit trail for every accepted exception.
3. Advisory vs enforcement is per-check, explicit, and changes only via
   reviewed PR. Enforcement candidates today: broken links, secrets patterns,
   dependency declarations (post-S-B), results-index staleness (already done).
4. Runtime target: < 30 s locally (current script corpus runs in ~10 s).
5. CI integration: NOT proposed now (per standing constraint); when approved,
   enforcement-subset runs as a separate step after the main suite.

## Implementation slice (when approved)

One PR: `scripts/repo_hygiene_check.py` + `hygiene_allowlist.json` +
`tests/test_repo_hygiene_check.py` (self-test: runs the tool on the repo,
verifies JSON shape, verifies allowlisted items don't fire). No workflow edit.
Rollback: revert.

## Spec compliance

- **Base SHA (exact):** `1927c8c8c8a4ae72af5be848dea865ce59bd5866` (origin/main).
  **Head at authoring:** branch tip `543fb50036220934948b4fd81ddfe88d4b927d7f`;
  committed as its own increment on top.
- **Inspected paths:** prior program audit artifacts (exact/near-dup scans,
  notebook-artifact census, entry-point inventory, dependency audit, CI
  coverage map — all committed on this branch); `git worktree list` output;
  `.gitignore`/`.cursorignore`/`.clineignore`.
- **Owner:** repo owner (Cbkaplinger) — enforcement classification, allowlist
  entries, thresholds, and any CI inclusion are owner decisions via reviewed PR.
- **Validation command (after implementation, not now — nothing is implemented):**
  `python scripts/repo_hygiene_check.py --json` must exit 0 with advisory-only
  output; `python -m pytest tests/test_repo_hygiene_check.py -q` green. Before
  implementation, the design is validated by review only.
- **Confidence:** HIGH on check provenance (each row cites an already-executed
  audit); MEDIUM on runtime target (~10 s observed for the one-off corpus,
  <30 s budgeted).
- **Risk:** Low — read-only tool, no CI change, no writes outside stdout/temp;
  main failure mode is false positives eroding trust (mitigated by allowlist
  with reasons).
- **Smallest follow-up PR:** the implementation slice above, advisory-only
  defaults; enforcement classification stays unchanged until a separate owner
  decision.
