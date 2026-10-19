# PENDING_FINDINGS — market-eval v2 review findings parked, not fixed

**Date:** 2026-10-14. Chat 1 (builder) records these two Chat 2 review
findings as PENDING on the PR #3 branch (`research/market-eval-v2`). They
are NOT fixed in this PR, per owner instruction. Status: OPEN until the
owner rules on each.

## Finding 6 — upstream PMF verification: PENDING (evidence limitation)

- **What:** the review could not independently verify the upstream
  construction of the frozen K PMFs in the predictor payload
  (`pmf_h3_raw_*` / `pmf_l5_raw_*`; the accepted projected-batter-state v2
  artifact built by pregame-pa-ext-v1).
- **Why pending:** evidence limitation. The payload is a frozen input and
  its upstream build artifacts/lineage live outside this repository (private
  research lake / pregame-pa-ext-v1 worktree), so the PR #3 branch cannot
  carry the evidence needed to close the finding.
- **What this PR did instead:** nothing beyond what is already committed
  (lineage disclosures in BUNDLE_EXTRACTION.md / ARTIFACT_MAP.md stay
  authoritative). No PMF code or payload bytes were touched.
- **Close condition:** owner supplies or points to upstream verification
  evidence (fit-key receipts, artifact hashes, review record in
  pregame-pa-ext-v1); then a follow-up docs-only commit can close this
  finding.

## Finding 7 — verify_ledger header: PENDING (minor)

- **What:** `verify_ledger.py` (same directory) carries a header/docstring
  issue flagged in review (minor; no behavioral impact identified).
- **Why pending:** minor severity; the owner ordered fixes (a)-(f) only in
  this pass. `verify_ledger.py` is out of scope for the confirmed-defect
  fix commits and touching it now would widen the diff without a named
  regression test.
- **Close condition:** owner authorizes a small follow-up commit on this
  branch to correct the header wording; verify the module still imports and
  its guard behavior is unchanged.

## Rule

Neither finding may be cited as closed anywhere. When closed, replace the
PENDING status here with the closing commit SHA and date; do not delete the
history of the finding.
