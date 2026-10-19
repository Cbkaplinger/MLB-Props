# repo_hygiene_check.py — usage

Advisory, read-only hygiene checker for the tracked tree. **It never modifies,
deletes, fixes, or networks** — findings only. Full design rationale:
[`reports/hygiene_automation_design_2026-10-16.md`](reports/hygiene_automation_design_2026-10-16.md).

## Run

```powershell
python scripts/repo_hygiene_check.py --repo .
python scripts/repo_hygiene_check.py --repo . --json hygiene.json --strict
```

- Findings print one-per-line as `[check] detail :: path[:line]` and never
  change the exit code.
- Exit codes: `0` ran clean of operational errors; `2` operational error (not a
  git repo, git failure, malformed allowlist); `3` only with `--strict` when
  findings exist.
- Secret-pattern findings report `file:line` with **values redacted**.

## Checks

`duplicate-blobs`, `broken-links`, `dead-notebook-refs`, `oversized-files`
(default >1 MiB, `--max-bytes`), `ignored-but-tracked`, `secret-patterns`,
`undeclared-imports` (import surface vs pyproject declared names),
`ci-collection-gaps` (test files outside `testpaths`), `untracked-generated`,
`worktree-status` (detached-HEAD worktrees, report-only).

## Allowlist

Accepted exceptions live in a committed JSON so every waiver is auditable:

```json
{
  "duplicate-blobs": [".cursorignore", ".clineignore"],
  "ignored-but-tracked": ["data/Pitcher-Starts-2023-2025-Data/README.md"],
  "dead-notebook-refs": ["docs/CLEANUP_LOG.md"]
}
```

Pass with `--allowlist <path>`. Entries are exact tracked paths or basenames;
allowlist edits are reviewed like any change.

## Boundaries

No network, no installs, no notebook execution, no repository-module imports,
no traversal outside the repo root, no writes (except the `--json` output path
you name). Deep audits (near-duplicate shingles, full import graphs) remain
separate dated reports, not part of this tool.
