# MLB Props — Execution Backlog & Directive
> **This is the ONE holy file.** Single source of truth for what is approved, blocked, waiting on the user, and parked. Do NOT create parallel backlog files. When the user drags in a markdown file, reconcile it INTO this file, then it / the old file goes away. Keep it evergreen (see Evergreen Rule below).
>
> **Always open this file first** (`docs/EXECUTION_BACKLOG.md`). After every user prompt / agent turn that changes work state, update the **Session Snapshot** before ending.
> Also linked from root `AGENTS.md` and `.cursor/rules/execution-backlog.mdc` so every agent session sees this as master.

### Document hierarchy (this file wins)
| Kind | Path | Role vs this backlog |
| --- | --- | --- |
| **Master work state** | `docs/EXECUTION_BACKLOG.md` (this file) | Approvals, Snapshot PAST/PRESENT/FORWARD/DEFERRED, standing ops rules |
| Agent entry pointer | `AGENTS.md`, `.cursor/rules/execution-backlog.mdc` | Point here only — no second queue |
| Research constraints | `docs/reference/research_assistant_instructions.md` | How to build/leakage-safe — **not** a todo list |
| Ops runbooks | `production/README.md`, `INDEX.md`, `RUNBOOK.md` | How to run commands |
| Dated evidence | `docs/reference/reports/*.md` | Point-in-time reports; must say if SUPERSEDED and point here for “what next” |
| OpenCode paste brief | `docs/reference/opencode_handoff.md` | Coworker briefing 2026-09-11 (replay era). **Not** a second queue. Pack #113 built; juiced #123 measured; totals #124 pulled. |
| Frozen-model replay spec | `docs/reference/oddsapi_replay_architecture.md` | How to backtest 2025-present Odds API open/close with the model frozen — **not** a queue. Freeze/work/product partition. Inventory: `reports/oddsapi_replay_inventory_2026-09-11.md`. |
| Golden metrics | `docs/reference/golden_metrics.md` | Canonical numbers + JSON sources. Cite, do not recompute. |
| Paper / resume | `docs/paper/manuscript.md`, `resume-summary.md` | Publication narrative — not the live work queue |
| Cleanup history | `docs/archive/CLEANUP_LOG.md` | Historical cleanup log — not instructions |
| Canonical surfaces | `docs/reference/repo_canonical_map.md` | What code/docs are canonical vs archive |

If another doc’s “next steps” disagree with the Session Snapshot, **this file wins**. Fix the subordinate doc to redirect here.

## Directive (read this first, every session)
You have blanket approval for every item below marked APPROVED. Execute them **in order**; do not re-ask on anything already approved. Do not start new discovery/analysis/philosophizing until every APPROVED item is DONE or marked BLOCKED with a one-line reason. Notice something interesting mid-task? Put it in "Parking Lot," don't chase it. Report only on item completion or a true block — not every intermediate find.

### Iterative session loop (required)
1. **Read** this file (Snapshot → Waiting on user → Forward → **Deferred** → Standing Rules).
2. **Do** the next APPROVED item(s) only — **never** pull work from **DEFERRED** unless the user asks or the reopen condition is clearly met.
3. **Write back** before the turn ends — Snapshot must always have four labeled blocks:
   - **PAST** — durable completed work (what already shipped).
   - **PRESENT** — where we are now / what just finished this turn.
   - **FORWARD** — concrete ordered plan for the next session(s).
   - **DEFERRED** — approved-or-parked work that is *not* next (with why + reopen trigger).
   - Also refresh Waiting on user; add ideas to Parking Lot; never silent-drop threads.
4. Tell the user briefly what changed and point them back here for the plan.

**Evergreen Rule (every session):** after reporting, reconcile THIS file against what actually happened — update PAST/PRESENT/FORWARD/**DEFERRED**, item statuses, Parking Lot, and **pre-write the next session's plan** so no thread is lost. Close every session with this file reflecting "here is where we were, where we are, where we're heading next, and what we are deliberately not doing yet."

---


## Session Snapshot — 2026-10-28 (PRs #46/#48/#49/#50 MERGED; main = 15fe7bf; PR #51 derivation runner at 60401f6 awaiting owner execution decision)

**Critical path:** `docs/NEXT.md` (single source of the current action;
ROLES_REV 2026-10-28-r1 merged to main via PR #46 at `1ef5cad`).
**This backlog is the concise active entry point.** Historical Session
Snapshot bullets (2026-08 through 2026-10), the CLV + Hosting Plan, the
Strategy Plan, and the SSAC27 Track are preserved verbatim in
[`docs/reference/reports/backlog_archive_2026-10-21.md`](reference/reports/backlog_archive_2026-10-21.md).

**INTEGRATION MILESTONE COMPLETE 2026-10-28:** PR #46 (documentation,
ROLES_REV 2026-10-28-r1), PR #48 (calibration execution gate), #49 (Stage A
prediction-path runner), #50 (historical starter-outcome derivation +
baseline helpers) all merged with history-preserving merge commits; GitHub
reported zero open PRs post-#50. Builder verification: 132/132 targeted
tests on the actual merged tree (checkout `integration-verify-50`).

**Current Chat 1 lane (PR #51, `research/baseline-v2-derivation-runner`,
head `6a15219`):** the historical derivation/overlap execution entry point
(`derivation_runner.py`) around the UNCHANGED registered functions
`derive_start_outcomes` + `validate_against_registered`. Published chain
e269019 -> 60401f6 (13 synthetic tests, 145 targeted regression, CI green,
reviewer trail accepted) + 6a15219 (docs-only backlog reconciliation; runner
blob unchanged 2bf8e06a). **REAL DERIVATION/OVERLAP RUN EXECUTED ONCE
2026-10-28 (owner-authorized; full-file decode permitted; destination
approved):** pa_table (731,347 rows, hash-verified preflight) ->
**9,714 derived starts** (2023-03-30..2024-09-30; 7,380 pre-overlap
2023-2024H1 starts newly materialized for reference estimation); 2024H2
overlap 2,334 vs 2,334, intersection 2,334, **0 BF/K mismatches, 0
keys-only-either-side, verdict IDENTICAL, validated TRUE, exit 0**; receipt
chain intact (initial c2a3afdd... == recorded chain); outputs write-once at
`MLB-Props-Research\baseline-v2\derivation_overlap_v1\` (derived parquet
95ac3638..., overlap_report 21e74cef...). Verification evidence published on
PR #51 (executor-side recomputation: all hashes, linkage, and field
reconciliation MATCH; independent Chat 2 signature owed on the record).
RUN-EXECUTION EVIDENCE = PR #51 comments (run record 6487951982;
verification 6488030762). **SCORECARD IMPLEMENTED + CLI REPAIRED (canonical delivery checkpoint
c19a01ad0e85cb8e5f102e5f4d0267bb1f20303c, published on GitHub; builder's
local cadba8c confirmed content-identical on runner+tests and retired
from the branch;** the reviewer's consolidated review cleared the
scientific construction and found one blocker: the missing `__main__`
guard meant the documented launch command exited 0 without calling
main(); repair = the standard two-line guard + two real-subprocess tests
proving exit 2 refusal with nonexistent inputs (zero side effects) and
exit 0 with full evidence (report, per-start parquet, receipts, cli
route, hash reconciliation). STATE: derivation completed; scorecard
implemented; CLI repair delivered at the canonical checkpoint; prior
scientific findings retained; architect statically inspected the narrow
repair (not an independent review; repair authored in the reviewer's
session - ownership failure acknowledged); ownership failure acknowledged); integration = scorecard PR #52 OPEN
(https://github.com/Cbkaplinger/MLB-Props/pull/52, base
research/baseline-v2-derivation-runner, head 2c02e46) with CI GREEN
(test-and-validate + tracking, run 40893412390).
**SCORECARD EXECUTED ONCE (owner-authorized, 2026-10-30):** exit 0 at
canonical checkpoint c19a01a code (delivery head 28c86cb); destination
MLB-Props-Research\baseline-v2\history_sensitivity_v1; inputs verified
pre-decode (all four pins + cohort f77d7a66 MATCH); S_v1 2,334 train
rows, S_v2 9,714, assessment 2,509 (cohort hash match); PRIMARY:
delta = RPS(S_v2)-RPS(S_v1) = -0.011070, CI95 [-0.020503, -0.001621] -
ENTIRELY below zero: development evidence favors the LONGER estimation
history (small effect); NOT a final test; F anchor descriptive only
(mean 1.3111, UNACCEPTED cold-start limitation unchanged; F does not
select anything). Receipt chain intact (initial aa770407...); output
hashes recorded; Chat 2 result verification NEXT; interpretation and
capability registration after verification. Real scorecard
estimation/scoring for THIS run: consumed per its scope.

**MULTICLASS E2E BASELINE SLICE (checkpoint 9bdd3b4, pushed):**
architect decisions ADOPTED and implemented - (1) forecast-cutoff state
contract v2 (states-v2-forecast-cutoff-v1, forecast_states_v2.py): prior
state at request cutoff t = aggregate over ALL rows strictly before t;
legacy as-of-activity construction preserved unchanged; the published
row-presence defect (6b64d0d) is thereby corrected for the new path as
an ORDINARY passing test (legacy Stage A xfail retained, documents the
v1 convention); (2) projected lineups only (oracle manifest mode never
accepted). Synthetic end-to-end multiclass baseline runner
(pregame_multiclass_baseline.py): m0 4-class taxonomy -> Ref 0
training-only population proportions + Ref 1 regularized multinomial
(fit_multinomial/apply_multinomial) through IDENTICAL cutoff-correct
attach_prior_features construction -> K marginal (class 0) ->
start_count_pmfs fixed-workload aggregation -> count-RPS + multiclass
log loss vs SEPARATE assessment outcomes -> receipts/ack/write-once.
9 synthetic tests green incl. real subprocess; affected suites 104
passed + 1 xfailed. NEXT: Chat 2 review of the slice; real-data
fitting/scoring of the multiclass baseline remains UNAUTHORIZED (its
own packet/decision). Stage A real run still unexecuted (packet ready,
identities staged).
implements the ONE history-only contrast - Arm S_v2 (accepted derived
artifact 95ac3638, 2023-2024 training) vs Arm S_v1 (registered
start_metrics_v2 2024H2 slice) with the registered ladder machinery held
FIXED (build_arms + build_arms_v2 + paired slate-date bootstrap 2000
draws seed 20261001 + kc.count_rps + bf-workload-v1 validator, all
unchanged); identical block_2025H1 eligible cohort enforced by the
registered sorted-key hash f77d7a66...(n=2,509); own scorecard identity
baseline_history_sensitivity_scorecard_v1 + contract sha; truthful
contrast labels (paired_contrast's legacy S_vs_F label disclosed);
F anchor descriptive only (UNACCEPTED cold-start, never refit/gating);
runner conventions: ack gate exit 2, write-once, all four input SHA-256s
verified before decode, full-file decode disclosed, empty/duplicate/
unequal populations fail loud, receipt chain + failure_record.
Registered input identities resolved from in-repo records
(COUNT_REGISTRATION.md, preflight pins): start_metrics_v2 af6814ec...,
count_agg_eval_v1 afc94ad7..., bf_forecasts c9c2762f..., derived
95ac3638... 16 synthetic tests green through the exact entry point;
affected regression 125 passed. Scorecard EXECUTION (real data) still
requires its own explicit owner authorization - NOT granted. The
derivation artifact does NOT validate pre-overlap rows externally and
establishes no predictive improvement.

**Current Chat 2 lane:** owns the consolidated review record for PR #51's
published checkpoint 60401f6 (builder self-review labeled as such; do not
repeat cleared tests; review only a substantive loader delta if one becomes
necessary).

**Current Chat 3 lane:** parked (docs lane not blocked by baseline review).

**Stale-content note:** the older lane bullets below this block (PR #50
checkpoint 786b9fd, Chat 2/3 lanes) predate the #46/#48/#49/#50 integration
and are retained as history; this block is the live state.

**CHAT 3 PARKED 2026-10-27 (architect directive):** count-PMF calibration v1
reviewed READY locally at receipt `1381e72` / computational `e34213a`
(chain `3291fc5 -> e34213a -> 1381e72` verified read-only; paext-v2 worktree
clean); integration push/PR owned by Chat 1. Chat 3 stays parked until the
calibration PR merges or the lane is explicitly parked. Resume conditions:
docs reconciliation, supersession links, ADR/PRD integration into existing
conventions, diagram updates; no file deletions without ownership
confirmation; no scientific code or result records. A stray uncommitted
backlog edit in the detached main checkout was preserved (diff archived) and
its content recreated in this entry; the main checkout was restored.


## Execution Order

1. **[APPROVED] Commit the current green working tree** (test fixes: `test_pipeline.py`, `test_pitcher_features.py`, `test_registries.py`, `test_train.py`; new observability files from the daily-improvement session). Clean baseline before anything else touches the repo.
2. **[BLOCKED — verified no-op 2026-08-27]** Split/commit `close_watcher.py` (lock hardening vs. aux-market-probe). Verified: working tree is clean, the aux-probe + late-open features are already buried together inside the broad commit `de942c3` (183 new lines in close_watcher.py among 27+ files), the pre-split backup `.py` is gone (only a stale `.pyc` remains), and there is **zero uncommitted delta to split**. The split would require a destructive rebase/filter of already-committed history — not doing that without explicit sign-off. Treat as effectively combined already; resume only if user explicitly wants the `de942c3` history rewritten.
3. **[DONE 2026-08-27 — commit 3947a7a]** Widen CI (`ci.yml`): py_compile all 60 production scripts (dynamic find, was 6 hardcoded), full 270-test suite (was 2 files), install pyproject deps `.[dev]`+scipy (was a no-op `requirements.txt` that never installed polars). Validated: 60/60 compile, 270 tests green, YAML OK.
4. **[DONE 2026-08-27 — commit 2d27ef3]** Dedupe-to-best-line as shared infrastructure. Fixed canonical `dedupe_ledger_props` to key on `(game_date, player, line, SIDE)` (was missing side — kept over/under of the same line merged, a latent bug; 22 such props in data). Wired the one canonical function into the 3 scripts still aggregating raw rows: `line_policy_settled_lookback`, `clv_basis_reconcile`, `build_automation_self_check`. Added 2 tests (over/under kept separate; best book per side). Validated: 272 tests pass; real-ledger settled 1118→643 props.
5. **[DONE 2026-08-27]** Regenerated every previously-cited number on the deduped ledger (old vs new, same ledger, apples-to-apples):
   | Metric | OLD (raw) | NEW (deduped) |
   |---|---|---|
   | Settled tickets | 1118 | 643 |
   | All-time PnL | +$576.15 | **+$84.51** |
   | All-time ROI | +2.08% | **+0.51%** |
   | Stake volume | $27,635.75 | $16,725.07 |
   | Skill-gate n_clv@floor12 | 248 | **150** |
   | Skill-gate WR | 0.534 | 0.5334 |
   | CLV beat>0 | 46.5% | 55.5% |
   | Line 4.5 all ROI | −26.4% (n=413) | −22.2% (n=244) |
   | Line 4.5 profile(≥.14) ROI | −33.3% (n=76) | −34.1% (n=52) |
   | Line 5.5 over ROI | −59.1% (n=22) | −61.8% (n=13) |
   **Headline: the all-time "green" was +2.08%/+$576 on raw; on the honest deduped ledger it is +0.51%/+$84.51 — barely above breakeven. Skill-gate n falls 248→150 (still met) and WR is essentially flat (0.534→0.5334); the edge shows in CLV, not raw WR.**
6. **[DONE (infra) + BACKFILL BLOCKED on operator prices — 2026-08-27, commit 1da4c82]** Built the append-only real-bet ledger: `src/Python/real_bets.py` (separate from paper-sim `ledger.parquet`; decision-time `bet_price`/`stake` snapshot; `append_real_bets` returns `(frame, n_appended, skipped_ids)` so no ticket can silently drop — the 8/24 failure mode); `tests/test_real_bets.py` (6 integration tests proving idempotency, in-batch dup reporting, re-append never-silent, real≠paper path, summary math, stable schema); `production/ops/backfill_real_bets.py` (holds the 8 confirmed identities Valdez U4.5 W / Suarez U4.5 W / Messick O6.5 L / Skenes U6.5 W / Melton O3.5 W / G.Rodriguez O4.5 L / Cantillo U6.5 W / Sasaki O4.5 L; refuses to write rows lacking a real decision-time price/stake — reports instead of fabricating zeros). **SATISFIES THE INTEGRATION-TEST REQUIREMENT.** Backfill WRITE is BLOCKED only on the per-ticket decision-time `bet_price`/`stake`/`pnl` (and the 9th ticket's identity+prices) which live in the user's records — fill `REAL_TICKETS` in the backfill script and rerun; complete set is 6W–3L, +$109.80/$455.
7. **[BLOCKED — no script to rewrite 2026-08-27]** CUSUM `corr_before`/`clv_before` null bug. Verified: the CUSUM/regime **regeneration script does not exist anywhere in the repo** (no source for `regime_model_report.json` / `corr_after` / `clv_after` / `cusum`; only the artifacts remain, and it's likely a deleted one-off probe like `_probe*.py`). Diagnosis captured from the surviving artifact for when the script is restored: `corr_before: null` despite `edge_win_corr_break_pos: 253` (rolling_window 40) and `clv_before: null` at `clv_break_pos: 191` — i.e. the pre-breakpoint sample window is too small/empty, so the "before" stat computes null. The rewrite needs a min-sample guard that emits an explicit `null`/`insufficient` with the n instead of an unlabelled null. Resume when the script is restored or the user provides it.
8. **[DONE (in-repo sweep) 2026-08-27 — external network call remains outside agent scope]** External-outcome recovery sweep. Verified from the ledger and stored artifacts:
   - **8/24 gap is isolated to a single day, not systemic**: `ledger.parquet` has daily rows through 8/20–8/23 and 8/25–8/27 but **0 rows on 2026-08-24** — an isolated one-day ingestion hole in an otherwise-continuous record.
   - `open_projection_quotes_raw`/`open_quotes_canonical` **end in early July entirely** (last rows ~2026-07-10/11), so they never reached August — their "0 rows for 8/24" is trivial; not the right source for recovery.
   - **Melton's real 8/25 O3.5 line is not in the paper ledger** (only other Melton dates/lines are: 8/04 U5.5, 8/15 O5.5, 8/21 O4.5, 8/26 O3.5) — same class of real-ticket data gap as 8/24.
   - **Real-ticket players are present in the paper ledger on different dates/lines** than their real bets — confirming real (real_bets.parquet) vs paper are correctly separate tracks.
   - **Recovery action**: both gaps are isolated ingestion/record flat-spots, so a targeted external odds/score call (not a systemic rebuild) is warranted; executing that network/API call is outside what the agent can run here. 8/24 outcomes are already user-confirmed (PnL not blocked); this is an auditability/completeness backfill only. Side pattern re-confirmed: all 3 real losses were Overs (Messick, G.Rodriguez, Sasaki).
9. **[EVIDENCE COMPLETE 2026-08-27 — swap still gated on user sign-off]** Champion-vs-monotone swap evidence package. The side-conditional breakdown is already fully built in `artifacts/odds_log/_audit_step4_monotone_sidebreak.json` — and it was **never actually blocked on #4-#5**: it operates on the 2025 model open universe (`config.PITCHER_TRAINING_PATH`) with its own `(pitcher+line+date)` dedupe, NOT the 2026 settled paper ledger that #4-#5 dedupe. That BLOCKED-PENDING-#4-#5 status was a false dependency. Evidence verdict (clean, complete):
   - **LODO robustness: passed** — 0/55 date-drops flipped monotone's advantage (`flip_dates: []`), pooled Brier margin +0.0135 for monotone.
   - **Overs: no change** (n=896; WR 0.4766 / ROI@fair 0.1067 identical; calib −0.0307→−0.0301).
   - **Unders: monotone improves calibration (+0.0073 on shared n=835) and reduces the unders bleed — but does NOT make it positive**: deduped under ROI@fair −0.0272 (champion) → −0.0166 (monotone). Softens but does NOT obsolete the unders-floor problem.
   - **Verdict**: swap is coherent and robust, but unders-floor still requires its own decision (not obsoleted). Per Standing Rules, the actual champion swap is NOT an approved action — it needs explicit user sign-off after this evidence is reviewed.


## New Items

10. **[DONE 2026-09-01]** Two-tier test-gating. Added `.pre-commit-config.yaml` (local system hook: pytest on `tests/test_odds_ledger.py tests/test_real_bets.py tests/test_registries.py`). Ran `pre-commit install`; fast subset **28 passed in ~3.9s**. Full suite remains CI-only.

11. **[PROVENANCE AUDIT — COMPLETE 2026-08-27]** Grep for every place that aggregates the ledger; confirm each historical finding's generating script and whether it used canonical `dedupe_ledger_props`, a bespoke grouping, or raw rows; flag what needs recomputation. **Verdict (evidence-backed):**
    - **CLEAN — already on the fixed canonical `dedupe_ledger_props`** (live import → round-trips fixed signature automatically): all `artifacts/odds_log/_*.py` (`_analysis_extra`, `_audit_stratify_by_epoch`, `_audit_stratify_edges`, `_calibration_deep`, `_clv_snapshot`, `_timing_results`) + production `grade_odds_ledger.py`, `build_automation_self_check.py`, `line_policy_settled_lookback`, `clv_basis_reconcile`, `weekly_kpi_report`.
    - **RESOLVED specific concern:** **favorite/dog ROI splits + line×side splits** come from `_audit_stratify_edges.py` (lines 85–124), which calls canonical `dedupe_ledger_props` — **CLEAN, no recompute.**
    - **BESPOKE but side-aware — unaffected by over/under merge bug:** `keep_best_available_lines` (`src/Python/notebook_analysis_utils.py`, keyed on `(game_date, player_name, side)`) used by `build_policy_governance_report.py` + `policy_simulator.py`. Key already includes `side`, so it never had item-4's bug. (It intentionally collapses across LINES per game/player/side — different, intended semantic, not a regression.) No recompute.
    - **AT-RISK — aggregates RAW settled rows, bypasses canonical dedupe (recompute under fixed logic):**
      - `build_runtime_monitoring_snapshot.py` `_compute_floor_table`/`_compute_monthly_regime`/`_compute_edge_deciles` (roi/pnl on raw rows). Quantified: raw settled **1118 / +$576.15**, deduped **643 / +$84.51**. The `daily_kpi_loop_last_run.json` `total_pnl=$+1041.04` is a stale raw-row artifact of this path. NOTE: `_compute_slippage_segments` segments *by book*, intentionally raw — leave it.
      - `edge_floor_sweep_governance.py` `_load_settled_ledger` (line 72): raw settled.
      - `policy_calibration_uncertainty_sweep.py` `_load_settled_ledger` (line 136): raw settled.
      - `build_daily_operator_summary.py` `_ledger_snapshot` (line 40): per-day stake/pnl/roi on raw settled rows (DK+FD pairs double-counted per day).
    - **ORPHAN — generator not in repo (same class as item 7):** `regime_model_report.json` (`is_fav`/`is_over` coefficients; 939/999-bet regime analysis) has **no source script** in the repo — only the artifact remains. Provenance cannot be confirmed; do not cite its coefficients as settled until the generator is restored.
    - **NOT AFFECTED (different data domain):** `build_board_ledger_reconciliation.py` (targets `status=="open"` slate occupancy, not settled ROI); the A1/champion side-strat audit (2025 model open universe, not the settled paper ledger — consistent with item 9).
    - **Next (approved, not blocking):** add `dedupe_ledger_props(settled)` to the four at-risk aggregators above (keeping slippage-segments raw-by-book) + a regression test. Do NOT touch the orphan regime artifact.
    11-followup. **[DONE 2026-08-27 — aggregator dedupe fix]** Wired canonical `dedupe_ledger_props` into the producer + all four at-risk aggregators: `grade_odds_ledger.py` (`--status` PnL sum, `--curve` n_settled), `build_runtime_monitoring_snapshot.py` (floor/monthly/deciles use deduped; slippage segments keep raw-by-book), `edge_floor_sweep_governance.py` + `policy_calibration_uncertainty_sweep.py` (`_load_settled_ledger`), `build_daily_operator_summary.py` (`_ledger_snapshot` daily ROI/PnL). Added regression test `test_dedupe_ledger_props_pnl_not_double_counted` (proves DK+FD pair is not double-counted in PnL aggregation). All 5 files py_compile; `tests/test_odds_ledger.py` 13/13 green. **Live-verified 2026-08-27**: `grade_odds_ledger.py --status` printed `settled=643 total_pnl=+$84.51` (was 1118/+$576.15 raw; stale loop artifact +$1041.04). Regenerated `daily_kpi_loop_last_run.json` via `run_daily_kpi_loop.py --skip-notebooks` → `n_settled=653` (deduped; +~10 settled during run). **Refresh 2026-09-01**: after more settled days, deduped ledger is `settled=790 total_pnl=+$10.55` (ROI ≈ +0.05%); full-cohort CLV reconcile is `n_closed=493`, `price_devig_gt0=0.544` (was 441 / 0.551 on 2026-08-27). Note: dashboard `_dedupe_frame` keys on `book` too — only exact-dupe removal, not canonical cross-book dedupe (potential item-11 follow-up). **(Item 11 follow-up now COMPLETE; reordered to run before item 10 per user approval.)**

12. **[WAITING ON USER] Item 6 backfill** — still needs your decision-time `bet_price`/`stake`/`pnl` for the 8 confirmed tickets (Valdez, Suarez, Messick, Skenes, Melton, G.Rodriguez, Cantillo, Sasaki) plus the 9th ticket's identity, to complete the real-bet ledger write.

13. **[APPROVED — DEFERRED] Local MLflow Tracking (thin v1).** Useful when actively iterating Strikeout/TBF train or Optuna — **not** on the critical path for this ops cycle (wrong tool for freeze/null/CLV/veto work). See Session Snapshot → **DEFERRED**. Resume when you ask or when train iteration restarts; do not jump here mid-ops.

14. **[DONE research 2026-09-01 — promote gated] Granular open calibration challenger (ROI path).** Fit line / line-bucket (and optional side-aware apply) isotonic/Platt on **open 2025–2026** with chrono-safe holdout; score **post-freeze** as pure OOS on skill vs market + shadow KING ROI. Do not refit on post-freeze tickets. Do not edit live calibrator / KING without sign-off. Script: production/ops/fit_granular_open_calibration.py.



## Next Session — Open Questions & Plan (evergreen)
> **Not a second backlog.** Canonical live plan = Session Snapshot → **PAST / PRESENT / FORWARD / DEFERRED** (top of this file). Checklists below are a short mirror only.

**Waiting on user (blocks these):**

**Waiting on user (blocks these):**

- [ ] Confirm 2.5/3.5 over style — **data rec 2026-09-11: freeze current probation** (from the archived CLV + Hosting Plan; carried forward at split)
- [ ] **Dashboard v1** — parked until backend #113 is green; say go to unpark (from the archived CLV + Hosting Plan; carried forward at split)
- [ ] `git push origin HEAD` so remote has promoted 4.5-over veto.
- [ ] Ops Checkpoint A review: 5 owner questions (`docs/reference/reports/ops_contracts_2026-09-30.md`, defaults YES) + OPS-1 defaults sign-off.
- [ ] Scoped infra/docs commit checkpoint (writers paused during staging; model/production/ledger files excluded).
- [ ] Item 6/#12: per-ticket decision-time prices/stakes/pnl for the 8 + 9th identity.
- [ ] Item 9: explicit champion→monotone sign-off, or leave deferred (not needed for 4.5 veto).

**Ready / operating now:**
- [x] Live `veto_4_5_over` + soft probation 2.5/3.5 — DONE 2026-09-01.
- [x] Weekly settle pack habit — re-run after each settle week.
- [ ] Item 13 MLflow — APPROVED but **DEFERRED** (wrong tool for this ops cycle).
- [ ] Optional polish: regenerate `manuscript.pdf`; dashboard dedupe → canonical `dedupe_ledger_props`.

**Blocked / parked (see DEFERRED + Execution Order):** Item 7 CUSUM rewrite; Item 2 history split; SSAC future-work 9–13.

**Historical polish notes** (2026-08-27 freshness sweep detail, ledger refresh figures): kept in git history; intentionally not repeated here so this section cannot compete with the Snapshot.


## Standing Rules (apply to all of the above)
- Never mutate historical labels (hold→bet relabeling) — always append new records instead.
- Every real-money conclusion requires ≥50 real tickets before being treated as evidence of edge. The current 9-ticket, +24.1% ROI record is now fully auditable (6W–3L, all outcomes confirmed) — a good start, not proof; don't let it drive stake-sizing yet.
- Verify settlement-rule parity (prediction-market vs. sportsbook K definitions, extra innings, early exits) before trusting any grading as final.
- Personal accounts/API keys only — never company-owned tooling for any of this.
- Do not touch `KING_PROFILE_AUG2026`, floors, staking, or the champion file without explicit sign-off after evidence is reviewed.
- **DEFERRED is binding:** Item 13 (MLflow) and other Snapshot → DEFERRED rows are not idle backlog to fill quiet turns. Do not scaffold/install them during an ops/policy week unless the user asks or the reopen condition is met.
- Prefer weekly settle-pack measurement and real-bet logging over new tooling while the live 4.5-over veto is the active experiment.
- A pre-registered sample-size gate that is *exactly* met (not comfortably exceeded) should be treated as "not yet conclusive" — do not size up or treat as validated edge until the sample comfortably clears the threshold with margin.
- **Measurement vs money (owner-locked 2026-09-11):** two jobs, never mixed. *Measurement* (are we right?) = devigged consensus median at the same snapshot (`consensus_cache.parquet`, never re-devig) for Brier/skill/CLV. *Money* (did we profit?) = juiced book-pair at the decision clock (DK else FD else next US book) for ROI/WR. Report both forever; cite which lane every number lives in. Dedupe (`dedupe_ledger_props`) is money-track aggregation only — selection stays per-quote, line×side cells stay per player O/U line.


## Parking Lot (new ideas noticed mid-task — do not act on these until the list above is clear)
- **Cheap agent stack (2026-09-02) — PARTIAL DONE:** ignore-files + agent-context rule shipped. Still parked: Cline/OpenCode + DeepSeek V4 Flash on Mac; kill Cursor Auto/credits; escalate Kimi/GLM; Claude escape hatch. Never route Lenovo work through Chinese APIs. Reopen when user starts Mac harness migrate.
- **Historical K CLV backfill (2026-09-02) — RESEARCH DONE, pull PARKED:** see `docs/reference/reports/historical_clv_odds_apis_2026-09-02.md`. Execute free HF + OddsPapi smoke then optional The Odds API month only when user asks. Do not start paid pull mid-ops week.
- **Book-quality filter — WONT_DO** (user 2026-09-01): books used for lines only; usually synced.
- **Juiced next-book vs DK+FD (2026-09-11 #123):** next-US-book fallback after DK/FD soaked BetRivers (n=1,001 of 2,077, WR 0.429). GO had said median. Waiting on owner which universe is canonical. Do not mix all-books ROI with DK+FD ROI.

- **Live A/B parallel ledgers:** score every opportunity under status_quo / veto_4_5 / asym16 even when only one rule is bet live.
- **Block bootstrap by game_date** for ROI/CLV CIs; do not bootstrap a line cell with n≈18 into a promote claim.
- **Real-bet first:** Item 6/#12 unblocks honest money ROI vs paper.
- **Optional soft veto:** size 2.5–3.5 overs at 0.5u instead of hard skip if learning value matters.
- Three-state action space (bet / prediction-market-watch / hold) as a cleaner replacement for the binary bet/hold flip.
- Calibration-drift monitor (recent-window WR 0.493 vs. all-time 0.534).
- Reliability/calibration bucket report (among props rated 0.7-0.8, what's the real hit rate).
- Cost-asymmetry-informed stake sizing (expected loss of missing a winner vs. betting a loser).
- Side asymmetry on real tickets: all 3 losses to date were Overs; every Under/low-line-Over hit. Worth a real-ticket side-conditional check once ledger reaches meaningful n, not a 9-shot pattern to bet on.
- **MLflow v2 (after Item 13):** Optuna callback → nested MLflow runs; log ensemble-sweep / null-lane decision metrics as separate experiments; optional Model Registry *mirror* of frozen champions (still not auto-promote).
- **W&B** only if you want hosted multi-machine dashboards; not needed for solo local research.
- **SSAC27 (MIT Sloan Sports Analytics Conference) — abstract deadline Oct 1, 2026.** Items **1–8 DONE**. Future-work 9–13 remain parked. Lead submission with modeling half; betting half stays demoted. Low-priority doc polish: move ablation/freshness self-notes to a Supplemental appendix.
- **Phase 10 pipeline-discovery + reusable-prop-platform prompt (2026-09-17) — CENSUS EXECUTED, design queued:** see PRESENT "PHASE 10 EXECUTED" + FORWARD Phase 10 workstreams (ARCH/DATA/PROP/SIM/EVAL/OBS/NB/OPS/TEST). Source file lives outside repo (`Downloads/Pipeline Discovery and Reusable Prop Platform Prompt.md`); content reconciled here, no second roadmap. Conflicts with FORWARD pickup box (no coding job until owner names it) and October sequencing (post-9/27) — design-only at most before then; no live/Modal/policy/model/schedule changes. Verified pre-checks: all 5 Modal schedules use `modal.Cron` (`modal_app.py:132,154,181,197,213`), so the Period-reset timing risk does not apply. Reopen when owner names the census or the October program starts.

- **GATE A CORRECTION COMMITTED 33e1f63 2026-10-09 (owner-authorized bounded numerical correction; 17 tests green; pre-commit passed; no push):** root cause = support truncation in cond24_binom (k>23 dropped from the uncollapsed conditional before expectation verification; NOT scipy, NOT dtype — builder verified vs exact Fraction reference at 4.7e-16). Fix: B conditional on full 0..n support, tail mapped via map24 (same as C), expectations via math.fsum; frozen 1e-9 gate UNCHANGED and passes all 4,446 rows x all supported n. Evidence wording corrected per owner: support-mapping identity verified over n=1..60 x 37-point p grid (max diff 4.7e-14); all 38 exported numeric columns x 4,446 rows max diff 7.3e-14 (float64 rounding; NOT claimed bit-identical); boolean flags identical; paired effects unchanged (B-A -0.033037*, C-B +0.000098*, C-A -0.032939*). Failed first validation preserved (pa-gateA-validation-20261009a) alongside passing full-row run (...20261009b). Negative tests (shifted PMF, wrong-sequence) still fail gate; edge tests p in {0,0.001,0.5,0.999,1} x n<=60 pass. Doc defect C closed. Chat-two closure review can proceed at c0805be + b2d7140 + 33e1f63. Remaining before pilot scoring: BF reconstruction (fixed recipe, pre-2025 fit, serialization, reload parity, availability audit — no automatic embargo per owner correction), pilot sealing, outcome authorization.
- **ADAPTER COMMIT 2026-10-09 (owner-authorized trio; see PRESENT top entry):** pinned latest-cutoff-valid-snapshot rule (NO older-revision substitution; naive cutoff rejected before any UTC coercion); naive-rejection + no-substitution tests added (25 green); dry run re-verified 32/110/142; committed after this line.

- **ADAPTER D1-D4 REMEDIATION COMPLETE (UNCOMMITTED, awaiting receipt review) 2026-10-09:** D1 coverage basis documented in runner receipts (team-game lineups != eligible pitcher-forecast count; population fixed only at sealing); D2 adapter now delegates to the canonical canonical_team_code (src/Python/daily_lineups.py:155, read-only import, identity-asserted in test; hand-rolled alias map removed); D3 mixed lineup_status within one latest snapshot -> explicit REASON_MIXED_STATUS fallback with statuses preserved; D4 stored-naive timestamp interpretation documented at the parse site per the writer contract, dead _receipt helper removed. 15 adapter tests green (incl. canonical-parity + mixed-status tests); dry-run re-verified unchanged 32/110/142 with the canonical mapper. Uncommitted: adapter, runner, tests. BF reconstruction (availability audit + training eligibility manifest + single pre-2025 fit + serialization + fresh-process reload parity) is the next deliverable; sealing waits on adapter closure review, aggregation closure review, and BF reload verification.

- **ADAPTER D1-D4 FINAL CLOSURE STATE (UNCOMMITTED, awaiting receipt approval) 2026-10-09:** D3 diagnosed per owner demand ? the shuffle divergence was a FIXTURE bug (rows[4] carried CUTOFF 17:00 vs 15:00 for the rest, splitting the snapshot into two revisions), not adapter control flow or dict ordering; both orders now produce identical decisions/reasons (r1==r2 verified directly); mixed-status fixture corrected to same-fetch. D1: cutoff_basis=max_fetch_per_team_game + status/completeness-availability-upper-bound wording added to runner receipts. D2: 30 canonical codes verified through the adapter selection path in an automated test (import verified side-effect-free). D4: malformed timestamps -> explicit malformed_fetched_at fallback (nulls and hard parse failures both). 35 tests green (18 adapter + 11 aggregation + 6 capture legacy suite). Uncommitted: adapter, runner, tests; commit only after receipt approval. BF reconstruction continues independently (lower bound frozen from training spec, exclusive upper 2025-01-01, feature-history vs training-row bounds separated, historical labels authorized, pilot outcomes locked).

- **CHAT 3 LANE CLOSED 2026-10-19 (maintenance/quality-baseline lane; final handoff artifact cd9983b + GitHub reconciliation receipt f6a5e05, both delivered via PR #18):** eight PRs merged with receipts (#4, #11, #12, #13, #14, #15, #8, #10); cleanup skill system live (.cursor/skills/repo-*); owner-blocked items S-B (dependency tier choices, patch in PR #17) and S-C (dead-module out-of-tree ruling) handed off with exact decisions; deviations recorded (1321b72 direct push, #10 integration bypass); full accounting in docs/reference/reports/chat3_final_handoff_2026-10-19.md.
- **HANDOFF TIP CORRECTION (Chat 3):** the final handoff artifact is commit cd9983b95a281220d5335fcf8039407f798b47cb (chat3_final_handoff_2026-10-19.md, includes the GitHub reconciliation receipt f6a5e05 + dual-window consolidation 92ae97f); branch tip is cd9983b - supersede the f6a5e05 tip reference above.

## Historical Archive

All dated Session Snapshot bullets (2026-08 through 2026-10), the
CLV + Hosting Plan (2026-09-08), the Strategy Plan (2026-09-01), and
the SSAC27 Track are preserved verbatim in
[`docs/reference/reports/backlog_archive_2026-10-21.md`](reference/reports/backlog_archive_2026-10-21.md).
Nothing was deleted.

## Research lane (pregame-pa-ext-v2, PR #34)

M0 v2 executed (both endpoints PASS, development-only); C-B1 exposure
profile closed (LOST); ablation count-RPS canonical (FULL 1.31744,
PITCHER 1.33457); market baseline verified (close beats model);
calibration runner implemented and reviewed (NOT executed); 2026
holdout untouched. Detailed experiment history:
`docs/reference/reports/experiment_impact_ledger_2026-10-22.md`.

Next (2026-10-27): lineup prediction-path reconciliation -
specification published at
[`docs/reference/reports/lineup_path_reconciliation_spec_2026-10-27.md`](reference/reports/lineup_path_reconciliation_spec_2026-10-27.md)
(measurement-reconciliation candidate; **Stage A only active** -
prediction-path equivalence (Stage A READS historical y as the one permitted strictly-prior input; target-outcome scoring NOT performed); Stage B deferred and NOT
authorized by a Stage A PASS; awaiting Chat 2 spec review then owner
authorization; NOT executed). Calibration execution remains gated
behind PR #48 merge + owner authorization; frozen at `1321e4b`.

Next (2026-10-27): lineup prediction-path reconciliation -
specification published at
[`docs/reference/reports/lineup_path_reconciliation_spec_2026-10-27.md`](reference/reports/lineup_path_reconciliation_spec_2026-10-27.md)
(measurement-reconciliation candidate; **Stage A only active** -
prediction-path equivalence (Stage A READS historical y as the one permitted strictly-prior input; target-outcome scoring NOT performed); Stage B deferred and NOT
authorized by a Stage A PASS; awaiting Chat 2 spec review then owner
authorization; NOT executed). Calibration execution remains gated
behind PR #48 merge + owner authorization; frozen at `1321e4b`.

### Two-scorecard design (baseline benchmark; recorded 2026-10-27)

Two SEPARATE scorecards, never merged into one number:

1. **Full-distribution scorecard** (forecast quality): registered
   count-RPS primary; baseline-ladder arms (P population / S simple
   pitcher / F frozen incumbent; `baseline_ladder.py`, PR #50,
   dependent on PR #49); estimation from block_2024H2 outcomes only;
   primary contrast S vs F declared (delta = RPS(S) - RPS(F)); P
   contrasts descriptive. Diagnostics: capped-mean residual MAE/RMSE
   (bucket-23 cap labeled separately from uncapped E[K]),
   threshold reliability with bin counts, ECE/MCE non-decisive.
2. **Same-contract market scorecard** (separate measurement lane,
   NOT AUTHORIZED for new scoring): reuse the repaired
   `market_eval_k.py` v3 full-key machinery (identity filter
   `verified_odds_for_start`, per-start consensus, true T-5 close
   cohort) for model-vs-market paired over/under log loss on identical
   contracts. Existing verified quote coverage
   (`results_market_eval_k_v1/RESULT_RECORD.md`): 825,326 quotes ->
   406,285 own-player -> 82,722 near-close -> 4,358 consensuses ->
   4,336 model-cohort eligible; 2025H1 true T-5 close n=2,154 (2,182
   2024 prior-evening rows). Executable EV/ROI stay in the money lane,
   never mixed with measurement.

### Split / exposure table (roles separated; verified from preserved evidence; recorded 2026-10-28; old windows preserved verbatim -- never rewritten)

**Arm-history statement (explicit):** baseline arms P and S estimate from **block_2024H2 start outcomes only** (2,334 start rows dated 2024-07-01..2024-12-31 in `start_metrics_v2`). Arm F (frozen incumbent) uses the frozen per-block EXPANDING recipe: coefficients fit on PA rows dated up to each block's train end (2024-06-30 for the 2024H2 model; 2024-12-31 for the 2025H1 model; 2025-06-30 for the confirm model) plus strictly-prior feature states -- so F's 2025H1 predictions consume 2024H2 PA outcomes in both coefficients and features. **P/S vs F is a PACKAGE benchmark, not equal-history model attribution.**

| window | dates | coefficient fitting | feature history | baseline estimation (P/S) | designated evaluation | actual executed uses (as recorded) |
|---|---|---|---|---|---|---|
| Pre-window history | 2022-04-07 .. 2024-06-30 | YES -- expanding PA-row fits (block train ends 2024-06-30); verified reconstruction n_fit 730,841 PA rows (PA table holds 731,347 rows over 2022-04-07..2025-09-28) | YES -- strictly-prior states for every scored start (`entity_daily_state`) | NO | NO | checkpoint reconstruction (one authorized run, MLflow-verified); ledger feature states; BF builder priors |
| block_2024H2 | 2024-07-01 .. 2024-12-31 | YES for the 2025H1/confirm models (PA rows <= their train ends); NO for the 2024H2 model | YES | YES -- P/S training window (2,334 start rows; declared interval 2024-07-01..2024-12-31) | Designated: calibration FIT cohort (2,314, `d38b10aa...`) -- **UNEXECUTED** | count-agg v1 + ablation canonical scoring (4,823-start eligible cohort); market-eval 2024 prior-evening rows (n=2,182, relabeled, excluded from close comparisons) |
| block_2025H1 | 2025-01-01 .. 2025-06-30 | NO (its model trains <= 2024-12-31) | YES (its PA rows feed confirm-period feature states) | NO (reserved) | Designated: calibration EVAL cohort (2,509, `f77d7a66...`) -- **UNEXECUTED**; baseline-ladder evaluation cohort (2,509) | Question A scoring; market-eval 2025H1 true T-5 close (n=2,154); ablation count-RPS scoring |
| confirm_2025H2 (protected) | 2025-07-01 .. 2025-09-28 | NO (its model trains <= 2025-06-30; confirm outcomes never fit) | partial -- its PA rows exist in the PA table but no scored window is downstream | NO | Designated: confirmation ("2025-select/2026-judge once, post-9/27, pre-registered") -- **UNEXECUTED** | Verified scoped access: slot/lineup ROW-COUNT and label metadata only (20,952 slot rows, 2,328 starts, 144 unusable-row reasons read as metadata; 2,328 past-boundary lineups starts counted for the Stage A boundary fix); ZERO outcome scoring, ZERO fitting |
| 2026 | 2026 season | -- | -- | -- | Designated: retrospective/confirmatory only (no-2026-tuning rule) | Verified ZERO access: no registered artifact contains 2026 rows (PA table and start_metrics end 2025-09-28); nothing read, scored, or fit |

Notes: (1) calibration is DESIGNATED on its cohorts but UNEXECUTED (runner merged, gated at `1321e4b`). (2) The historical 277-start ablation subset and the invalid lineup diagnostic are preserved superseded evidence, not current window uses. (3) `start_metrics_v2` window counts verified: 2,334 / 2,532 / 2,328 (2024H2 / 2025H1 / 2025H2).

### Proposed calendar walk-forward (PROPOSAL ONLY -- no data access or scoring authorized)

After the baseline scorecard closes, feature-experiment and tuning folds would be calendar-anchored expanding windows inside the dev evidence, with confirmation untouched: F1 fit 2024-07-01..2024-12-31 -> score 2025-01-01..2025-03-31; F2 fit <= 2025-03-31 -> score 2025-04-01..2025-06-30; optional F3 fold only if the owner extends the dev evidence (never confirm/2026 for tuning). Every fold scored with the registered count-RPS + slate-date paired scheme; all folds reported (no fold selection); Holm across the declared contrasts; the frozen incumbent stays fixed; each feature challenger pre-registered before its fold. This is a PROPOSAL ONLY: no new data access, scoring, or fitting is authorized by it.

### Model inventory (compact; for the architect; 2026-10-27)

| lane | entry point | target | estimator | checkpoint / artifact | prediction unit | downstream consumer | evidence status |
|---|---|---|---|---|---|---|---|
| Production k-rate (frozen champion) | `production/ops/run_daily.py`; blend selection `production/ops/live_krate_ensemble.json` | pregame k-rate per qualifying starter | LightGBM blend (0.00 sparse72 / 0.60 sparse72_monotone / 0.40 final58) + Ridge TBF + Poisson count layer + WS1c per-line Platt | frozen 2025-lock champion; policy KING_AUG2026 (`kpi_policy.json`, `line_floor_policy.json`) | per pitcher-game k-rate -> count distribution | policy filter -> sizing (flat $50u, 1/16-Kelly anchor) | frozen; retrain path closed; no 2026 tuning; `tests/test_live_stack_pin.py` |
| PA research (pregame-pa-ext-v2) | `research/offseason_2026/pregame_pa_ext/` (`build_checkpoint.py` -> `m0_multiclass.py`) | per-PA outcome probabilities (`p_h3_raw` per projected slot) | L3 ridge logistic (tree challenger KILLED 2026-09-30; LightGBM equal-information CLOSED - logistic stays the PA representative) | `h3_raw_checkpoint.json`, pin `176fb18b...`, raw sha `d266a1cd...` | per (start, slot) PA | count layer (ledger slots + BF aggregation) -> per-start K PMF -> count-RPS / market-eval / calibration | M0 v2 development acceptance only (NOT production approval); ablation / aggregation / C-B1 / recency resolved; calibration implemented, unexecuted |
| Docs lane | PR #49 (`docs/lineup-path-reconciliation-spec`, head `b2090cc`) | Stage A specification | n/a | n/a | n/a | Chat 2 spec review -> owner authorization | in review |

