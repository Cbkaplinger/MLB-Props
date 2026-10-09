# Publication checkpoint - proposed staging list (2026-10-08)

> Status: DRAFT staging proposal. No commits, no pushes. Parked
> worktree inspected only (see 4).

## 1. Proposed staging list (main-active)

All paths relative to `MLB-Props-worktrees/main-active`:

**Contracts (frozen):**
- `research/offseason_2026/kcount-integration-prereg.md`
  (sha `796a3606...`, frozen 2026-10-08)
- `research/offseason_2026/pregame-opportunity-contract.md`
  (sha `2f3b9f22...`)
- `research/offseason_2026/i4-card-source-experiment.md`
  (sha `5fbedb77...`)
- `research/offseason_2026/i5-tail-challenger.md`
  (sha `2d58a7d2daba90c7cff2a24660076348be3bb967a12909db47561c7cf533b040`)

**Code + tests:**
- `research/offseason_2026/bf_distribution.py`,
  `pa_k_baseline.py`, `kcount_combiner.py`, `lineup_opportunity.py`,
  `retrosheet_cards.py`, `eval_package.py`
- runners: `run_corrected_history_2023.py`,
  `run_kcount_integration_2023.py`, `run_i3_opportunity_2023.py`,
  `run_i4_card_source_2023.py`, `run_i5_tail_2023.py`
- tests: `tests/test_bf_distribution.py` (if new),
  `tests/test_kcount_combiner.py` (18),
  `tests/test_kcount_runner.py`, `tests/test_lineup_opportunity.py`,
  `tests/test_i3_runner.py`, `tests/test_retrosheet_cards.py` (6),
  `tests/test_eval_package.py` (4)

**Docs (dated, lowercase-hyphenated):**
- `research/offseason_2026/bf-origin-tail-audit-2026-10-08.md`
  (incl. section 7 owner corrections)
- `research/offseason_2026/i3-closeout-2026-10-08.md`
- `research/offseason_2026/kcount-integration-clarification-2026-10-08.md`
- `research/offseason_2026/i5-tail-challenger-draft.md`
  (superseded by the frozen contract - keep as history)
- `research/offseason_2026/transfer-validation-readiness-2026-10-08.md`
- `docs/EXECUTION_BACKLOG.md` (session receipts)

## 2. Diff summary (main-active vs HEAD 6bcf9e1)

`git status --short` count: 23 paths. Composition: 4 frozen
contracts + 1 draft-kept-as-history, 2 new code modules
(`eval_package.py`, `run_i5_tail_2023.py`), 6 runner/analysis modules
from earlier lanes, 5 test files, 5 dated docs, backlog. No data
files, no odds-lake paths, no credential paths, no
`artifacts/`/`data/` paths (both gitignored and verified below).

## 3. Exclusion verification

- `git check-ignore data/Retrosheet/x` in main-active -> matches
  `.gitignore:36` (raw archives + register excluded).
- `git check-ignore data/x artifacts/x` -> matches (long-standing
  rules).
- Run outputs live OUTSIDE the repo under
  `C:\Users\ckaplinger\MLB-Props-Research\` (all scored runs incl.
  `i5-tail-20261008_212247`); only hashes are recorded in manifests.
- No `*.env`, no key material, no `SHARPAPI_KEY`/token strings in
  the staged set (receipts reference names only).
- Proposal: staging = the list in section 1 ONLY; anything else
  appearing in `git status` stays unstaged.

## 4. Parked worktree (inspected, not changed this turn)

- `MLB-Props` original dir = the parked checkout (branch
  `preserve/legacy-pending-20261005`, d311b75).
- **Documented exception:** a protective `.gitignore` edit (adding
  `data/Retrosheet/` + `Data/Retrosheet/`) sits UNCOMMITTED there
  from the I4 acquisition turn. Per the owner's message this
  specific edit is RATIFIED as a documented exception; the freeze on
  all other parked changes stands. The identical rule now also
  exists in main-active's `.gitignore` (the branch that would carry
  it into history).
- No other parked-tree modifications observed this turn.

## 5. Not done (by rule)

No `git add`, no commit, no push. Staging executes only on an
explicit owner order; the owner runs any push themselves.

## 6. Reconciliation executed 2026-10-08 (pre-commit)

Actual git status --short = 29 paths (5 modified, 24 untracked)
vs section 1's list. Every actual path maps to documented 2023-lane
work. Discrepancies found and resolved:

- kcount-integration-prereg-draft.md (M) and
  pregame-opportunity-contract-draft.md (??) are the draft
  counterparts of frozen contracts - included, same
  keep-as-history convention as the i5/i4 drafts.
- 	ests/test_bf_distribution.py was listed conditionally; it is
  already tracked upstream - no action.
- Final decision: stage ALL 29 paths. Nothing else is modified; no
  data/, artifacts/, odds-lake, or credential paths exist in status.

Staged-diff review: file types only .py/.md/.gitignore; no
binaries; no secrets (grep for KEY/TOKEN/SECRET over staged
content: clean); largest additions are code + dated docs.

One checkpoint commit created 2026-10-08 (see git log). No push;
parked worktree untouched.