# Offseason overhaul plan 2026-09-28 (CONSOLIDATED — read this first)

Owner order: planning stage; no code changes until each build is approved.
This doc supersedes scattered planning bullets (backlog stays the ledger —
decisions + hashes live there; reasoning lives HERE). Backtest terms locked:
2023–24 train, 2025 validate, 2026 locked retrospective (never pristine),
2027 prospective. Rolling-origin folds inside.

## 1. Repo audit (measured 2026-09-28)

- 352 tracked Python files, 541 tracked files total, 17 dated reports.
- Hotspots: `production/ops/market_research/` (87 scripts — probe sprawl),
  `artifacts/odds_log/` (330 files, 90% cited research evidence),
  `src/Python/` canonical core (~40 modules that matter).
- Backlog is ~700 lines of deep bullets (owner wants depth KEPT).

### Prune (safe, offseason)

| Target | Reason | Guard |
|---|---|---|
| `__pycache__` / `.pytest_cache` / `.hypothesis` | Regenerable | Already ignored; delete locally anytime |
| Stale `*_preview.json`, `morning_alert_preview` copies | Regenerated per run | Keep latest only |
| Dead laptop `.ps1` fallbacks | Tasks disabled since cutover | Keep ONE documented fallback runner until first cloud outage proves restore |
| Pre-cutover scheduler logs | Heartbeat supersedes | Already done 9/21; keep policy |
| `notebooks_exec/`-style copies | Zero references | Verify refs, then delete |

### Replace (needs owner order each)

| Old | New | Why |
|---|---|---|
| Hand-rolled bootstrap CIs | Keep (tested, pinned) | No reason to move |
| Unittest-only new tests | hypothesis already added | Done, extend |
| Manual Kalshi panels | Hourly chain step (shipped) | Done |
| `open_dedupe_key` per-book callers | `signal_key`/`family_key` | Migrated where live; audit leftovers |

### Deprecate soon / watch

| Risk | Status | Mitigation |
|---|---|---|
| Paid OddsAPI sub ends | Research-only already; chains can't spend it | Let lapse; lake stays |
| RotoGrinders HTML scraping | Most fragile external dep (staleness ~8:30 ET) | Dawn verdict decides; MLB schedule API is the backstop |
| Polars 2.0 API churn | Deprecation warnings in CI output already | Pin major or fix warnings in consolidation |
| SharpAPI free-tier limits | Quota ~1% used; terms can change | Quota monitor exists; Kalshi/Novig diversify |
| Modal SDK drift | Pinned? verify | Pin in consolidation |
| Flat $50 unit | Fine at current bankroll | Revisit if bankroll 2x |

## 2. Organization ruling (no new top-level folder)

A second repo/folder creates two sources of truth. Instead, the approved
bounded workspace (prior decision, kept):

```text
research/offseason_2026/
  README.md            # one page: question, gates, status
  decisions.md         # decision log (not a second backlog)
  pa_matchup/          # slot-vector challenger + GLMM
  ladder/              # paper tracker + maker-vs-taker
  outs/                # outs board v1
  market_blend/        # nfelo-style blend + error-weighted
  reports/             # dated findings only
```

Boundaries (kept from prior approval): no copied prod modules (import
canonical), no live writes (workspace artifacts only), no prod imports
from research, no creds, no committed bulk data, promotion = extraction.

Subfolders inside existing dirs stay as-is (market_research/ is probe
territory; one-in-one-out rule: no new script without retiring one).

## 3. Backlog fluff fix (keep depth, add navigation)

- Monthly archive: move closed bullets to `docs/reference/archive/`
  dated files; backlog keeps current month + Session Snapshot.
- Add a 20-line index at backlog top (leases: money / ops / research).
- Reports stay (17 files, evidence); no new report without retiring one.

## 4. Diagrams/docs verdict

Keep 00–05 (05 covers the live loop; 00–04 training-era sound; one stale
line fixed). ADD: (a) data-flow/warehouse diagram (lake → L1/L2 → board),
(b) retrain/promotion pipeline diagram (staging → regression-guard →
registry → deploy, borrowed from pitch-predictor below). Quality bar met;
these two close the black box fully.

## 5. Research synthesis (tried → learned → status)

| Tried | Learned | Status |
|---|---|---|
| Glicko RD overlay | Shrinks everything to league (-0.0166, 33x wrong) | KILLED |
| Kalshi overlay gate | 80% generic shrinkage; +0.005 direction | Shelved (display flag) |
| v2 posterior sim | Loses to ws1c (0.1465 vs 0.1424), beats raw Poisson | Archived challenger |
| v3 joint bootstrap | Overshoots (0.427 vs 0.345 truth) | Archived; mixture idea kept |
| v4 PA slots | Ties Poisson (0.1472) | Needs vs-hand + hook levers |
| Power archetype | Stable 3 seasons, 2x tails | KEPT (bucket, not model) |
| Hierarchical pooling | Dead via Glicko, but arios37 shows the RIGHT way (MCMC + conjugate) | Revisit via PyMC, not Glicko |
| Kelly fractions | ROI invariant (+8.66% all) | KILLED as lever |
| Flat vs Kelly live | Tie (+8.70 vs +8.66) | Flat stands |
| Overs research | Low-line overs bleed; veto fixed it | Policy live |
| Unpooled pairs | 2–3 PA/yr noise | KILLED, forever |
| Market making | Bankroll/inventory/adverse selection forbid | Declined; maker-vs-taker study kept |

## 6. Links re-mined (what we take)

- **nfelo market regression** → market_blend build (flat + error-weighted
  trailing model-vs-market error; our Kalshi +0.0263 independently agrees).
- **gbnet** → ordinal rung model (ladders) + survival hook model (TBF);
  torch cost flagged, sklearn fallback ready.
- **Sloan DRL** → distributional + synergy thinking only (already ours);
  full agent declined with reason.
- **pitchpredict (xLSTM/similarity)** → similarity comps for form
  ("find similar starts") as research probe; xLSTM declined (needs
  count/context we exclude pregame + tiny samples).
- **mlb-pipeline (Snowflake)** → rolling windows 10/35/75 validate ours;
  no warehouse needed at our scale (parquet + volume suffice).
- **arios37 Bayesian hierarchical** → the correct partial-pooling
  template (MCMC subsample + conjugate rest) for the PA/GLMM build.
- **stuff-plus** → engineered interactions (spin-velocity ratio,
  velo×IVB, plate distance) as October retrain CANDIDATES (measured
  by ablation, not assumed).
- **mlb_py probabilistic** → NegBin-vs-Poisson test for counts;
  temperature scaling alongside Platt; per-model dirs (we mirror).
- **pitch-predictor retrain pipeline** → THE enterprise process we lack:
  staging dirs + regression-guard promotion + model registry + run state.
  Adopt as the promotion pipeline (replaces ad-hoc image bumps with
  gated promotion — biggest ops upgrade available).
- **Karl Whelan hold %** → per-quote hold% (built) + hurdle-aware floors.

## 7. Batter-K architecture (approved shape, unchanged)

Slot-vector matchup (9-vector log5 blend, Poisson-binomial over TBF),
post-processing, no retrain. PA training mix (Savant pitch rows exist)
for the GLMM build. No pair memorization, ever. Backtest terms §locked.

## 8. Ordered builds (meshed, single list)

1. Ship research batch (family rule + flips + sims + diagram) — image.
2. Seed sweep already green; V4 levers (vs-hand + hook) OR archive.
3. Market blend (flat → error-weighted) vs ws1c.
4. Paper ladder price-aware + maker-vs-taker study.
5. Slot-vector challenger + GLMM PA model (arios37 template).
6. Outs board v1 (TBF distribution) — paper winter.
7. Promotion pipeline (staging + regression guard + registry).
8. Novig key/stages; dawn verdict; frozen cuts; bankroll review.
9. Consolidation (prune table §1) + spring checklist (one deploy).
Gates: paper ROI before money; Brier+logloss+ECE+season-slices before
board; 2027 spring before promotion; kill list honored.

## 9. Surgical-change map (where to look)

| To change… | Look at… | Never touch alongside… |
|---|---|---|
| Main-line pricing | `live_assembly.py` + `market.py` + WS1c pointer | Policy, sizing, grading |
| Ladder/rung pricing | paper tracker + ordinal model (research) | Live board |
| TBF/workload | pipeline + TBF bundle + hook table | K-rate ensemble |
| Policy/floors/vetoes | `kpi_policy.json` + `odds_board.py` gates | Calibration, sizing |
| Sizing/caps | `market.py` sizing + exposure controls | Edges, thresholds |
| Grading/surface | `send_daily_grading.py` + `dedupe_ledger_props` | Ledger schema |
| Closes/CLV | `odds_close.py` + sweeps | Open logging |
| Chains/schedules | `modal_app.py` (5 crons) | Research modules |
| Calibration | WS1c pointer + showdown harness | Live board logic |
