# PR workflow — how this repository makes, documents, reviews, and merges pull requests

Operating standard for all agent windows and the owner. Complements
[`AGENTS.md`](../../AGENTS.md) (entry point), the canonical role cards under
`docs/roles/` (precedence in `docs/roles/README.md`), and
[`repo_canonical_map.md`](repo_canonical_map.md) (what surfaces exist).

## 1. Who does what

| Role | Authority |
| --- | --- |
| Any chat window | May create branches/PRs **from its own isolated worktree only**, in its declared scope |
| Builder (Chat 1) | Implements, pushes, obtains CI; performs authorized merges/integration |
| Reviewer (Chat 2) | Trailing reviewer/fixer: independent review at the exact published SHA; bounded repairs on claimed paths per docs/roles/chat2-reviewer.md |
| Repo health (Chat 3) | Documentation, inventories, PR hygiene; docs-only PRs (see docs/roles/chat3-cleaner.md) |
| Owner | Approves scope, decisions, and any merge/deletion |

**Never** edit another chat's worktree or branch. Never merge, close another
chat's PR, or delete a branch without explicit authorization for that action.

## 2. Making a PR

1. Branch from **fetched `origin/main`** (or the relevant base) in your worktree:
   `git worktree add <path> -b <lane>/<topic>-<date> origin/main`
2. Lane prefixes observed in this repo: `maintenance/`, `research/`,
   `review/`, `chat2/`, `agent/`, `docs/`. One topic per branch.
3. Commit **completed, understandable units** (see §3). No placeholder commits.
4. Push with `-u`; open the PR with a body meeting §4.
5. Open as **draft** when review depends on outstanding work; mark ready when
   the packet is complete and CI is green on the exact head.

## 3. Commit standards

- Conventional style matching repo history: `type(scope): summary` —
  `docs(maintenance): ...`, `feat(review): ...`, `research(pa): ...`,
  `fix(...)`; body carries the details, including hashes/SHAs where relevant.
- ASCII-safe messages (cp1252 consoles).
- One logical change per commit; tests alongside the change they cover.
- Never commit: `data/`, `artifacts/`, `.venv/`, secrets, keys, generated
  parquet/pickles, machine-specific paths. See `AGENTS.md` ignore rules.

## 4. PR body template (required sections)

```text
Repository / origin URL:
Worktree / branch:
Task base SHA:
Current HEAD:
Remote branch SHA:
Working-tree status:
PR / CI run and tested SHA:
Config + input hashes, when applicable:

# <Title>
## Purpose and scope        — why; what lane assigned it
## Behavior changes         — files/classes of change; production touched?
## Tests and tested SHA     — exact test commands + results at the exact head
## Measured results vs unproven claims — evidence separated from narrative
## Artifact locations and known limitations
## Production behavior?     — yes/no; research tooling vs live path
```

A PR whose body cannot state its tested SHA and CI run is not mergeable.

## 5. CI — what green means

Workflow: `.github/workflows/ci.yml` (job `test-and-validate`):
1. Clean checkout + Python 3.11.
2. Installs `.[dev]` plus the live-stack extras (scipy, joblib, scikit-learn,
   lightgbm, statsmodels).
3. `py_compile` syntax check over every `production/**/*.py` (no imports run).
4. **Full pytest suite** (`pytest -q -rs`), including the `integration` marker
   lane's synthetic-only default; artifact-pinned tests skip with named reasons
   when private-lake artifacts are absent, and fail loudly in every lane if
   hashes mismatch.
5. JUnit report uploaded as an artifact on every run.

**Green CI on the exact head is necessary, never sufficient.** It does not
substitute for the independent review verdict or owner authorization.

## 6. Reviewing

- The reviewer **fetches and pins the exact PR head SHA** before reviewing;
  a pushed change re-opens review of the delta only.
- Review verdicts are `READY` (exact SHA) or **one concrete blocker**.
- Builder self-check is never independent READY.
- Reopen passed checks only when the delta affects them.

## 7. Merge rules

Merge only when ALL hold:
1. Scope authorized by the owner (or standing lane authority).
2. Exact-head CI green (verify the run on the live head, not an older report).
3. Independent review verdict recorded (READY or accepted-as-docs).
4. No unresolved review threads.
5. Merge order respects the current integration plan (single `main`, no
   force-push, no history rewrite).

Merge mechanics: normal merge per repo precedent (merge commits; e.g. PR #1).
After merging: update local `origin/main`, **record the resulting main SHA** in
the closeout/identity record, and verify dependent PRs still contain the new
main or plan their refresh/rebase.

## 8. Comments and closures

- PR comments record decisions, scope notes, and closure rationale — one
  authoritative comment per decision, not threads of status chatter.
- Closing as superseded: state the canonical replacement, that this is a
  selection (not a file-for-file containment claim), and that the branch + unique
  commits are retained for provenance. Preserve the branch until the closure is
  recorded **and** its commits are confirmed reachable elsewhere or explicitly
  abandoned by the owner.
- Conflicting status reports: inspect the live PR state first; post at most one
  reconciliation comment.

## 9. Status reporting

Every status report delivers one of: **a deliverable, a decision, or a concrete
blocker** — with identity block + CI run. Holding notices without new evidence
are noise; say "no change since <SHA/run>" and stop.

## 10. Current optimization notes (CI)

Recorded 2026-10-16; changes to `.github/workflows/` require owner
authorization before landing:

| Proposal | Expected effect | Risk |
| --- | --- | --- |
| `setup-python` with `cache: pip` (+ lockfile or hashed extras) | Cuts the ~40s dependency install from every run | Low |
| `concurrency` group per ref with `cancel-in-progress` | Stops redundant runs on rapid pushes | Low |
| `python -m compileall -q production` instead of per-file `py_compile` | One interpreter instead of ~160 spawns | Low |
| Job-level `timeout-minutes` | Bounds a hung run | Low |
| `pytest-xdist -n auto` (optional extra) | Parallelizes the suite; needs a test-isolation check first | Medium — adopt only after verifying no shared-state tests |
| Path-filtered docs-only fast lane | Skips heavy steps for docs-only diffs | Medium — must still run docs-linked tests (e.g. results-index staleness); defer until the cheap wins land |

Cheap wins (cache, concurrency, compileall, timeout) preserve full test
coverage exactly; the medium items are opt-in and gated on verification.
