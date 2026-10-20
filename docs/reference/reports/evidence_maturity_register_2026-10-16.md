# Evidence maturity and citation-gate register — 2026-10-16 (Chat 3, report-first)

Classification of every material result family: **computed / persisted /
independently reconciled / citation-ready / blocked**, with artifact locations,
review-verdict references, known limitations, accountable owner, and the minimal
next action to citation-ready. Base: branch state `f3f55ca…` (reports) over
`origin/main` @ `1927c8c…`. Lake-resident artifacts are referenced via their
recorded receipts (paths/hashes live in the receipt documents, not duplicated
here). **Citation gates below are per coordination 2026-10-16: they gate
citation, not the frozen B1 count experiment.**

## Register

| Family | Computed | Persisted | Independently reconciled | Citation-ready | Owner | Blocking gap -> minimal next action |
|---|---|---|---|---|---|---|
| **PA probability (count-eval-v2 harness)** | YES | YES (write-once run dirs; repo + lake mirrors) | YES (Chat 2: eval-identity, shared rows/labels, recompute-vs-metrics) | PARTIAL — dev-fold claims only; EW-only ablation unrun so "which EW component drives the gain" is NOT citable | Chat 1 / Chat 2 | Run registered EW-only ablations when authorized; until then cite only the both-EW family result |
| **Equal-information LightGBM (PA)** | YES | YES (freeze JSONs, metrics, persisted preds) | YES (Chat 2 verified matched exposure, bootstrap, artifact inventory) | YES — narrowly: "no detectable development advantage vs logistic on the 8 both-EW features under matched exposure" | Chat 1 | GAP: CAL lanes not independently reviewed -> keep CAL claims out of citations until reviewed (citation gate) |
| **BF B0 reference** | YES | YES (audited forecast packets) | YES (B0 audit PASSED: pregame-validity + bit-identity through combiner seam) | YES — as the audited pregame BF reference | Chat 1 | none for B0-as-reference |
| **BF B1 (Ridge recentering)** | YES | YES (lake `bf-lane-v1/b1_run_v1/` + committed closeout chain `3de017a -> 6ee8544 -> 77c01c8 -> 45446b5`) | YES (Chat 2 ACCEPT-WITH-LIMITATION: recompute from persisted artifacts, 217/4,866 flags verified, MLflow recovery validated) | YES WITH LIMITATION — "Ridge-conditioned recentering improved BF-distribution + predeclared count-RPS vs B0 (−0.02818, CI [−0.03656, −0.01980], p=0.0005); integer-shift recentering of B0's empirical PMF, NOT a new uncertainty model; 217 flagged boundary rows (4.5%)" | Chat 1 | Chat 2 two-part verdict at `45446b5…` (D1/L2/L3 + count registration) — citation of the closeout awaits that verdict |
| **Count integration (I3b benchmark)** | YES | YES (`start_metrics_v2` persisted `base_h3_rps`/`base_l5_rps`; combiner seam) | HISTORICAL — original count-eval-v1 report not fully independently reconciled | PARTIAL — I3b citable as retained benchmark; the v1 report's numbers carry the citation gate | Chat 1 / Chat 2 | CITATION GATE: full independent reconciliation of the historical count-eval-v1 report (post-count-run slice) |
| **B1-vs-I3b count comparison** | NOT RUN | n/a | n/a | BLOCKED — no result exists | Chat 1 (run) / Chat 2 (gate) | Chat 2 READY at `45446b5…` -> exactly one registered execution -> independent reconciliation |
| **Calibration** | YES (live WS1c; research CAL lanes) | YES (`prob_calibration_production.json`; run CAL artifacts) | PARTIAL — live stack pin-tested; decile tables NOT independently recomputed | PARTIAL — "calibrated by construction + pin-tested" citable; specific decile-table numbers are NOT citation-ready | Chat 1 / Chat 2 | CITATION GATE: independent recomputation of calibration decile tables (post-count-run slice) |
| **Line/take (frozen champion)** | YES | YES (board, ledger, policy pins) | YES (board-ledger parity lock, `test_live_stack_pin.py`) | YES — for frozen-policy descriptions; 2026 judge numbers remain disclosed-peek only | Chat 1 / owner | none within scope; no new policy claims post-9/27 (standing rule) |
| **Paper-quant** | YES | YES (ledger + golden-metrics JSON sources) | YES (within golden-metrics discipline) | YES — only via `golden_metrics.md` citation; never recomputed; no edge/ROI claims from PA/BF results | owner | none; enforce the no-cross-lane-claims rule in every report |

## Standing citation gates (coordination-designated, report-backed follow-ups)

1. Full independent reconciliation of the historical count-eval-v1 report.
2. Independent recomputation of calibration decile tables.
3. Independent review of the LGBM equal-information CAL lanes.
4. Consolidation of the canonical bootstrap implementation + tests into a
   durable shared location (currently duplicated across harness copies — see
   code census; `m=1` Holm family retained for the count run per the Holm
   guidance).

## Rules this register enforces

- A family absent from the "citation-ready = YES" column may still be *reported*
  with its limitation verbatim; it may not be cited as a settled claim.
- Limitations travel with results (B1's recentering limitation is permanent).
- Verdicts are SHA-bound: Chat 2's ACCEPT-WITH-LIMITATION binds to the reviewed
  head; the pending `45446b5…` verdict supersedes for closeout purposes.
- No cross-lane inference: PA/BF evidence never implies market performance.

## Disposition

Report-only slice on `maintenance/quality-baseline-20261016` (no PR). Update
trigger: any Chat 2 verdict, count-run execution, or citation-gate closure —
this register is versioned by dated re-issue, not in-place rewrites of prior
registers.
