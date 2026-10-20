# O-3 settlement/grading exit-code & summary contract — proposal (2026-10-19, Chat 3)

Companion to [`observability_audit_2026-10-16.md`](observability_audit_2026-10-16.md)
(O-3 slice). **Test-only this turn: characterization executed, contract
PROPOSED — no production behavior changed.** Requires separate owner approval
before any implementation PR.

## Characterization results (EXECUTED — 14/14 pass at the branch head)

Pinned current behavior of `production/odds/grade_odds_ledger.py` in
`tests/test_grade_settlement_characterization.py`:

| Behavior | Current (characterized) |
|---|---|
| `--settle` parse | `Name,YYYY-MM-DD,K`, whitespace-stripped; wrong arity → `SystemExit("Bad --settle ...")`; **non-numeric K → raw `ValueError` (uncaught — first gap)** |
| `--close` parse | `Name,YYYY-MM-DD,over,under`; wrong arity → `SystemExit("Bad --close ...")` |
| `_find_tickets` | case-insensitive LAST-WORD name match + `str.contains` date substring — **substring, not equality (documented sharp edge)** |
| `_status_counts_ascii` | `status=<s> count=<n>` lines, descending by count; empty ledger → `[]` |
| Exit contract (de-facto) | success → `main()` returns None (exit 0); 5 guards raise `SystemExit(<message string>)` → **exit 1** with message on stderr; **no distinct code for partial failures (the O-3 gap)** |
| Ledger absence guard | `SystemExit("No ledger at <path>. Log quotes first.")` when missing and not `--status` |

## Proposed contract (NOT implemented — owner-gated)

1. **Formalize what exists:** exit `0` success; exit `1` guard failures with
   the existing message strings on stderr (already de-facto; document it).
2. **Add a summary line** on every settle/grade run:
   `graded=<n> skipped=<n> anomalies=<n> voided=<n>` — machine-greppable,
   matching the O-1 step-manifest convention.
3. **Add exit `2` for partial failure** (e.g. some tickets failed to settle
   while others succeeded) — distinct from guard-failure `1`. This is the only
   behavior change; it needs the characterization tests extended first, then a
   one-line change, then the tests flip to the new pin.
4. **Keep messages on stderr, summaries on stdout** (already true).
5. **Out of scope:** structured-logging migration, retry changes, schedule
   changes.

## Explicit non-actions

No production file touched. No CI change. No rerun of any scientific lane.
Adoption path (if approved): extend characterization tests to the proposed
behavior → implement → flip pins in the same PR → record merge receipt.
