# PR-quality template pack — 2026-10-16 (Chat 3, PROPOSED documentation)

Proposed reusable templates. **Status: drafted on this report branch pending the
governance-vehicle decision** (role-card PR vs PR #10 refresh — one will be
chosen, not both). Nothing here edits `docs/reference/pr_workflow.md` (PR #10's
file) until that decision. After adoption, `pr_workflow.md` §4/§7 should link
here instead of duplicating.

## T1 — Standard PR body (non-research)

```markdown
Repository / origin URL:
Worktree / branch:
Task base SHA:
Current HEAD:
Remote branch SHA:
Working-tree status:
PR / CI run and tested SHA:
Config + input hashes, when applicable:

## Purpose
What problem this PR solves and why now.

## Scope
Included paths; explicit non-goals.

## Design
Key decisions, alternatives rejected, compatibility constraints.

## Evidence
Tests, CI run on exact head, validations, quantitative results.

## Operational impact
CI/runtime/production/research impact; rollback behavior.

## Review guide
Suggested file order; reviewer focus areas.

## Merge conditions
Exact-head CI, required review verdict, dependencies, post-merge verification.

## Follow-ups
Deliberately deferred items with issue/PR links.
```

## T2 — Experiment identity block (research PRs; appended to T1)

```markdown
## Experiment identity (immutable)
Registration/freeze hash:
Input hashes (binary byte-exact / text LF-normalized):
Execution SHA:
Output manifest hash (lake, not in Git):
Primary endpoint + family (m=):
Limitation statement (permanent, verbatim):
PR contents: [ ] code  [ ] evidence pointers only  [ ] closeout receipts
```

## T3 — Merge receipt (posted by the integration owner at merge time)

```markdown
Merged: PR #<n> (<title>)
Merged head: <full SHA>
CI run on that head: <run id> (<conclusion>)
Merge method: merge commit (no force-push, no rewrite)
Post-merge origin/main: <full SHA>
Changed paths: <summary or diffstat tail>
Verification: test command on main unchanged: <yes/no + command>
Downstream: <which open PRs now need base refresh at merge slot>
```

## T4 — Review verdict (Chat 2)

```markdown
Verdict: READY | READY-WITH-LIMITATION | BLOCKED | INVALID   (at SHA <full>)
Checked: [ ] exact head pinned  [ ] CI green on that head  [ ] identity/hashes
[ ] recomputation from persisted artifacts  [ ] preregistration conformance
[ ] limitations persisted and worded
Blocker (if any): one concrete defect + owning chat
```

## T5 — Closure comment (superseding a PR)

```markdown
Closed as superseded by PR #<n>.
Relationship: parallel implementations / partial containment (state which).
Canonical choice rationale: <one paragraph, evidence-linked>.
Branch/commit retention: <branch> retained; unique commits: <SHAs, reachable-from>.
No merge of this PR's distinct paths occurred.
```

## Usage rules (from the standing contract)

- Templates are floors, not ceilings: add lanes/sections, never delete the
  identity or evidence sections.
- The identity block is mandatory for research PRs; "code vs evidence pointers"
  must be explicit (lake outputs stay out of Git).
- Merge receipts are posted once, by the integration owner, at merge time.
- Review verdicts cite the exact SHA they cover; a new head invalidates them.
