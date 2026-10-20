# Secrets / security / configuration audit — 2026-10-16 (Chat 3, READ-ONLY)

Scope: all 809 tracked files at `origin/main` @ `1927c8c…` scanned for
credential patterns, hardcoded local paths, unsafe shell/eval patterns, workflow
permission breadth, action pinning, and sensitive logging. Method: pattern scan
(regex classes: secret assignments, bearer tokens, hardcoded user paths,
`Invoke-Expression`/`iex`, curl-pipe-shell, `eval(`/`exec(`) + workflow review.
**Nothing rotated, removed, or modified.** Line-level hits are in the session
data; values (if any) are deliberately not reproduced here.

## Results

| Check | Result | Assessment |
|---|---|---|
| Committed credentials (secret assignments, bearer tokens) | **0 hits** | clean — API keys are env-sourced (`SHARPAPI_KEY` etc.), consistent with docs |
| Hardcoded local user paths | **61 hits** | concentrated in `analysis/` + `models/Strikeout-Model/research/` notebooks and historical docs; **production daily-chain code shows near-zero** (the 2026-10-13 portability pass cleaned the staged surfaces) | 
| Unsafe shell patterns | **3 `Invoke-Expression` hits** (historical research `.ps1`/utility context) | flag for review when those scripts are next touched; not on the daily chain |
| `eval(`/`exec(` usage | present in research/parser contexts | reviewed as non-security-critical (no untrusted input path identified); re-check if any script ever parses external input |
| Workflow permissions | **no `permissions:` block** → default token scope | already CI backlog T3 (approved scope, deferred by coordination until post-count-run) |
| Action pinning | `checkout@v4`, `setup-python@v5`, `upload-artifact@v4` — version-tagged, not SHA-pinned | backlog T10 |
| Untracked configuration dependencies | the 8 undeclared imports (dependency audit) — incl. `modal` (deploy path) and `requests` (pullers) | dependency audit slice D1 |
| Sensitive logging | no key/token logging patterns found in production code sampled | clean |

## Assessment

No secret-material exposure found. The security posture is fundamentally sound:
env-based secrets, no credentials in tree, dry-run-default destructive tooling,
and the only real hardening items are the already-ticketed CI ones (T3
permissions, T10 pinning) plus opportunistic cleanup of historical
hardcoded-path notebooks and the 3 `Invoke-Expression` sites.

## Smallest safe follow-ups

1. (Already approved, deferred) T3 least-privilege workflow permissions — first
   CI slice after the count run finalizes.
2. (Owner, optional) Sweep the 3 `Invoke-Expression` sites into explicit
   argument forms during their next natural edits — no dedicated PR warranted.
3. (Opportunistic) Hardcoded-path cleanup in historical notebooks rides any
   future touch of those files (never a standalone mass edit).
