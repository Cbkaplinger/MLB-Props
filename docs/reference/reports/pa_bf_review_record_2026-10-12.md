# PA/BF independent review record (2026-10-12)

Point-in-time record of the independent review arc for the PA aggregation
and BF forecast work. **Not the work queue** (`docs/EXECUTION_BACKLOG.md`
wins) and **not the plan**. Written by the review window (chat two) in an
isolated worktree; integration is the main-active owner's job.

## What was reviewed and how

Independent read-only closure review of chat one's PA/BF work, performed at
explicit commits or byte-hash-pinned working files in isolated worktrees.
No data reads, no scientific reruns, no model access at any point.

Method contract (so future readers know what "closed" means here):

- "Closed" = verified in code/tests at the pinned bytes, not executed.
- Execution claims are quarantined (reported by chat one, never reproduced
  by review).
- Every finding carries a closure map; "unchanged bytes after a claimed
  fix" reverts the item to open.

## Review timeline

| Object | Review verdict | Outcome |
|---|---|---|
| `72a99ef` aggregation A/B/C | 8 findings (naming, denominator, vacuous mean gate, slot conflicts, invariance, slices, paths, CSV flags) | all closed via `c0805be` + `33e1f63` + `a671e7a` |
| `1d3b382` lineup adapter | status policy, naive cutoff, team mapping, future-append, runner invocation | closed via `b2d7140` |
| `b2d7140` + `dee0c5a` adapter closure | D1-D4 (coverage basis, map drift, mixed status, malformed timestamps) | closed at `dee0c5a`; `f28fdfd` closed doc residuals |
| `33e1f63` + `a671e7a` Gate A | mean gate made substantive (actual uncollapsed PMFs, fsum, negative tests); root cause = support truncation, scores unchanged | closed; Finding B recorded by-construction |
| BF runners (uncommitted, hash-pinned) | 3 blockers (hardcoded cohort asserts; mb/mb self-comparison; no bundle-hash binding) + mediums/lows | closed across three fix rounds |
| Two-item receipt closure (`921f7e5e` / `0913a37f` / `0e0607ac`) | computed reconciliation text + preflight coverage labels + shared helper test | PASS on locked scope |

## Final byte pins at review close (SHA-256 content / git blob SHA-1)

| File | SHA-256 | Blob |
|---|---|---|
| `research/offseason_2026/run_bf_reconstruct_2026.py` | `5f66d516b7a0f4437e542473d35dcd1b582460e74bbf61e5ac542cf6eaa0226a` | `dbeab893ff8e212314d3bb0d55d54a214a62fb27` |
| `research/offseason_2026/run_bf_preflight_2026.py` | `0913a37fe6eb22b7c9018a08bb6027e9c786f9fa313bf37fc6dd6f1604ff914d` | `d2c721139c3777d1f9b36362f7be1ac1370de3e8` |
| `research/offseason_2026/run_bf_ab_forecast_2026.py` | `921f7e5e1b89cdb92be0d06ece3a61d76764e772f0c1596b0cbf63928af13c35` | `34a0659db064ec633d0e3836c7916ed5958e9d3a` |
| `tests/test_pa_aggregation_abc.py` | `0e0607ac6d7288d6515f14d25cde539a067d1d45a86f279ca56787c202759b84` | `625c7f1e0cd99931ef8472da3277f500d35e0525` |

## Hash terminology (recorded so it is not re-litigated)

- Git blob ID = SHA-1 over object header + content (this repo uses the
  SHA-1 object format; native commit IDs are SHA-1).
- File content SHA-256 is a separate identifier over raw bytes.
- The same bytes have both identifiers; never compare across algorithms
  (this caused one false "changed file" alarm, resolved same day).

## Established facts that survive this arc

- Aggregation B arm uses cycled-PREFIX means (first n of the cycled
  9-slot order); a discriminating partial-cycle fixture pins this.
- Mean gates compare PMF-derived uncapped expectations against
  `sum(p_1..p_n)` at frozen 1e-9 via explicit `MechanicalFailure`; the
  24-bucket K mapping is 0..22 exact + index 23 absorbing K>=23;
  reporting means are collapsed-support by the same convention in both
  arms (disclosed, consistent with the frozen aggregation contract).
- BF tail: `bf_pmf_from_37` redistributes P(N>=37) over 37..60
  (frozen, documented geometric approximation); support capped at 60.
- Adapter policy: confirmed-only default, latest cutoff-valid snapshot
  wins, no older-revision substitution, naive cutoffs rejected before
  UTC coercion, explicit fail-closed reasons; mixed-status and
  conflicting captures fail closed.
- Both forecast-path runners verify the approved bundle SHA-256 before
  deserialization (one shared `verify_bundle_identity`), with negative
  tests.
- Historical A/B/C scores were unchanged by the numerical correction
  (max elementwise diff 7.3e-14, receipt-reported).

## Quarantined execution claims (reported, NOT reproduced by review)

- `APPROVED_BUNDLE_SHA` matches the actual bundle bytes.
- 99 direct-reference prior matches; executed counts (142/8/11/123);
  mean tail mass; probe / fit-to-reload equality; 9,712 retained starts;
  convergence; rev-conflict gate behavior on real captures.
- These require execution (seal package / scoring) to verify; they are
  not review findings.

## Approval pipeline at time of record

1. Commit + push of the four pinned files to the review branch for CI
   (authorized; execution belongs to chat 1; stop concurrent writes
   first; CI must pass on the exact new commit).
2. Seal package preparation (after CI) - separate approval.
3. Frozen scoring (outcomes) - separate approval.

The review window's remaining role: optional independent post-commit
hash confirmation on request; documentation updates as receipts arrive.

## Nonblocking residuals register (future cleanup candidates)

- Dead inline `rep["fallback_mask_note"]` construction in
  `run_bf_ab_forecast_2026.py` `main()` (overwritten by helper).
- Dead `--bundle-sha` argument (forecast runner).
- Bare `assert` guards (forecast 84/226/318-320; preflight 48) vs
  `MechanicalFailure` discipline.
- Dead `if False` conditional (forecast); dead placeholder loop and
  dead import (preflight).
- Identity-guard test's positive leg depends on a machine-local bundle
  path (portability).
- `test_ab_forecast_fixtures` retains one stale `assert_mean_gate(..., mb, mb)`
  call (its independent `ref` comparison is the substantive check).

## Related records

- Pointer-repair batch: `docs/pointer-repairs-20261009` branch, commit
  `20c2724` (awaiting integration).
- Diagrams handoff: `docs/architecture-20261009` branch, commit
  `804e86b` (integrated as `9a48391`).
- Cleanup inventory: delivered in-chat 2026-10-09 (read-only; top
  findings: stale notebook pointers (repaired by `20c2724`), operator
  script invocation issue (ops lane), duplicate-name prune tools
  (documented), devig/implied-prob pairs (retain + document)).

## Provenance update (2026-10-13, post-CI)

- Reviewed/executed working-byte hashes: forecast runner 921f7e5e...13c35, test file 0e0607ac...9f64f (original pins PRESERVED as historical evidence).
- LF-normalized committed-content hashes at b212ffb: forecast runner 7f1baac9..., test file dd3316c7... (mechanically verified: committed == working reviewed bytes with CRLF->LF only; 373 CRLFs, zero CRs remain).
- Source commits: b212ffbbb741c29bc9a1981ff6d85c8978c3c019 (BF runners+tests), 56e2799 (skip-guard), 2497391 (odds-board ET-clock fixture repair, owner-authorized test-only; production stale_days verified correct). CI: test-and-validate PASS on 2497391 (run 38334351105).
- Docs source commit: 0ddb050408cb0e75db1cefdc4d73178ac223e862; integrated via cherry-pick -x (only the two declared documentation paths changed).
- Process deviation recorded plainly: local commit b212ffb was created before the hash discrepancy was resolved; push was correctly held until verification.
- Ruling: option (a) accepted - LF normalization is content-equivalent; a future .gitattributes change should use text eol=lf (not -text).
