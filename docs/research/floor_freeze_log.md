# Floor freeze log

This file is the auditable record of every decision that changed — or
reaffirmed — the active `DEFAULT_EDGE_FLOOR` in `src/Python/market.py`. Each
entry pins the decision to:

- the date (UTC),
- the prior and new floor,
- the exact code-answer (the `market.DEFAULT_EDGE_FLOOR` constant),
- a ledger cell-hash (SHA-256 of `artifacts/odds_log/ledger.parquet`) so the
  exact ledger the decision was made on can be reproduced,
- the evidence that drove the decision (CLV mean + CI, win-rate vs 0.524,
  n, and any other numbers cited),
- the stopping rule that will re-open the question.

**Rules of the log:**

1. The floor is *frozen* between entries. Do not change `DEFAULT_EDGE_FLOOR`
   or the pre-registered decision rule without writing a new entry here first.
2. No back-dating. Entries are appended in chronological order; older entries
   are immutable.
3. If two entries conflict on the same date, the later one wins *and* the
   earlier one stays (with a `SUPERSEDED` note) — no deletion.
4. Pre-registered checkpoints count as freeze events. If the next-50-bet
   checkpoint at `artifacts/odds_log/next_50_checkpoint.json` is the basis for
   the decision, its `frozen_at_utc` and `ledger_sha256` are quoted in the
   entry's evidence.

---

## 2026-08-06 — Reaffirmed 12% (`DEFAULT_EDGE_FLOOR == 0.12`)

**Prior floor:** 0.12 (system uv-reco review froze it earlier this session
and locked it via `tests/test_market.py::test_unit_anchor_reflects_current_floor`).
**New floor:** 0.12 — no change.

**Decision:** Hold the floor at 12% for the entire n_clv >= 150 gate window.
Do NOT move the floor based on the 2026-08-06 read.

**Ledger snapshot (the universe as of this entry):**

| metric | value |
| --- | --- |
| `ledger_sha256` | `cfddcf674c20da314fab1243c52fa2a637e875cec3c09ce825b8ebe60ac49e37` |
| ledger rows (total) | 330 |
| settled tickets (n with `result in {win,loss}`) | 199 |
| `n_clv` at `floor >= 12%` | 72 (wins = 38, win-rate ≈ 0.528) |
| CLV ≥ +1.0pp | n=54, wins=28, win-rate ≈ 0.519 |
| CLV < +1.0pp | n=145, wins=55, win-rate ≈ 0.379 |

The headline split read at the time of the user's message was the prior
`n_pos=52 / n_neg=141` snapshot; the resolved ledger now shows
`n_pos=54 / n_neg=145` — both groups grew slightly, and the directionality of
the gap is preserved. The freeze is grounded on the *current* snapshot, not
on the stale numbers in the user prompt.

**Evidence cited (the corroborating reasons for holding):**

- The prior recommendation to *lower* the floor from 12% to 6-8% was driven by
  stale cell output citing CLV of +0.66–0.72pp at 6-8% against an n=67 ledger.
  The ledger has since grown to 199 settled tickets (330 ledger rows total)
  and the corrected numbers recompute the n-needed estimate: **floor >= 6%
  needs ~620 bets, floor >= 8% ~375, floor >= 12% ~655** to get a CLV CI that
  excludes zero at these effect sizes — vs. the (wrong) 130-190 bets claimed
  in the old read. The argument to lower the floor is fundamentally
  invalidated by the corrected effect size, not just cosmetically.
- The CLV-vs-win headline (`p_pos ≈ 0.519 @ n=54` versus `p_neg ≈ 0.379 @ n=145`
  on the resolved ledger) is the strongest single piece of evidence in the
  ledger but does *not* clear α=0.05: a two-proportion z-test gives
  `z ≈ +1.84, two-sided p ≈ 0.065` (computed locally via
  `src/Python/skill_stats.py:two_proportion_z_test`). **State it as
  "directionally strong but not yet significant"** — not as proven. It is
  exactly because of this borderline status that building the full reliability
  artifact (Section 11 of the dashboard) and waiting on `n_clv` growth to 150
  is the right gate.
- The "CLV isn't stagnant" argument was a mislabel against the Kelly-plateau
  observation. Re-arguing it was attacking a claim nobody made.

**Stopping rule that re-opens this:**

- `n_clv >= 150` at `floor >= 12%`, evaluated on live-ledger reruns of this
  notebook (Section 18a's BCa-CLV sweep + Section 11's
  `clv_reliability.parquet`).
- Check together: **does BCa CLV CI exclude zero**, and **does win-rate clear
  the 0.524 break-even**. Either alone is insufficient.
- Pre-registered next-50-bet checkpoint
  (`artifacts/odds_log/next_50_checkpoint.json`) defines the rule: mean CLV
  `>= +0.30pp` AND win-rate `>= 0.54` *escalates* (keep floor at 12%, double
  KB-class stake size); mean CLV `< +0.30pp` OR win-rate `< 0.524` *reverts*
  (still hold the floor at 12% but drop KB to quarter-Kelly). All other
  outcomes → no change; re-evaluate at `n_clv = 200`.
- Time horizon: 3-4 weeks at the current grading rate.

**Code references:**

- `src/Python/market.py`: `DEFAULT_EDGE_FLOOR = 0.12`, `DEFAULT_KELLY_FRACTION = 0.125`
  (1/8-Kelly).
- `tests/test_market.py::test_unit_anchor_reflects_current_floor`: pins
  `unit_anchor_kelly_frac` against `DEFAULT_EDGE_FLOOR` / `DEFAULT_KELLY_FRACTION`
  so the bankroll anchor can't drift silently. The old hardcoded 0.042 anchor
  (the pre-freeze 8% / quarter-Kelly value) was retired by this same freeze.
- `src/Python/skill_stats.py`: `two_proportion_z_test`, `bootstrap_bca_ci`,
  `stake_weighted_bootstrap_ci`, `rolling_stat_with_se`.
- `production/notebooks/results_dashboard.ipynb`: Sections 11-18.

**Ledger cell-hash:** `cfddcf674c20da314fab1243c52fa2a637e875cec3c09ce825b8ebe60ac49e37`
(SHA-256 of `artifacts/odds_log/ledger.parquet`, 330 rows / 199 settled, computed
2026-08-06). The digest above is the literal value; to reproduce it:

```python
import hashlib
print(hashlib.sha256(
    open("artifacts/odds_log/ledger.parquet", "rb").read()
).hexdigest())
```

Both the digest and the row counts above should match if you re-run the script
on the same ledger file. If they don't match, the ledger has been mutated since
the freeze — re-evaluate before changing the floor.
