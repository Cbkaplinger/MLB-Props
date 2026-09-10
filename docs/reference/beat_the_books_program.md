# Beat-the-Books Research Program (2026-09-08; external lessons merged 2026-09-10)

> Goal: sustained positive EV vs books on MLB K props, measured in money on
> Novig fills. Standing rules apply: post hoc only, chrono-safe splits,
> post-freeze eval-only, no live promotion without sign-off + revert path.
> Master work-state: `docs/EXECUTION_BACKLOG.md`.
> External teachers: KSplit methodology + diagnostics (benchmark, not gospel),
> open-command CV command data (research stage → NC license compliant).

## 1. Diagnosis (evidence-locked 2026-09-08, n=1,049–1,512 joined)

- Books are nearly perfectly calibrated (consensus ECE 0.015); model ECE 0.159.
  Gap is post-calibration (83% of probs already Platt/isotonic).
- K error is k-rate error (corr 0.93 vs 0.37 TBF; TBF = 21.5% of variance).
- Range compression is learned shrinkage, not coded caps (TBF clip 33, non-binding).
- NEW: on BET tickets the model OVER-predicts xK by +0.7–0.9 (vs +0.05 globally) —
  the edge floor SELECTS over-predicted tickets. Over-bleed = selection amplifier
  on top of a probability problem. Both must be fixed; veto only treats selection.
- NEW: "capped" arms are breakouts/call-ups the model never heard of (Seymour −4.8,
  Lopez, Rogers, Luzardo, Detmers) + declining vets over-predicted (Sale, Eovaldi)
  — STALENESS + age curves, not ace saturation. Mid-bin (xK 4–6, n=1,168) bleeds
  spread-wide, so this is not "just aces."
- NEW: TBF error is symmetric shrinkage — +5.2 PA on early hooks (<15), −5.1 on
  marathons (≥28). Textbook case for a two-stage workload model.
- UNIVERSE (n=70,200 line-points, 2026-09-09+): we BEAT the opener (+0.044 skill)
  but trail closes (−0.006) — edge decays −12h→−5h fully; selection amplifies
  (ticket skill −0.041 vs universe −0.005). Bias flips +4.8pp @2.5 → −14.5pp @9.5
  (under-dispersed curve). TBF tails +9.5/−5.4 at scale (marathons irreducible
  pregame — three killed mixtures). Age skill U-shape (≤26 −0.009, prime −0.003,
  33+ −0.006; no linear edge, r≈−0.02; 38+ survivors elite-xK yet −0.45 resid).
- EXTERNAL BENCHMARK — KSplit (3,582 logged): MAE 1.749 (ours 1.77), bias +0.029
  (ours +0.11); overs −0.01 bleeding at 15%+ edge (universal over-bleed, not our
  bug alone); unders +0.03 green at 0–15% (same pockets). TARGETS: bias ≤0.03,
  MAE ≤1.75, then beat via TIMING (distribution shops don't time; our opens
  edge is the differentiator). Even KSplit ≈ breakeven: ROI comes from timing +
  selection + fills, never raw edge alone.

## 2. Workstreams (ordered by EV ÷ cost; kill criteria each)

**WS1 — Shrink-to-consensus blend (tactical, days).** Fit blend weight on the
close panel (never opens). Ships as shadow first. KILL: no Brier gain on held-out
chrono split vs current bundle.
**WS2 — Form-staleness fix (weeks).** Breakout detection (recent-whiff velocity,
call-up priors) + age-curve handling for declining vets. This is the capped-leaderboard
fix. KILL: no MAE_K improvement on post-April rookie/vet cohorts.
**WS3 — TBF two-stage (weeks).** Hook-probability head + conditional-outings head
replacing single ridge. KILL: no MAE_TBF improvement in PA tails (<15, ≥28).
**WS4 — Tail-aware k-rate (weeks).** Quantile/focal emphasis on high-K starts +
elite-whiff interactions. KILL: no Brier gain in xK 6+ bin.
**WS5 — NB count-layer challenger (research).** Unparks SSAC #9. Fatter tails than
beta-binomial. KILL-final (#69): NB-TBF workload mixture gains +0.00052 but
FLAT across r=50..1000 — mechanism falsified (residual Jensen gap from mixing
per se, untunable, 4% above bar). Moment-match found no overdispersion
(r→500 fallback). No logloss gain that measures the hypothesis.
**WS5b — Poisson-binomial aggregation (KSplit homework).** Nine per-hitter
Bernoulli trials (slot K% vs hand from batter_rolling first-9) instead of one
aggregate rate — more spread by construction, direct fix for the bias flip.
KILL: no Brier gain vs Poisson on held-out.
**WS6 — Steam/timing overlay (after WS1).** Morning-snapshot path features; answers
whether edge lives in timing. ANSWERED 2026-09-10: yes — skill +0.043 open →
−0.005 morning ≈ close; entire decay −12h→−5h. DOCTRINE: bet at open/earliest
number, never chase close. REMAINING: how early can live SharpAPI go.
KILL (overlay features): no CLV gain vs morning-only baseline.
**WS7 — Over-floor raise (policy).** Evidence supports ≥0.16, but ONLY through the
chrono-split gate with pre-registered cells. Never from a sweep alone.
**WS8 — Arsenal residuals / kAdj (KSplit homework).** Per-pitch CSW/whiff/chase/
putaway/quality vs pitch×hand league baselines, usage-weighted; pitcher-side
performance vs L/R (usage splits exist, performance splits need Savant join);
batter-vs-pitch-family vulnerability. Single-feature rule each.
KILL: no universe Brier gain per term.
**WS9 — Command features (open-command, research stage).** Season medians now;
start aggregates after pull (targets+pbp 2024–26, ignored `data/Open-Command/`).
Stabilizes ~10x Location+, YoY r=0.80, min-n 300 + hard shrink below. Test
"fast K%" (command → ROS whiff/K) on our outcomes. LICENSE: CC BY-NC-SA 4.0 —
research only, money-path needs clarity. KILL: no Brier gain per term.

## 3. Explicitly disregarded

- More global floor sweeps; pooled raw-vs-cal debates; tail-cell tuning (n=4 cells);
  GARCH vol (nightly settlement); price-momentum signals (steam-chasing);
  Pinnacle envy (absent — Kalshi + consensus suffice); repo renames; MLflow-as-ops.
- Umpires (ABS era — no zone edge to model); weather (Ballpark-Pal avenue but no
  historical panel — revisit only with data in hand); team-level lineup variance
  (injury-driven, low signal/cost); minor-league translation (costly, parked
  2026-09-10); TBF point-modeling past ridge+workhorse (three killed versions —
  policy-side + fat tails instead, pending retrain); full zone-grid replication
  (command target-maps partial cover; grids heavy, revisit post-WS5b).

## 4. Measurement contract (every workstream)

Report: Brier + skill-vs-consensus, ECE, side×line ROI/WR/CLV, floor sweep,
Sharpe/Sortino/decay, xROI-vs-realized gap — on the SAME joined panel + held-out
chrono split. Promote nothing from one green week. Weekly settle pack stays the
decision loop; this program feeds it challengers.
TRACK EXTERNALS: KSplit diagnostics as standing benchmark (bias/MAE/edge bands);
re-measure quarterly, never chase weekly.
BERKSON RULE: pitcher-level correlations conditioned on stuff (velo/whiff
proxies) or within-pitcher changes — survivors confound everything (age lesson).
EXTERNAL DATA RULES: license check first (NC = research only); coverage-split
documented before use (e.g., command starts 2024 → split options A/B/C);
stability gate (YoY/split-half r≥0.7 + min-n) before any window/feature enters.

## 5. Definition of money-truth

Skill (CLV vs consensus/Kalshi) gates selection; `real_bets` Novig fills gate
staking. Paper ROI never sizes stakes. ≥50 real tickets before any edge claim.
