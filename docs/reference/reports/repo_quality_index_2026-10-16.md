# Repository source-of-truth index — 2026-10-16 (Chat 3, report-first)

One navigable index consolidating the pipeline map (baseline §4) and the
metrics map, with explicit boundaries between production, research, governance,
and historical evidence. Base `origin/main` @ `1927c8c…`. Companion maps:
[`metrics_evaluation_architecture_2026-10-16.md`](metrics_evaluation_architecture_2026-10-16.md),
[`repo_quality_baseline_2026-10-16.md`](repo_quality_baseline_2026-10-16.md) §4,
[`docs/diagrams/00-index.md`](../../diagrams/00-index.md) (visual), diagram 06
(harness). This index is the **table of contents**, not a replacement for those.

## The four territories (and what may never cross)

| Territory | Paths | Owner | Change rule |
|---|---|---|---|
| **Production** | `src/Python/`, `production/**`, `models/`, policy JSONs | Chat 1 (builder) + owner | protected paths; PR + owner order; never research-driven |
| **Research** | `research/offseason_2026/**` | Chat 1 (builder) / Chat 2 (review) | frozen packets; prereg -> freeze -> one run -> receipt |
| **Governance/docs** | `AGENTS.md`, `CONTEXT.md`, `docs/reference/` (non-report), `docs/diagrams/`, `docs/agent_roles/` (pending) | Chat 3 | narrow PRs; never rewrites evidence |
| **Historical** | `docs/archive/`, `docs/research/`, `docs/reference/reports/` | Chat 3 (custodian) | immutable; errata/pointers only |

## Source-of-truth register (which doc answers which question)

| Question | Authoritative source | Status |
|---|---|---|
| What is approved/queued now? | `docs/EXECUTION_BACKLOG.md` | canonical-living (Chat 1/coordination lane) |
| What is the current research state? | `docs/reference/current_state_2026-10-16.md` (PR #4) | canonical-living |
| What numbers can I cite? | `docs/reference/golden_metrics.md` + its JSON sources | canonical-living; cite, never recompute |
| What results exist per experiment? | results index (PR #8) + per-run `metrics.json`/manifests | machine-generated |
| Where does each metric live? | [`metrics_evaluation_architecture_2026-10-16.md`](metrics_evaluation_architecture_2026-10-16.md) | canonical-living |
| How do I run daily ops? | `production/README.md`, `INDEX.md`, `RUNBOOK.md` | operational |
| How do PRs/reviews/merges work? | `docs/reference/pr_workflow.md` (PR #10) | canonical-living (proposed) |
| How are documents classified? | [`repo_quality_baseline_2026-10-16.md`](repo_quality_baseline_2026-10-16.md) §2 + register CSV | canonical-living |
| What do the diagrams say? | `docs/diagrams/00-index.md` + 01–06 | canonical-living (dated views) |
| What was true at time X? | `docs/reference/reports/<dated>.md` | historical; never edited retrospectively |

## Pipeline flow (data → decision), with metric checkpoints

```text
INGEST      production/ops collectors + odds arms          identity: input hashes
  v
FEATURES    src/Python L1->L2->L3 (frozen)                 integrity gates, no p-values
  v
PA LANE     P(K|PA) logistic (representative)              PA log loss/Brier, RAW+CAL   [CLOSED family]
  |
  +--> BF LANE   B0 audited / B1 accepted-with-limitation   BF MAE/RMSE/bias, PMF calibration, RPS
  |                                                        limitation: 217/4,866 recenter flags (4.5%)
  +--> COUNT    kcount_combiner seam                       count-RPS GATE; one registered B1-vs-I3b run pending READY
  v
MARKET      market.py de-vig -> board -> ledger            edge/fair-line; policy floors/veto     [frozen champion]
  v
TRACKING    MLflow execute-first-import-after (D-1)        receipts; recovery deviations documented
MONITOR     results_*.ipynb set                            KPI/CLV/calibration/cohort views       [Issue #5 defect open]
```

Boundary rules: research never feeds production automatically; metrics never
cross lanes; a BF/PA result alone promotes nothing; paper-quant is tier-5,
last.

## Consolidation guidance (evidence-backed, not yet actioned)

- The index above is the intended single entry for "where is truth about X";
  once PR #4/#8/#10 land, `README.md` + `AGENTS.md` should link it, and any
  doc that currently re-states one of these answers gets a pointer instead.
- Candidates from the register (0-inbound canonical docs with overlapping
  content) are itemized in the staleness audit — each needs its own slice.
