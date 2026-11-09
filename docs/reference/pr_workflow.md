# PR workflow — how this repository makes, documents, reviews, and merges pull requests

Operating standard for all agent windows and the owner. Complements
[`AGENTS.md`](../../AGENTS.md) (entry point), the canonical role cards under
`docs/roles/` (precedence in `docs/roles/README.md`), and
[`repo_canonical_map.md`](repo_canonical_map.md) (what surfaces exist).

## 1. Who does what

Roles and their authority are defined once in the canonical role cards —
[architect](../roles/architect.md),
[builder / Chat 1](../roles/chat1-builder.md),
[reviewer / Chat 2](../roles/chat2-reviewer.md),
[documentation maintainer / Chat 3](../roles/chat3-cleaner.md) — under the
precedence rule in [`docs/roles/README.md`](../roles/README.md) (roles +
`docs/NEXT.md` override older agent instructions). Every chat works from its
own isolated worktree in its declared scope; the owner approves scope,
decisions, and any merge/deletion.

**Never** edit another chat's worktree or branch. Never merge, close another
chat's PR, or delete a branch without explicit authorization for that action.

**Repair ownership.** Repairs to another chat's implementation require an
explicit path-ownership transfer recorded on the PR for the named paths, and
the repair is reviewed by a non-author. A reviewer/fixer assignment does not
imply standing permission to edit the builder's implementation.

## 2. Making a PR

1. Start from **fetched `origin/main`** (or the relevant base) in your
   existing role workspace. Create a topic branch:
   `git checkout -b <lane>/<topic>-<date> origin/main`
2. Lane prefixes observed in this repo: `maintenance/`, `research/`,
   `review/`, `chat2/`, `agent/`, `docs/`. One topic per branch.
3. Commit **completed, understandable units** (see §3). No placeholder commits.
4. Push with `-u`; open the PR with a body meeting §4.
5. Open as **draft** when review depends on outstanding work; mark ready when
   the packet is complete and CI is green on the exact head.
6. **Verify publication before reporting READY FOR REVIEW:** freshly fetch
   origin and confirm local HEAD == remote branch SHA == PR head SHA; confirm
   the repository, worktree, owned branch, intended PR base branch, and staged
   scope; push explicitly to that branch. Work that failed to publish is a
   blocker, not a delivered checkpoint; unpushed work is labeled LOCAL ONLY.

The same identity checkpoint applies at four handoffs: before creating a
topic branch, before publishing, before review, and before merge. Record the
base SHA, local HEAD, remote/PR head, ahead/behind counts against
`origin/main`, working-tree status, claimed paths, and tested SHA. A mismatch
is `LOCAL ONLY` or `STALE`, never READY; refresh the branch and rerun affected
checks before handing it forward.

### Worktree lifecycle

A worktree belongs to a role or an explicitly named long-running purpose,
not to each PR, commit, or review checkpoint.

Default active footprint:
- one primary checkout;
- one builder worktree;
- one reviewer worktree;
- one temporary maintainer worktree only while an assigned maintenance
  task is active.

Existing HOLD/evidence worktrees are preserved exceptions, not reusable
workspace capacity and not automatically safe to remove.

Before creating a worktree:
1. Inspect the existing worktree registry once.
2. Reuse the role's current workspace if safe.
3. If reuse is blocked, identify the exact blocker and request a scoped
   exception naming owner, purpose, path, and retirement condition.

A new branch or PR does not by itself justify a new worktree. Reviewers
fetch and checkout successive reviewed SHAs in their existing clean,
released review workspace.

Never check out the same branch in two worktrees. Reuse a role workspace for
successive topics only after its prior branch is released and its tracked,
untracked, and relevant ignored state has been rechecked.

Before switching an existing workspace:
- confirm ownership and no active job/process depending on it;
- check tracked, untracked, and relevant ignored content;
- preserve unique work and environment dependencies;
- never reset, clean, stash, or overwrite unknown content to force reuse.

After integration:
- retire the task assignment;
- retain the role workspace for its next task;
- remove an exceptional workspace only under an exact approved cleanup
  batch after safety rechecks.

Worktree removal, local branch deletion, and remote branch deletion are
separate actions. No automatic deletion, force removal, blanket pruning,
or history rewriting.

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

Update the body from a literal file: write the body to a file, apply it, then
read it back to verify the actual rendered content. The body states the actual
task, published SHA, tested SHA, review state, and next action — never a
remembered or aspirational state. Do not paste completed-experiment execution
instructions into a utility PR; each body describes its own task and next gate.

### Test-result vocabulary

Report results under the exact category they belong to; never upgrade a
weaker category's label:

| Category | Meaning |
| --- | --- |
| Targeted synthetic tests | A named test file or `-k` selection on synthetic fixtures; cite the exact command and pass/fail counts |
| Synthetic integration tests | The `pytest -m integration` lane (synthetic-only default; artifact-pinned cases skip with named reasons when private artifacts are absent) |
| Full-suite results | `pytest -q -rs` over the whole tree (CI job `test-and-validate`, or the local equivalent); state which ran |
| Private-artifact validation | Runs that consumed private-lake artifacts (sha-verified inputs); name the artifact identities; never implied by the categories above |
| Real forecast evaluation | Owner-authorized scoring against real outcomes; never implied by any category above |

The pre-commit hook (fast trio: `test_odds_ledger`, `test_real_bets`,
`test_registries`) is a local gate, not a full-suite result; report it as
"pre-commit fast trio".

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

- The reviewer **fetches the named PR head SHA** (not a remembered branch) and
  **pins** it before reviewing; a pushed change re-opens review of the delta
  only.
- A review response **names the exact reviewed head SHA**. When the review
  target moves, the next review explicitly **supersedes or retains** each
  earlier finding; a finding raised against a superseded SHA is re-validated
  against the current head before it blocks.
- The published review target does not move without an explicit superseding
  handoff from its author.
- Review responses classify findings **BLOCKER / NONBLOCKING / RESOLVED**
  (response format and finding rules: `docs/roles/README.md`); a checkpoint
  passes only with an explicit independent review at the named SHA.
- Builder self-check is never independent review.
- Reopen passed checks only when the delta affects them.

## 7. Gates by task type

Gates scale with the task. Do not impose experiment packets, real-data
execution, or repeat owner approval on ordinary already-authorized
implementation or utility work. Merge never authorizes an experiment.

| Task type | Gate chain |
| --- | --- |
| Implementation | scope -> implement / synthetic-test -> publish -> independent review -> applicable merge delegation/authorization -> integrate -> verify once |
| Experiment | registered contract -> reviewed implementation -> applicable access/run authorization -> execute under that authorization -> independent evidence verification -> scientific decision |
| Maintenance | bounded ownership/safety checks -> applicable exact-action approval -> perform approved scope -> verify once |

Approval recording follows `docs/roles/README.md` (Approval requests): one
explicit question, one recorded approval, no re-ask while the scope is
unchanged.

## 8. Merge rules

Merge only when ALL hold:
1. Scope authorized by the owner (or standing lane authority).
2. Exact-head CI green (verify the run on the live head, not an older report).
3. Independent review verdict recorded at the reviewed SHA
   (finding classification per `docs/roles/README.md`).
4. No unresolved review threads.
5. Merge order respects the current integration plan (single `main`, no
   force-push, no history rewrite).

Merge mechanics: normal merge per repo precedent (merge commits; e.g. PR #1).
After merging: update local `origin/main`, **record the resulting main SHA** in
the closeout/identity record, and verify dependent PRs still contain the new
main or plan their refresh/rebase.

Use this closeout sequence:
`merged -> main-verified -> released -> removable`.
`main-verified` records the resulting main SHA and dependent-PR disposition.
`released` confirms that no owner, process, or claimed path still depends on
the topic workspace. Role worktrees remain reusable; only an exceptional
workspace reaches `removable`, and only through a separately approved,
non-force cleanup batch. Branch deletion is never implied.

## 9. Comments and closures

- PR comments record decisions, scope notes, and closure rationale — one
  authoritative comment per decision, not threads of status chatter.
- Closing as superseded: state the canonical replacement, that this is a
  selection (not a file-for-file containment claim), and that the branch + unique
  commits are retained for provenance. Preserve the branch until the closure is
  recorded **and** its commits are confirmed reachable elsewhere or explicitly
  abandoned by the owner.
- Conflicting status reports: inspect the live PR state first; post at most one
  reconciliation comment.

## 10. Status reporting

Every status report delivers one of: **a deliverable, a decision, or a concrete
blocker** — with identity block + CI run. Holding notices without new evidence
are noise; say "no change since <SHA/run>" and stop.

## 11. Current optimization notes (CI)

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
