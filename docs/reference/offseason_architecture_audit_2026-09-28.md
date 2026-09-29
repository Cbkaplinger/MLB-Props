# Offseason architecture + model audit 2026-09-28 (PLANNING-ONLY, read-only)

Owner order: planning only. No code, retrain, schedule, deploy, or tracked-output changes.
Supersedes nothing. Complements `offseason_overhaul_plan_2026-09-28.md` (consolidated plan)
and `docs/EXECUTION_BACKLOG.md` (master queue — this file approves nothing).
Backtest terms locked: 2023–24 train, 2025 validation, 2026 locked retrospective
(never pristine), 2027 prospective. Rolling-origin folds inside development period.

Evidence: 4 parallel read-only censuses 2026-09-28 (inventory / docs+links / arch+model /
git+tests) + direct reads of backlog, canonical map, model-card, golden_metrics, plan.
Methods, commands, and gaps are recorded — indexing alone was not treated as proof.

## A. Executive brief

**Current system.** Frozen k-rate ensemble (0.00 sparse72 + 0.60 sparse72_monotone +
0.40 final58) × frozen Ridge TBF → Poisson + per-line Platt (WS1c, live since 2026-09-10)
→ devig → policy (`kpi_policy.json`: floor 0.12, cap 0.24, under-lean, DK/FD-only,
4.5-over veto, 2.5/3.5 probation, flat $50) → board → ledger (one-slip family rule) →
tip-window close capture (q5m + urgency + 60s burst, T+5 stop) → settle/grade → CLV/ROI
reporting → drift/manifest monitoring. Cloud Modal NY-tz primary (5 crons); laptop
mirror disabled-but-present fallback. Season closed 9/27 into postseason HOLD; app
STOPPED; season truth −$176.17 (−0.7% stake-weighted) after Hunter Brown repair.

**Strengths.** Leakage-safe L2 (shift(1) + same-date first-collapse), forbidden-feature
gate, as-of live assembly, idempotent atomic ledger writes, one-slip dedupe, same-book
headline CLV + xbook + consensus triple, fail-LOUD serving gates, run manifests, 530-test
suite with property+pin pairing, pipeline registry P1–P9, golden_metrics contract.

**Risks.** 2026 repeatedly consulted (thresholds, floors, caps, calibration) — judge
contamination is the load-bearing evaluation risk. Research sprawl (87
market_research probes, 240 `__main__` files) vs 40 canonical `src/Python` modules.
Committed tests importing untracked files (repeat of 9/18 CI break). Modal image deps
drift from pyproject. RG-scrape fragility. No dead-man miss-detection wording gap
(being closed by drift check #8). L1–L3 atomicity fixed 9/21 but still verify.

**Highest-value seams.** (1) Slot-vector batter-K post-processor (no retrain).
(2) Expected-TBF/hook refinement (survival hook + TTO). (3) Market blend
(error-weighted vs ws1c). (4) Calibration governance (WS1c pointer + showdown harness).
(5) Promotion pipeline (staging + regression guard + registry — biggest ops upgrade).
(6) Evaluation consolidation (one engine, pre-reg, kill rules).

**Order.** Truth reconciliation → reproducibility → evaluation lock → seam
stabilization → baselines → isolated experiments → shadow → promotion review →
migration → monitoring. Details §R.

**Blocking questions.** §S Q-01…Q-08 (champion selector, open-timestamp, 2026
consultation scope, uncertain-lineup doctrine, live schedules, retention, subs,
out-of-scope list).

## B. Coverage manifest

| Area | Method | Status | Gaps |
|---|---|---|---|
| Top-level dirs (28 entries) | Read + README skim | DONE | `.env` contents, `.venv/.git` internals unread |
| Tracked files (541) by type | `git ls-files` + Group-Object | DONE | Ignored lake (13k JSON, 1.2k parquet/CSV, 322 media, 5 binaries, 10 logs) counted, not content-read |
| Largest / most-changed / dupes | Length sort + log --name-only + basename group | DONE | Point-in-time (51 M files dirty) |
| Entry points / schedules | `if __name__` scan + modal_app decorators + workflows + ps1 | DONE | ps1 bodies not line-read; notebook cell outputs not verified |
| Production workflows P1–P9 | modal_app + RUNBOOK/INDEX/README + registry | DONE | Volume heartbeat rowcounts not re-pulled |
| Markdown (108 tracked) | Per-file date + 6-line skim; reports 30-line skim | DONE | Full text past skim via keyword hits only; dirty-tree diffs not triaged |
| Research memory | Title+lede extraction, R-001…R-016 | DONE | Follow-up linkage partial (see F) |
| Prompts/plans | md + .cursor/rules + TODO scan + commit messages | DONE | Commit diffs not read; external URL bodies not fetched |
| External URLs | Select-String `https?://` md+py | DONE | Bodies unverified; truncated identity.py Sheets prefix unclear |
| Git history | log/tags/branches/deletes/reverts/stats/blame-by-path | DONE | Revert body 642f2d6, data-v1 content beyond stat unverified |
| Model + features + calibration | Sidecars + registries + rolling code | DONE | Threshold-origin commit not re-derived; novig/kalshi internals not line-audited |
| Tests + deps | tests/ census + conftest + CI + pyproject + image | DONE | No tests executed this pass (prior suites cited: 530 green) |
| Batter-K seam (20 Qs) | log5/PB/conversion/rolling/showdown code search | DONE | Live volume measurements not re-pulled |

**Indexing scope.** Single-root, no submodules/symlinks/workspace-files. `.cursorignore`
hides data/parquet/artifacts/models/binaries/media/logs from semantic index; `.gitignore`
additionally hides Savant/Odds-Historical/Open-Command/processed + Saved-Models. Agents
see code+docs; lake + binaries are invisible to indexing by design — inventoried by
filesystem/git commands instead.

| Resource | Indexed | Tracked | Generated | Relevant | Review |
|---|---|---|---|---|---|
| `src/Python` (~40 canonical) | yes | yes | no | yes | DONE (arch census) |
| `production/` (189 tracked) | yes | yes | no | yes | DONE |
| `models/Strikeout-Model` trainers | yes | partial (Saved-Models ignored) | models ignored | yes | DONE (sidecars) |
| `data/Savant-Data`, `data/Odds-Historical`, `data/Open-Command` | no | no | yes (re-downloadable) | yes | COUNTED, content not read |
| `artifacts/` (odds_log 340, live_scores, stabilization) | no | no | yes | yes (evidence) | COUNTED, cited via reports |
| `production/ops/market_research` (87) | yes | yes | no | mixed (probe sprawl) | DONE (one-in-one-out rule kept) |
| notebooks (22 ipynb) | yes (code) | yes | outputs stale-risk | yes | ENTRY-POINTS only |
| `.env` / Modal Secret `mlb-props-keys` | no | no | no | keys only | NOT inspected (correct) |

## C. Repository map

Top-level purpose (1 line each): `.agents/` cleanup skill; `.cursor/` rules+skills;
`.github/` CI only; `analysis/` narrative notebook; `artifacts/` ignored provenance;
`data/` local-only lakes; `docs/` backlog+paper+reference+research+diagrams+archive;
`models/` frozen trainers (Strikeout k-rate + TBF ridge); `playground/` frozen demos;
`production/` live stack (ops chain, odds board/ledger, projections, cloud Modal,
notebooks, app); `scripts/` support; `src/Python/` canonical lib; `src/Notebooks/`
legacy; `tests/` 70 files / 520 test fns.

Boundaries: `src/Python` = canonical lib (import me); `production/` = wiring + chains
(import canonical, never duplicate logic); `market_research/` = probes (import canonical,
no live writes); `models/` = frozen trainers; `artifacts/data` = ignored outputs.
Known dupes kept deliberately (frozen+tested): `odds_board.py` lib vs CLI,
`training.py` ×2, `train.py` ×2, `prune_artifacts.py` ×2 — canonical homes filed in map.

## D. Pipeline census

| ID | Workflow | Trigger | Entry | Status |
|---|---|---|---|---|
| P1 | Collection (baseball + odds arms) | Morning + tip windows + manual | `refresh_statcast`, `daily_lineups`, `sharp_odds`, paid puller (manual) | LIVE |
| P2 | Transform + L1–L3 | `refresh_features` / live assembly | `pipeline/games,rolling,training` | LIVE |
| P3 | Training + calibration | Manual only | `models/*/train.py`, `prob_calibration` | FROZEN-CLOSED |
| P4 | Daily serving + selection | 08:00 + hourly 09–22 | `score_slate → odds_board → poll open → alert` | LIVE |
| P5 | Close capture | q5m 12–22 + urgency + burst | `run_close_sweep → fill_closes` | LIVE |
| P6 | Settlement + grading + monitoring | 03:00 + 05:30 | `grade_odds_ledger → drift → grading msg` | LIVE |
| P7 | Replay + policy sim | Manual | `juiced_replay_ledger`, `select_2025_champion`, `policy_simulator` | RESEARCH-ON-LIVE-CODE |
| P8 | Evaluation + promotion gates | Weekly/manual | weekly pack, quant track, showdowns | LIVE-FRAGMENTED → unify |
| P9 | Notebooks + publication | Manual | 10 production notebooks + paper | LIVE (thin-client queued) |
| OPS | Control plane | Modal NY-tz crons + laptop fallback (disabled) | `production/cloud/modal_app.py` (5 crons) | LIVE |

Per-workflow stages/inputs/outputs/state-changes: arch census §1/§6 tables (source).
Manual-only, never cron: paid puller, consensus builder, dawn_probe, backfills,
`backfill_real_bets` (unrun by order), sims v2–v4, showdowns, paper ladder, ws5b.

## E. Documentation inventory (108 tracked md)

Canonical: AGENTS.md, README.md, EXECUTION_BACKLOG.md, reference/{README,
repo_canonical_map, research_assistant_instructions, model-card, golden_metrics,
market_clv_gates, oddsapi_replay_architecture, experiment_sop, retrain_spec,
post_freeze_holdout}, models/README, production/{README,INDEX,RUNBOOK},
research/floor_freeze_log. Supporting: skills, diagrams 00–05, paper README/summaries,
most reference specs + all `*/README.md`. Historical evidence: archive ×2, most
research freezes, all 14 reports R-001…R-016, dev-notes, lineup_train_serve. Superseded:
data snapshots README, cursor_deep_dive_brief (redirect), step7/step10 freezes,
prob_calibration pointer (isotonic→WS1c cutover 9/10 — two docs still say isotonic =
stale). Contradicted: none asserted as canonical; conflicts live in §I. Parked:
dashboard IA. Unknown: none — every md classified.

Reports R-001…R-016 (chronological): quality passthroughs (×2) → model comparison pack
→ granular open calib → real-bets checklist → historical CLV APIs → freeze playbook →
juiced replay → replay inventory → 2025-lock prereg → slate shock → weekly pack →
cloud hosting → confounder audit → forward diary → ratings/hook. `reports/README.md`
references since-merged names — stale index, merge candidate.

## F. Research-memory index (abridged; full table in plan §5)

| ID | Finding | Later status |
|---|---|---|
| Glicko RD overlay | Shrinks all to league (−0.0166, 33× wrong) | KILLED |
| Kalshi overlay gate | 80% generic shrinkage; +0.005 direction | SHELVED (display flag) |
| v2 posterior sim | Loses to ws1c 0.1465 vs 0.1424, beats raw Poisson | ARCHIVED challenger |
| v3 joint bootstrap | Overshoots 0.427 vs 0.345 truth | ARCHIVED; mixture idea kept |
| v4 PA slots | Ties Poisson 0.1472 | NEEDS vs-hand + hook |
| Power archetype | Stable 3 seasons, 2× tails | KEPT (bucket, not model) |
| Hierarchical pooling | Dead via Glicko; arios37 shows right way (MCMC+conjugate) | REVISIT via PyMC |
| Kelly fractions | ROI invariant +8.66% all | KILLED as lever; flat $50 stands |
| Overs research | Low-line overs bled; 4.5 veto + probation fixed; Sep overs −$38 vs Aug −$1,728 | POLICY LIVE |
| Unpooled pairs | 2–3 PA/yr noise | KILLED forever |
| Market making | Bankroll/inventory/adverse-selection forbid | DECLINED; maker-vs-taker study kept |
| Order weighting | +1.5% relative, noise | DO NOT PROMOTE |
| 200-PA prior | Empirical-Bayes convention; K% stabilizes ~150–200 PA | KEPT |

## G. Prompt-to-outcome ledger (abridged)

opencode_handoff #113/#123 → DONE as briefed. beat_the_books 7 WS → partial (WS1c+
Poisson shipped; stacker/overlays killed-or-shadow; fills owner-blocked). experiment_sop
→ adopted as law. retrain_spec → EXHAUSTED/CLOSED #66. champion_challenger → used for
9/11 select/judge. clv_backfill → BUY DONE. live_assembly → shipped. outs expansion →
shadow only, PARKED. dashboard IA → PARKED, not built. oddsapi replay → partial
(ledger+inventory DONE; full replay queued). agentic_stack → infra only, unknown
adoption. Rules (backlog-only, Polars-first, never-push) → observed; pushes occurred
only on explicit owner order (documented exception).

## H. External-source register (abridged)

Implemented: MLB StatsAPI (settle/rosters/schedule), RotoGrinders (lineups — most
fragile dep), SharpAPI (live DK/FD), OddsAPI (historical pull only; chains cannot
spend), Kalshi keyless elections-host (panels + history), ntfy (alerts), Open-Command
HF (440MB 2024–26), Fangraphs GUTS constants (vendored), Marcel (baseline).
Scaffold-only: Novig (Stage 0/1, orders blocked till Stage 3, key pending). Cited-only:
SmartStake slice, OddsPapi smoke, prop-line backfill, xFIP/Marcel papers, SharpAPI
historical-CLV docs. Adopt-from-links (plan §6): nfelo blend, gbnet ordinal+survival,
arios37 GLMM template, stuff+ interactions, mlb_py NegBin/temperature, pitch-predictor
promotion pipeline, Whelan hold%. Declined: Sloan DRL agent, xLSTM, market making,
pair memorization, overhaul-of-frozen-layers. Unverified: URL bodies not fetched;
identity.py Sheets prefix truncated.

## I. Contradiction register (abridged; full quotes in census)

1. Train/val/test years: 2023–24 fit vs legacy overlapping runs (train→2025-04-15,
val+test shared 2025-07-06) — SUPERSEDED, current rule wins.
2. Pristine/holdout/locked: 2025 = selection holdout AND contaminated benchmark;
2026 judge = disclosed-peek, never clean; post-freeze n=0 at lock. Genuine tension,
resolved by labeling not by purity.
3. ROI/PnL/CLV/beat-close: same label across live ledger vs juiced replay vs fair
harness; fraction×100 vs percent; tiny-n veto beat 0.432 (n=37). Different universes —
must cite universe + n.
4. Open/close ts: live ~08:00 board (T−5h…T−11h) ≠ friend −12h ≠ paid −30h; vendor vs
reconstructed `snapshot_ts` coexist. Definitions differ by source.
5. Push/void: ledger n excludes pushes/voids; ladder sim scores pushes as losses.
Different denominators.
6. Devig: pair-devig (executable) vs median-consensus (measurement). Different "fair"s.
7. Calibration: isotonic pointer (stale, 2 docs) vs live WS1c per-line Platt (9/10).
Cutover documented; stale docs need fixing, not code.
8. Champion: MAE-lane / Aug-21 search numbers explicitly not production; live = ensemble
config + 2025-lock select/judge. Old champions retired as search evidence.
9. Thresholds: global 0.12 vs line floors vs side overlays vs 0.24 cap — layered, not
single number.
10. Bankroll/sizing: 1/8→1/16 cutover; $1,590 math-anchor vs $5k operating bankroll;
auto-brake REFUSED, human kill line only. `playground/README` still says 1/8 — stale.
11. Retrain: no cadence — event-gated only (new source or 2026-full review). Daily
refresh = features/score, never refit.
12. Backtest-term violators in code: `age_walkforward` F3/F4/F5 train on spent
2025/26H1 (by own comments); `combined60_final`, `age_member_brier`,
`multi_lift_pre_freeze`, CLEANUP_LOG 358–361 use 2025 as train/test. Record, do not
rewrite yet.

## J. Model card (grounded)

Target `k_rate=K/PA`, one row per qualifying starter/game (PA≥9, openers excluded).
Train 2023–24 (6,557/1,404/1,413 chrono 70/15/15, boundary dates wholly in later
partition), 2025 excluded before any split/preprocessing fit. Live selector
`live_krate_ensemble.json` (`manual_best_aug21_deduped_transfer`): 0.00/0.60/0.40 over
sparse72 / sparse72_monotone / final58 (72/72/58 feats; sha-pinned; sum-to-1 enforced).
TBF: Ridge 24 feats, α=123.28, clip 33, val MAE 2.568 / test 2.489.
Calibration: WS1c per-line Platt (8 lines 2.5–9.5, n_fit 8,775 each + global 70,200;
fit through 2026-09-03) + Poisson default (`COUNT_LAYER_FAMILY_DEFAULT="poisson"`,
one-line revert to binomial). Policy: §A. Repro: LGBM early-stop 200 on validation;
Ridge α by chrono MAE; `features.py` forbidden-gate + frozen registries.
Uncertainty: threshold-origin commit not re-derived; legacy 0803 stem default is
fallback-only (ensemble path rules when config present); `models/README` still names
0803 — doc lag.

## K. Feature-lineage map (abridged)

All L2 rolling prior-only (shift(1), same-date first-collapse); doubleheaders share
first-row value. K/PA/Outs/k_rate blocked from X by 3 gates. Live as-of
`game_date<slate_date`; park fallback prior-season; rest/debut flags have documented
train/serve skew (live debuts zeroed vs train nulls); lineup train=realized 9-man vs
live=RG announced 9-man (filed skew, not leakage). L3 null season-open rows by design
(no backfill). Calibrator fit on universe panel thru 9/03 (chrono prior-date fits);
reusing same panel for floor selection = HIGH risk, governed by 2025-select/2026-judge
discipline. Threshold-curve helpers exploratory; live floors frozen KING profile.
Full family table: arch census §3.

## L. Evaluation-integrity report

Metrics with locations: MAE/RMSE/R² (`training.py`, `count_layer`), Brier/logloss/
accuracy per line, ECE/bias/AUC (`prob_calibration`), CLV pp (`market.clv_pp`,
ledger `apply_close` + xbook), beat-close strict >0, ROI=sum(pnl)/sum(stake),
Sharpe/Sortino/MaxDD/Calmar (per-day √162; phone Sharpe window-labeled never
annualized), bootstrap CIs (weekly pack + grading). Separations: prediction (MAE on
xK) vs probability (Brier/logloss/ECE per line, same-subset) vs decision (ROI/WR on
deduped staked) vs pricing (CLV/beat, same-book headline) vs execution (fills = 0;
paper upper-bound labeled). Non-reproducible without canonical command: any number
cited without universe + n + source JSON (golden_metrics rule). Contamination: 2026
influenced features/thresholds/architecture — treat all 2026-graded claims as
retrospective, never pristine.

## M. Surgical-change map

| Candidate | Seam (attach) | Must not touch | Test / backtest / shadow | Scope |
|---|---|---|---|---|
| Slot-vector batter-K | New post-proc after `attach_count_predictions`, before board; reads as-of slot rates + pitcher p + league; Poisson-binomial agg | Ensemble, TBF, WS1c, policy, ledger schema | Unit: disable→bit-identical current; showdown vs actuals same-subset; shadow paper | M |
| Expected TBF / hook | `tbf.py` feats + hook table + TTO counters beside Ridge | K-rate ensemble | Brier/MAE slices; survival calibration | M |
| Distribution family | `count_layer.py` family flag | Calibration pointer, policy | Pre-reg Brier/logloss/ECE + season slices | S |
| Calibration | WS1c pointer + `fit/prob_calibration` + showdown harness | Board logic, sizing | Same-subset skill; kill if < ws1c | S |
| Market blending | Blend step in `score_frame`/board | Trainer, ledger | Flat vs error-weighted vs ws1c on showdown | S–M |
| Feature additions | `registries.py` + allow-list + L2 cols | Frozen 72/58 sets | Ablation, both-fold bar | M |
| Partial pooling / GLMM | `research/offseason_2026/pa_matchup` (import canonical; no live writes) | Prod modules | PA Brier vs slot baseline; MCMC subsample | M–L |
| Retraining workflow | Manual trainers + staging dirs | Live chains | Regression guard + registry | M |
| Model registry | Per-model dirs + pins + promotion gates (pitch-predictor template) | Selection logic | Repro from pin | M |
| Regression guards | CI + pin tests + bootstrap CIs | Policy | Red-team a known-bad challenger | S |
| Freshness/schema validation | `serving_gates` + manifests + drift checks | Selection | Fault-injection (stale/missing/garbage never-raise) | S |
| Evaluation consolidation | One engine + pre-reg + kill rules (EVAL-1) | Live grading | Duplicate-metric flag, never inline-fork | M |
| Docs/research memory | Backlog monthly archive + index + reports retire-rule | Queue semantics | Link-check + cite-check | S |

Change-impact for batter-K (§12 answers): distributions at `count_layer.
p_strikeouts_ge` via `live_assembly.attach_count_predictions`; TBF at `tbf.py` +
TBF-Model bundle; lineup enters training L3 `opposing_lineup_features`, live
`_live_lineup_aggregates`; pre-official = RG projected/confirmed + `lineup_status`
logged, not gated; uncertain slots = as-of means with season-open nulls (no backfill)
— replacement priors vs delay-publication is Q-04; blend = pitcher k-rate vs slot
batter rate via log5 (research `pa_sim.log5` only; no prod log5); handedness split
exists in data (`_vR/_vL`) but v4 ran hand-neutral; pitch→PA canonical
(`statcast.plate_appearances` + event flags); shrinkage = 200-PA prior + shrunk cols,
rookies → league; order enters only via slot sim (production flat mean); TBF emergent
in sim vs input in prod; PB aggregation only in `ws5b_poisson_binomial` (DP); downstream
contract preserved = same board/ledger schema + disable-flag bit-identity; promotion =
pre-reg Brier/logloss/ECE + season slices + paper ROI before money.

## N. Diagram assessment

00-index, 01-architecture (L1→L3→train→artifact + live/CLV), 02-leakage, 03-modeling/
evaluation, 04-roadmap, 05-live-prediction-flow. Verdict: keep 00–05 (05 covers the
live loop; 00–04 training-era sound; one stale ⅛-Kelly line fixed, ensemble node
spelled out). Gaps: (a) data-flow/warehouse (lake→L1/L2→board) MISSING; (b) retrain/
promotion pipeline (staging→guard→registry→deploy) MISSING. Recommend exactly those
two, each with scope/responsibilities/directional flow/tech/canonical paths/
last-verified date. Quality bar met otherwise.

## O. Decision-record proposals

Accepted (record): no sparse pair memorization; slot-vector + Poisson-binomial shape;
frozen lower layers; backtest semantics; Poisson+WS1c current family; pair-devig for
execution + consensus for measurement; flat $50 + 1/16 anchor; DK/FD-only champion;
one-slip family dedupe; fail-LOUD (no auto-blocks); 2025-lock select / 2026 disclosed
judge. Unresolved: uncertain-lineup doctrine; dawn opens; outs scope; Novig stages;
registry canonicalization; notebook deletion; plugin framework; metric-drift vs
docs-from-artifacts order. Each future ADR needs status/date/context/decision/
alternatives/evidence/consequences/risks/revisit-trigger/code+research IDs.

## P. Dependency / deprecation watchlist

HEALTHY: numpy/pandas/polars/pyarrow/dotenv. PINNED-INTENTIONALLY: none (no lockfile —
gap). UPGRADE: add lockfile in consolidation; pin Modal SDK + image deps to pyproject.
WATCH: Polars 2.0 churn (warnings in CI), SharpAPI terms/quota (~1–3% used; monitor),
OddsAPI lapse (research-only already; let lapse), RG scrape (most fragile; dawn
verdict decides; MLB schedule API backstop), Modal drift, Kalshi marquee-only,
Novig key pending. UNUSED: none asserted (all probes referenced or filed). FRAGILE:
RG HTML parse, pybaseball upstream, image-vs-pyproject drift (pandas/pyarrow/
statsmodels missing in image). Per-file action vs monitor flags in plan §1 tables.

## Q. Experiment portfolio (1–5 each: value/evidence/cost/data/leak/ops/revers/isol/reuse/dep)

READY TO SPECIFY: market blend error-weighted vs ws1c; slot-vector challenger (post-proc);
NegBin-vs-Poisson; temperature-vs-Platt race; stuff+ interaction ablations. NEEDS DATA/
TRUTH: GLMM PA model (data exists 674k rows; needs lineage extension); per-archetype
calibration; dawn opens (needs 5-morning probe); outs board v1. NEEDS OWNER: Novig
stages; frozen cuts; bankroll/unit review; uncertain-lineup doctrine. LONGER-TERM:
ordinal rung model; survival hook; similarity comps; maker-vs-taker. REJECTED:
pair memorization, Glicko overlay, Kelly fractions, overhaul-of-frozen-layers,
full DRL agent, xLSTM, market making, live-context modeling (parked with live betting).

## R. Sequenced roadmap

1. Truth reconciliation (conflict register → doc fixes only; stale isotonic/0803/⅛-Kelly
lines; reports index). Gate: cite-check green.
2. Reproducibility (pins + manifests + atomic writes verified; committed-tests-only rule
enforced). Gate: full suite green from clean checkout (lake-skips allowed).
3. Evaluation lock (terms enforced; one engine; pre-reg template; kill rules).
Gate: 2026 labeled retrospective everywhere; no new 2026-tuned thresholds.
4. Seam stabilization (serving gates + manifests + drift #8 + flips-only + schema
validation). Gate: fault-injection never-raise + real-content manifests.
5. Baselines (mean/rolling/pitcher-only/rate×opp/Poisson/NegBin/book/devig/blend/old
champion). Gate: every future claim beats the right baseline same-subset.
6. Isolated experiments (blend, distribution, calibration, features, GLMM in
`research/offseason_2026/`, no prod imports from research). Gate: pre-reg + Brier/
logloss/ECE + slices.
7. Shadow comparison (paper ladder + outs shadow + blend shadow; no live writes).
Gate: paper ROI + CLV before money.
8. Promotion review (staging + regression guard + registry; pitch-predictor template).
Gate: human approval + rollback target named.
9. Production migration (single deploy + heartbeat proof; postseason HOLD respected).
Gate: board/ledger/manifest proof on new image.
10. Monitoring + retrospective (drift, Sharpe-decay recorder, monthly rule-versioned
tables, spring checklist). Gate: one-deploy re-activation path.

Parking lot (unique reasoning preserved, not scheduled): live-context modeling,
DORA, SLO targets (record-only ok), uv restructure (declined), external registry,
notebook deletion (waits on eval engine), plugin framework (waits on outs).

## S. Owner-question register

| ID | Question | Why it matters | Best answer today | Recommendation |
|---|---|---|---|---|
| Q-01 | Champion selected by config, filename, or convention? | Promotion safety | Config `live_krate_ensemble.json` + sha pins; 0803 fallback exists | Confirm config-is-truth; fix README lag |
| Q-02 | Exact "open" timestamp for CLV? | CLV comparability | Live = ~08:00 board bet_price; friend −12h dead; paid −30h metered | Lock live-open = first-logged board price; label others |
| Q-03 | Was 2026 consulted for any feature/threshold/architecture? | Judge validity | Yes (floors, caps, WS1c, showdowns) — disclosed-peek | Keep 2026 retrospective; freeze new 2026 tuning |
| Q-04 | Uncertain lineups: projected, replacement prior, or delay? | K-seam design | Projected logged, not gated; nulls no-backfill | Choose before PA build |
| Q-05 | Which live schedules are deployed? | Ops truth | Modal 5 NY crons (08:00, 09–22, q5m 12–22, 03:00, 05:30); app STOPPED | Confirm spring re-activation = one deploy |
| Q-06 | Which reports legally/operationally required to retain? | Archive policy | Unknown — 330 odds_log 90% cited; retention undecided | Name retention set before prune |
| Q-07 | Which data subs remain available? | Planning | SharpAPI free + Kalshi keyless yes; OddsAPI lapsing; Novig pending; RG fragile | Confirm Novig key + RG backstop |
| Q-08 | Which experiments explicitly out of scope first? | Sequencing | Plan §8 ordered; outs/batter order debated | Lock first-3 builds |

Blocking: Q-03, Q-04. High-leverage: Q-02, Q-07. Confirmation: Q-01, Q-05.
Later: Q-06, Q-08 details.

## T. Recommended canonical index (landing page design)

One page: what it is → what runs daily (5 crons + fallback) → data in → transforms →
train (frozen) → inference → calibrate → devig → select/size → publish → settle →
metrics → replay → where to look (canonical files) → manual workflows → replay a day →
isolate a change → restore prior model. Route: backlog (queue) → this audit (map) →
canonical map (surfaces) → golden_metrics (numbers) → model-card (model) → RUNBOOK/
INDEX (commands) → plan (future). Monthly-archive the backlog; add 20-line index;
reports retire-rule (no new report without retiring one).

## Honesty ledger (updated Phase 2)

Phase 1 gaps closed: ignored lake bounded-inspected (Savant schemas + 2015–2026 pitch-row
counts + L1–L3 counts + null/PK scans, read-only); ps1 bodies partially read (chain roles
verified via modal_app + RUNBOOK); probe purposes verified by line reads; notebook outputs
statically inspected (not executed); volume rowcounts still not re-pulled; URL bodies not
fetched; commit diffs not read; dirty-tree diffs not triaged. Confidence: HIGH on
pipeline/champion/seams/lineage (code-cited); MEDIUM on historical follow-through;
LOW on any number without universe + n + source JSON.

---

# Phase 2 — Content-level archaeology + experimental contract (2026-09-28, read-only)

Four parallel line-by-line reads (ingestion+features / training+calibration /
serving+money / research+notebooks+tests+enterprise). No code, train, backtest, test-run,
install, or git-state change. Line cites are `file:line`. Confidence per claim.

## U. Key-file content dossiers (32 files)

| Path | Role | Core logic (exact) | Time semantics | Tests | History | Future role |
|---|---|---|---|---|---|---|
| `src/Python/statcast.py:501-519` | Canonical pitch→PA primitive | Filter `events not-null & ∉ NON_PA_EVENTS(15)` → sort `(game_pk,at_bat_number,pitch_number)` → group-last → `is_k ∈ {strikeout,strikeout_double_play}`; `is_pa` same filter; zone 10 = neither In nor Out; rates `num/den else None` | Event `game_date`; publish Savant lag (`yesterday_et`); no ingest ts stored | `test_statcast.py` | 4 commits | FROZEN primitive |
| `src/Python/daily_lineups.py:1413-1685` | RG+MLB slate ingestion | `lineup_status = projected iff "unconfirmed" in classes`; attach by `game_number` else nearest `rg_game_time` with `used_game_pks` dedupe; resolve exact→alias→fuzzy (0.50/0.35/0.15, gates 0.98/0.88/0.55/0.84/0.70, margin 0.08); drop bad games + warn | Event ET date; publish `fetched_at` UTC; ±2d inference for overnight lag | `test_daily_lineups.py` | 6 commits | Reusable adapter boundary |
| `src/Python/pipeline/games.py:50-130` | L1 per-game tables | `k_rate=K/max(PA,1)` (PA=0→0); `prior_league_k_rate=Σis_k/height`; park needs prior history | Postgame-faithful; "not leakage-sensitive yet" | `test_pipeline`, features/ballpark/bullpen suites | 8 commits | FROZEN builder |
| `src/Python/pipeline/rolling.py:41-201` | L2 trim + anomaly weights | Keep statics + `(_P\d+\|_std…)`; anomaly high→0.0/med→0.5/low→1.0, labels restored via 2-key join | Inherits pregame guarantees | `test_rolling_anomaly_policy` | 7 commits | FROZEN |
| `src/Python/pitcher_rolling.py:88-1065` | Pitcher pregame engine | `_prior_rate=(cumsum-cur)/…`; `_rolling_rate=shift(1).rolling_sum.over(pitcher)`; `_rolling_mean` same; same-date `first().over(pitcher,game_date)`; FIP/SIERA/RV formulas; rest `shift(1).over(pitcher,season)`; shrunk K opt-in `(priorK+m·shrink)/(priorPA+m)` | Strictly prior | `test_pitcher_rolling.py` | 8 commits | FROZEN core + opt-in research |
| `src/Python/batter_rolling.py:78-325` | Batter pregame engine | Same shift/collapse pattern; `k_rate_std(_vL/_vR)` + 21 extras; shrunk `(priorK+200·lg_k)/(priorPA+200)` with expanding daily `lg_k`; lineup weight prior-date avg PA/slot | Strictly prior | `test_batter_rolling.py` | 6 commits | FROZEN |
| `src/Python/pitcher_features.py:135-478` | Pitch→start spine | VAA physics; `CSW=CS+Whiffs`; starter = inning-1 opener; `PA≥9` filter; HR/FB prior; FIP `Outs≥9` gate | Postgame per-start | `test_pitcher_features.py` | 8 commits | FROZEN spine |
| `src/Python/batter_features.py:50-247` | Pitch→batter-game | 16 hand cols `_vL/_vR`; `lineup_slot=rank(first_ab)`; `is_initial_lineup=slot≤9`; all rates `den>0 else None` | Postgame per-batter | `test_batter_features.py` | 5 commits | FROZEN |
| `src/Python/ballpark.py:106-165` | Park dimension | `EB=(K+500·lg)/(PA+500)`; `factor=EB/lg`; `source_season<season`; missing→1.0; TB override closed | Prior-season only | `test_ballpark.py` | 3 commits | FROZEN dimension |
| `src/Python/bullpen.py:74-342` | Bullpen lookbacks | Non-1st-inning-starter = pen; windows (1,2,3)d `[asof-W,asof)`, `bp_date<game_date`; missing→0 | Prior-date | `test_bullpen.py`, `test_tbf.py` | 1 commit | FROZEN flat source |
| `src/Python/pipeline/training.py:102-545` | L3 joins | Realized 9-man means + order-weighted + order-sd; `_k_vs_hand=R→vR/L→vL`; season-open nulls by design; `opp_lineup_size≠9` raises; kadj gates ≥5 starts + ≥300 pitches; age null-tolerant | Join-only, preserves L2 | `test_safety_invariants`, `test_kadj_join` | 8 commits | FROZEN join contract |
| `src/Python/features.py:12-257` | Safety gates | `TARGET=k_rate`; `FORBIDDEN={PA,K,Outs,k_rate,actual_*}`; allow-list + experimental regex; redundancy exclusions | Pregame gate | `test_feature_safety.py` | 8 commits | FROZEN gate |
| `src/Python/registries.py:27-624` | Feature-set names | `production`=step10_180+4-col discipline lift; Step-9c P1 swap; true IDs `production_sparse72/mono/final58_consensus` (no bare 72/58) | Frozen alias | `test_registries.py` | 4 commits | FROZEN alias |
| `src/Python/config.py:9-61` | Paths + seasons | `TRAIN=(2023,2024)`, `PIPELINE=(23,24,25)`, `HOLDOUT=2025`, `PROJECTION=2026`; `MIN_STARTER_BATTERS_FACED=9`; `Data` vs `data` casing risk | Calendar | indirect | 8 commits | FROZEN |
| `models/Strikeout-Model/train.py:23-266` | k-rate regression | 70/15/15 chrono no-date-split; `predict→clip(0,1)`; mono constraints ±1 by prefix; PA never feature (weight only); lightgbm-only persists + sidecar (features/eval/sha/seasons) | Train-era only | `test_train.py` | 8-deep | FROZEN |
| `models/TBF-Model/train.py:45-254` | TBF Ridge | Grid `logspace(-2,3,12)` chrono-val MAE argmin → α=123.28; `upper=train PA q0.999=33.0`; joblib `{model,features,alpha,upper}` iff `--persist` | Train-era only | `test_tbf.py` | 2 commits | FROZEN spine |
| `src/Python/tbf.py:18-111` | TBF registry | 24-feat `workload_context_bullpen`; `TBF_TARGET=PA`; label-not-in-features guard | Pregame | `test_tbf.py` | 2 commits | FROZEN |
| `src/Python/prob_calibration.py:67-471` | Post-hoc calibration | `y=1(K≥floor(line)+1)`; Platt `σ(a·logit(p)+b)`; isotonic clip-interp; `MIN_LINE_N=200/MIN_GLOBAL_N=400`; fallback stem→nearest→global→identity; WS1c 8 lines `n=8775` + global 70200, fit thru 2026-09-03 | Prior-date fits | `test_prob_calibration` | 1 commit | WS1c LIVE; isotonic revert backup |
| `src/Python/count_layer.py:34-233` | Count layer | `E[K]=clip(k,0,1)·TBF`; `trials=max(rint(TBF),1)`; Poisson `sf(t-1,μ)` / binomial / beta-binom; live Poisson (fn default binomial — pinned contradiction) | Decision-time | `test_count_layer`, pin test | 3 commits | Poisson LIVE |
| `src/Python/live_assembly.py:91-789` | Frozen inference | Ensemble Σw·p clip (`Σw=1±1e-6`) else single-stem fallback (stale 0803); TBF clip 33; count + WS1c + fair-American + OOS; as-of `game_date<slate`; park fallback yr-1; debuts zeroed | As-of pregame | `test_live_assembly`, pin tests | 6 commits | FROZEN live stack |
| `production/cloud/modal_app.py:20-268` | 5 NY crons | 08:00 full chain / 09–22 hourly+flips / q5m sweep+burst / 03:00 settle / 05:30 drift; `_run_steps` never-raises; `_beat` heartbeat; `_link_state` volume; image lacks pandas/pyarrow/dotenv/bs4, adds untracked requests | NY wall-clock | `test_modal_schedules` | ~20 commits | LIVE control plane |
| `src/Python/market.py:22-401` | Pure math | `devig` multiplicative; `hold=1-1/total`; `edge=p_model-p_mkt`; Kelly 1/16; unit-anchor; `clv=p_close-p_bet`; `bet_pnl`; `threshold_curve`; seeded bootstrap CI | Timeless | `test_market`, properties | 4 commits | FROZEN math |
| `src/Python/odds_board.py:237-1396` | Board + policy | Prefer `_cal`→raw→count fallback; 3-tuple offset clip ±0.02; floors/lean/probation/cap/robust/veto/postseason/OOS; best-book; game-cap; loud stale-HOLD; slate-final | Per-quote decision | `test_odds_board_lines`, pin | 8+ commits | FROZEN execution truth |
| `src/Python/odds_open.py:30-192` | Open scorer | 2-tuple offset, no clip/lean/probation/cap/robust — diverges from board; masked by `--from-recommendations` | Per-quote | `test_sharp_quotes`, one-slip | stable | DEPRECATE except via board lock |
| `src/Python/odds_ledger.py:39-1170` | Paper ledger | Keys `signal/date\|norm\|line\|side`, family `/date\|norm\|side`, ticket deterministic; collapse→link→append/replace; close/xbook/settle/void/dedupe-family-earliest; ET canonical; atomic writes | Append-only paper | ledger/one-slip/properties/gc suites | 12 commits | FROZEN schema |
| `src/Python/odds_close.py:28-364` | Close primitives | Same-book line→event→name else cross; due `[-5,+15]`; expire past T+5; `fill_closes` + xbook | Tip-relative | `test_odds_close` | 4 commits | FROZEN |
| `production/odds/close_watcher.py` + `run_close_sweep.py` | Daemon vs cron | Watcher sleep-until-window + live-fallback + late-open; sweep ET window + urgency(45/5) + burst 60s×8 + sidecar | Tip windows | `test_odds_close` | mixed | Sweep PRIMARY; daemon fallback |
| `production/odds/grade_odds_ledger.py:105-702` | Settle + clocks | Never settle K=0 skeleton; void Final+!appeared + 24h-unstarted; paid/Kalshi clocks canonical-sign recomputed; gate-next-N; curve; status+bootstrap | Postgame | settle/postponed/clocks suites | mixed | LIVE |
| `production/projections/log_projections.py:38-219` + `grade_projections.py:46-259` | Log + grade | Replace-slate (not append); keep raw+cal+fair+shas+lineup_status worst-wins; grade joins L1 on `(date,pitcher)` → residuals | Log pregame; grade postgame | assembly/count/support suites | sparse | LIVE |
| `production/ops/send_morning_alert.py:37-410` | Pager | Fail-open unknown; flips-first header; slip-pick 0.12–0.18; serving banners; exit 1 if nothing sent | ET-today | flips/retry/slip suites | 8+ commits | LIVE |
| `production/ops/frozen_edge_watch.py:51-312` | Harvest | `prev≠BET & cur==BET` flips (first-seen incl.); started-filter; history JSONL; stake-sync upgrades-only | Intraday | `test_frozen_edge_watch` | 5+ commits | LIVE |
| `production/ops/send_daily_grading.py:51-276` | Report card | `stake>0 → dedupe`; windows d/w7/d30/ytd; Sharpe window-only never-annualized; 3-source CLV scales differ | Post-settle | grading/sharpe suites | 4 commits | LIVE |
| `production/ops/check_nightly_drift.py:7-459` | Verdict | Exits 0/1/2/3; 8 checks (settle/model/side/veto/tail/freshness/ship/heartbeat); L3-zero = GREEN not-rebuilt | Nightly | `test_nightly_drift` | 4 commits | LIVE |
| `src/Python/serving_gates.py:31-89` + `run_manifest.py:1-304` | Warnings + provenance | Never-raises gates; run statuses + `notification_key` + sha12 pins; safe-emit | Per-run | gates/manifest suites | 4 commits | LIVE |
| `src/Python/sharp_odds.py:38-312` | Odds fetch | 6s throttle; 429 backoff; paginate ≤20; pair complete over+under; shared-fetch persist; stale-refuse unless explicit | `fetched_at` UTC per fetch | `test_sharp_quotes` | 3 commits | LIVE |

Reusable research (borrow math, never promote without gates): `pa_sim.log5+sim_game`
(TBF emergent), `ws5b.pb_sf` DP, `nb_tbf_mixture.fit_r`, `count_family_race` kill rule,
`calibrate_showdown` contestant harness, `paper_ladder` rung tracker + breakevens +
Poisson-λ inversion, `monte_carlo_starts` vectorized alive/ks loop, `slate_shock_join`
environment join, `build_consensus_cache` devig-median, `select_2025_champion`
LCB+White+gates (reuse verbatim), `band_grid_v2.PeekRefused` blindness,
`decision_grade_harness.run_year` (fair=upper-bound only), `policy_simulator` sweep
parsers, `pull_oddsapi_historical` closes-first + credit caps, `kalshi_k_reader`
panels, `novig` Stage-1 boundary, `dawn_probe` GO criteria, backfill match-keys.

## V. Data and feature lineage

**Training-row contract.** One row = one qualifying postgame starter-game
(`PA≥9`, openers excluded — selection bias, documented). Date = `game_date` (ET
calendar). Target `k_rate=K/PA`. Permitted = strictly prior-date L2 rolling
(`shift(1)` + same-date `first()` collapse verified in pitcher/batter/rest/bullpen/
park/kadj), prior-season park, age/DOB, trailing command, kadj with history gates.
Forbidden = same-game `K/PA/Outs/k_rate/actual_*` (3 gates: `features.validate`,
`training.assert_pa_not_in_features`, `tbf.assert_tbf_label_not_in_features`).
Population filters: seasons ∈ (2023,2024), `dropna(target,date)`, 70/15/15 chrono
no-date-split (train ≤2024-06-08 / val 06-09–08-05 / test from 08-06; n=6557/1404/
1413). Postseason/spring/canceled/suspended/data-poor: postseason never joined;
spring not in pipeline seasons; PPD/scratch handled in odds layer, not L1–L3.
Missing: denom-gated nulls; debuts null→live-zeroed (filed skew); season-open
lineup nulls by design (no backfill); bullpen missing→0; park missing→1.0.
Transforms fitted inside folds required (rolling is precomputed leakage-safe;
kadj/league priors expanding prior-only; calibrators prior-date only).

**Feature manifest (abridged).** Pitcher ability: `k_rate_P5/10/20/std`,
`bb/csw/swstr/whiff/chase/zone_*`, physics `ff_velo/sl_vaa/cu_vaa…_P1/3/5/10`,
usage `_vR/_vL`, mechanics `extension/rel_*`, `FIP/xFIP/siera/rv_per_100`,
workload `PA/Outs/Pitches_P*`, `days_rest(_capped)/long_gap/severity/debut`,
bullpen `L1/2/3d`, `opp_lineup_k/vs_hand/whiff/swstr/chase/zswing/swing/
zcontact/bb(_P10/20)`, `park_k_factor`, `age/age2/interactions`, `cmd_roll30`,
`kadj/missing`. No pitcher K-vs-hand splits (only usage). Batter L1→L2 feeds lineup
means only; no batter-side model trained. Grain table + formulas: Phase-2 dossier
§5–§8 (source). PA-use column: pitcher/batter trailing rates + hand splits +
zone/chase + rest/workload + park + slot + lineup-status are adoptable; pitch-mix
interactions, TTO, hook are challengers; market/implied features excluded from PA
model (evaluation-side only).

**Artifact manifest.** Ensemble `live_krate_ensemble.json` (0.00/0.60/0.40,
`manual_best_aug21_deduped_transfer`, CSV sources); stems 72/72mono/58 sidecars
(train/val/test, sha, seasons, monotone, windows); TBF joblib (α=123.28,
clip 33.0, val MAE 2.568/test 2.489, grid best-of-12, sha); WS1c pointer→joblib
(8 lines n=8775 + global 70200, a/b per line, fit thru 2026-09-03, supersedes
isotonic-20260821 5-line/2024-fit). Repro: seasons+cutoffs+splits deterministic;
stamp-named files need sidecar sha; champion pick is manual-ROI (no command repro);
TBF needs `--tune-alpha --persist`; WS1c final refit needs universe panel.

**Train-vs-serve comparison.** Shared: rolling shift/collapse code paths verified
identical in construction; forbidden gates both sides; park fallback yr-1 both.
Diverge (documented skews, not leaks): train lineup = realized 9-man vs live = RG
announced (projected/confirmed logged, never gated); train rest nulls vs live
debuts zeroed; live recomputes bullpen as-of + rest vs slate; live drops labels;
live stale-guard fail-open + heal-first; ensemble report drops per-model sha live.
Parity test required: disable→bit-identical (not retrain).

**Skew points.** (1) Realized-vs-announced lineups. (2) Debut/rest null-vs-zero.
(3) L3-zero-recent = GREEN not-rebuilt (live stops at L2 `--skip-training`).
(4) `Data` vs `data` casing on Linux. (5) Stamp-named artifacts need sidecar.
(6) Ensemble live omits per-model sha. (7) TBF clip from train quantile.
(8) `PA=0 → k_rate=0` via clip must be filtered pre-split. (9) Unexplained
`batter −829 / pitcher −75` rolling→training drops (audit before retrain).
(10) Hand-split short windows absent by design.

**Bounded data verdict.** Savant pitch rows verified 2015–2026
(2026: 674,483 pitch rows YTD — confirms "674k" as pitch rows, not PA).
L1–L3 present: `pitcher_games/rolling 18,491 → training 18,416`;
`batter_games/rolling 193,046 → training 192,217`; `pitch_type_games 90,189`;
`bullpen_team 19,144 / appearances 62,519`; `park 150`. Nulls match doctrine
(`pitcher_training k_rate_std 1,293 null = season-openers`). PKs verified
`(game_pk,pitcher)` dup-0; `(game_pk,at_bat_number)` PA key verified by code +
5-row terminal sample (pitches 2–4 `events None`, 5 terminal).
Eligible PA counts: NOT yet measured — pitch rows ≠ PA; PA population after
`is_pa` filter + starter-game + PA≥9 + 9-man + prior-history gates must be counted
in dataset spec. Do not cite "couple hundred thousand" until measured.

## W. PA architecture feasibility

**Pitch→PA truth: FEASIBLE, canonical converter exists.**
Key `(game_pk,at_bat_number)`; terminal = last by `pitch_number` after
`events-not-null & ∉ NON_PA_EVENTS`; `events` terminal-only confirmed in lake
sample; `STRIKEOUT_EVENTS={strikeout,strikeout_double_play}`. Substitutions:
pitcher/batter IDs stable within PA by construction (starter keys + batter table);
mid-PA changes not observed — treat as data-quality assert. Auto-K/pitch-clock:
inherit `events` (no special-case in code — verify in spec). Interference/
sacrifices/intent-walks: `NON_PA` deny-list (15 baserunning/misc) vs batting
outcomes allow — new Savant strings bypass as PA (fragility: prefer allow-list in
spec). Postseason/spring/suspended/DH: `game_type` + schedule status + `game_number/
double_header` + `used_game_pks` dedupe. Stable sort `(game_pk,at_bat_number,
pitch_number)`; historical corrections possible (no version pin — spec needs
`source_sha + pull_date`).

**PA-row contract (proposed).** PK `(game_pk,at_bat_number)` + `batter/pitcher`
observed (not joined). Target `is_k = events ∈ STRIKEOUT_EVENTS`. Eligible =
`is_pa` true + starter-game + PA≥9 game + 9-man lineup + pitcher/batter IDs
resolved + prior-history available (or explicit rookie path). Exclusions: postseason/
spring/exhibition, `NON_PA`, unresolved IDs, opener/bulk games (or separate family),
suspended-incomplete. Required raw: `game_pk/at_bat_number/pitch_number/events/
pitcher/batter/stand/p_throws/inning_topbot/game_date/home/away/zone/description/
type`. Optional: velo/spin/IVB/HB/VAA/location/xwoba/delta_run_exp/hc_x. Availability
ts = first-pitch time of that PA (features strictly `< PA start`). Assertions:
one terminal row per PA; no dup terminals; IDs constant within PA; K-label from
closed event set; sort-order deterministic. Dup policy: fail-loud on dup terminal.
Missing-event policy: null-`events` non-terminal only; missing terminal → quarantine,
never impute label. Versioning: `statcast_sha + pull_date + converter_version`.

**Feature-family order (evaluate in this order).** 1. Pitcher trailing K/whiff/chase
+ batter trailing K/whiff/chase + league baseline (log5 inputs). 2. Handedness
splits (batter populated; pitcher usage only — needs min-n). 3. Zone/chase/contact
splits. 4. Rest/workload/role stability. 5. Park + slot + lineup-status. 6. Pitch-mix
+ velo/movement (ablation, not assumed). 7. Recent-form deviations. 8. Repertoire×
tendencies, location, TTO (one family at a time). Rolling forms in order:
season-to-date (cold-start safe) → prior-N PA (pregame-available, needs PA clock) →
prior-N games → shrunk/hierarchical → hand/repertoire-specific → career+deviation.
Windows chosen inside 2023–24 rolling-origin folds only. Helps-PA vs helps-opportunity
labeled per family (workload/bullpen/hook = opportunity, not K).

**Model ladder.** B0 frozen (exact config). B1 generalized log5
(`log5(pb,pp,pl)` clipped 1e-4, `pa_sim.py:25` — hand-neutral first, handed iff
populated). B2 regularized logistic on transparent pre-PA features. C1 tree
(LightGBM existing framework — stable nonlinear iff beats B2 paired). C2 partial
pooling — binomial mixed-effects / empirical-Bayes / conjugate (NOT Gaussian: binary
K/no-K; Gaussian predicts fractional/negative K, breaks rung monotonicity, Brier/
logloss, λ-inversion — dossier §11h). C3 context extensions one family at a time
(handedness, repertoire, location/zone, TTO, recent-form, lineup uncertainty).
Each spec: target/inputs/strengths/failure-modes/cost/cold-start/interpretability/
calibration/data-volume/per-PA output/integration-without-prod-change/falsifier.
Complexity earned by paired wins over simpler rungs.

**Aggregation ladder + K/opportunity boundary.** Conditional PA p (given batter+slot)
vs slot occupancy vs cycling (`pa%9`, TTO on wrap) vs TBF count vs removal (hook/
pitch-count/survival) vs correlated state. Repo has: TBF point (Ridge, no
distribution), flat hook (`pull_prob=0.10`, `PITCHES_PER_PA=3.85`, `MAX_PA=45`),
MC alive/ks loop, `hook_pull_table` (353k PAs, uncalibrated), no survival/TTO model,
no substitution logic, no TBF distribution. Candidates: (1) fixed-TBF +
Poisson-binomial DP `pb_sf` (isolable, board-compatible; assumes independent PAs +
known TBF). (2) Discrete TBF-mix over PBs (needs TBF distribution — unbuilt).
(3) Survival/hook process (needs calibrated hook — unbuilt). (4) Full sim over
lineup+TBF+matchup (needs all above; most honest, costliest). (5) Current Poisson
baseline (mean=variance, no order). Isolate PA vs aggregation vs calibration vs
blend vs policy as separate experiments. Board consumes `p_over per line` — any
aggregator emitting that schema needs no ledger change.

## X. Evaluation contract

**Levels + metrics (no single metric promotes).** PA: logloss + Brier (proper),
calibration intercept/slope + reliability, ECE secondary with recorded bins,
discrimination, slices (pitcher/batter/hand/slot/month/history-bucket). Start:
MAE (primary) + RMSE, count NLL, distribution calibration, (randomized) PIT,
per-line calibration, over/under slices, integer-line push handling, TBF/hook-
bucket errors. Market: Δ-vs-devigged, CLV magnitude + beat rate, ROI + PnL + n +
Sharpe/MaxDD/Calmar/decay, book/line/side/month/edge-band slices. ECE never sole;
ROI never without uncertainty+volume+CLV.

**Temporal protocol.** 2023–24: strict as-of features, rolling-origin folds,
out-of-fold preds, in-fold transforms, pre-spec ladder + primary metrics. 2025:
fit on permitted 23–24, chrono-honest preds, identical eligible starts vs frozen;
calibrator/filter selection on 2025 ⇒ label in-sample (temporal split or
cross-fit); record every 2025 choice; freeze architecture/features/calibrator/
lines/policy/gates BEFORE 2026. 2026: one locked retrospective, no tuning, no
threshold re-search, paired differences, label retrospective (prior 2026 exposure
reduces credibility — control = pre-freeze + blindness gate + no 2026-fit +
single run). 2027: prospective, logged inputs/outputs, strongest claim.

**Paired comparison.** Same pitchers/games/timestamps/lineup-status/books/lines/
prices/open-def/close-def/devig/policy/stakes/push-void/universe, keyed by stable
observation ID (`game_pk + pitcher + game_date + line + book + side` + policy hash).
Existing frozen intermediates: `projections.parquet` (raw+cal+fair+shas),
`recommendations` + meta, ledger opens/closes/settles, `last_log`, manifests,
consensus/panel lakes. Recreate only what is missing via frozen code path —
never "repair" frozen during comparison. Six isolated experiments: PA-only,
aggregation-only, calibration-only, blend-only, policy-only, full stack last.

**Harness spec (design only, no code).** In: dataset/split/feature/candidate/
frozen/calibration/aggregation/market-snapshot/policy manifests + seeds + code
versions. Out: PA preds, start distributions, line probs, calibration outputs,
paired diffs, slices, policy outputs, CIs, regression checks, hashes, run manifest
(machine) + comparison report (human). Invariants: no as-of breach; no 2026 in
fit/select; disable→frozen-identical; finite bounded probs; mass sums; integer
pushes explicit; matched observations; missing-lineup logged; every result carries
universe/n/period/version/manifest. Gates: data/feat/leak/parity/eval/loadability/
shadow/approval/rollback.

## Y. External production parallels + enterprise gaps + consolidation + assumptions

Parallels (adopt principle, not platform): Rules-of-ML (already lived — no overhaul);
TFX stages (adopt Polars contract + checklist, reject full TFX); MLflow aliases
(deferred — sha-stamped monthlies + pointers suffice till train loop resumes); Savant
semantics (canonical); pybaseball (keep + retries); log5/slot-vector (adopt post-proc,
GLMM later); hook/survival (calibrate table, sklearn not torch); Poisson-binomial DP
(adopt as aggregator over slot probs, not 50/50 blend). Grades: supported vs plausible
vs blog vs vendor in dossier §D.

Enterprise (14 stages): strong = ingest/stats/transform/train-closed/shadow/prod-
infer/monitor/retro; informal/duplicated = candidate-eval/artifact-val/promotion/
rollback; missing = schema-val/registry; not-needed now = serving infra/TFX/MLflow.
Smallest: Polars contracts fail-LOUD; one eval engine with headers; manifest pointers;
staging + regression guard + registry (pitch-predictor borrow); documented rebuild-day
+ rollback command; monthly archive + index.

Consolidation (do not execute): devig, `bet_pnl/settle_side/size_in_units`, CLV scale,
ECE (6 copies → `prob_calibration`), count probs (`pb_sf` → canonical + pin),
selection (`apply_config` service), line-prob fallback disclosure, metrics
(`summarize_taken` + `quant_block`), open/close/edge/CLV/ROI defs (gates + golden),
paths/keys (`sorted_key` + `norm_player_name` unification). Owners/risks/prereqs in
dossier §F.

Hidden assumptions (sample; full table dossier §G): fixed 9-man (HIGH), fixed
starter/hand/TBF (HIGH), PA independence (HIGH), Poisson = variance (MED-HIGH),
stable league (MED), no subs/opener/injury/delay (MED), book uniformity (MED),
over/under complement (LOW-MED), calibration transfer (HIGH), source availability
(HIGH), TZ (guarded MED), ID stability (MED), feature order (MED), silent clip/
stale-fallback (HIGH). Each has location + test proposal.

## Z. Open questions + next authorization

Twenty investigated questions (best answer + evidence searched):

1. Champion selector? File `live_krate_ensemble.json` + convention defaults; manual-ROI, no command repro. [Blocking dataset: NO — comparator pinned.]
2. Frozen repro from command+manifest? L1–L3 + score reproducible; champion pick + WS1c refit need panels/CSVs. [NO — manifest incomplete (sha gaps).]
3. Canonical pitch history? `data/Savant-Data/regular/<yr>/statcast_<yr>_regular.parquet` (119 cols, verified counts). [NO.]
4. Pitch→PA canonical? YES `statcast.plate_appearances:501` + flags. [NO.]
5. Batter rolling pre-PA? YES `shift(1)` + collapse (verified lines). [NO.]
6. Pitcher rolling pregame? YES same pattern; P1 = prior start (variance noted). [NO.]
7. Rookies/sparse? Nulls → live-zeroed; shrunk 200-PA; hand splits std-only; explicit rookie path needed in spec. [Blocking dataset: YES — Q-D1.]
8. League-average K? Three computations (L1 scalar, batter expanding daily, pitcher opt-in prior-season) — unify in spec. [Blocking dataset: YES — Q-D2.]
9. Handedness populated? Batter yes (16 L1 + 10 L2 splits, min-n = den>0 only); pitcher usage-only. [Blocking model: YES — Q-M1 (min-n + shrink rule).]
10. Lineup order known at predict ts? RG projected/confirmed logged, never gated; realized (train) vs announced (live) skew. [Blocking dataset: YES — Q-D3 (doctrine).]
11. Before confirmed? Heal-first, loud stale-HOLD, fail-open; `--require-confirmed` legacy-only. [Dto: Q-D3.]
12. TBF point or distribution? POINT only (Ridge scalar, clip 33); no distribution/hook/survival. [Blocking model: YES — Q-M2 (fixed-TBF vs mix vs survival).]
13. Openers identifiable? Excluded `PA≥9`; opener family unmodeled (bias). [Blocking dataset: YES — Q-D4 (family rule).]
14. Which 2025 decisions used 2026? Floors/caps/WS1c/showdowns/panels — 2025-select/2026-judge discipline; granular pre-reg + `PeekRefused` pattern. [Blocking eval: YES — Q-E1 (choice log).]
15. Eligible PA rows by year? NOT measured (pitch rows ≠ PA). [Blocking dataset: YES — Q-D5 (count after exclusions).]
16. Identical market snapshots? Yes — ledger + quotes + consensus/panels + meta/shas persist; morning shared-quotes file missing (hourly has it). [Blocking eval: YES — Q-E2 (snapshot manifest).]
17. Intermediate live inputs persisted? Yes (board/ledger/quotes-sidecars/manifests/heartbeat/edge-watch/alert/grading/drift). [NO.]
18. Live-open reproducible? Ticket-ID deterministic + `logged_at` + policy/meta/shas; byte-repro needs morning quotes file. [Q-E2.]
19. 2027 logging for parity? Path exists (log slate + shas + manifests); needs run-ID/rowcount/cutoff/checksum per OBS-1. [Blocking eval: YES — Q-E3.]
20. Minimum improvement? LCB+White+cell+dkfd gates exist (selector); PA needs pre-reg deltas (Brier/logloss/ECE + slices + paper ROI/CLV) + kill rule. [Blocking eval: YES — Q-E4 (thresholds).]

Groups: dataset-blocking = Q-D1…D5 (rookie path, league-avg unification, lineup
doctrine, opener family, PA counts); model-blocking = Q-M1/M2 (hand min-n, TBF
representation); eval-blocking = Q-E1…E4 (2025-choice log, snapshot manifest,
2027 logging, promotion deltas); nonblocking = image-dep pin, Sharpe annualization,
key unification, morning quotes file, zone-10/NON_PA allow-list, row-drop audit.

**Next authorization requested (planning only, no build):** approve dataset
specification scope covering Q-D1…D5 + PA-row contract + feature-family order, with
frozen comparator (`ensemble + TBF + WS1c + policy + ledger`) untouched and 2026
untouched until the single locked run.

**Verdict: NOT READY — MISSING DATA TRUTH.** Pitch→PA conversion is canonical and
frozen inference is reproduced exactly, but eligible PA counts after exclusions,
rookie/league-avg rules, lineup doctrine, opener family, and snapshot manifest are
unresolved. No model spec until dataset spec closes them.

---

# Phase 3 — Data truth + frozen protocol (2026-09-28, measurement + spec, no build)

Four parallel read-only passes (PA funnel + pitch-to-PA; rookie/league/role; lineup +
odds replay; temporal/loss/distribution/bootstrap/policy/staking/workspace/promotion).
No dataset/model/CV/sweep/2026-run/code/artifact/schedule/install/commit/copy/merge.
Queries were lazy scans with in-memory counts; nothing written to
`data/`, `artifacts/`, `models/`, or the repo. Numbers below are measured unless
labeled ESTIMATED/ABSENT.

## AA. Data-truth measurements

**Pitch→PA (per season 2023/2024/2025/2026; 2026 thru 9/16, 2,285 games).**
Pitch rows: 720,684 / 711,208 / 712,528 / 674,483. Distinct `(game_pk,at_bat_number)`:
184,478 / 182,687 / 183,362 / 173,422. Pitches/PA mean 3.89–3.91, median 4, p90 6,
max 16–18. Zero PAs with >1 terminal event (0%). No-terminal PAs ~0.06%/yr
(101–117/yr — scorekeeping gaps, exclude). Terminal PA denominator: 184,376 /
182,582 / 183,245 / 173,321. `strikeout` 21.98–22.64% of terminals; `strikeout_double_play`
~0.06%. Observed `events` closed set (22 + null): field_out, strikeout, single, walk,
double, home_run, force_out, GIDP, HBP, sac_fly, field_error (~0.6%), triple,
intent_walk, sac_bunt, double_play, fielders_choice(_out), truncated_pa (~0.17%),
strikeout_double_play, catcher_interf, sac_fly_double_play, triple_play. NON_PA
deny-list hits: 0 rows all seasons. Unknown-vs-code: `field_error` and `truncated_pa`
only. Clock: `automatic_ball` ~2.1–2.4k pitches/yr, `automatic_strike` 85–302/yr, zero
in `events` (descriptions only — inherit label, no special-case). Mid-PA pitcher sub
44–65/yr (~0.03%); mid-PA batter sub 13–19/yr (≤0.011%) — quarantine, never impute.
Dup `(game_pk,ab,pitch_number)`: 0. `game_type`: regular files 100% R; postseason
files F/L/W/D (11.9k/12.9k/13.4k rows) — separation clean. Suspended-game columns:
ABSENT (no susp/resume/delay/game_number cols in Savant schemas). Doubleheaders:
21–35 team-dates/yr with >1 game_pk. Zone-10: 0 pitches all seasons (grid is
1–9,11–14; nulls ~2.6–2.8k) — no risk. IDs/hand nulls: 0. Data fault: postseason/2025
= 2024-postseason duplicate (43 shared gpks) + 2 regular games (747064/747139) —
quarantine before any postseason use. No spring files.

**Q-D5 funnel (step-0 = terminal PAs; training PAs → odds-evaluable PAs).**
Steps 1–6/11 lossless (terminal 99.94%, is_pa 100%, label 100%, IDs 100%, regular
100%, handedness 100%). Step 7 (pitcher ∈ pitcher_games): 56–58% kept
(105,385/106,267/106,123/97,537); miss ~42–44% = bullpen + sub-9 openers by design.
Step 8 (PA≥9): dropped starts 2.3–4.4%/yr (110–203), PA vol dropped 572–1,068
(~0.6–1%); kept starts = pitcher_games exactly (4,663/4,711/4,750/4,367), kept PA
min 9, median 23. Step 9 (pitcher history, `k_rate_P5` null proxy): 7.0% (2023,
no-2022 window) → 1.6–2.5% steady state. Step 10 (batter history): ~1.4% all years.
Step 12 (projected lineup): ABSENT 2023–25; 2026 only 6 daily snapshots — training
uses realized Statcast initial lineup. Step 13 (nine valid): 100%, L3 badsize=0.
Step 14 (odds match, early-open join measured): 2023/24 0 (ABSENT lake); 2025
3,381/4,750 starts (71.2%), 76,151/106,123 PAs (71.8%); 2026 1,880/4,367 (43.1%),
42,548/97,537 PAs (43.6%; envelope thru 09-10 only). Final 15a (all eligible
training PAs): 105,385 / 106,267 / 106,123 / 97,537. Final 15b (odds-evaluable):
0 / 0 / 76,151 / 42,548. Overlaps: steps 2/4/5/6/11 fully overlap step 1; step-8
loss ⊂ step-7 miss explanation; step-14 loss is coverage (date-bounded), not
within-coverage selection.

**Risk probes.** `PA=0` rows: pitcher_games 0; batter_games 15 total (pinch-hit
remnants, documented); pitch_type_games 9,285 (10.3%, expected slices). The
`K/max(PA,1)` clip never fires on the pitcher spine. `diagonal_relaxed` sites:
statcast:440,498; ballpark:162; odds_ledger:375,465,592; real_bets:170; plus
research/ops harnesses — drift silently absorbed (`__index_level_0__` 23/24 only;
`miss_distance` 25/26 only; `game_date` datetime vs Date; 118/119 common cols).
Rolling→training drops (−75/−829): 100% = 2026-09-14/15/16 L3 staleness (training
max 09-13 vs rolling 09-16), not filters. Source-version pin: NO `pull_date`/sha
columns anywhere — unpinned.

## AB. Dataset eligibility specification

**Q-D1 rookie/sparse (resolved).** Current: debut = `k_std/P5/rest` null,
`is_season_debut=1`, `is_career_mlb_debut=1` (`pitcher_rolling:215-291`); season-first
= std null but P-windows carry (recent-form); batter null → shrunk
`(priorK+200·lg_k)/(priorPA+200)` with expanding prior-date league, fallback scalar
`0.22381258`, so built shrunk nulls = 0; hand splits std-only, null 3.0% vL / 1.6%
vR; unresolved IDs → TBD→None, lineup-strict raise, starter-coalesce, bad-game
whole-slate drop with WARNING (rate unlogged — unmeasured); no minors; absent
projected player → as-of left-join nulls counted in `n_missing_form`, then
`score_frame` fail-loud (no silent impute). Contradiction: live forces both debut
flags to 0 on every slate row (`live_assembly:704-710`) — true debuts score as
rested veterans to the Ridge. Frequencies: batter std-null ~1.4%/yr; pitcher
season-open ~7%/yr every year; career-debut 7.0% (2023 window-start over-flag) →
1.6–2.5% steady state; opener lineup nulls 30 starts/yr (0.64%, exactly opening
games). DEFAULT: expanding empirical-Bayes shrinkage at current strengths (200 PA
batter; 1000 FB; 500 park) + missingness flags kept + fix live debut-flag
propagation (`prior_start_date.is_null() → is_season_debut=1`, rest nulls, never
force 0). CHALLENGER: prior-season carry-forward wired as candidate
(`add_prior_season_shrunk_k`, strength tuned in 23–24 folds only) vs plain league
fallback. Falsifiers: no MAE/Brier gain on first-30-day slice; debut-flag fix moves
TBF MAE <0.1 PA; hand-league prior beats player-only on vL-null bucket.

**Q-D2 league baseline (resolved).** Eleven implementations inventoried; three
families: (i) K-rate: L1 static prior-season scalar (all-PA, PA-weighted);
batter expanding daily (all batters, shift-1, DH-safe); pitcher opt-in
prior-season starter-only (UNUSED — not wired); scored-subset globals in
ladder_sim/v4 (research-only, lookahead — never train/serve). (ii) HR/FB league
(all pitches, 1000-strength, expanding + static anchor — keep separate, FB
denominator). (iii) Park (venue, 500-strength, seasons<target — keep separate).
Canonical (spec, not built): all-regular-season-MLB-PA (`is_pa`), both hands,
starters+relievers+subs; expanding cumulative strictly prior-date (DH-safe) +
prior-completed-season scalar fallback (today 0.2238); overall only — hand/slot/
pitch-type priors stay separate features. F/H lookahead globals labeled
research-only.

**Q-D4 opener/role (resolved).** Traditional starter only cohort that trains
(`_starter_keys` inning-1 + `PA≥9`); opener excluded by design; bulk invisible
(never inning-1, no family); spot starter indistinguishable if PA≥9 (rest flags
only signal); relief excluded from spine (team lookbacks only); scratch via
dual-score + Final-unappeared/24h-unstarted voids; doubleheader no separate family
(first-collapse + game_number disambiguation); suspended/resumed unmodeled (ledger
void only). Prevalence: excluded PA<9 = 3.5% of first-pitcher appearances
(340/9,714, 2023–24 artifact); PA≤6 opener-like 2.3%; filtered marginals PA<12
1.5%, PA<15 3.6%; singleton-starter games 6.5% (other side opener/short);
same-pitcher same-date 0; void/scratch rate unmeasured (no ledger on disk).
Narrowest first population: KEEP `PA≥9` first-pitcher estimand for k-rate/TBF/
count + metrics; add pregame role-flag ingestion before any expansion; live scores
announced starters but forces OOS on known opener/short plans via pregame-
observable source (never postgame PA); unify three divergent OOS thresholds
(`projection_support` TBF<12/expK<1.5/rest≥45 vs board line≤2.5/TBF<15 vs gate
TBF<15) into one spec. Language stays conditional ("first pitchers who faced ≥9").
Bias note: MAE/Brier/ROI upward-selected (excluded PA<9 K-rate 0.238 vs 0.220).
Falsifier to expand: opener/bulk >5% of announced 2026 starts or OOS rows carry
net edge.

## AC. Historical lineup and odds replayability

**Lineup verdict: oracle YES, realizable THIN.** Persisted projected history =
six 2026 DailySlate snapshots (07-28/07-30/08-07/08-10/08-20/08-21; 1,278 lineup +
142 starter rows; `lineup_status` projected/confirmed + `fetched_at` UTC + order +
game_pk) + 4 projection_log dates (09-14…17, 98 rows, 44 conf/30 proj/24 null) +
graded 44 dates (status only post-09-15). ABSENT: everything before 2026-07-28
(no snapshots, no fetched_at, no status). Quality on retained rows: 0 miss/dup
slots, 0 null batters — but lossy upstream (bad games dropped with WARNING, no
ID ledger). Projected-vs-actual slot personnel 44–64% (teams exact 0–43%);
08-20 is post-game (100%, not a prediction). Only 08-10/08-21 are true pre-tip
daytime fetches; no 08:00-pinned series; only 09-16 multi-snapshot. Oracle actual
(`is_initial_lineup` 9-man): YES all years (43.7k/43.7k/43.7k/41.1k rows, exactly
9 per team-game, 0 nulls) — labeled non-actionable. Code: `lineup_status` from RG
markup (`daily_lineups:773`); L3 = realized oracle means; live = announced means
+ dual-starter rows; status worst-wins join (post-09-15). Modes: 1 realizable =
2026-THIN (5 pre-tip snapshots); 2 confirmed = THIN (single clean 07-30 case);
3 oracle = YES all years, non-actionable; 4 missing-fallback = supportable as
logged nulls (training already emits them). Never pass projected as actual.

**Odds verdict (upgraded 2026-09-28 refresh): FULL board/close/morning clocks,
2025-03-18 → 2026-09-27.** Refresh rebuilt all four parquets (~18:17 UTC; hashes
in source register): pitcher 2,404,372 rows, batter 15,577,193, consensus 97,801
(gd 2025-03-27 → 2026-09-27), envelope 14,531 rows with 0 missing envelopes
(board 4,912 / close 4,724 / morning 4,895). Clocks: board = requested 12:00 UTC
(≈08:00 ET, CANONICAL OPEN, vendor lag ~4.4 min); close ≈ commence−5 min; morning
≈ commence−5 h. K-main per clock: board 115,103 rows / 4,841 events; close
156,660 / 4,705; morning 153,468 / 4,866; board+close event intersection 4,645.
Coverage (K-main, name-join, envelope-gated): board 2025 3,469 starts / 77,740 PAs,
2026 3,175 / 71,335; close 2025 3,381 / 75,695, 2026 3,146 / 70,700; morning 2025
3,495 / 78,291, 2026 3,171 / 71,248. The 09-11…26 envelope gap is CLOSED.
Remaining: friend CSVs deprecated (end 07-10); featured_totals stale at gd 09-10
(environment only); Kalshi sparse; live tip-window ticks in cloud volume only.
Full per-file register: `docs/reference/offseason_2026_source_register.md`.
Lineup replayability UNCHANGED (realizable still THIN — odds completeness does not
fix lineup snapshots). Modes 1–4 labeling stands.

## AD. Temporal development and policy protocol

**2023–2024 rolling-origin (PRIMARY A, sensitivity B+C).** Ground: seasons from
config; bounds from `regular_season_schedule()` + L1 audit at freeze (not
hardcoded); null doctrine kept (no debut drops; report `prior≥5 + pitches≥300`
slice); hard season reset (2024-04 trains on 2023 only; carry only park/league
scalars + declared prior-season shrunk); preprocessing fits strictly
`< test_start`; hyperparams frozen; no calibration fitted in base comparison
(WS1c-style maps only as declared secondary arm on train-fold dates); unit =
start; CIs game-clustered. A = expanding monthly (~9 folds, every-row-predicted
OOF for 2023-05→2024-09, Aprils warm-up); B = 3 multi-month blocks (stability,
no full OOF); C = 2023→2024 transfer probe (Opening-Day survival). Nested
evaluation feasible but deferred (retrain path closed; CV here judges frozen
config, never tunes). Floors/caps/veto/probation/Kelly frozen during CV.

**Loss hierarchy.** PA fit: PRIMARY unweighted L2 on k-rate (frozen continuity);
secondary binomial/BB-NLL, PA-weighted MAE/RMSE; logloss/Brier/focal/weights/
market-weighted as research arms only (market-weighted = leakage, never trainer;
classifications never fitting signals). Start mean: MAE/RMSE/bias + xK/TBF/line/
debut/month/season slices. Start distribution: count NLL + RPS/discrete-CRPS +
randomized PIT + coverage (all NEW — absent from `src/Python`) + per-line
Brier/logloss/ECE/bias + push documentation (K half-lines; whole-number rungs
push-not-loss). Trading: paired edge/CLV (same-book headline, consensus
secondary)/ROI/PnL/n/Sharpe/Sortino/MaxDD/Calmar/decay + monthly/cumulative, CI
always. Four non-substitutions: MAE≠distribution; xK-MAE≠distribution choice;
trading≠calibration repair (BET ECE 0.159 was selection, not calibrator failure);
probabilities≠fills (fair/xROI/juiced are upper bounds).

**2025 policy protocol (PRIMARY A-split, B sensitivity, C deferred).** Search
space inventoried: floors {0.08,0.10,0.12}×caps×sides×books = 36 (selector), 80
(band_grid), 56 (decision_grade); lines 2.5–9.5; veto 4.5-over always-on;
probation bump 0.18; TBF≥15; DK/FD-sign; WS1c vs raw; ensemble fixed; flat $50
(canonical `bet_pnl`); family rules; freshness/postseason gates. Contaminated
inputs flagged (veto/probation/floors from 2026 n≈74; WS1c/distill/offset cuts
ate 2025/26). A = select-2025-once/judge-2026-once (disclosed-peek, precedented,
matches freeze); B = 23–24 OOF for model/distribution only; C = nested (deferred
till retrain ordered). Choice-log schema required
(timestamp/cutoff/candidates-hash/metric/constraints/selected/rejected-top3/
rationale/code+data+artifact hashes). Freeze-before-2026: no selector/
calibrator/floor/veto/probation/cap/book/sizing change on 2026 outcomes; 2026
judge-only.

## AE. Distribution and bootstrap experiment specification

**D0–D5 (TBF params frozen; mean `E[K]=k_rate·TBF` unless declared).**
D0 frozen Poisson (`sf(t−1,μ)`, `t=floor(line)+1`, live default) — variance μ;
fails as under-dispersion bias flip (+4.8pp@2.5→−14.5pp@9.5). D1 fixed binomial
(`sf(t−1,rint(TBF),p)`) — silent round-half-even is NOT coherent (no Jensen
correction); keep as legacy arm only; coherent alt = floor/ceil mixture (new).
Variance < μ. D2 fixed-sequence PB (9 slot probs, n=round(TBF), DP `pb_sf`) —
killed (no Brier gain) but surviving hypothesis as aggregator over slot probs
(not 50/50 blend); needs coverage audit (`n_noslot` dropout); O(n²)/start;
independence conditional-on-slots is false — report spread miscalibration
separately. D3 TBF-mixture PB — UNBUILT law; EXISTS as inputs: graded residuals,
historical_scores panel, hook_pull_table + EB rates + MC consumers, TBF/bulk/
month/lineup columns; UNBUILT: versioned OOF residual store
`(date,pitcher,gpk,proj,actual,resid,buckets,cutoff,hash)` + mixer API; no
in-sample, no 2026 buckets; mean preserved or shift declared. D4 NegBin
(`sf(t−1,r,r/(r+μ))`, moment-match r∈[0.5,500]) — H0 Poisson vs H1 NB on held-out
NLL + per-line Brier/logloss + PIT + coverage; pre-reg kill on no gain. D5
survival/hook — future only (no hazard module in `src/Python`); censored sim;
never live until D3 survives. Per-distribution: mean/variance/inputs/assumptions/
line+push probs/metrics/failure/complexity/seam tabled in dossier.

**Bootstraps.** A (metric uncertainty): resample the CLUSTER, keep all rows;
paired challenger−champion diffs on same resampled clusters; PRIMARY = game-day
slate-clustered (market-correlation + precedent); SENSITIVITY = pitcher-block
(same-arm critique) + i.i.d.-row strawman; report rows AND clusters (rows≥200,
clusters≥30). B (TBF uncertainty): OOF residuals only from graded/scores panels
(TBF sidecar eval store UNBUILT); buckets pre-reg ≤2025, never 2026; residuals
never feed fits. C (bagging): default NO — only on measured instability
(fold-variance/churn/small-n) with pre-reg variance target + OOF proof.
Bootstrapping quantifies a fixed estimator — never re-weights/repairs loss.

**Staking (flat primary; Kelly later, same bets).** Flat $50u is money-truth lane
(selectors recompute flat via `bet_pnl`; juiced DK+FD flat +12.3% vs Kelly +6.6%;
live flat vs 1/16 tie +8.70/+8.66). Later: flat vs capped-1/16 (+smaller iff
drawdown-justified, never ROI-picked) on IDENTICAL takes. Kelly spec frozen from
code: `f*=(p·dec−1)/(dec−1)`, 1/16 frac, $5k bankroll (fixed-anchor per call —
declare fixed vs compounding at build), bet-side price, calibrated prob declared,
correlation ignored (report concentration), family 1/16 only, drawdown
human-monitored (no automation per stoppages order), no-bet on NULL prob. Gate:
edge-ordering evidence (threshold monotone + White-lite + LCB) before
edge-proportional primary. Live floor 0.12 (policy) vs market default 0.08 —
declare floor source per report.

## AF. Research workspace boundary specification

`research/offseason_2026/` approved-but-NOT-BUILT (glob = no files). Import audit:
safe = market, count_layer, prob_calibration-read, odds_ledger-read
(`load/settled/dedupe`); adapters = odds_board builder (pulls live-fetch),
live_assembly (hard lightgbm + DailySlate), slate/modal chains (shells);
never-import = poll/grade/log writers, alert/drift pagers (ntfy/dotenv/write
side effects at import/run), modal as scheduler. Spec: read-only roots (src,
policy JSONs, L1–L3, historical_scores, universe panels, graded, model loads);
writable roots (`experiments/reports/artifacts` under workspace only); config/env
boundary (read paths, never override; no keys/API calls); manifest formats
(run/dataset/split/feature per `run_manifest` precedent + hashes); champion/
challenger refs by hash, never copies; retention (dated reports kept,
experiments one-in-one-out, no bulk data committed); repro (decisions entry →
hashes → single command); live-write prevention (writer/pager import ban + CI
grep for LEDGER/LOG/NTFY writes outside production); entry-point prevention (no
deploy/cron/settle/close/append flags; --help smoke); promotion by extraction PR
(weights/config/pointer + manifests + decision log). Options: 1 bounded folder =
DEFAULT (adopted — no contradicting evidence); 2 subpackage, 3 branch-only,
4 separate repo rejected (truth/import/lineage costs); 5 file-copy EXPLICITLY
REJECTED (forks devig/edge/Kelly/CLV — the SOP failure mode).

**Promotion Gates 1–6 (evidence; numeric deltas set at build):** panels (hash +
join audit) → bins (per-line skill + slices, same subset) → calibration
(close-skill ≥0 chrono-safe + version/cutoff) → policy (n≥200/30/100+5, ROI>0,
Sortino≥0.25, PF≥1.2, MaxDD/CVaR not worse, cell≤40%, dkfd-sign, CLV≥0, LCB +
White-lite) → shadow (sidecar columns, zero live change, weekly-pack confirm) →
sign-off (owner order + revert path + choice log + freeze attestation). Baselines
= frozen D0 + ensemble + policy champion (hashes in manifests); CIs =
slate-clustered 95% + pitcher-block sensitivity; slices = L1/L2 list + full/
last-60/last-30 windows.

## AG. Remaining decisions and readiness verdict

**Replayability matrix (2025 | 2026 | timestamped | reconstructable | limit).**
Projected lineups: none | 5 pre-tip snapshots | fetched_at yes | NO (no 08:00
series) | oracle-or-fallback, never projected-as-actual. Probables: none | 6
dates | fetched_at yes | NO history | coalesce is code-only. Frozen features:
4,663+4,711 rows | 4,292 (75 opener-nulls short) | game_date | YES via L2-asof |
nulls stay null. First-logged opens: friend −12h to 07-10 | same (gap after) |
bookmaker_last_update yes | YES to 07-10 | no opens 07-11…09-27. Tip-window
prices: none | none in lake | n/a | NO (no q5m/60s replay from 5-min/5-h
clocks). Closes: full (12 invalid refused) | to 09-24 lake, envelope to 09-10 |
vendor to 09-10 | YES after 09-11…26 envelope backfill | 09-11…26 unjudgeable
till then. Book/market: 9 books K-main+alt+4 aux | same | yes | YES | alt
over-only, aux one-sided, FD sparse 26. Settlements: 4,750 starts 0-null | 4,367
0-null | game_date | YES (+void rules) | cloud ledger holds live voids; repo
tickets 1 row — not season truth. Push/void: win/loss/push, voids excluded |
same | settle_ts | YES | all lines .5 (push n/a). Artifacts/policy: ensemble
0.60/0.40 (08-21), TBF 07-28, WS1c 09-10 (cutoff 09-03), Poisson, 1/16, cap
0.24, veto, probation, TBF≥15, DK+FD, postseason HOLD | pointer JSONs yes | YES
(pin shas) | pre-09-10 universe scored under binomial/isotonic — disclose deltas.

**2026 one-shot contract.** Consumes: frozen historical_scores probs (never
re-score) + vendor-ts paid closes/mornings + friend opens (to 07-10) + batter_
rolling settlements + pinned artifacts + policy configs. Emits: single
`universe_panel_2026lock` + `juiced_replay_2026lock` + accept/reject ledger +
block-bootstrap report. Seven prohibitions: no 2026 fit/calibration/feature/
threshold/stake/exclusion-rerun; no envelope relaxation (12 invalid stay out,
09-11…26 waits); deviations become preregged hypotheses, never reruns.

**Still unverified:** 2026-09-11…26 envelope rebuild (blocks close judging);
morning/market snapshot for 07-11…09-27 opens gap; multi-snapshot/day lineup
proof of last-update-before-wager; unresolved-ID drop rate (needs automation
logs); void/scratch season rate (needs cloud ledger); raw-JSON field audit
25-vs-26 (medium confidence only); nested-CV cost confirmation; TBF sidecar
residual store (unbuilt); count NLL/RPS/PIT/coverage helpers (absent).

**Next authorization requested (no build):** dataset specification — PA funnel
code (read-only, workspace-scoped) with Q-D1 default + Q-D2 canonical + Q-D4
cohort + mode-1/mode-3 lineup labeling + §AD/AE/§AF manifests, frozen comparator
untouched, 2026 untouched.

**Verdict: READY FOR DATASET SPECIFICATION.**
(Lineup replay is THIN and odds need envelope backfill, but neither blocks a
2023–2024 PA dataset spec on oracle-labeled + mode-flagged lineups with
odds-evaluable 2025/26 subsets declared; those blockers gate the 2026 run, not
the spec. If ordered otherwise: next blocker would be LINEUP REPLAY, then ODDS
REPLAY.)

---

## AH. Canonical index (one page — decision → section)

| Decision / term | Status | Section |
|---|---|---|
| Repo scope, manifest, production truth (P1–P9) | DONE | B, C, D |
| Doc census (108 md), R-001…R-016, prompt ledger, link register | DONE | E, F, G, H |
| Contradiction register (12 conflicts; age_walkforward violators recorded) | DONE, unresolved items flagged | I |
| Model card (ensemble 0.00/0.60/0.40, TBF α=123.28 clip 33, WS1c 8-line) | FROZEN comparator | J |
| Feature lineage + leakage audit (shift(1) + collapse verified) | DONE | K, V |
| Eval integrity (metric locations, scale rules, contamination note) | DONE | L |
| Batter-K seam (20 Qs; log5/PB research-only; no prod log5/PB) | DONE | M, W |
| Surgical dossiers (13 candidates, S/M/L) | DONE | M |
| Diagram gaps (2 missing: warehouse flow, promotion pipeline) | OPEN | N |
| Decision-record proposals (accepted vs unresolved) | DONE | O |
| Dependency watchlist (image-vs-pyproject drift; RG fragility) | MONITOR | P |
| Experiment portfolio + 10-stage roadmap | DONE | Q, R |
| Owner questions Q-01…Q-08 | Q-03/Q-04 blocking; rest §S | S |
| 32 key-file dossiers; frozen equation map | DONE | U |
| Training-row / feature / artifact manifests; train-vs-serve skews (10) | DONE | V |
| Pitch→PA truth (canonical converter + terminal-only confirmed) | DONE | V, W, AA |
| PA-row contract + feature order + model/aggregation ladders | DONE | W |
| Temporal contract (A/B/C folds; A-split policy; 7 prohibitions) | FROZEN | X, AD, AG |
| Loss hierarchy (L0–L3 + 4 non-substitutions) | FROZEN | X, AD |
| Harness design (no code) | SPEC ONLY | X |
| Behavior-to-test matrix (gaps: schema/parity/denom/book-universe) | OPEN | Y-dossier §C |
| Enterprise gaps (schema-val + registry missing; TFX/MLflow rejected) | DONE | Y-dossier §E |
| Consolidation candidates (10, unexecuted) | DEFERRED | Y-dossier §F |
| Hidden assumptions (13, with tests) | DONE | Y-dossier §G |
| Q-D1 rookie default (shrinkage + flags + debut-fix) | FROZEN §AB | AB, AA |
| Q-D2 canonical league baseline (all-PA expanding + 0.2238 scalar) | FROZEN §AB | AB |
| Q-D3 lineup modes (oracle-YES / realizable-THIN) | FROZEN §AC | AC, AA |
| Q-D4 cohort (`PA≥9` first-pitcher + role flags next) | FROZEN §AB | AB, AA |
| Q-D5 funnel (105k/106k/106k/98k; 76k/43k odds-evaluable) | MEASURED §AA | AA |
| Lineup/odds replayability + 2026 one-shot contract | FROZEN §AG | AC, AG, AA |
| Distribution D0–D5, bootstraps A/B/C, staking (flat primary) | FROZEN §AE | AE, AD |
| Workspace boundaries (option 1; file-copy rejected) | FROZEN §AF | AF |
| Promotion Gates 1–6 (deltas set at build) | FROZEN §AF | AF |
| 20 owner questions (dataset/model/eval/nonblocking groups) | §Z | Z, AG |

Frozen terms (do not relitigate): 2023–24 train/dev, 2025 validation+policy,
2026 locked retrospective (never pristine), 2027 prospective; frozen comparator
(ensemble + TBF + WS1c + policy + ledger + dedupe + schedules + sizing);
slot-vector post-proc, no pair memorization, lower layers frozen; fail-LOUD, no
auto-blocks; flat-$50 primary; pitch counts never cited as PA n; final 2025
policy refit is in-sample (choice log #2); 2025B n-floors (choice log #3).

Owner decisions: five approvals §AH-choice-log (4 approved + Q-04 pending);
Q-01…Q-08 §S; Q-D1…D5/M1–M2/E1–E4 §Z/§AG. All statuses in
`docs/reference/offseason_2026_choice_log.md`.
Per-file source register: `docs/reference/offseason_2026_source_register.md`.

---

## AI. Data-quality register (permanent rules from wonky findings, 2026-09-28)

1. **Missing-board = no-bet, never forward-fill.** Absence of a row is not evidence
   of absence of a market. A start with no board-clock K-main coverage is excluded
   from the eval universe; never carry a morning/close price backward as the open.
2. **Postdate-first-pitch exclusions via vendor flags.** Refuse any snapshot with
   `lag_vendor_vs_commence_sec < 0` (measured: board 2, close 14, morning 0).
   No recon-ts substitution, no `next_timestamp` forward-fill. The 16 refused rows
   stay refused in every rebuild.
3. **No −30h/−24h clocks exist for MLB props; open ≈ 8am.** Probes (`_probe/
   open_clock_probe*.json`, evidence-only) show −12h thins to ~4 books vs board
   5–9; markets are not posted a day out. Canonical open = board clock
   (requested 12:00 UTC). Friend −12h CSVs are RETIRED (deleted 2026-09-28,
   backups hashed in source register §6); they are evidence, not a second open.
4. **Batter-K is a ghost market.** 43,006 rows / 742 close + 602 morning events,
   zero board rows, vs pitcher-K ~4.7–4.9k events per clock. Never a primary
   eval population; any batter-market use must cite its own coverage first.
5. **Postseason excluded by design.** 88 Oct/Nov-2025 envelope rows exist and are
   out of scope (regular-season model; separate run environment). Same for the
   duplicated 2024-postseason files under `Savant-Data/postseason/2025`
   (quarantined, §AA). Spring/board-early rows before 2025-03-27 (Tokyo Series
   edge) are flagged, never silently pooled.
6. **Discovery must not run past season end without the regression guard.**
   Pulls stop at the regular-season boundary (2026-09-27/28); any October rows
   arriving later trip the guard (fail-LOUD manifest flag + choice-log entry),
   never silent ingestion. `skipped_events.json` (51 IDs) is re-checked before
   the 2026 run — a skipped event with later coverage must not silently re-enter.
7. **Lake asymmetry is declared, not repaired inline.** Board starts 2025-03-18
   (10 days before close/morning 03-27); `featured_totals` is stale at gd 09-10
   (environment only); consensus is research-only (never re-devig). Rebuilds
   preserve these boundaries; any change gets a new envelope + manifest hash.



