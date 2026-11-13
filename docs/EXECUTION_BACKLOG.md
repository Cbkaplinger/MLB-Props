# MLB Props â€” Execution Backlog & Directive
> **This is the ONE holy file.** Single source of truth for what is approved, blocked, waiting on the user, and parked. Do NOT create parallel backlog files. When the user drags in a markdown file, reconcile it INTO this file, then it / the old file goes away. Keep it evergreen (see Evergreen Rule below).
>
> **Always open this file first** (`docs/EXECUTION_BACKLOG.md`). After every user prompt / agent turn that changes work state, update the **Session Snapshot** before ending.
> Also linked from root `AGENTS.md` and `.cursor/rules/execution-backlog.mdc` so every agent session sees this as master.

### Document hierarchy (this file wins)
| Kind | Path | Role vs this backlog |
| --- | --- | --- |
| **Master work state** | `docs/EXECUTION_BACKLOG.md` (this file) | Approvals, Snapshot PAST/PRESENT/FORWARD/DEFERRED, standing ops rules |
| Agent entry pointer | `AGENTS.md`, `.cursor/rules/execution-backlog.mdc` | Point here only â€” no second queue |
| Research constraints | `docs/reference/research_assistant_instructions.md` | How to build/leakage-safe â€” **not** a todo list |
| Ops runbooks | `production/README.md`, `INDEX.md`, `RUNBOOK.md` | How to run commands |
| Dated evidence | `docs/reference/reports/*.md` | Point-in-time reports; must say if SUPERSEDED and point here for â€œwhat nextâ€ |
| OpenCode paste brief | `docs/reference/opencode_handoff.md` | Coworker briefing 2026-09-11 (replay era). **Not** a second queue. Pack #113 built; juiced #123 measured; totals #124 pulled. |
| Frozen-model replay spec | `docs/reference/oddsapi_replay_architecture.md` | How to backtest 2025-present Odds API open/close with the model frozen â€” **not** a queue. Freeze/work/product partition. Inventory: `reports/oddsapi_replay_inventory_2026-09-11.md`. |
| Golden metrics | `docs/reference/golden_metrics.md` | Canonical numbers + JSON sources. Cite, do not recompute. |
| Paper / resume | `docs/paper/manuscript.md`, `resume-summary.md` | Publication narrative â€” not the live work queue |
| Cleanup history | `docs/archive/CLEANUP_LOG.md` | Historical cleanup log â€” not instructions |
| Canonical surfaces | `docs/reference/repo_canonical_map.md` | What code/docs are canonical vs archive |

If another docâ€™s â€œnext stepsâ€ disagree with the Session Snapshot, **this file wins**. Fix the subordinate doc to redirect here.

## Directive (read this first, every session)
You have blanket approval for every item below marked APPROVED. Execute them **in order**; do not re-ask on anything already approved. Do not start new discovery/analysis/philosophizing until every APPROVED item is DONE or marked BLOCKED with a one-line reason. Notice something interesting mid-task? Put it in "Parking Lot," don't chase it. Report only on item completion or a true block â€” not every intermediate find.

### Iterative session loop (required)
1. **Read** this file (Snapshot â†’ Waiting on user â†’ Forward â†’ **Deferred** â†’ Standing Rules).
2. **Do** the next APPROVED item(s) only â€” **never** pull work from **DEFERRED** unless the user asks or the reopen condition is clearly met.
3. **Write back** before the turn ends â€” Snapshot must always have four labeled blocks:
   - **PAST** â€” durable completed work (what already shipped).
   - **PRESENT** â€” where we are now / what just finished this turn.
   - **FORWARD** â€” concrete ordered plan for the next session(s).
   - **DEFERRED** â€” approved-or-parked work that is *not* next (with why + reopen trigger).
   - Also refresh Waiting on user; add ideas to Parking Lot; never silent-drop threads.
4. Tell the user briefly what changed and point them back here for the plan.

**Evergreen Rule (every session):** after reporting, reconcile THIS file against what actually happened â€” update PAST/PRESENT/FORWARD/**DEFERRED**, item statuses, Parking Lot, and **pre-write the next session's plan** so no thread is lost. Close every session with this file reflecting "here is where we were, where we are, where we're heading next, and what we are deliberately not doing yet."

---


## Session snapshot - identity-exclusion policy PR (2026-11-12)

### PAST

- Paid-morning baseline: FIVE authorized attempts; four closed with
  preserved receipts: (1) PR #86 - 3-key morning-scan identity stop
  (comment 6816558623); (2) PR #87 - four-key binding-gate refusal
  (comment 6829936974); (3) PR #88 - four-key MATCH + duplicate-side
  refusal (comment 6838485286); (4) PR #89 diagnostic run - 26 close
  same_time_conflicts diagnosed (comment 6857588715). The FIFTH (PR #90
  recovery, integrated main aa61986) SUCCEEDED: baseline produced
  (receipt PR #90 comment 6861125006; artifact index 6861289910).
- PR #87 (identity-exclusion policy), PR #88 (control-vs-books
  benchmark + four-key binding), PR #89 (quote-integrity diagnostics +
  idempotent normalization), PR #90 (close-conflict drop-and-count)
  all merged (mains 16a99b0 / 0977a2d / 19a4d89 / aa61986).
- Market-only T-5h replay implemented + accepted + MERGED (PR #86).
- Board-coverage probes, boundary follow-up, recovered-ideas register:
  CLOSED as recorded in prior snapshots.

### PRESENT

- **CONSENSUS SHARED-POPULATION POLICY (PR, this branch):** Packet B's
  one authorized attempt refused at the exact-cohort gate (2,509 ->
  2,154 model-vs-consensus; receipt PR #91 comment 6862633285; the
  failed run and its receipts are PRESERVED). The bounded follow-up:
  runner --consensus-policy shared_population (opt-in; default refusal
  unchanged) -- model-vs-consensus scored ONLY on the declared shared
  population; ORIGINAL 2,509 cohort stays the coverage denominator;
  matched/unmatched start keys + reason codes
  (no_near_close_quotes / no_two_sided_quote_at_any_line /
  consensus_unavailable_other) derived BEFORE scoring and persisted as
  consensus_matched_starts.parquet / consensus_unmatched_starts.parquet;
  book/LTBO populations separate with per-book denominators; all
  duplicate/identity/timestamp/protected-data/PMF refusals preserved.
  Tests: 5 new through main() (tests/test_consensus_shared_population.py,
  incl. default-refusal-preserved and hand-computed shared-population
  metrics); combined gates 104 passed. NOT EXECUTED on real data (any
  rerun needs a new owner order).
- Packet B remains otherwise unauthorized; NEAR-CLOSE DEVELOPMENT
  labeling unchanged.### PRESENT

- **PACKET B OWNER-DECISION BRIEF PREPARED (PR, this branch):** the
  existing control_vs_books evaluation packet now carries the complete
  Packet B brief (section "PACKET B OWNER-DECISION BRIEF"): the
  question (registered control PMF vs near-close books/LTBO), the
  accepted runner identity (run_control_vs_books.py at 735bb54 /
  main aa61986; ack EXECUTE-CONTROL-VS-BOOKS-V1), the exact command
  with literal paths, honest full-file eager-read disclosure
  (book_lines/envelope/workload/id-map all decoded for ALL years with
  in-memory window filtering - the window is NOT pre-decode
  protection), the panel-not-consumed guarantee, timing/identity
  limitations (NEAR-CLOSE label; commence semantics; confirmed-lineup
  gap; tiebreak-not-validation), fresh output directory and stop
  conditions. Packet B remains UNAUTHORIZED - the brief is for the
  owner's decision only. No new features were added to prepare it.
- **PACKET A RECONCILED (executed + closed):** the paid-morning 2025H1
  market-only baseline was PRODUCED on 2026-11-13 (exit 0; code
  735bb54, main aa61986; receipt PR #90 comment 6861125006; artifact
  index comment 6861289910). Preserved artifacts: baseline parquet
  e4348d3b..., report 18cd418d..., policy-tagged integrity sidecar
  53b989e0..., preserved pre-#90 diagnostic c590d3b6... untouched.
  Headline (market-only, no model-edge claim): 19,800 candidates;
  entry-eligible 5,441/19,797; valid close 4,934/5,441; mean movement
  -0.0869 pp; positive-CLV shares over 0.4270 / under 0.4497; entry
  flat-1u ROI over -0.0452 / under -0.0782 units per unit. Single-run
  permission CONSUMED; no reruns.

### FORWARD

1. Baseline recovery: PR #87 MERGED (main 999ffbe); the amended
   single run was EXECUTED once on integrated main and REFUSED at the
   binding gate, exit 1: the morning+close identity union detected a
   FOURTH ambiguous reduced key (2025-04-09, castillo luis, 4.5)
   beyond the three receipt-bound keys (all three confirmed). No
   outputs; panel exception NOT consumed; receipt preserved (PR #87
   comment 6829936974). Next decision (owner): amend the binding to
   the four-key set (new order) or declare close-side treatment.
2. Current-control-versus-books benchmark EXECUTION-READY (PR #88,
   this branch): the gated runner is complete with output discipline
   (tables as parquet; scores/coverage JSON via fail-loud conversion,
   never default=str; receipt_final written LAST - output-write
   failure test proves no completed receipt on failure); required
   args validated before any output/decode; consumed identities
   recorded (cohort content hash, pinned artifacts, book_lines/
   envelope/workload hashes, bridge source + card manifest sha).
   Timing/identity contract recorded in every output: commence
   semantics (vendor-scheduled commence, NOT observed first pitch),
   near-close interpretation with the confirmed-lineup limitation,
   and the declared per-mapping tie-break gap (closest-date + id-
   order tiebreak is NOT independent identity validation; aggregate
   counts only in existing metadata). Synthetic main-entry success
   test reads outputs back with hand-computed log-loss/Brier values.
   Four-key binding amendment PREPARED
   (expected_exclusions_2025H1.json: three receipt keys + castillo
   luis 2025-04-09; union-exclusion policy unchanged; lineage +
   not-a-duplicate caveat recorded). Combined gates: 83 passed.
   Two execution packets proposed (PR #88 handoff): (A) paid-morning
   baseline recovery (needs a recorded order with the amended
   binding); (B) control-vs-books near-close benchmark (ack
   EXECUTE-CONTROL-VS-BOOKS-V1 + registered gate). NOT EXECUTED.
3. Boundary-exception coverage follow-up: implemented + 8 synthetic
   tests; NOT RUN on real odds (owner authorization; near-close
   labeling preserved).
4. Scientific queue: no other task assigned.

### DEFERRED

- No new framework, model, calibration, tuning, dashboard, or
  consensus features.

## Session snapshot - baseline K-PMF diagnostic (2026-11-11)

### PAST

- Consolidation closeout (Chat 3) integrated (PR #78); Chat 3 CLOSED.
- Dual-contract harness baseline checkpoint reviewed PASS (Chat 2,
  `165b7a9`).
- Control-arm parity selection implemented, reviewed, integrated (PR
  #79, reviewed head `05bab809...`); explicit arm registry in
  `parity_platoon_candidate_v1.py`; challenger semantics unchanged.
- Control-arm parity EXECUTED once 2026-11-10: PASS, exact zero both
  grains (2,509 starts; 22,581 PA rows; 60,216 PMF rows; max abs diff
  0.0; receipt chain `7b239920...` -> COMPLETED); Chat 2 VERIFIED
  (superseding verdict, PR #79 comment 6779379426). Result record at
  `...\diagnostics\parity_platoon_candidate_v1_control_arm\`.
- Registered paired comparison (platoon_information_v1) reproduced
  BIT-EXACTLY once (owner-authorized; PR #80 record; every output
  artifact byte-identical, receipt_final = `b1b91357...224ba`).
- Harness-to-market shadow bridge implemented, reviewed, integrated
  (PR #81, merged at main `6f45d37...`).
- Confirmation-cohort reconciliation: dev-exhausted 2,509 cohort
  (`f77d7a66...`) is NOT reserved; genuinely reserved population =
  confirm_2025H2 (2,328 starts), INSPECTED (pre-offseason ladder/
  market-eval scoring) - only reusable as a single fresh
  pre-registered contract.

### PRESENT

- **BASELINE K-PMF DIAGNOSTIC IMPLEMENTED (owner-assigned, this PR):**
  `research/offseason_2026/pregame_pa_ext/count_pmf_diagnostic.py` -
  thin keyed glue over the EXISTING registered scorers (no duplicated
  math): `kcount_combiner.count_logscore` (natural log, 1e-12 clip;
  SIGN CONFIRMED FROM CODE: returns POSITIVE log loss),
  `kcount_combiner.count_rps` (summed-CDF-squared, no clip),
  `market_eval_k.model_p_over` (the eight canonical half-integer
  lines), `adapter.check_pmf` (PMF validity), strict bucket-label
  validation (reused bridge contract). Contract: complete start
  identity (game_pk, side, pitcher); unique/non-null observed and
  start/bucket keys; complete 24-bucket support; observed K finite/
  nonnegative/integer-valued; EXACT forecast/observation key equality
  (mismatch reports both directions then refuses - no silent inner
  join); equal weight per matched start; denominators = matched
  starts; K >= 23 = declared overflow category (bucket 23); fixed
  declared reliability bins [0,.1)...[.9,1] (p=1 in the last bin;
  empty bins report null means); per-arm results separate + paired
  challenger-minus-control deltas on identical keys; conventions
  returned in every result.
- **Label source ESTABLISHED from committed construction code:**
  `prepare_assessment_2025H1.py` preserves EVERY completed PA of the
  requested starters (anti-join start reconciliation, invalid-label
  refusal), so `assessment_2025H1_v1.parquet` supplies complete
  full-start realized K via the registered derivation (class_label
  == 0 count, as in platoon_comparison); it covers exactly the
  requested 2025H1 starters - any key gap refuses (reported) rather
  than scoring partially.
- Tests: `tests/test_count_pmf_diagnostic.py` 16 green (hand-computed
  log-score sign + RPS incl. overflow; half-line boundaries;
  fixed-bin edges, p=0/p=1, empty bins; paired deltas + shuffled-row
  alignment; duplicate/null keys; both-direction key mismatch;
  malformed labels/observed K/PMF; CLI ack/write-once/success).
  Pre-commit trio + bridge suite 43 green.
- **FIRST AUTHORIZED EXECUTION: REGISTERED GATE REFUSAL (execution of
  record; no output written, no failure receipt exists).** Preflight
  (procedural, disclosed): reference receipt hash-verified
  (`b1b91357...224ba`); complete expected PMF hash recovered from its
  manifest - `8c5c849c289ecd65a561719d9ca7e9ce0975e6e0c377107fb6587c
  475b3a4916` (the packet's paste was corrupted mid-string); both
  input disk hashes MATCHED; destination absent. Execution HEAD
  `a830dda`; exit 1 at the exact-key gate:
  `missing_from_observed=0; missing_from_forecast=23` - the prepared
  assessment covers ALL 2,532 requested 2025H1 starters while the
  forecast side is the 2,509-start eligible cohort (the registered
  eligible-cohort exclusions; count consistent with the partition
  table). No tuning, no retry.
- **COHORT CONTRACT AMENDMENT (this PR):** the diagnostic now takes an
  explicit `--cohort-keys` input + `--expected-cohort-hash` (registered
  `bk._cohort_hash` convention) and explicitly evaluates the declared
  eligible cohort: forecast keys must equal the cohort exactly;
  observations are restricted to the cohort and must then cover it
  exactly; observed-only starts outside the cohort are recorded as
  DECLARED EXCLUSIONS with full key lists (eligibility never derived
  from forecast availability; no hardcoded discrepancy count). Tests
  prove the excluded keys are exactly cohort-set-difference members
  (exact key identity, not count subtraction): broader observation
  source, missing eligible observations, missing/extra forecasts, bad
  cohort identity. 16 diagnostic tests green (59 with trio + bridge).
  The failed command + refusal error are preserved in this record; NO
  failure receipt exists for that run (destination was never created).

- **Opening-clock reconciliation (2026-11-11):** paid-lake clocks are
  close (commence-5min), morning (T-5h), board (fixed 12:00Z / 8am ET,
  all-EDT edge documented), open18 (-18h; T-24h/-30h dead per probe);
  Friend opens are vendor-designated -12h/-6h (97/3). 2025 board-clock
  coverage UNKNOWN (2023/24 sampled only). Replay baseline rows
  renamed over_hit (panel y is binary, not full-start K). Deferred
  hypothesis (corrected; not implemented): recency weighting of the
  model's EW features (fixed 90d half-life, self-relative, unshrunk -
  the committed stale-form finding: a 2022-only batter presents stale
  form as current at a 2025 start). The batter-recency challenger was
  REJECTED and recency-batch-v1 showed development-only gains; no
  implementation without a new registered reason.
- **RECOVERED-IDEAS REGISTER RECONCILED (owner-supplied, this PR):**
  docs/reference/reports/recovered_research_ideas_register_2026-11-11.md
  (26 entries R01-R26; provenance corrected: R02-R09 directly quoted in
  conversation, R26 assistant-originated and withdrawn). Dispositions:
  R05 Markov, R02 Holt, R03 state-space, R04 change-point, R06-R08
  survival/count families = DEFERRED with revisit triggers in the
  register (R08 note: Poisson is already the registered count-layer
  default, src/Python/count_layer.py); R09 PMF-vs-moments = design
  principle already implemented (24-bucket PMFs throughout); R10-R13 =
  active/implemented this checkpoint; R14 RotoGrinders = future
  capture, historical morning availability unestablished; R15
  pitch-by-pitch = PARKED; R16 = operating requirement; R17
  calibration/blending = provenance preserved, not a fresh request;
  R18-R21, R23-R25 = historical leads linked to existing evidence,
  not reopened; R26 = withdrawn. The register is evidence of intent,
  not an execution queue.

### FORWARD

1. Owner decision on the proposed execution packet (NOT RUN; fresh
   `python research/offseason_2026/pregame_pa_ext/count_pmf_diagnostic.py
   --k-pmf "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\platoon_information_v1_reproduction_20261110\k_pmf_per_start_v1.parquet"
   --assessment "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet"
   --arms pmf_multinomial_control,pmf_platoon
   --cohort-keys "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet"
   --expected-cohort-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7
   --out-dir "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_pmf_diagnostic_v1"
   --execution-ack EXECUTE-COUNT-PMF-DIAGNOSTIC-V1`.
   Pins: k-PMF = the byte-identical reproduction output
   (`8c5c849c289ecd65a561719d9ca7e9ce0975e6e0c377107fb6587c475b3a4916`,
   attested via the verified reference receipt manifest); assessment
   pin `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa`;
   cohort = the registered eligible cohort (hash `f77d7a66...`,
    hash-checked by the runner). Access: full-file decode of those
   three files ONLY: k-PMF, assessment, and cohort-keys; no Friend
   CSV read. Stop conditions: ack gate; destination exists;
   cohort hash mismatch; forecast/observed-vs-cohort key mismatches
   (both directions reported); duplicate/null identities; malformed
   labels/PMFs. Input identity hashes are PROCEDURAL preflight
   (the CLI enforces the cohort hash + structural gates, not the
   file byte pins). Malformed labels/PMFs refuse via the registered
   gates. The board-coverage probe's access is SEPARATE: it uses
   declared-column / allowed-row-group decoding (not full-file); no
   Friend read (Friend is not a dependency of that probe).
   gates.
2. Scientific queue: no other task assigned; ablation work stays
   closed (no-2026-tuning; 2025-select / 2026-judge sequencing
   unchanged).

### DEFERRED

- No new framework, no model/feature search, no calibration, no
  workload recomputation, no dashboard revival; nothing pulled from
  deferred lanes.

## Post-closeout canonical state â€” 2026-11-10

This is the handoff for main after this docs checkpoint integrates following
PRs #74-#77. Main is the canonical
integration history; the role rules and workflow remain in `AGENTS.md`,
`docs/roles/`, and `docs/reference/pr_workflow.md`.

### PAST

- PR #74, PR #75, PR #76, and PR #77 are merged. The resulting
  `origin/main` and primary checkout are
  `57ce8b2f67130329bc894de2b8bfa50e5e1b83f4`.
- PR #77 removed the superseded result-summary test module, retained its
  behavioral coverage in the canonical module, and removed one redundant
  logger assertion. No production or scientific code changed.
- The approved redundant refs and obsolete scientific worktrees were
  released. Unique source and ignored research storage remain recoverable
  outside the active workspace set.

### PRESENT

- Three worktrees remain: primary `main`, Chat 1's `wtsc`, and detached Chat 2
  reviewer workspace `review-68`. The temporary Chat 3 workspace is released.
- The only active local and remote branches are `main` and
  `research/dual-arm-prediction`; no maintenance branch remains.
- Primary is synchronized with `origin/main` and retains these unregistered
  owner-local experiment files without modification:
  `research/offseason_2026/experiments/forward_2025.parquet`,
  `research/offseason_2026/experiments/run_2025_selection.py`, and
  `research/offseason_2026/experiments/selection_2025_report.json`.
- The preserved ignored storage has 52 verified files and a hash manifest at
  `C:\Users\ckaplinger\MLB-Props-Research\worktree-preservation-20261019\chat3-test-signal-20261110-storage`.
- No open PR or unreviewed maintenance delta remains. The root rules,
  canonical roles, single backlog, and main-only integration workflow are
  present on main.

### FORWARD

1. Chat 1 fetches `origin/main` and fast-forwards `wtsc` before beginning a
   new bounded builder task.
2. Chat 2 reuses detached `review-68` and reviews only the exact published
   builder SHA.
3. The architect assigns the next bounded scientific or implementation task;
   Chat 3 remains closed until a new, named maintenance scope is approved.

### DEFERRED

- Do not merge or delete the unregistered experiment files without explicit
  provenance/owner disposition.
- Do not start another repository-wide cleanup, test redesign, Helios
  exploration, policy framework, or additional worktree.

## Historical consolidation closeout receipt â€” 2026-11-10

The detailed batch record below is preserved execution evidence. It is not
current ownership or queue state; the current state is recorded above.

### PAST

- PR #74 merged at `81fb30b`; PR #72 merged at `acf00e3`; PR #73 merged at
  `731a32e`. Exact-head CI and review history remain intact. No scientific
  execution, promotion, direct-main push, force operation, or unknown-content
  deletion occurred.
- The previously approved local
  `research/baseline-recipe-rec@971df98` ref was deleted non-force; its
  remote ref was deleted in the approved remote batch.
- The existing preservation hold now verifies 25 copied files and five
  patches (all copied-file hashes and nonempty patch dry-runs pass):
  `C:\Users\ckaplinger\Downloads\MLB-Props-preservation-20261109`.
  It excludes raw data, credentials, MLflow storage, artifacts, and caches.

### PRESENT

- Fetched integration reference: `origin/main =
  731a32e56a494e778ea0e45d51ea18f3362ac975`.
- Primary `main` is now fast-forwarded to that exact SHA. The three
  untracked experiment files and ignored storage were not touched. A
  read-only comparison found 0 collisions between 80,220 ignored/untracked
  files and tracked paths at `origin/main`.
- `review-68` is the protected Chat 2 reviewer workspace, detached at
  `165b7a9`; it has no tracked or untracked edits.
- `wtsc` is the protected Chat 1 builder workspace on
  `research/dual-arm-prediction@165b7a9`; it has exactly one uncommitted
  edit, `docs/EXECUTION_BACKLOG.md`. That edit contains stale pause/open-PR
  statements and is preserved at
  `preservation-20261109\patches\wtsc-backlog-uncommitted.patch`; it was not
  copied into current authority.
- `agent/distribution-spec@52379dd8c82fe87537173c8b3798caaf5688f41c` is
  reachable from `origin/main`; its dirty backlog/spec edits and 16
  untracked scientific files are preserved outside the active workspace set.
  `main-active` has unique documentation commits `beb146b` and `b70ebfc`, a
  dirty `AGENTS.md`, five untracked files, and ignored research data; its
  unique source state is preserved. `paext-v2@1321e4bf45ca1673985612b2994cbda4eca23f9f`
  is reachable from `origin/main`; its reported modification to
  `tests/test_count_pmf_calibration_runner.py` is metadata-only
  (`index=worktree=417755a...`). Its local synthetic MLflow output, duplicate
  artifact/dimension data, and caches are noncanonical and were included only
  in the approved worktree-removal scope. None is bulk-merged.
- All reachability statements above use
  `git merge-base --is-ancestor <ref> origin/main`; a tip-equals-main claim
  is not used.
- **Chat 2 baseline checkpoint review verdict (2026-11-10, exact SHA
  `165b7a9f5b349cf308133425ba5481c922585468`): PASS with 2 nonblocking
  notes.** Scope limited to the new dual-contract baseline-parity
  selection behavior in
  `research/offseason_2026/pregame_pa_ext/label_free_prediction.py`
  (`_match_contract` set-match against the two registered contracts,
  order-authoritative feature selection, challenger-only platoon attach
  block, additive `contract` result key) and the affected tests in
  `tests/test_label_free_prediction.py` (7 new tests). Reviewer reran
  17/17 synthetic tests in that file and the 34 pre-commit tests: all
  green, no real-data execution. Contract sets are unambiguous
  (8-feature control is a strict subset of the 12-feature challenger;
  multiset match refuses duplicates). Nonblocking notes: (1)
  `needs_platoon` is hard-keyed to `platoon_challenger_v1`, so a future
  third contract added to `_REGISTERED_CONTRACTS` would silently take
  the non-platoon path; (2) the refusal message hardcodes contract
  names instead of deriving from `_REGISTERED_CONTRACTS`. Neither gates
  the checkpoint; both are future-proofing only. Retained findings from
  the completed challenger parity review, cleanup review, and historical
  model comparisons are not repeated. The `review-68` worktree remained
  clean at the pinned SHA; no builder edits, private-artifact reads, or
  merges occurred.
- Helios signal criteria were checked read-only against the current test tree:
  141 test files and 1,460 test functions are present; no unconditional
  `assert True` tests were found. Seven tests use only non-`None` assertions
  and 25 have no direct `assert`/`pytest.raises` node, but many of those call
  assertion helpers or deliberately raise on failure. They are candidates for
  producer/deletion-proof review, not proven low-signal tests. PR #75 removed
  no tests, and no test deletion is included in this cleanup batch.
  A test is removable only when its named production publisher/path,
  production-shaped fixture, and failure-on-behavior-deletion check are
  documented; CI green alone is insufficient.

### Storage disposition verified for the three removed worktrees

- `distribution-spec`:
  `artifacts/odds_log/recommendations_meta.json` is 140 bytes and byte-identical
  to primary (`c0a42301...`); `data/dimensions/player_id_map.parquet` is
  34,937 bytes (`bf6a653f...`), a regenerable dimension copy with no
  canonical consumer in this worktree. Its tracked patch and 16 untracked
  source/test/report files are already preserved.
- `main-active`:
  the four model files plus `recommendations_meta.json` are byte-identical to
  primary (1,031,169 bytes total); `data/dimensions/player_id_map.parquet`
  is a 35,036-byte regenerable copy (`4396257a...`). The
  `research/offseason_2026/bf_workload_v1/data/start_metrics_v2.parquet`
  file is 2,355,296 bytes (`af6814ec...`) and matches the canonical external
  file at
  `C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet`.
  No relocation is required.
- `paext-v2`:
  `recommendations_meta.json` is byte-identical to primary; its 35,499-byte
  dimension copy (`8f0d07f7...`) is regenerable. Its local MLflow stores are
  9 files / 20,452 bytes under `mlruns/` and 52 files / 424,850 bytes under
  `research/offseason_2026/specs/count-eval-v2-spec/harness/mlruns/`.
  They are local synthetic harness output, not the canonical tracking store.
  The canonical `C:\Users\ckaplinger\MLB-Props-Research\mlflow.db`
  exists (1,212,416 bytes, hash `04d71487...`); no database deletion or
  relocation is proposed. The metadata-only test state has identical index
  and worktree blob `417755a...`.

### FORWARD

1. Review this closeout branch/PR as one documentation-maintenance unit.
2. The owner-approved exact batch below was executed on 2026-11-10 after
   expected-tip and preservation checks; no candidate was skipped.
3. Obtain independent review and merge approval for this documentation
   checkpoint. After integration, reuse `wtsc` for Chat 1 from fetched
   `origin/main`, and use `review-68` only for the exact published builder
   head. Release Chat 3's maintenance workspace under separate approval.

### DEFERRED

- No scientific branch is merged through maintenance. Unique source state for
  `distribution-spec` and `main-active` is recoverable from the existing
  preservation hold; `paext-v2` had no tracked code delta. The three obsolete
  checkout directories were removed by the exact approved batch. Canonical
  external storage remained outside scope.
- No test-suite redesign, lifecycle-policy expansion, PR-template
  expansion, new registry, or additional cleanup framework is started.
- Primary synchronization is complete; verified canonical storage required no
  relocation. Noncanonical/regenerable ignored storage was confined to the
  removed worktrees and no protected storage was touched.

### One exact approval batch â€” executed 2026-11-10

Before execution, every expected ref tip matched, had no open PR, and was
verified reachable from fetched `origin/main`. Each ref candidate had no
linked worktree; the three linked worktrees were checked separately under the
same approval. Local and remote deletion were performed separately.

**Local branches removed:**

```text
docs/reconcile-20261106@9976d0cdd6be0b8e33eb553704ff847505377907
research/next-assigned@8e9fe3a07eca6f1e51ecb5f9ac7d3e4dfd795b5e
research/parity-platoon-candidate@3a807a988f76c6a2bec59209349b20c6cfc77d9f
research/result-summary-v1@1570679edc1c790559f8124738ee6f3253776d8b
```

**Additional local refs removed in the final consolidation batch:**

```text
agent/distribution-spec@52379dd8c82fe87537173c8b3798caaf5688f41c
chat3/doc-collapse-20261023@c27eb68f53cee50bc97f66484fbf3dc4bac5c23d
chat3/lighten-20261023b@94a16b9d1e841da67ce85ded347c9acb04c880a5
chat3/verify-and-consolidate@9ec1a7afe56975de30752ad23b363c5c81f20480
chat3/verify-script-20261023@84966bedd752020ec54da5cd163b766dbde13ec0
docs/architecture-20261009@804e86bc1babf1237d60d1afffed25927275d0fb
docs/pa-review-record-20261012@0ddb050408cb0e75db1cefdc4d73178ac223e862
docs/pointer-repairs-20261009@20c2724ce62a8884abf81b83a8cc87ad175f439c
maintenance/quality-baseline-20261016@35282f14cf50ac85db4230a93da53f3e5ad64ed7
research/calibration-exec-gate-v1@1321e4bf45ca1673985612b2994cbda4eca23f9f
research/market-eval-v2@f14530c7991541cbffe4cdd06201616def1ae7c6
research/paired-uncertainty-v1@80320dedd8ee79a27a8fcb9b4e1931271ea98cb8
research/paired-uncertainty-v2@b70ebfc4763965b747e44f0be0cd7f3993616cf2
research/pregame-pa-ext-v1@e03f2386ea5daf5584ab09c641f1275d0158d71b
research/pregame-pa-ext-v1-legacy@dfd8f1709a52a58bf2ac331dac8af053a79e5e31
research/pregame-pa-ext-v2@562ab7a49fc80d407f3113fcc0386dcdb23ae982
research/results-index-v1@7211269a62c20df1a9ba2efce4f98ae1f317ffe1
review/overnight-20261013@a4c3060906fed3ce80c334b24bb4efe0029777b2
```

**Remote branches removed separately after the local batch:**

```text
origin/chat3/doc-simplify-20261023@587fa4f8fbf5f97526767266b23b9f0e9cf143cf
origin/chat3/pub-rules-20261106@47b887b0b7a13d1ba422aac1b3b28ef6436cae15
origin/docs/consolidation-slice-1@ad5871a95c1862cf89c6d8fefec9af9a0214984b
origin/docs/integration-reconciliation-20261103@ffdae7b239a2c3572ccb26dbd49abfd2ad76b7b5
origin/docs/lineup-path-reconciliation-spec@ca00e4df5a426acf37ef9d3f43f8e25aa95dc8e1
origin/docs/orchestrator-source-pack@9850a281cba3fd4a33ad2443a2728934b019036e
origin/docs/reconcile-20261106@9976d0cdd6be0b8e33eb553704ff847505377907
origin/docs/untracked-backfill-20261105@14afec6eeefdd2385fedec20b7edf1b056f72acd
origin/docs/worktree-reuse-rule@8e9b7f8e8633cc74fe15e48d82c6c6c403ae0cd3
origin/research/baseline-benchmark-v1@69aa861e398a730b020887eed8a90b6c6cbab688
origin/research/baseline-history-scorecard-v1@1a1790c4aef0c77f0f8909dbdf59c5eef1af07d4
origin/research/baseline-recipe-rec@971df98a09701431743c23f940f5d9876f06d21e
origin/research/binary-k-vs-multinomial-v1@ab220994d9a179cd595e196c1646b7c5266089e7
origin/research/count-pmf-calibration-v1@1381e72badca507eb19331ad28967031aeed5a56
origin/research/label-free-inference@40269793005cd0da3e9751bf1eb2e861714578c5
origin/research/label-free-prediction@fdbf5541636a3ee346da0ff5433510048251d81c
origin/research/lgbm-multiclass-v1@34efade12ee08f9ad178c5f487c6fc1f68308f4d
origin/research/paext-v2-count-agg-eval@d6ce42a73011ef11f0198a624f0572c88214f887
origin/research/parity-platoon-candidate@29592fb36d358195483d1372bc77e54c873385d4
origin/research/platoon-information-v1@672aaf63c137528b704148d9f5bb579229f9bfe6
origin/research/result-summary-v1@1570679edc1c790559f8124738ee6f3253776d8b
origin/research/stage-a-numerical-gate@b8461178d015a58a54c3d2b37235bb0897dc02c2
```

**Additional remote refs removed in the final consolidation batch:**

```text
origin/chat3/verify-and-consolidate@9ec1a7afe56975de30752ad23b363c5c81f20480
  Integrated/superseded: its read-only scripts/verify_theoddsapi.py content
  is identical to origin/main and PR #44 is merged. No linked worktree or
  open PR; removed in the executed batch.

origin/docs/connector-confirmation-policy-20261027@39e2b4a26b2308ad05e3d168420f6d0ed12cbba1
  Superseded: its two-document policy commit is not in the current canonical
  role/NEXT text; current owner-directed rules supersede it. No linked
  worktree or open PR; the commit is recoverable from the compact bundle and
  was removed in the executed batch; do not merge it.

origin/research/baseline-v2-derivation-runner@c8638f4e734032f00f996292f3fda7d1940aad85
  Historical/superseded: PR #51 is merged and PR #55 is closed redundant;
  this stale scientific tree is recoverable from the compact bundle and is
  not an active consumer. No linked worktree or open PR; it was removed in the
  executed batch without merging its historical tree.

origin/research/calibration-exec-gate-v1@1321e4bf45ca1673985612b2994cbda4eca23f9f
  Obsolete calibration checkout ref: the tracked test difference is
  metadata-only and local MLflow output is synthetic/regenerable. Its
  canonical external database remains retained; its ref was removed with
  `paext-v2` in the executed batch.
```

**Scientific worktrees removed under the same exact approval, with
noncanonical storage disposition verified:**

```text
C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\distribution-spec
  branch agent/distribution-spec @ 52379dd8c82fe87537173c8b3798caaf5688f41c
  preserve tracked patch + 16 untracked source/test/report files; remove
  only these verified noncanonical files:
    artifacts/odds_log/recommendations_meta.json
      140 bytes, SHA-256 c0a42301d9eeca7752aa8fffc0fd8f44918435f29a5418953566ac9fb2697b76
    data/dimensions/player_id_map.parquet
      34,937 bytes, SHA-256 bf6a653f476ab81de9c611c4315796275d2d52a5e23733a589a4baf6a7d5edff
  plus generated cache paths only: .hypothesis/, .pytest_cache/,
  **/__pycache__/, *.pyc, and *.pyo.

C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\main-active
  branch research/paired-uncertainty-v2 @ b70ebfc4763965b747e44f0be0cd7f3993616cf2
  preserve unique commits, dirty AGENTS.md, and five untracked files;
  retain the canonical external start_metrics_v2 file; remove only these
  verified duplicate files:
    artifacts/models/lightgbm_krate_20260821_054126.json
    artifacts/models/lightgbm_krate_20260821_054126.txt
    artifacts/models/lightgbm_krate_mono_20260821_054127.json
    artifacts/models/lightgbm_krate_mono_20260821_054127.txt
    artifacts/odds_log/recommendations_meta.json
    data/dimensions/player_id_map.parquet
    research/offseason_2026/bf_workload_v1/data/start_metrics_v2.parquet
  The five artifact/model files total 1,031,169 bytes and are byte-identical
  to primary; start_metrics_v2 is 2,355,296 bytes and byte-identical to
  C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet.
  Also remove generated cache paths only: .hypothesis/, .pytest_cache/,
  **/__pycache__/, *.pyc, and *.pyo.

C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2
  branch research/calibration-exec-gate-v1 @ 1321e4bf45ca1673985612b2994cbda4eca23f9f
  retain external C:\Users\ckaplinger\MLB-Props-Research\mlflow.db
  (1,212,416 bytes, SHA-256 04d714879aad0776e5563f439fa9aedf08d8c13877c7ae5651b45182141def5c).
  Remove only local synthetic MLflow output:
    mlruns/ (9 files, 20,452 bytes)
    research/offseason_2026/specs/count-eval-v2-spec/harness/mlruns/
      (52 files, 424,850 bytes)
  and these verified duplicate/regenerable files:
    artifacts/odds_log/recommendations_meta.json
    data/dimensions/player_id_map.parquet
  plus generated cache paths only: .hypothesis/, .pytest_cache/,
  **/__pycache__/, *.pyc, and *.pyo. The tracked test state is metadata-only
  (index=worktree=417755a...), so no source recovery is required.
```

At the time of that batch, `wtsc`, `review-68`, and the maintenance workspace
were protected role lanes; primary contained owner-local state. That batch
left 4 worktrees and 3 local/remote branch heads, including the then-active
`chat3/lifecycle-docs-20261109` maintenance refs. PR #77 later integrated
the final test cleanup and released those maintenance refs and its workspace.
No relocation was needed because every retained canonical storage destination
was verified before that batch.
No raw data, credentials, receipts, canonical MLflow database, or unresolved
experiment output is in the removal scope.

**Recovery evidence:** `MANIFEST.json` records the exact source heads,
paths, hashes, and retrieval instructions. The compact hold contains
`distribution-spec.tracked.patch`, `main-active.tracked.patch`,
`main-active-unique-commits.patch`, the empty `paext-v2` tracked patch, and
the preserved `wtsc` backlog patch. Applying the nonempty patches against
their recorded source/base heads passed `git apply --check`; no scientific
code was run. `historical-refs-20261109.bundle` is 215,557 bytes
(SHA-256 `30d8bc006ab0ce96403db03c4e692985587387f94e8a72add54aed6939557832`);
`git bundle verify` passed, and a temporary repository recovered all 48
local/remote deletion tips with 0 missing tips before being removed.

---

## Session Snapshot â€” 2026-10-28 (PRs #46/#48/#49/#50 MERGED; main = 15fe7bf; PR #51 derivation runner at 60401f6 awaiting owner execution decision)

**INTEGRATION COMPLETE 2026-11-03 (Chat 1 builder reconciliation; docs-only;
single post-integration update; supersedes the integration-order items in the
2026-11-03 closeout below):**
(1) **main = `8399f2c`** (actual integrated SHA; verified locally). Sequence:
#51 merged `7764ac1` (from reconciled head `2757015`), #53 merged `4f2490c`,
then the #52 content reached main via **PR #54** (`1a1790c` merged origin/main
into the `77131b3` head; `8399f2c` merged to main) because #52's own merge
commit `c8638f4` had landed on its base branch instead of main - the gap was
found by builder verification, announced on PR #52, and repaired same-day;
carrier PR #55 was opened and then closed REDUNDANT after #54 landed. GitHub
open-PR count: zero.
(2) **Integration checks:** CI test-and-validate + tracking PASS on the
integrated heads (runs 2026-11-03: `2757015`, `77131b3`, and #55's
`c8638f4` carrier); verified on the merged main tree locally: `77131b3` is an
ancestor of main; workload/scorecard/multiclass code + suites present
(`workload_comparison.py`, `test_workload_comparison.py`, etc.); roles
README approval-requests section present; backlog closeout + approval blocks
present; rewritten NEXT present; cohort-test determinism fix at
`tests/test_pregame_multiclass_baseline.py:683`; **97 targeted tests green**
(multiclass 27 + workload 10 + derivation 13 + pre-commit subset).
(3) **Content now canonical on main:** the accepted workload closeout
(COMPLETED / VERIFIED; pooled league BF control W0 favored on development
data; delta +0.012406, CI95 [+0.004410, +0.020368]; BF interpretation
retained), the roles approval-requests rule, and the reviewed baseline-stack
deliverables. Original run artifacts and receipts remain preserved write-once
outside the repo (path in the closeout below). No production, policy, model,
ledger, or real-data change was made or authorized by this integration.
(4) **Next experiment NOT started:** it will not launch until the architect
assigns its single question; see rewritten `docs/NEXT.md` (current action =
none pending; integration complete).
(5) **Communication amendment 2026-11-03 (owner directive, short form in the
canonical roles doc - new 'PR communication' section, no separate policy
file):** the PR description is the current dashboard; link evidence, do not
paste tables; no status-only comments; batch corrections into the next
checkpoint; one integration summary per merge; ~150-word routine handoffs;
historical evidence preserved. Applied going forward; no cleanup project.

**Owner (temporary chat) 2026-11-05, docs-only:** added `docs/reference/orchestrator_source_pack.md`
(verified 12-file core upload pack for orchestrator/Perplexity-engine chats, provenance
template, refresh triggers; corrects earlier proposals - roles doc = `docs/roles/README.md`
+ card, adopted decisions = `docs/DECISIONS.md` register, `docs/AGENTS_ROLES.md` excluded)
+ one pointer row each in `AGENTS.md` and `docs/README.md`; no code, policy, or production change.

**OWNER BACKFILL + ALIGNMENT 2026-11-05 (temporary owner chat; one PR, docs/ops-only, no promotion):**
(1) **Untracked backfill PR** (`docs/untracked-backfill-20261105`): 46 machine-local
files committed to main so the orchestrator's GitHub connector can see them -
17 ops/market-research scripts (`production/ops/`, incl. `market_research/` +
`backfill_closes_from_cloud.py`, `dawn_probe.py`), 12 matching test suites,
12 dated evidence reports + `repo_quality_passthrough/`, 2 referenced paper
figures (`fig11_live_equity.png`, `fig12_ab.png`), and
`Odds-Historical.sha256` **relocated from `data/` (never-commit zone) to
`docs/reference/data_manifests/`**. Labeled owner-directed backfill of
already-executed local work; NO promotion, NO policy/production-path change.
(2) **Deliberately NOT committed:** `research/offseason_2026/experiments/`
trio (`forward_2025.parquet`, `run_2025_selection.py`,
`selection_2025_report.json`) - experiment outputs are write-once and the
report implies a 2025-select run whose registration/authorization status
needs explicit owner disposition (clean-2025-select-once rule). PARKED until
the owner rules on it.
(2b) **LOST machine-local work (discovered by CI on backfill):** two test
files targeted extended modules that were never committed and survive nowhere
on this machine: (a) extended `join_keys.py` (verified alias table
"Mike Soroka"->"michael soroka", "Daniel Lynch"->"daniel iv lynch" suffix
rule, `suggest_aliases`) - `tests/test_join_keys.py` REMOVED from the
backfill rather than fabricating the alias table; (b) cloud-scheduler task
health in `build_automation_self_check.py` (committed version emits only
found=yes/no) - the one affected test in `tests/test_automation_self_check.py`
is `@pytest.mark.skip` with the reason inline; the other 4 tests pass against
the committed module. Both rebuilds are SMALL, WELL-SPECIFIED follow-ups for
the owner/Chat 1 if the alias verification and cloud-scheduler health check
are still wanted; do not re-add the tests before their modules exist.
(3) **Pack re-verified:** `docs/reference/orchestrator_source_pack.md` row 10
corrected - the active ASSIGNED experiment is platoon-information value
(card `docs/adr/PROPOSED-platoon-information-multiclass.md` + packet
`execution_packet_platoon_v1.md`), not "unassigned". Binary-K and LGBM lanes
CLOSED/VERIFIED; temporal robustness remains a separate gated milestone
(NEXT.md does NOT assign it).
(4) **PR #60 directive (temporal-robustness runner):** stays BUILDER-FROZEN
for Chat 2's consolidated review. Do NOT merge before review - review
precedes merge, and merge never authorizes execution. If an orchestrator
audit needs the runner, attach the PR #60 link as a temporary source.
(5) **Handoff rule for the orchestrator pack freeze:** provenance
`Source commit` stamps are taken only AFTER all merges settle; permanent
instructions stay SHA-free (orchestrator runs `git log --oneline -5` and
reads `docs/NEXT.md` live).

**BINARY-K VS MULTINOMIAL-K LANE OPENED 2026-11-03 (owner assigned the single
question; implementation + synthetic tests ONLY; NO real-data execution):**
spec card `docs/adr/PROPOSED-binary-k-vs-multinomial-k.md` (ID
`binary_k_vs_multinomial_v1`) names, before any scoring: control = the
existing multinomial-plus-W0 arm (registered m0 multinomial recipe + W0 pooled
BF37 through the registered `start_count_pmfs`), reconstructed exactly and
gated against the pinned accepted per-start reference (tolerance 1e-12);
challenger = binary K-vs-non-K logistic (SAME estimator family, hyperparameters,
8 features, training rows; sigmoid head); binary labels derived ONLY from the
bridged class_label (`is_k = 1[class_label == 0]`), single-class refusal,
row counts asserted equal across arms; keyed probability alignment (one keyed
table from the shared feature rows, no positional transfer, permutation
invariance); same-population checks (identical sorted key list, cohort
semi-join BEFORE features, duplicate-identity refusal, 9-slot requirement);
shared aggregation (same function, same pooled BF37, only p9 differs);
saved-model reload parity; primary endpoint = paired per-start count-RPS
contrast (bootstrap 2000/20261001); statistical direction reported
separately (CI below zero favors binary-K, above retains the control,
overlapping zero inconclusive) from the practical magnitude: a magnitude
below the declared practical threshold (0.005 count-RPS) does not justify
added complexity regardless of CI direction; promotion never automatic;
artifacts = write-once run dir (report, per-start parquet, keyed
probabilities, both model artifacts, K PMFs, pooled BF37, receipt chain,
failure record); limitations = development evidence on the registered 2025H1
cohort only, binary arm models P(K) only and says nothing about non-K class
uses, 2026 untouched. Implementation: `research/offseason_2026/pregame_pa_ext/
binary_k_comparison.py` + `tests/test_binary_k_comparison.py` (18 synthetic
tests through the actual entry point incl. subprocess CLI; requirement-to-test
closure table in the test docstring). 133 targeted tests green (binary 18 +
workload 27 + multiclass 27 + scorecard 18 + derivation 13 + pre-commit
subset). Ack token `EXECUTE-BINARY-K-VS-MULTINOMIAL-V1` is a technical gate,
NOT authorization. FINDING (nonblocking, recorded for Chat 2):
`m0.apply_multinomial`'s manual softmax is undefined for a 2-class model
(single logit column -> constant 1.0), and the reviewed
`workload_comparison.py` compensation branch inherits the defect
(probs[:,0]=1.0 -> degenerate [0,1] expansion); the real registered cohort has
4 observed classes so accepted results are unaffected; the new runner applies
the identical softmax definition explicitly for the 2-class parameterization
(`_multinomial_pk`) and flags a follow-up repair for the reviewed files
through review, not silently; the two-class repair stays DEFERRED and out
of scope for this experiment per owner direction. Checkpoint published on
the stacked PR (base `docs/integration-reconciliation-20261103` = PR #56).
**PACKET PREPARED 2026-11-03 (owner-directed, before integration):**
`research/offseason_2026/pregame_pa_ext/execution_packet_binary_k_v1.md` -
one action, all input identity pins (pa/lineups/assessment/raw events from
the workload run's consumed identities), cohort pin `f77d7a66...`, and the
accepted multinomial-plus-W0 reference pin `ae971758...`
(`workload_per_start_v1.parquet`) ENFORCED via the new REQUIRED
`--expected-reconstruction-sha256` CLI check verified before any decode
(recording alone was not identity enforcement; +2 CLI tests, suite 20/20,
133 targeted still green). Approval flow: Chat 2 packet review -> explicit
**BINARY-K VS MULTINOMIAL RUN EXECUTED ONCE 2026-11-03 - CLOSED 2026-11-04:
CHAT 2 ARTIFACT VERDICT = VERIFIED (supplied via owner; builder-reported
record confirmed) (owner-approved
against packet revision 2 `af5e84dd...` at code checkpoint `49f19ac`; exact
packet command, exit 0):** destination write-once at
`MLB-Props-Research\pregame-pa-ext-v2\diagnostics\binary_k_vs_multinomial_v1\`
(9 files; output hashes reconcile against receipt_final; receipt chain
intact; receipt_initial hash-verified unchanged). Guards: 4 file-byte pins
verified pre-decode; cohort `f77d7a66` MATCH (64,746 -> 22,581 requests);
reconstruction gate PASSED EXACTLY (control arm reproduced the accepted
multinomial-plus-W0 per-start RPS, max abs diff **0.0**, n=2,509). RESULT
(2,509 starts; 148,369 train rows, 33,541 positive): mean count-RPS control
**1.2952473** (= accepted W0 1.29525) vs binary-K **1.2953442**; delta =
RPS(binary) - RPS(control) = **+0.0000969, CI95 [-0.0000828, +0.0002673]**.
Pre-declared rule, direction and magnitude reported SEPARATELY: statistical
direction INCONCLUSIVE (CI overlaps zero); practical magnitude **far below
the declared practical threshold (0.005)** regardless of CI direction ->
the dedicated binary objective does not improve K-count forecasts enough to
justify the added complexity; the multinomial-K control is retained.
Descriptive per-PA (43,565 matched PAs): log loss control 0.505684 vs
binary 0.505703; Brier 0.163504 vs 0.163510 - consistent with the count
result. Valid negative/inconclusive result: NOT a bug to rescue; no rerun,
no rescue variants, no promotion (none was automatic). Development evidence
only; no production/policy/model change; outputs preserved untouched.
Evidence handoff delivered to Chat 2 on PR #57. CLOSEOUT 2026-11-04: Chat
2's artifact verdict = VERIFIED; record closed once; the multinomial
control is kept; no binary variants or reruns. PR #57 prepared for
integration through the existing process (merge via architect delegation
on the PR). Original run artifacts and receipts preserved untouched.

**SEPARATION COORDINATED 2026-11-04 (owner directive, before further PR
growth):** completed binary closeout vs new platoon work are separated -
**PR #57** (`research/binary-k-vs-multinomial-v1`) = the completed binary
closeout surface (VERIFIED result, artifacts untouched; its head also
carries the first platoon checkpoint, which is frozen content); **PR #58**
(`research/platoon-information-v1`, stacked on #57) carries the platoon
REPAIRED checkpoint `6afe413` (global-prior fallback repaired to the
cutoff's actual global proportions; cutoff-aware pitcher-hand lookup; card
reconciled on tie-break/hand-lookup/endpoint weighting; packet revision 2;
22 platoon tests incl. 2 discriminating regressions). All further platoon
work (review repairs, execution prep) goes to the platoon branch/PR so
#57's binary-closeout integration is not coupled to platoon review churn.
History preserved: no direct-main pushes, no duplicate carriers, no
destructive edits, no branch rewrites.

**LGBM MULTICLASS LANE OPENED 2026-11-04 (owner-assigned milestone;
implementation + synthetic tests ONLY; NO real-data execution):** card
`docs/adr/PROPOSED-lgbm-multiclass-challenger.md` + packet
`execution_packet_lgbm_multiclass_v1.md` on the NEW stacked branch
`research/lgbm-multiclass-v1` (PR stacked on the platoon branch; separation
rule maintained). Registered reentry reason: the lgbm-equal-info v2
closeout is NOT reopened - new owner-assigned design vs the NEW
multinomial-plus-platoon control. Control = the 12-feature
multinomial-plus-platoon pipeline (reconstruction gate vs the platoon
run's challenger arm `c7428375...`, tol 1e-12, ENFORCED pre-decode);
challenger = LightGBM multiclass on the IDENTICAL 12 columns (equal
information); tuning budget pre-declared: 6 configs (num_leaves
{7,15,31} x min_data_in_leaf {50,200}) x 2 chronological folds INSIDE the
training window (fit ..08-31 -> val ..10-31; fit ..10-31 -> val ..12-31)
= 12 fits, selection = lowest mean validation log loss with declared
tie-breaks, ALL fold results reported; the registered assessment cohort
NEVER touches tuning/selection (discriminating test: flipping assessment
labels leaves the fold table identical). Endpoints pre-declared: primary
= per-PA multiclass log loss (per-start-mean weighting, paired bootstrap
2000/20261001); practical threshold 0.0005 nats; K-count POINT-ESTIMATE
acceptance guard 0.002 (NOT a noninferiority claim); classwise/K
secondary; promotion never automatic. Implementation:
`lgbm_multiclass_comparison.py` +
`tests/test_lgbm_multiclass_comparison.py` (19 tests incl. fold
boundaries/refusals, tuning accounting + selection-rule recomputation,
assessment-isolation, reload parity incl. serialized booster, all gates;
requirement-to-test closure table in the test docstring). 19 lgbm + 24
platoon = 43 targeted green. Command-to-CLI checked (15/15). Ack token is
a technical gate, NOT authorization; the executable is frozen during
review. No feature expansion, no SHAP, no calibration, no rescue
variants, no double-play simulation.

**LGBM EXECUTION AUTHORIZATION RECORDED 2026-11-04 (owner, scoped):
ONE run of the exact LightGBM packet command** - executable `31b721a`
(module bytes; packet at docs checkpoint `d7e81db`), scope = the declared
12 tuning fits + one final LightGBM fit + one control fit. FOUR
LIMITATIONS stay visible in interpretation (owner-codified): (1)
development evidence - the 2025H1 cohort has informed architectural
decisions and is NOT a fresh final test; a win creates a candidate, not a
production promotion; (2) the comparison is "bounded-selected LightGBM
versus fixed multinomial", NOT a universal verdict about model families;
(3) the PA evaluation is conditional on matched projected matchups (K-count
scoring over complete starter outcomes is a downstream check, not full
PA-level coverage); (4) the K guard is a POINT-ESTIMATE acceptance guard,
not statistical noninferiority - interval reported as context. Chat 2's
post-run decision table (pre-declared by owner): meaningful improvement +
guard passes -> retain LightGBM as a candidate development model; no
meaningful improvement -> retain the simpler multinomial; improvement but
guard fails -> do NOT adopt the combined pipeline, record the tradeoff;
execution/evidence failure -> preserve evidence and stop, no silent
retry. Post-candidate steps (owner): freeze the selected recipe +
predeclare a time-ordered robustness evaluation within existing access
(protected partitions do NOT open because this run finishes); next feature
work targets a concrete information gap (e.g., player-specific platoon
skill or pitch-arsenal information), calibration follows model selection
on disjoint chronological data.

**LGBM RUN ATTEMPTED ONCE 2026-11-04 - EXECUTION FAILURE, EVIDENCE
PRESERVED, STOPPED (no retry, no adjustment):** pre-execution checks all
passed, then the exact packet command refused at the declared guard:
chronological fold B (fit ..2024-10-31 -> validate 2024-11-01..2024-12-31)
had an EMPTY validation split - the registered pa_table contains NO
offseason PAs, so the pre-declared calendar-month fold calendar was
infeasible on real data (a SPECIFICATION defect in the frozen packet, not
a code defect - the guard did exactly its job). Failure evidence
preserved write-once at
`MLB-Props-Research\pregame-pa-ext-v2\diagnostics\lgbm_multiclass_v1\`
(`failure_record.json`; immutable `receipt_initial.json`; the pre-tuning
split-rate artifact; NO run outputs); the failed destination remains
unchanged. Stopped per the decision table - no silent retry, no tolerance
change, no substitution.

**REVISED-SCOPE APPROVAL RECORDED 2026-11-04 (owner, per the roles rule):
ONE execution of packet revision 3** (sha `80fe287a...`) at repaired
executable checkpoint `34c4caf` (runner `de5a4560...`), fresh destination
`lgbm_multiclass_v1_attempt2`, same inputs/pins/cohort/reference; Chat 2
review of the repaired checkpoint pending but the owner's revised-scope
approval is explicit. Pre-execution verification for the attempt:
packet/runner bytes verified, fresh destination confirmed absent, failed
destination confirmed unchanged.

**LGBM RUN EXECUTED ONCE 2026-11-04 (revised scope approved; exact packet
revision 3 command, exit 0) - CLOSED 2026-11-04: CHAT 2 ARTIFACT VERDICT =
COMPLETED / VERIFIED (supplied via owner); record closed once; BOTH attempt
directories and all original evidence preserved untouched. RESULT
INTERPRETATION (corrected per owner): (a) statistical direction
INCONCLUSIVE; (b) the point improvement is BELOW the declared practical
threshold; (c) the interval still permits a practically useful
improvement - NO equivalence claim and NO claim that LightGBM cannot help
generally; (d) the K point-estimate guard FAILED. Decision per the
pre-declared table: RETAIN multinomial-plus-platoon; NO LightGBM
adoption;** pre-execution verification passed (runner/
packet bytes, input pins, cohort, reference, fresh destination
`lgbm_multiclass_v1_attempt2` absent; failed destination preserved).
Destination write-once (9 files; output hashes reconcile against
receipt_final; receipt chain intact; receipt_initial verified immutable).
Guards: 4 file-byte pins pre-decode; cohort `f77d7a66` MATCH (64,746 ->
22,581 requests); reconstruction gate PASSED EXACTLY (the
multinomial-plus-platoon control reproduced the platoon run's challenger
arm per-start RPS, max abs diff **0.0**, n=2,509; control mean count-RPS
1.2952882 = the platoon run's challenger 1.2952882). **Resolved folds
published (rule: deterministic one-third/two-thirds expanding split over
49 observed in-window date clusters): fold 1 = fit 2024-05-01..2024-06-18
(48,393 rows) -> validate 2024-06-19..2024-08-11 (50,920 rows); fold 2 =
fit ..2024-08-11 (99,313 rows) -> validate 2024-08-12..2024-09-30 (49,056
rows). Tuning: exactly 12 fits; selected config = num_leaves 7,
min_data_in_leaf 200 (all fold results in the report/receipt).** PRIMARY
(per-PA multiclass log loss, per-start means, paired bootstrap
2000/20261001): control 1.2238507 vs bounded-selected LightGBM
1.2237087; delta = **-0.0002498, CI95 [-0.0009056, +0.0003974]** -
direction INCONCLUSIVE (CI overlaps zero) and |delta| BELOW the declared
0.0005-nat practical threshold. **K-COUNT NON-DEGRADATION GUARD FAILED:
point estimate +0.0020884 > the 0.002 margin** (CI as context; the guard
is a point-estimate acceptance criterion, NOT a noninferiority claim).
**Decision per the pre-declared table: RETAIN multinomial-plus-platoon;
NO LightGBM adoption; the tradeoff is recorded** (small inconclusive
log-loss gain vs K-count degradation just beyond the margin; the
interval still permits a practically useful improvement, so this is NOT
an equivalence finding and NOT a claim that LightGBM cannot help
generally). The four interpretation
limitations carry over (development evidence; bounded-selected-vs-fixed
framing; matched-matchup PA coverage; point-estimate guard). No rescue
  variants, no grid enlargement, no production/policy/live-model change;
  outputs preserved write-once untouched; evidence handoff delivered to
  Chat 2 on PR #59. REPAIR SUMMARY: the fold calendar is
  replaced by a deterministic expanding split over observed in-window
  game-date clusters (one-third/two-thirds positions; outcome-blind; dates
  kept together; feasibility verified before expensive work; resolved dates
  + counts published in the report/receipt); the failed attempt's evidence
  remains preserved. **CLOSEOUT 2026-11-05: Chat 2 artifact verdict =
  INDEPENDENTLY VERIFIED (supplied via owner); temporal-robustness lane
  CLOSED; LGBM bounded-selected challenger also CLOSED (control retained,
  no adoption). PR #64 merged (result-summary renderer); PR #65 merged
  (publication/dashboard/gate-rules consolidation); PR #66 merged
  (integration-status reconciliation).**

**STAGE A NUMERICAL-VALIDITY GATE PUBLISHED 2026-11-05 (owner-assigned
harness engineering slice; synthetic tests ONLY; no real-data run):**
PR #67 (`research/stage-a-numerical-gate`, base main). Minimal
reproducer: NaN `p_h3_raw` in the ledger passes the existing null
filter and I2 (NaN > tol is False in Polars), then causes an unhandled
AdapterError in I3's `start_count_pmfs`. Repair: numerical-validity
gate added after route construction, before I1/I2/I3 â€” checks both
routes' `p_h3_raw` for NaN, infinity, and [0,1] range violations;
reports the route name, affected key count, and example keys; fails
with `numerical_validity` gate and write-once failure receipt. 4
discriminating tests (NaN, infinite, out-of-range, valid-endpoints).
34 Stage A tests green (30 existing + 4 new); 46 Stage A + smoke tests
green. Existing valid baseline behavior unchanged; no feature
construction or aggregation change; no generic validation framework.

**INTEGRATION COMPLETE 2026-11-04 (#57/#58/#59 -> main; existing process;
actual destination verified):** all three merged - #57 (binary-K lane
closeout), #58 (platoon lane: repaired checkpoint, verified run, closeout),
#59 (LGBM lane: repaired fold calendar, verified attempt 2, closeout) at
21:12:48Z; main at b32fd0c (merge of #59; #56 reconciliation included
earlier). Bases and destinations verified before each parent merge;
children retargeted/merged per the recorded procedure by Chat 2/architect.
No carrier duplication, no direct-main pushes. Integration did not block
the next specification (below). **FURTHER INTEGRATION 2026-11-05: main
advanced to 38da8aa (PR #60 temporal-robustness lane merged). The earlier
owner-directed backfill/source-pack alignment PR #63 was merged
(2026-11-05). Local worktree/branch cleanup is a separate maintenance
activity; its actual outcome and approval exceptions are recorded
separately (Chat 3 supplied: batch 1 â€” 5 worktree removals explicitly
approved; batch 2 â€” 4 local branch deletions under weak approval, one of
which exceeded the presented batch, all 4 tips ancestors of main, zero
content loss, restorable on request; batch 3 â€” 4 forced-deletion
candidates PROPOSED NOT EXECUTED per owner stop; no remote branch
touched).** **FURTHER INTEGRATION 2026-11-06: PR #64 (result-summary
renderer) merged at 290b0fa; PR #65 (publication/dashboard/gate-rules
consolidation) merged at 2ca8aef; main at 2ca8aef. Integrated content
verified by Chat 2; main CI passed.**

**TEMPORAL-ROBUSTNESS SPECIFICATION PUBLISHED 2026-11-04 (owner-assigned
milestone; SPECIFICATION ONLY - no execution, no run):** card
docs/adr/PROPOSED-temporal-robustness-evaluation.md = retained-candidate
manifest (12-feature multinomial-plus-platoon: recipe, cutoff/label rules,
pooled workload, lineup assumptions, aggregation, verified artifacts, code
identities) + temporal-evaluation specification: R1 fit
2023-03-30..2024-06-30 (277 verified date clusters) -> score
2024-07-01..09-30 (88; EXPOSED); R2 fit ..2024-12-31 (365) -> score
2025-01-01..06-30 (98; EXPOSED); R3 fit ..2025-06-30 (463) -> score
2025-07-01..09-28 (86; UNEXPOSED confirm partition - requires a specific
new owner authorization, NOT requested). Data-date feasibility
established BEFORE fold declaration (game_date column only, no outcome
reads; offseason gaps verified - the LGBM failure root). Prior exposure
disclosed per period; metrics/weighting/calibration allocation/acceptance
criteria pre-declared; promotion never automatic. The verified LGBM ledger
row was added to the experiment impact ledger (from its VERIFIED record;
nothing recomputed). No new learner, feature family, framework, or model
run.

**TEMPORAL-ROBUSTNESS R1/R2 AUTHORIZATION RECORDED 2026-11-04 (owner,
explicit): ONE execution of the exact packet command** - packet revision
4 (file sha `dc71da5680fa723661034de33752c43b14a2f0daefb73b78486d7d0469e
5339f` at commit b96c158) against the unchanged reviewed action
(executable frozen at `7949ad2`; retained recipe fixed; the repaired
runner identity = Chat 2's verified on-disk LF sha `3c7b1468...` in the
designated execution worktree wtsc). Includes the added 2023 raw-event
file (`statcast_2023_regular.parquet`, sha `b9f9db99...`) and full-file
decoding disclosure for all three raw-event years; earlier experiment
approvals do not cover this source. Packet revision 3 identity check
passed (owner-verified); revision 4 is the packet-only identity-
documentation correction (runner pin + convention wording) - no further
approval request for it. R3/2026 remain structurally inaccessible.

**AUTHORIZATION UPDATED 2026-11-05 (owner, master-orchestrator
conversation): revision-7 authorization confirmed** - packet checkpoint
ef0356c, packet revision 7, as-stored LF SHA-256 `54bef47c501f435f5a228
1b8201abb8a5846beb593873b4f876760bc14386dd6`; executable checkpoint
0128961, runner LF sha `aa71c4bf...`, destination
`temporal_robustness_v1_attempt2`. The previously published sha
`78b14928...` was a PUBLICATION ERROR (not a byte-representation
artifact and not a changed method). Conditional on Chat 2
exact-checkpoint PASS. No further approval request needed.

**TEMPORAL-ROBUSTNESS R1/R2 EXECUTED ONCE 2026-11-05 - CLOSED 2026-11-05:
CHAT 2 ARTIFACT VERDICT = INDEPENDENTLY VERIFIED (supplied via owner);
record closed once; BOTH attempt directories and all original evidence
preserved untouched; the POINT-ESTIMATE-ONLY K-count guard limitation is
RETAINED (it is an acceptance guard, not a noninferiority test). Outcome
per the pre-declared rule: the platoon feature family registers a
CANDIDATE for a future frozen-contract decision; the 12-feature
multinomial-plus-platoon pipeline is the lane's development control going
forward; promotion never automatic; no production/policy/live-model
change made or authorized** (owner authorization + Chat 2
PASS both recorded; exact packet revision 7 command, exit 0).
Destination write-once at
`MLB-Props-Research\pregame-pa-ext-v2\diagnostics\temporal_robustness_v1_attempt2\`
(10 files; output hashes reconcile against receipt_final; receipt chain
intact; receipt_initial sha `983ce5aa...` verified immutable). Guards:
4 file-byte pins pre-decode; cohort `f77d7a66` MATCH; reconstruction
gate PASSED EXACTLY (max abs diff 0.0, n=2,509; anchor reference =
`workload_per_start_v1.parquet` sha `ae971758...`, column `rps_w0_pooled`,
read from receipt_final, not from memory). **RESULTS (per-period,
declared metrics):**
- **R1** (fit 2023-03-30..2024-06-30 -> score 2024-07-01..09-30; 2,334
  starts; 39,568 matched PAs): log loss control 1.222370 vs platoon
  1.221846; per-start-mean delta = **-0.000415, CI95 [-0.000779,
  -0.000053]** - entirely below zero (challenger favored statistically);
  K guard -0.000167, within the 0.002 margin (point estimate, True).
- **R2** (fit ..2024-12-31 -> score 2025-01-01..06-30; 2,509 starts;
  43,565 matched PAs): log loss control 1.224939 vs platoon 1.224133;
  per-start-mean delta = **-0.000870, CI95 [-0.001231, -0.000542]** -
  entirely below zero (challenger favored statistically); K guard
  -0.000300, within the 0.002 margin (point estimate, True).
- Both periods: direction CONSISTENT (both favors platoon), improvement
  above 0.0005 threshold in R2 but below in R1, K guard PASSES in both.
  Per the card's acceptance criteria: the platoon family qualifies as a
  CANDIDATE for a future frozen-contract decision; promotion never
  automatic. Label coverage: 2023 184,104/184,104 labeled; 2024
  182,266/182,266 labeled (zero unlabeled, the 2023 raw-events pin
  worked). Development evidence only; no production/policy/live-model
  change. Outputs preserved write-once untouched; single run, no retry.
  Evidence handoff delivered to Chat 2 on PR #60. **CLOSEOUT 2026-11-05:
  Chat 2 artifact verdict = INDEPENDENTLY VERIFIED (supplied via owner);
  temporal-robustness lane CLOSED; PR #60 merged into main at 38da8aa
  (retained recipe fixed; no adoption of the LGBM challenger).**

**RESULT-SUMMARY HARNESS SLICE OPENED 2026-11-05 (owner-assigned
milestone; synthetic tests ONLY; no real-data execution):** reusable
result-summary renderer from the existing declared report schema
(`temporal_robustness_report.json` schema). Implementation boundaries:
synthetic fixtures only; no fitting/tuning/scoring/bootstrap; no new
framework/registry/dependency; do not rewrite the temporal runner; do
not reopen deferred fixes. Summary must distinguish: identities and
provenance; population/period/coverage; pooled descriptive metrics vs
registered weighted contrasts; statistical direction vs practical
threshold; point-estimate guards vs inferential claims; execution,
verification, and promotion status; development/exposure limitations.
Do not infer VERIFIED from exit code alone; do not hard-code temporal
conclusions.

**PLATOON-INFORMATION LANE OPENED 2026-11-04 (owner-assigned milestone;
implementation + synthetic tests ONLY; NO real-data execution):** card
packet `research/offseason_2026/pregame_pa_ext/execution_packet_platoon_v1.md`.
Source verification (identity + handedness columns only, no outcome reads):
pa_table natively carries `stand`/`p_throws` (731,347 rows, zero nulls,
domains {L,R}); `p_throws` perfectly stable per pitcher (1,512 pitchers,
0 multi-valued) -> pregame-known; 113 of 1,052 batters switch; 51
batter-x-throw pairings mixed -> forecast stand is NOT pregame-observable
for switch hitters, so the declared rule = modal strictly-prior stand
CONDITIONAL on the pitcher's hand (tie -> lexicographically smallest), then
overall modal, then unknown -> global fallback. Declared feature family
(platoon-features-v1): 4 columns = shrunk (stand, p_throws) class rates,
alpha 40, strictly-prior population (same-date/future cannot enter; no
target outcomes), unseen split/unknown hand -> exactly the global prior.
Control = existing 8-feature multinomial-plus-W0 pipeline (reconstruction
gate vs pinned `ae971758...`, tol 1e-12, ENFORCED pre-decode); challenger =
12-feature fit, same estimator family/hyperparameters. Endpoints
pre-declared: primary = per-PA multiclass log loss (identical matched-PA
population, per-start paired bootstrap 2000/20261001); practical threshold
0.0005 nats; K-count non-degradation margin 0.002 count-RPS; classwise +
K metrics = declared secondary; promotion never automatic. Implementation:
`platoon_features.py` + `platoon_comparison.py` +
`tests/test_platoon_comparison.py` (20 synthetic tests incl. same-date/
future label-exclusion, sparse-split shrinkage direction, switch-hitter
stand rules, keyed alignment, reload parity, all gates; requirement-to-test
closure table in the test docstring). 135 targeted tests green. Command-
to-CLI checked (15/15 flags). Refusals/stop conditions exhaustive
(matched-PA class outside fitted set refuses). Ack token is a technical
gate, NOT authorization; the executable is frozen during review.

approval will not be asked for again. No merge prerequisite, no new
feature work, no SHAP, calibration, taxonomy expansion, or unrelated
ticket work.

**CANDIDATE-PARITY ENTRY POINT IMPLEMENTED 2026-11-09 (owner-assigned;
implementation + synthetic tests ONLY; no execution, no private-artifact
reads, no real-data access). RECEIPT-FINALIZATION CORRECTION (Chat 2
finding at 10b18ad, superseding that checkpoint's evidence):** one thin committed invocation
`research/offseason_2026/pregame_pa_ext/parity_platoon_candidate_v1.py`
(`run_parity` + CLI, parity-platoon-candidate-v1) answering: does the
integrated prediction path (PR #70 module, main `5b5d93d`) reproduce the
saved platoon-candidate forecasts from the same fitted model and pinned
inputs? Identity discipline: expected SHA-256 of the accepted reference
receipt (`platoon_information_v1/receipt_final.json`) is a REQUIRED
execution parameter; the receipt is hash-verified BEFORE its `outputs`
manifest is interpreted; model/reference artifact hashes are verified
from that manifest BEFORE decode; PA/lineups byte pins and raw-event
byte pins are ENFORCED pre-decode; cohort identity = registered
sorted-key content hash (`f77d7a66...` expected, `bk._cohort_hash`
recipe). Population: cohort restriction before construction; start-key
set equality vs the cohort; row counts DERIVED from validated keys
(9 slots x starts, 24 buckets x starts); duplicate/null comparison
identities refuse before any dedup; no inner-join comparison at either
grain. Workload: keyed per-start BF37 REUSED from the saved
`bf37_pooled_by_date_v1.parquet` (the runner's own record; no
recomputation) - missing/duplicate dates, malformed categories (must
be exactly 0..36), and invalid distributions refuse (existing
`ad.validate_bf37_by_start` + structural gates). Comparison: declared
column mappings (`p_class_{c}_platoon` -> `p_class_{c}`;
`pmf_platoon` -> `pmf_h3_raw`); finite/valid checks before
differences; acceptance = key equality + max abs diff <= 1e-12 both
grains; exact observed diffs reported, zero not required; any mismatch
stops (failure_record.json, NO success receipt). Receipt ordering
explicit: ack gate -> destination nonexistence (pre-decode) ->
reference-receipt verification -> manifest/artifact hashes ->
receipt_initial (module identities + runtime versions + expectations +
full-file-decode access disclosure) -> pre-decode input pins ->
decode/bridge -> cohort -> keyed BF37 -> prediction -> comparison ->
receipt_initial IMMUTABILITY VERIFICATION -> parity_comparison.json ->
receipt_final.json (both published atomically AFTER the check; a
finalization-write failure cannot leave a valid-looking COMPLETED
receipt; failure_record describes the ACTUAL stage and files written).
**14 synthetic tests green** (12 original + 2 finalization-ordering
regressions: receipt_initial mutation detected before success
publication; finalization-write failure leaves no valid COMPLETED
receipt) (`tests/test_parity_platoon_candidate.py`; success path builds
the reference through the registered seams independently of the
wrapper, so the success case is a genuine end-to-end parity exercise).
**Evidence honesty:** synthetic only - no real-registered-output
validation, not full-suite or private-artifact validation.
**EXECUTION-READINESS GAP (disclosed):** the trusted reference-receipt
SHA-256 value must be supplied from permitted records at execution time
- NOT read from the private artifacts under this instruction.
**EXECUTION REQUIRES FRESH OWNER AUTHORIZATION** (prospective command
in the PR description; full-file decode of pa_table, lineups, and
2024+2025 raw Statcast events; post-R3 rows are documented in the PA
source and the full-season 2025 raw-event file, and are excluded from
the comparison population by the cohort restriction and the wrapper's
structural filters - presence in other decoded files is not asserted;
prior approvals do not carry over). PR #71 integrated (PASS at
29592fb); superseded by the executed-parity block below.

**CANDIDATE PARITY EXECUTED ONCE 2026-11-09 - CLOSED 2026-11-09: CHAT 2
ARTIFACT VERDICT = INDEPENDENTLY VERIFIED (owner closed the record after
verification).** Reference identity resolved per the declared role split:
Chat 2 attested a **present-day verified reference snapshot** (receipt
`receipt_final.json` SHA-256 `b1b9135761f3d272d6ac978400fced6defa9ff6a
61b9cb7a15d0d8dc731224ba`; all four consumed artifacts verified MATCH
against the receipt's outputs manifest; NO historical receipt hash
exists in permitted records, so no historical byte continuity is
claimed). Chat 1 then ran the disclosed parity command ONCE at
integrated main `3a807a98` with the attested hash and the declared full
input pins (PA/lineups byte pins and raw-event pins enforced pre-decode;
cohort content hash `f77d7a66...` matched; assessment parquet excluded;
fresh write-once destination). **RESULT: PASS, EXACT ZERO** - 2,509
starts; 22,581 keyed PA-grain rows; 60,216 PMF rows; key-set equality
both grains; max abs diff **0.0** in all four classes and every K-PMF
bucket (tolerance 1e-12). Scope: reproducibility/identity ONLY - parity
does NOT establish predictive superiority. Evidence (write-once,
preserved): `...\diagnostics\parity_platoon_candidate_v1\`
(receipt_initial -> parity_comparison -> receipt_final, chain sha
`b70a2f90...`, status COMPLETED, no failure record); reference
artifacts in `platoon_information_v1\` untouched; single run, no retry.

**ABLATION BASELINE DECISION RECORDED 2026-11-09 (owner decision +
recommendation support from existing VERIFIED records only - no new
experiment, no data reads beyond existing permission):** for subsequent
ablations: **Reference control = the registered 8-feature multinomial +
pooled W0 recipe (reconstruction-anchored). Development challenger =
the registered 12-feature platoon recipe (multinomial-plus-platoon,
platoon-features-v1). NO production promotion and NO fresh-validation
claim; promotion never automatic.** Component support (declared
comparisons, NOT universal proof): (a) 4-class multinomial logistic
(strikeout/walk_hbp_interference/in_play_out/hit; K = class 0),
StandardScaler + multinomial LR, no tuning - the binary-K lane and the
LGBM lane each RETAINED THE CONTROL WITHIN ITS DECLARED COMPARISON
(binary objective and bounded-selected LGBM did not displace the fixed
multinomial in those comparisons; that is not universal proof that
multinomial is superior), and Ref0-vs-Ref1 favored the K marginal over
population proportions; (b) history = cutoff-correct states-v2
(strictly-prior aggregate, w150 shrinkage, EW 90d half-life); longer
estimation history favored (history-sensitivity scorecard, delta
-0.0111, CI below zero); (c) workload = pooled league BF37 by date
(W0), favored over pitcher-specific W1 (+0.012406, CI [+0.004410,
+0.020368]); (d) K-COUNT AGGREGATION (construction, separate from
evaluation): `adapter.start_count_pmfs` builds per-start K-count PMFs
from per-PA probabilities + the pooled BF37 - it is distribution
machinery, NOT a metric; (e) EVALUATION METRICS (separate layer):
per-PA multiclass log loss primary, per-start means for contrasts,
paired slate-date bootstrap 2000/20261001, K-count RPS non-degradation
guard (0.002 margin); (f) calibration = NONE in every verified arm
(uncalibrated softmax; no calibration comparison exists). The platoon
family's three favored results (platoon run -0.0008712 [-0.0012622,
-0.0005038]; temporal R1 -0.000415, R2 -0.000870; K guard within
margin in all three) remain CANDIDATE evidence for the challenger -
never a promotion. Parity closure is carried above (reproducibility/
identity only). **Standing unresolved item: no calibration comparison
exists; production promotion of the challenger remains unset. Next
action: the architect names the first assigned ablation; no ablation
work starts before that.**

**LABEL-FREE PREDICTION PATH PUBLISHED 2026-11-08 (owner-assigned
checkpoint; implementation + focused synthetic tests ONLY; no real/private
data, no fitting/scoring, no calibration, no promotion):** research-only
orchestration `research/offseason_2026/pregame_pa_ext/label_free_prediction.py`
(`run_prediction`) connecting the retained 12-feature candidate's existing
feature construction to the existing label-free inference (PR #68 module).
Reused seams (no parallel math): `forecast_states_v2.build_v2_states`,
`adapter.projected_long` / `attach_prior_features`,
`platoon_features.build_split_class_rates` / `forecast_matchup_hands` /
`attach_platoon_features`, `label_free_inference.run_label_free_inference`
(itself reusing `pc._softmax_full`, `adapter.start_count_pmfs`,
`validate_bf37_by_start`). Wiring mirrors the registered temporal runner's
request path. Public contract: inputs = fitted 12-feature model dict
(`platoon_comparison.CHALLENGE_FEATURES`), PA source (`game_date`,
`game_pk`, `pitcher`, `batter`, `y`, `stand`, `p_throws`, `class_label`),
projected lineups (nine distinct slots), keyed BF37 frame; outputs = keyed
full class-probability vectors + keyed 24-bucket K-count PMFs + shape
metadata. Semantics: cutoff-correct states at request dates only (asof
backward carries the latest strictly-pre-cutoff aggregate; same-date and
future PA rows cannot enter by construction); `feat_req` selected to key
identity + declared features before inference (contract check refuses
undeclared numeric columns). Coverage/refusal: contract mismatch,
incomplete nine-slot coverage, empty history, and R3 request dates all fail
loud; **10 synthetic tests green after the Chat 2 probe repair
(`tests/test_label_free_prediction.py`; tested SHA published on the PR).
Test-evidence repair (supersedes the 91ae218 fixture): Chat 2 confirmed
the original default model used identical coefficient rows across classes
(feature-independent predictions); the default fixture now uses
deterministic DISTINCT per-class coefficient rows, and the evidence set
is: same-date AND future pre-R3 label perturbations leave the forecast
unchanged (semantics-preserving y/class_label flips); a strictly-prior
label perturbation changes keyed probabilities by max 0.0251 (comfortably
above the 1e-6 assert); row-permutation invariance within 1e-12; adapter
parity (wrapper output == the registered construction seams followed by
label-free inference on the same synthetic inputs; no numerical
re-implementation in the test); the zero-coef uniform case is retained as
a separate degenerate arithmetic smoke test ONLY (not chronology or
construction evidence); a non-uniformity guard in the base test asserts
the fixture model is actually feature-sensitive.
**Evidence honesty (disclosed for review):** these are synthetic-path
tests through the public entry point; they do not validate feature
construction against real registered outputs; they are not full-suite or
private-artifact validation. **R3 refusal rationale:**
the R3 confirm partition (2025-07-01+) is UNEXPOSED and accessible only via
a specific new owner authorization; the wrapper enforces the lane's
declared structural limit at its boundary. This is a scope guard, NOT
evidence that protected data was never consumed and NOT a claim of
protected-data access. Limitations: synthetic-only; strictly-prior dates
do not certify real historical source availability; unlabeled history
handling untested; 4-class bridge mapping assumed. PR targets main;
awaiting Chat 2 review.

**PLATOON RUN EXECUTED ONCE 2026-11-04 - CLOSED 2026-11-04: CHAT 2 ARTIFACT
VERDICT = INDEPENDENTLY VERIFIED (supplied via owner; owner authorization +
Chat 2 checkpoint/packet confirmation both recorded; exact packet command,
exit 0). Artifacts and receipts preserved untouched; the record is closed
once; the POINT-ESTIMATE-ONLY K-count guard limitation is RETAINED (it is
an acceptance guard, not a noninferiority test). Outcome per the
pre-declared rule: the platoon feature family registers a CANDIDATE
feature-family addition for a FUTURE frozen-contract decision; the
12-feature multinomial-plus-platoon pipeline is the lane's development
control going forward; promotion never automatic; no production/policy/
live-model change made or authorized):** pre-execution
verification passed (10/10 module hashes, 7/7 file pins incl. procedural
raw-event hashes, cohort content hash recomputed 2,509 keys, destination
absent). Destination write-once at
`MLB-Props-Research\pregame-pa-ext-v2\diagnostics\platoon_information_v1\`
(9 files; output hashes reconcile against receipt_final; receipt chain
intact; receipt_initial verified immutable). Guards: 4 file-byte pins
verified pre-decode; cohort `f77d7a66` MATCH (64,746 -> 22,581 requests);
reconstruction gate PASSED EXACTLY (control arm reproduced the accepted
multinomial-plus-W0 per-start RPS, max abs diff **0.0**, n=2,509; control
mean count-RPS 1.2952473 = accepted W0). **RESULT (2,509 starts; 148,369
train rows; 43,565 matched PAs):** primary = mean per-PA multiclass log
loss control **1.2245976** vs platoon challenger **1.2238507**; contrast
statistic = per-start means (each start equally weighted), paired
bootstrap 2000/20261001: **delta = -0.0008712, CI95 [-0.0012622,
-0.0005038] - ENTIRELY BELOW ZERO -> platoon challenger favored
statistically.** Practical magnitude: |delta| = 0.00087 > the declared
0.0005-nat practical threshold -> practically meaningful. **K-count
non-degradation guard (point-estimate acceptance guard, NOT a statistical
noninferiority claim): point estimate +0.0000409, within the 0.002
margin** (CI [-0.0029, +0.0030] reported as context). Per the pre-declared
rule: the platoon feature family REGISTERS A CANDIDATE feature-family
addition for a FUTURE frozen-contract decision; promotion is NEVER
automatic - no production, policy, or live-model change is made or
authorized by this result. Classwise/K metrics and per-cutoff split-rate
table in the report/artifacts (declared secondary). Development evidence
only; outputs preserved write-once untouched; single run, no retry, no
variants. Evidence handoff delivered to Chat 2 on PR #58. CLOSEOUT
2026-11-04: Chat 2's artifact verdict = INDEPENDENTLY VERIFIED; record
closed once (see block header); artifacts untouched; no rescue variants,
no rerun.

**INTEGRATION PREP 2026-11-04 (#57/#58, existing process; NOT blocking the
next specification):** destination of the stack is MAIN via the dependent
chain #58 (`research/platoon-information-v1`, base = #57's branch) -> #57
(`research/binary-k-vs-multinomial-v1`, base = main) -> main; the
dependency order is preserved (merge #57 first, then #58, or both in one
delegation). Both PRs: CI pass both jobs, CLEAN, no conflicts. Merges are
architect-delegated on the PRs (Chat 2 executes); no direct-main pushes.
The LGBM slice below is specified and implemented WITHOUT waiting for that
integration.

**CHAT 3 FINAL CLOSEOUT 2026-10-29 (read-only inventory + PR #53 disposition;
NO deletions, NO merges, NO worktree changes; lane CLOSED after this entry):**
(1) STATE: local main == origin/main at `31bc557`; primary checkout 0 dirty /
48 untracked (preserved, listed in Waiting-on-user). PRs #46/#48/#49/#50 all
MERGED 2026-10-28 evening - the 2026-10-28 closeout's UNMERGED list is stale;
ROLES_REV docs are on main (pointer above repaired). Open PRs: #51/#52
(baseline stack, PRESERVE) + #53. (2) WORKTREES (19): clean+synced: wtsc
(PR #52 lane - NOTE: lives under %TEMP%\opencode\wtsc, fragile location,
owner should consider relocating), baseline-lane, docs-consolidation
(PR #53), docs-lane, integration-verify-50 (PR #51), maintenance-dep-declarations
(PR #46 branch). DIRTY - PRESERVED, no touch: distribution-spec (2 dirty
backlog+spec edits + 16 untracked D0/TBF research files - agent lane,
uncommitted research content), main-active (AGENTS.md edit + 5 untracked
drafts - Chat 1 legacy), paext-v2 (1 dirty test file), repo-review-paext-registration
(3 `_*.py` scratch). Nine detached review-* worktrees at pinned SHAs =
PRESERVED HISTORICAL; retirement owner-gated; closing this window does not
require deleting any of them. (3) **PR #53 DISPOSITION: KEEP FOR REVIEW**
(mergeable CLEAN vs main; merge-base 15fe7bf = pre-today). Unique content on
4/4 files: DECISIONS consolidation 15,931->5,837 bytes (main still carries 5
stale "quote below" pointers - the PR fixes a real defect); README authority
map (+15); repo_canonical_map retirement table (+14); ROADMAP idea-record
format (+29/-5). One claimed fix is MOOT: the "bounded repairs from another
worktree" role paragraph is already absent at its merge-base, so main never
needed that repair. Nothing merged or closed. (4) BRANCH CLASSIFICATION
(inventory, not deletion approval): PRESERVE ACTIVE - research/
baseline-v2-derivation-runner, research/baseline-history-scorecard-v1.
OWNER-APPROVED-RETIREMENT CANDIDATES (work fully merged, evidence checked:
theoddsapi script landed via PR #44, BOM fix present on main, PRs #46/#49/#50
merged): docs/lineup-path-reconciliation-spec, chat3/doc-simplify-20261023
(remote still exists), chat3/verify-and-consolidate, chat3/lighten-20261023b
(ahead 2, content verified on main), chat3/doc-collapse-20261023 + chat3/
verify-script-20261023 (local-only, origin gone), research/baseline-benchmark-v1
(worktree clean; PR #50 merged), research/paext-v2-count-agg-eval (PR #29
merged). NOT RETIRED / OTHER-LANE OWNERSHIP: research/calibration-exec-gate-v1
(PR #48 merged BUT worktree paext-v2 is DIRTY - retire branch only after the
dirty file is dispositioned by its lane); research/count-pmf-calibration-v1
(integration owned by Chat 1 per CHAT 3 PARKED entry); architect/
roadmap-20261021 (owner-instruction branch); research/pregame-pa-ext-v1
(ahead 5, superseded by v2 - owner question); chat2/review-tooling (Chat 2);
research/paired-uncertainty-v1/v2 + preserve/legacy-pending-20261005
(explicitly preserved); 9 pr*-review merge-slot branches (historical review
records). No local-only commit was found on any branch whose content is
absent from main except the flagged ahead-branches above (all verified
integrated or owner-questioned). (5) Chat 3 lane is CLOSED. Chat 1 continues
the Stage-1 preparation command under its own authorization; Chat 2 stays
parked until preparation evidence exists.

**CLOSEOUT 2026-11-03 (Chat 1 builder; docs + one test-determinism repair; NO run,
NO new science; this block is the live state and supersedes the stale PR #52
head/CI pointers earlier in this snapshot):**
(1) **Workload personalization experiment COMPLETED / VERIFIED.** Chat 2's
independent recomputation from the saved artifacts VERIFIED the builder-reported
record (PR #52 comment `6595706937`): all identities, reconstruction gate
(max per-start RPS diff 0.0 vs pinned reference `3414d0d2...`, n=2,509, cohort
`f77d7a66...`), and metrics reconcile. Verdict: **pooled league BF control (W0)
favored over pitcher-specific workload personalization (W1) on development
data** - delta = RPS(W1) - RPS(W0) = +0.012406, CI95 [+0.004410, +0.020368],
entirely above zero; |delta| exceeds the 0.005 engineering threshold. BF
interpretation retained: negative mean BF error = underprediction (W1 -1.03,
W0 -0.19); higher interval coverage is NOT automatically better (both arms
overcover; W1 covers more yet scores worse); interval width is not established
by coverage alone. Single-update rule satisfied: this block + the rewritten
shortened `docs/NEXT.md` (stale checkpoint/card pointers replaced) are the ONE
update. Workload-model assumptions are to be investigated before any
complexity; no refit, no rerun, no rescue variants.
(2) **Original run artifacts and receipts preserved, untouched:** write-once
dir `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\
workload_personalization_w0v1\` (9 artifacts incl. receipt_initial/receipt_final;
hashes reconcile; verified present 2026-11-03).
(3) **PR stack prepared for integration (three open PRs; merge is
architect-delegated, not builder-authorized; the scientific verdict does NOT
authorize merge or any production/policy/model change):** #51
`research/baseline-v2-derivation-runner` -> main (reconciled head `2757015`,
origin/main merged in 2026-11-03 to clear the CONFLICTING flag; CI green
before the docs-only merge) -> #52 `research/baseline-history-scorecard-v1`
(stacked, base = #51 branch) -> #53 `docs/consolidation-slice-1` -> main
(ad5871a, CI green). CI repair on #52:
`tests/test_pregame_multiclass_baseline.py::test_cohort_restriction_excludes_extra_starts`
selected the cohort row via `unique().head(1)`, whose row order is not
deterministic (CI got P2 where local runs got P1); replaced with an explicit
`filter(pl.col("pitcher") == P1)` - test-only determinism fix, no registered
semantics. Integration order: #51, then #52, then #53. This file and
`docs/NEXT.md` now carry BOTH sides' entries reconciled (Chat 3's 2026-10-29
closeout above + this block).
(4) **Chat 2 handoff (async protocol):** review the superseding checkpoint
SHA once published (delta from `ca87ba1`: NEXT rewrite, backlog closeout
block, roles-README approval-rule amendment, one test-determinism fix, plus
the 2026-11-03 origin/main reconciliation merges), then park again. No
polling, no reopening unchanged findings.
(5) **Approval/handoff rule amended into the canonical roles document**
(`docs/roles/README.md`; no new policy file): an approval request names exactly
ONE action with its action, full SHA, packet, data scope, and destination;
approval is recorded once and not re-asked for unchanged scope.
(6) **Next experiment NOT started:** it will not launch until the architect
assigns its single question.
(7) **APPROVAL RECORDED 2026-11-03 (owner, per the amended roles rule):**
delegated integration merge of the existing PR stack APPROVED - action: merge
PR #51 (head at approval `8047529`; reconciled to `2757015` 2026-11-03, same
scope), then PR #52 (head at approval `72cf9a3`; superseding checkpoint names
the reconciled head), then PR #53 (head ad5871a), in that order, each after
current-head review and required CI checks, executed by Chat 2 on architect
delegation; packet: none (docs + one test-determinism fix); data scope: none
(no data reads, no production/policy/model/ledger changes); destination: main.
Do not re-ask while this scope is unchanged.

**Critical path:** `docs/NEXT.md` (single source of the current action;
ROLES_REV 2026-10-28-r1, MERGED to main via PR #46 2026-10-28).
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

**MULTICLASS E2E BASELINE SLICE (checkpoint 9bdd3b4, pushed;**
column (label-integration repair subsequently implemented at f1eda215);
that failed attempt's evidence preserved at pregame-pa-ext-v2\diagnostics\
pregame_multiclass_baseline_v1_inputs\ (failure_record.json only; label-
source disposition resolved by architect: m0 raw-file bridge).**
**STAGE-2 BASELINE EXECUTED (owner-authorized, 2026-10-30): exit 0.
Cohort restriction to registered 2,509-start eligible population applied
(--cohort-keys from count_agg_eval_v1 block_2025H1 slice, hash
f77d7a66... verified). 148,369 training rows; 2,509 scored starts;
55,579 assessment PAs (43,565 matched to projections, 12,014 excluded
no-projected-matchup, 467 excluded by cohort restriction). PRIMARY
RESULT: RPS(Ref1 multinomial) - RPS(Ref0 population) = -0.086351,
CI95 [-0.104141, -0.067529] â€” ENTIRELY below zero: the regularized
multinomial logistic model's K marginal produces significantly better
count forecasts than population proportions under identical workload,
aggregation, and assessment starts. K-marginal log loss: Ref0 0.5171,
Ref1 0.5057. K-marginal Brier: Ref0 0.1672, Ref1 0.1635. Multiclass
log loss: Ref0 1.2379, Ref1 1.2246. Development evidence only; not a
production or betting claim. Receipt chain intact; cohort hash matches
f77d7a66...; output hashes verified; failed inputs_v1 preserved
unchanged; Chat 2 independent result verification NEXT.**
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

**PAEXT LANE BRIEFING CAPTURED 2026-10-29 (docs-only; NO new claims, NO
execution, NO experiment/policy authorization):** two coworker briefings
consolidated into
`research/offseason_2026/pregame_pa_ext/briefing_pa_model_and_architecture_2026-10-29.md`
(code inspected at `0cd8175c`). Part A = baseline mechanics explainer: three
inputs (PA table / reconstructed lineups / BF PMF), the 8-feature w150
shrinkage + 90d-EW construction, fixed-config softmax multinomial logistic,
empirical BF workload, and the registered aggregation = **binomial
conditionals at averaged cycled-slot probabilities mixed over workload --
explicitly NOT a heterogeneous Poisson-binomial**, correcting earlier
explanations (including the briefer's own) that blurred that distinction;
plus TTO/lineup-order notes, proposed feature-family queue, leakage rules,
and the 3-target scorecard (PA K prob / BF distribution / total K). Part B =
architecture direction: STAY PA-level, no pitch-by-pitch simulator
(three-architecture table; PA-level joint simulator as possible later
challenger); prop pricing via joint PGF with taxonomy caveats (walk class
includes HBP/interference; in-play-out includes errors/FC); RotoGrinders
capture path feasible but needs preseason validation + lineup-accuracy
metrics. The file carries status notes reconciling it with existing evidence
(Question A exact-aggregator result = dev-only diagnostic, baseline retained;
lgbm-equal-info v2 closeout: nonlinear challengers RETIRED); the
debut-pitcher/cold-start owner decisions remain OPEN per
`docs/reference/reports/backlog_archive_2026-10-21.md`.

**BRIEFING PART C + CHAT 2 ASYNC PROTOCOL (captured 2026-10-29, same file,
Part C appended):** Chat 2 is KEPT but operates ASYNCHRONOUSLY - parked while
Chat 1 builds, active once at each PUBLISHED checkpoint (fetch + review that
exact SHA, blockers vs follow-ups), then parked again; no polling, no
mid-edit working-tree review, no reopening unchanged findings; Chat 2 never
edits builder files. Chat 1 implements one agreed task, publishes complete
SHA + evidence, responds to consolidated findings, executes only authorized
procedures. Modeling-change discipline (recipe FROZEN until real
Ref0-vs-Ref1 scores): keep StandardScaler + current logistic unchanged;
later single-change experiments in order (fixed logistic ref -> one
representation change, first candidate log1p(n_prior_pitcher/batter) ->
bounded regularization search -> nonlinear challenger on same features ->
new feature families), tuned on earlier chronological periods and assessed on
a later one (nested evaluation; never change scaler+features+regularization
+history+workload simultaneously). Distribution coherence (valid probs, PMF
sums to 1, nondecreasing CDF) is REQUIRED for any estimator; feature-response
monotonic constraints are OPTIONAL challengers, never blanket (support/rest/
velocity/handedness are not monotone; class-score constraints do not
guarantee monotone final K prob after softmax). Smoothing lanes kept distinct
(shrinkage strength estimable on dev; continuous workload pooling
P=w*P_pitcher+(1-w)*P_league is a hypothesis to compare, not assume).
Training-loss charts only from real recorded evaluations (LightGBM
record_evaluation; no fabricated curves for the logistic). Comparison ladder
after baseline: population rate / binary logistic / existing multinomial /
one-representation logistic / fixed-config LightGBM (RETIRED lane - reentry
needs a new registered reason per lgbm-equal-info v2 closeout) / bounded
tuned winner; KNN + neural nets deferred. IMMEDIATE (owner direction): Chat 1
finishes the corrected preparation script + synthetic checks; Chat 2 reviews
the published script ONCE then parks pending authorized preparation
evidence; active scope = assessment preparation then population-vs-
multinomial comparison, NOT a model tournament (PR #52 open at `0cd8175c` at
capture time). Next empirical milestone: real Ref0-versus-Ref1 scores.

**WINDOW CLOSEOUT 2026-10-29 (docs-only session; 5 commits to local main, ALL
UNPUSHED at close - owner runs `git push origin main`):** commits 0bc2e24
(briefing Parts A+B captured + ROADMAP Question A delta corrected to
-0.0003333 + diagram 04/06 status notes), 9f9a718 (briefing Part C + Chat 2
async protocol), d7c7452 (five repo-* specialist bounded read-only passes +
10 broken-link repairs), and the final closeout commit (diagram 08 Question A
stale-node correction + NEXT.md PR #52/async reconciliation). Consistency
sweep complete: no tracked doc still claims (a) the registered research
aggregation is Poisson-binomial (registered baseline = binomial conditionals
at averaged cycled-slot probs), (b) Question A unevaluated, or (c) the stale
-0.000169 Question A figure (PROJECT_STATE's -0.000169 correctly remains: it
labels the separate M0 v2 diagnostic). OPEN owner decisions carried in
Waiting-on-user: pingouin declaration (reliability.py), CI slice for the 15
research-lane test files, ~30 untracked local files disposition, cleanup
deeper gated phases. Known operational gap: `artifacts/odds_log/ledger.parquet`
MISSING (run production refresh).


## Execution Order

1. **[APPROVED] Commit the current green working tree** (test fixes: `test_pipeline.py`, `test_pitcher_features.py`, `test_registries.py`, `test_train.py`; new observability files from the daily-improvement session). Clean baseline before anything else touches the repo.
2. **[BLOCKED â€” verified no-op 2026-08-27]** Split/commit `close_watcher.py` (lock hardening vs. aux-market-probe). Verified: working tree is clean, the aux-probe + late-open features are already buried together inside the broad commit `de942c3` (183 new lines in close_watcher.py among 27+ files), the pre-split backup `.py` is gone (only a stale `.pyc` remains), and there is **zero uncommitted delta to split**. The split would require a destructive rebase/filter of already-committed history â€” not doing that without explicit sign-off. Treat as effectively combined already; resume only if user explicitly wants the `de942c3` history rewritten.
3. **[DONE 2026-08-27 â€” commit 3947a7a]** Widen CI (`ci.yml`): py_compile all 60 production scripts (dynamic find, was 6 hardcoded), full 270-test suite (was 2 files), install pyproject deps `.[dev]`+scipy (was a no-op `requirements.txt` that never installed polars). Validated: 60/60 compile, 270 tests green, YAML OK.
4. **[DONE 2026-08-27 â€” commit 2d27ef3]** Dedupe-to-best-line as shared infrastructure. Fixed canonical `dedupe_ledger_props` to key on `(game_date, player, line, SIDE)` (was missing side â€” kept over/under of the same line merged, a latent bug; 22 such props in data). Wired the one canonical function into the 3 scripts still aggregating raw rows: `line_policy_settled_lookback`, `clv_basis_reconcile`, `build_automation_self_check`. Added 2 tests (over/under kept separate; best book per side). Validated: 272 tests pass; real-ledger settled 1118â†’643 props.
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
   | Line 4.5 all ROI | âˆ’26.4% (n=413) | âˆ’22.2% (n=244) |
   | Line 4.5 profile(â‰¥.14) ROI | âˆ’33.3% (n=76) | âˆ’34.1% (n=52) |
   | Line 5.5 over ROI | âˆ’59.1% (n=22) | âˆ’61.8% (n=13) |
   **Headline: the all-time "green" was +2.08%/+$576 on raw; on the honest deduped ledger it is +0.51%/+$84.51 â€” barely above breakeven. Skill-gate n falls 248â†’150 (still met) and WR is essentially flat (0.534â†’0.5334); the edge shows in CLV, not raw WR.**
6. **[DONE (infra) + BACKFILL BLOCKED on operator prices â€” 2026-08-27, commit 1da4c82]** Built the append-only real-bet ledger: `src/Python/real_bets.py` (separate from paper-sim `ledger.parquet`; decision-time `bet_price`/`stake` snapshot; `append_real_bets` returns `(frame, n_appended, skipped_ids)` so no ticket can silently drop â€” the 8/24 failure mode); `tests/test_real_bets.py` (6 integration tests proving idempotency, in-batch dup reporting, re-append never-silent, realâ‰ paper path, summary math, stable schema); `production/ops/backfill_real_bets.py` (holds the 8 confirmed identities Valdez U4.5 W / Suarez U4.5 W / Messick O6.5 L / Skenes U6.5 W / Melton O3.5 W / G.Rodriguez O4.5 L / Cantillo U6.5 W / Sasaki O4.5 L; refuses to write rows lacking a real decision-time price/stake â€” reports instead of fabricating zeros). **SATISFIES THE INTEGRATION-TEST REQUIREMENT.** Backfill WRITE is BLOCKED only on the per-ticket decision-time `bet_price`/`stake`/`pnl` (and the 9th ticket's identity+prices) which live in the user's records â€” fill `REAL_TICKETS` in the backfill script and rerun; complete set is 6Wâ€“3L, +$109.80/$455.
7. **[BLOCKED â€” no script to rewrite 2026-08-27]** CUSUM `corr_before`/`clv_before` null bug. Verified: the CUSUM/regime **regeneration script does not exist anywhere in the repo** (no source for `regime_model_report.json` / `corr_after` / `clv_after` / `cusum`; only the artifacts remain, and it's likely a deleted one-off probe like `_probe*.py`). Diagnosis captured from the surviving artifact for when the script is restored: `corr_before: null` despite `edge_win_corr_break_pos: 253` (rolling_window 40) and `clv_before: null` at `clv_break_pos: 191` â€” i.e. the pre-breakpoint sample window is too small/empty, so the "before" stat computes null. The rewrite needs a min-sample guard that emits an explicit `null`/`insufficient` with the n instead of an unlabelled null. Resume when the script is restored or the user provides it.
8. **[DONE (in-repo sweep) 2026-08-27 â€” external network call remains outside agent scope]** External-outcome recovery sweep. Verified from the ledger and stored artifacts:
   - **8/24 gap is isolated to a single day, not systemic**: `ledger.parquet` has daily rows through 8/20â€“8/23 and 8/25â€“8/27 but **0 rows on 2026-08-24** â€” an isolated one-day ingestion hole in an otherwise-continuous record.
   - `open_projection_quotes_raw`/`open_quotes_canonical` **end in early July entirely** (last rows ~2026-07-10/11), so they never reached August â€” their "0 rows for 8/24" is trivial; not the right source for recovery.
   - **Melton's real 8/25 O3.5 line is not in the paper ledger** (only other Melton dates/lines are: 8/04 U5.5, 8/15 O5.5, 8/21 O4.5, 8/26 O3.5) â€” same class of real-ticket data gap as 8/24.
   - **Real-ticket players are present in the paper ledger on different dates/lines** than their real bets â€” confirming real (real_bets.parquet) vs paper are correctly separate tracks.
   - **Recovery action**: both gaps are isolated ingestion/record flat-spots, so a targeted external odds/score call (not a systemic rebuild) is warranted; executing that network/API call is outside what the agent can run here. 8/24 outcomes are already user-confirmed (PnL not blocked); this is an auditability/completeness backfill only. Side pattern re-confirmed: all 3 real losses were Overs (Messick, G.Rodriguez, Sasaki).
9. **[EVIDENCE COMPLETE 2026-08-27 â€” swap still gated on user sign-off]** Champion-vs-monotone swap evidence package. The side-conditional breakdown is already fully built in `artifacts/odds_log/_audit_step4_monotone_sidebreak.json` â€” and it was **never actually blocked on #4-#5**: it operates on the 2025 model open universe (`config.PITCHER_TRAINING_PATH`) with its own `(pitcher+line+date)` dedupe, NOT the 2026 settled paper ledger that #4-#5 dedupe. That BLOCKED-PENDING-#4-#5 status was a false dependency. Evidence verdict (clean, complete):
   - **LODO robustness: passed** â€” 0/55 date-drops flipped monotone's advantage (`flip_dates: []`), pooled Brier margin +0.0135 for monotone.
   - **Overs: no change** (n=896; WR 0.4766 / ROI@fair 0.1067 identical; calib âˆ’0.0307â†’âˆ’0.0301).
   - **Unders: monotone improves calibration (+0.0073 on shared n=835) and reduces the unders bleed â€” but does NOT make it positive**: deduped under ROI@fair âˆ’0.0272 (champion) â†’ âˆ’0.0166 (monotone). Softens but does NOT obsolete the unders-floor problem.
   - **Verdict**: swap is coherent and robust, but unders-floor still requires its own decision (not obsoleted). Per Standing Rules, the actual champion swap is NOT an approved action â€” it needs explicit user sign-off after this evidence is reviewed.


## New Items

10. **[DONE 2026-09-01]** Two-tier test-gating. Added `.pre-commit-config.yaml` (local system hook: pytest on `tests/test_odds_ledger.py tests/test_real_bets.py tests/test_registries.py`). Ran `pre-commit install`; fast subset **28 passed in ~3.9s**. Full suite remains CI-only.

11. **[PROVENANCE AUDIT â€” COMPLETE 2026-08-27]** Grep for every place that aggregates the ledger; confirm each historical finding's generating script and whether it used canonical `dedupe_ledger_props`, a bespoke grouping, or raw rows; flag what needs recomputation. **Verdict (evidence-backed):**
    - **CLEAN â€” already on the fixed canonical `dedupe_ledger_props`** (live import â†’ round-trips fixed signature automatically): all `artifacts/odds_log/_*.py` (`_analysis_extra`, `_audit_stratify_by_epoch`, `_audit_stratify_edges`, `_calibration_deep`, `_clv_snapshot`, `_timing_results`) + production `grade_odds_ledger.py`, `build_automation_self_check.py`, `line_policy_settled_lookback`, `clv_basis_reconcile`, `weekly_kpi_report`.
    - **RESOLVED specific concern:** **favorite/dog ROI splits + lineÃ—side splits** come from `_audit_stratify_edges.py` (lines 85â€“124), which calls canonical `dedupe_ledger_props` â€” **CLEAN, no recompute.**
    - **BESPOKE but side-aware â€” unaffected by over/under merge bug:** `keep_best_available_lines` (`src/Python/notebook_analysis_utils.py`, keyed on `(game_date, player_name, side)`) used by `build_policy_governance_report.py` + `policy_simulator.py`. Key already includes `side`, so it never had item-4's bug. (It intentionally collapses across LINES per game/player/side â€” different, intended semantic, not a regression.) No recompute.
    - **AT-RISK â€” aggregates RAW settled rows, bypasses canonical dedupe (recompute under fixed logic):**
      - `build_runtime_monitoring_snapshot.py` `_compute_floor_table`/`_compute_monthly_regime`/`_compute_edge_deciles` (roi/pnl on raw rows). Quantified: raw settled **1118 / +$576.15**, deduped **643 / +$84.51**. The `daily_kpi_loop_last_run.json` `total_pnl=$+1041.04` is a stale raw-row artifact of this path. NOTE: `_compute_slippage_segments` segments *by book*, intentionally raw â€” leave it.
      - `edge_floor_sweep_governance.py` `_load_settled_ledger` (line 72): raw settled.
      - `policy_calibration_uncertainty_sweep.py` `_load_settled_ledger` (line 136): raw settled.
      - `build_daily_operator_summary.py` `_ledger_snapshot` (line 40): per-day stake/pnl/roi on raw settled rows (DK+FD pairs double-counted per day).
    - **ORPHAN â€” generator not in repo (same class as item 7):** `regime_model_report.json` (`is_fav`/`is_over` coefficients; 939/999-bet regime analysis) has **no source script** in the repo â€” only the artifact remains. Provenance cannot be confirmed; do not cite its coefficients as settled until the generator is restored.
    - **NOT AFFECTED (different data domain):** `build_board_ledger_reconciliation.py` (targets `status=="open"` slate occupancy, not settled ROI); the A1/champion side-strat audit (2025 model open universe, not the settled paper ledger â€” consistent with item 9).
    - **Next (approved, not blocking):** add `dedupe_ledger_props(settled)` to the four at-risk aggregators above (keeping slippage-segments raw-by-book) + a regression test. Do NOT touch the orphan regime artifact.
    11-followup. **[DONE 2026-08-27 â€” aggregator dedupe fix]** Wired canonical `dedupe_ledger_props` into the producer + all four at-risk aggregators: `grade_odds_ledger.py` (`--status` PnL sum, `--curve` n_settled), `build_runtime_monitoring_snapshot.py` (floor/monthly/deciles use deduped; slippage segments keep raw-by-book), `edge_floor_sweep_governance.py` + `policy_calibration_uncertainty_sweep.py` (`_load_settled_ledger`), `build_daily_operator_summary.py` (`_ledger_snapshot` daily ROI/PnL). Added regression test `test_dedupe_ledger_props_pnl_not_double_counted` (proves DK+FD pair is not double-counted in PnL aggregation). All 5 files py_compile; `tests/test_odds_ledger.py` 13/13 green. **Live-verified 2026-08-27**: `grade_odds_ledger.py --status` printed `settled=643 total_pnl=+$84.51` (was 1118/+$576.15 raw; stale loop artifact +$1041.04). Regenerated `daily_kpi_loop_last_run.json` via `run_daily_kpi_loop.py --skip-notebooks` â†’ `n_settled=653` (deduped; +~10 settled during run). **Refresh 2026-09-01**: after more settled days, deduped ledger is `settled=790 total_pnl=+$10.55` (ROI â‰ˆ +0.05%); full-cohort CLV reconcile is `n_closed=493`, `price_devig_gt0=0.544` (was 441 / 0.551 on 2026-08-27). Note: dashboard `_dedupe_frame` keys on `book` too â€” only exact-dupe removal, not canonical cross-book dedupe (potential item-11 follow-up). **(Item 11 follow-up now COMPLETE; reordered to run before item 10 per user approval.)**

12. **[WAITING ON USER] Item 6 backfill** â€” still needs your decision-time `bet_price`/`stake`/`pnl` for the 8 confirmed tickets (Valdez, Suarez, Messick, Skenes, Melton, G.Rodriguez, Cantillo, Sasaki) plus the 9th ticket's identity, to complete the real-bet ledger write.

13. **[APPROVED â€” DEFERRED] Local MLflow Tracking (thin v1).** Useful when actively iterating Strikeout/TBF train or Optuna â€” **not** on the critical path for this ops cycle (wrong tool for freeze/null/CLV/veto work). See Session Snapshot â†’ **DEFERRED**. Resume when you ask or when train iteration restarts; do not jump here mid-ops.

14. **[DONE research 2026-09-01 â€” promote gated] Granular open calibration challenger (ROI path).** Fit line / line-bucket (and optional side-aware apply) isotonic/Platt on **open 2025â€“2026** with chrono-safe holdout; score **post-freeze** as pure OOS on skill vs market + shadow KING ROI. Do not refit on post-freeze tickets. Do not edit live calibrator / KING without sign-off. Script: production/ops/fit_granular_open_calibration.py.



## Next Session â€” Open Questions & Plan (evergreen)
> **Not a second backlog.** Canonical live plan = Session Snapshot â†’ **PAST / PRESENT / FORWARD / DEFERRED** (top of this file). Checklists below are a short mirror only.

**Waiting on user (blocks these):**

**Waiting on user (blocks these):**

- [ ] Cleanup-skills bounded pass DONE (see Parking Lot 2026-10-29 entry): two owner decisions open - (a) `pingouin` undeclared import (`src/Python/reliability.py`): declare or remove; (b) approve a CI slice adding strict-failure pytest steps for the 15 research-lane test files outside `testpaths`.
- [ ] Disposition ~30 untracked local files (tests, reports, market_research scripts, `research/offseason_2026/experiments/forward_2025.parquet` + `run_2025_selection.py` + `selection_2025_report.json`) - uncommitted work at risk; commit, archive, or explicitly discard per file.
- [ ] Confirm 2.5/3.5 over style â€” **data rec 2026-09-11: freeze current probation** (from the archived CLV + Hosting Plan; carried forward at split)
- [ ] **Dashboard v1** â€” parked until backend #113 is green; say go to unpark (from the archived CLV + Hosting Plan; carried forward at split)
- [ ] `git push origin HEAD` so remote has promoted 4.5-over veto.
- [ ] Ops Checkpoint A review: 5 owner questions (`docs/reference/reports/ops_contracts_2026-09-30.md`, defaults YES) + OPS-1 defaults sign-off.
- [ ] Scoped infra/docs commit checkpoint (writers paused during staging; model/production/ledger files excluded).
- [ ] Item 6/#12: per-ticket decision-time prices/stakes/pnl for the 8 + 9th identity.
- [ ] Item 9: explicit championâ†’monotone sign-off, or leave deferred (not needed for 4.5 veto).

**Ready / operating now:**
- [x] Live `veto_4_5_over` + soft probation 2.5/3.5 â€” DONE 2026-09-01.
- [x] Weekly settle pack habit â€” re-run after each settle week.
- [ ] Item 13 MLflow â€” APPROVED but **DEFERRED** (wrong tool for this ops cycle).
- [ ] Optional polish: regenerate `manuscript.pdf`; dashboard dedupe â†’ canonical `dedupe_ledger_props`.

**Blocked / parked (see DEFERRED + Execution Order):** Item 7 CUSUM rewrite; Item 2 history split; SSAC future-work 9â€“13.

**Historical polish notes** (2026-08-27 freshness sweep detail, ledger refresh figures): kept in git history; intentionally not repeated here so this section cannot compete with the Snapshot.


## Standing Rules (apply to all of the above)
- Never mutate historical labels (holdâ†’bet relabeling) â€” always append new records instead.
- Every real-money conclusion requires â‰¥50 real tickets before being treated as evidence of edge. The current 9-ticket, +24.1% ROI record is now fully auditable (6Wâ€“3L, all outcomes confirmed) â€” a good start, not proof; don't let it drive stake-sizing yet.
- Verify settlement-rule parity (prediction-market vs. sportsbook K definitions, extra innings, early exits) before trusting any grading as final.
- Personal accounts/API keys only â€” never company-owned tooling for any of this.
- Do not touch `KING_PROFILE_AUG2026`, floors, staking, or the champion file without explicit sign-off after evidence is reviewed.
- **DEFERRED is binding:** Item 13 (MLflow) and other Snapshot â†’ DEFERRED rows are not idle backlog to fill quiet turns. Do not scaffold/install them during an ops/policy week unless the user asks or the reopen condition is met.
- Prefer weekly settle-pack measurement and real-bet logging over new tooling while the live 4.5-over veto is the active experiment.
- A pre-registered sample-size gate that is *exactly* met (not comfortably exceeded) should be treated as "not yet conclusive" â€” do not size up or treat as validated edge until the sample comfortably clears the threshold with margin.
- **Measurement vs money (owner-locked 2026-09-11):** two jobs, never mixed. *Measurement* (are we right?) = devigged consensus median at the same snapshot (`consensus_cache.parquet`, never re-devig) for Brier/skill/CLV. *Money* (did we profit?) = juiced book-pair at the decision clock (DK else FD else next US book) for ROI/WR. Report both forever; cite which lane every number lives in. Dedupe (`dedupe_ledger_props`) is money-track aggregation only â€” selection stays per-quote, lineÃ—side cells stay per player O/U line.


## Parking Lot (new ideas noticed mid-task â€” do not act on these until the list above is clear)
- **Full cleanup-skills program (owner request 2026-10-29) - BOUNDED PASS COMPLETE 2026-10-29, deletions still owner-gated:** all five specialists' read-only "Explore first" inventories executed + allowed pointer repairs applied; findings consolidated here (no separate report written). (1) **docs-canonicalizer:** 10 broken relative md links found and REPAIRED (reports README full-index: 9 dead rows converted to the established "FILE REMOVED; git history preserves it" plain-text convention per the PR #41 pattern; `docs/archive/CLEANUP_LOG.md` relative path fixed to `../EXECUTION_BACKLOG.md`); register + supersession CSVs exist and current; 6 prereg `*-draft.md` pairs in `research/offseason_2026/` remain per T6 disposition plan (banners executed PR #15; deeper disposition pending, untouched). (2) **dead-code-auditor:** static text scan over `src/Python/` + `production/` found ZERO zero-reference candidates - no deletion candidates surfaced (scan is text-only; skill caveats on dynamic imports/lake runners apply; full evidence-graph audit NOT run). (3) **artifact-lifecycle:** inventory only - 22 tracked notebooks, 79 files under `models/`, 9 paper figures; `check_notebook_artifacts.py` shows 1 required artifact MISSING (`artifacts/odds_log/ledger.parquet` - run production refresh); per-file lifecycle classification deferred. (4) **ci-coverage:** CI collects `testpaths=["tests"]` = 128 files; 15 research-lane test files sit OUTSIDE default collection (bf_lane 2, bf_workload_v1 1, market_eval 4, p1_harness 3, prospective_logging 1, count-eval-v2-spec 4); CI runs only ONE explicitly (`tests/test_pregame_pa_tracking.py`); gap spec = add explicit strict-failure pytest steps for the research harness suites - workflow edit needs an approved slice, NOT done. (5) **dependency-hygiene:** `tests/test_sb_dependency_declarations.py` 4/4 PASS (sage remains a registered deliberate exclusion per its test contract); scanner surfaced one REAL undeclared import: `pingouin` (consumer `src/Python/reliability.py`) - outside the S-B test's src-only declared-set scope; needs owner decision: declare (tier?) or remove consumer. Declared-but-unimported candidates (PIL/cv2/fitz/plotly/pyarrow/yaml/bs4/sklearn etc.) are false positives of the name-normalization scan - not findings. Prohibition #3 unchanged: no deletions without evidence artifact + owner gate + validation + rollback.
- **Cheap agent stack (2026-09-02) â€” PARTIAL DONE:** ignore-files + agent-context rule shipped. Still parked: Cline/OpenCode + DeepSeek V4 Flash on Mac; kill Cursor Auto/credits; escalate Kimi/GLM; Claude escape hatch. Never route Lenovo work through Chinese APIs. Reopen when user starts Mac harness migrate.
- **Historical K CLV backfill (2026-09-02) â€” RESEARCH DONE, pull PARKED:** see `docs/reference/reports/historical_clv_odds_apis_2026-09-02.md`. Execute free HF + OddsPapi smoke then optional The Odds API month only when user asks. Do not start paid pull mid-ops week.
- **Book-quality filter â€” WONT_DO** (user 2026-09-01): books used for lines only; usually synced.
- **Juiced next-book vs DK+FD (2026-09-11 #123):** next-US-book fallback after DK/FD soaked BetRivers (n=1,001 of 2,077, WR 0.429). GO had said median. Waiting on owner which universe is canonical. Do not mix all-books ROI with DK+FD ROI.

- **Live A/B parallel ledgers:** score every opportunity under status_quo / veto_4_5 / asym16 even when only one rule is bet live.
- **Block bootstrap by game_date** for ROI/CLV CIs; do not bootstrap a line cell with nâ‰ˆ18 into a promote claim.
- **Real-bet first:** Item 6/#12 unblocks honest money ROI vs paper.
- **Optional soft veto:** size 2.5â€“3.5 overs at 0.5u instead of hard skip if learning value matters.
- Three-state action space (bet / prediction-market-watch / hold) as a cleaner replacement for the binary bet/hold flip.
- Calibration-drift monitor (recent-window WR 0.493 vs. all-time 0.534).
- Reliability/calibration bucket report (among props rated 0.7-0.8, what's the real hit rate).
- Cost-asymmetry-informed stake sizing (expected loss of missing a winner vs. betting a loser).
- Side asymmetry on real tickets: all 3 losses to date were Overs; every Under/low-line-Over hit. Worth a real-ticket side-conditional check once ledger reaches meaningful n, not a 9-shot pattern to bet on.
- **MLflow v2 (after Item 13):** Optuna callback â†’ nested MLflow runs; log ensemble-sweep / null-lane decision metrics as separate experiments; optional Model Registry *mirror* of frozen champions (still not auto-promote).
- **W&B** only if you want hosted multi-machine dashboards; not needed for solo local research.
- **SSAC27 (MIT Sloan Sports Analytics Conference) â€” abstract deadline Oct 1, 2026.** Items **1â€“8 DONE**. Future-work 9â€“13 remain parked. Lead submission with modeling half; betting half stays demoted. Low-priority doc polish: move ablation/freshness self-notes to a Supplemental appendix.
- **Phase 10 pipeline-discovery + reusable-prop-platform prompt (2026-09-17) â€” CENSUS EXECUTED, design queued:** see PRESENT "PHASE 10 EXECUTED" + FORWARD Phase 10 workstreams (ARCH/DATA/PROP/SIM/EVAL/OBS/NB/OPS/TEST). Source file lives outside repo (`Downloads/Pipeline Discovery and Reusable Prop Platform Prompt.md`); content reconciled here, no second roadmap. Conflicts with FORWARD pickup box (no coding job until owner names it) and October sequencing (post-9/27) â€” design-only at most before then; no live/Modal/policy/model/schedule changes. Verified pre-checks: all 5 Modal schedules use `modal.Cron` (`modal_app.py:132,154,181,197,213`), so the Period-reset timing risk does not apply. Reopen when owner names the census or the October program starts.

- **GATE A CORRECTION COMMITTED 33e1f63 2026-10-09 (owner-authorized bounded numerical correction; 17 tests green; pre-commit passed; no push):** root cause = support truncation in cond24_binom (k>23 dropped from the uncollapsed conditional before expectation verification; NOT scipy, NOT dtype â€” builder verified vs exact Fraction reference at 4.7e-16). Fix: B conditional on full 0..n support, tail mapped via map24 (same as C), expectations via math.fsum; frozen 1e-9 gate UNCHANGED and passes all 4,446 rows x all supported n. Evidence wording corrected per owner: support-mapping identity verified over n=1..60 x 37-point p grid (max diff 4.7e-14); all 38 exported numeric columns x 4,446 rows max diff 7.3e-14 (float64 rounding; NOT claimed bit-identical); boolean flags identical; paired effects unchanged (B-A -0.033037*, C-B +0.000098*, C-A -0.032939*). Failed first validation preserved (pa-gateA-validation-20261009a) alongside passing full-row run (...20261009b). Negative tests (shifted PMF, wrong-sequence) still fail gate; edge tests p in {0,0.001,0.5,0.999,1} x n<=60 pass. Doc defect C closed. Chat-two closure review can proceed at c0805be + b2d7140 + 33e1f63. Remaining before pilot scoring: BF reconstruction (fixed recipe, pre-2025 fit, serialization, reload parity, availability audit â€” no automatic embargo per owner correction), pilot sealing, outcome authorization.
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

