# BF origin/tail audit (saved artifacts only) - 2026-10-08

> Owner-ordered read-only audit. Descriptive only; 2023 DEVELOPMENTAL.
> No fitting, recalibration, challenger scoring, acquisition, production
> changes, commits, or pushes. All frozen experiments and original
> outputs preserved. Analysis inputs: canonical expanding-BF artifacts
> (`workload-training-policy-20261007_090000`: predictions.csv sha
> 902e61da..., pmfs.parquet sha 1917c789...) and canonical I3b
> artifacts (`i3-opportunity-20261008_184154`: predictions.csv sha
> 23287ab4..., pmfs.parquet sha 1d361106...).

## 1. Input verification

- Positional alignment of the saved BF artifact pair re-proven:
  rps_B reproduction max diff **0.0** (all 4,446 rows).
- PMF mass max deviation from 1: 8.9e-16.
- **BF support (documented):** 37 categories - index 0..35 = BF 1..36
  exact; index 36 = P(N>=37) overflow. Overflow extension: geometric
  tail with ratio 1 - (mean implied hazard of indices 31..36); cap 60
  frozen, cap 120 sensitivity. **K support:** 24 categories (exact
  K=0..22 + absorbing >=23).
- Canonical identities carried from the prior alignment audits (key
  join + functional pinning; see kcount clarification section 1).

## 2. April tail mechanism - SEPARATED

**Predicted vs observed P(N>=37):**

| Origin | pred mean | observed freq | events |
| --- | --- | --- | --- |
| Apr | 0.02746 | **0.00000** | 0 |
| Jul | 0.00627 | 0.00000 | 0 |
| Aug | 0.00445 | 0.00000 | 0 |
| Sep | 0.00328 | 0.00000 | 0 |
| Pooled | 0.01512 | 0.00000 | 0 |

**The model assigns real probability to BF>=37 that never occurs: zero
observed events in 4,446 pitcher-games (observed max BF = 35; the
position-36 risk set is empty).** The pooled diff is +0.0151
[+0.0132, +0.0171] (date-clustered bootstrap; CI excludes 0). This is
error in ENTERING the overflow bucket - NOT an allocation problem
within it. The cap-60 vs cap-120 allocation question is second-order:
given the excess entry mass, the in-bucket assumption amplifies it
(April K>=12: +50% relative between caps) but the entry error is the
defect.

Count-layer impact of the cap-120 sensitivity (I3b, saved artifacts,
absolute + relative):

| Slice | dE[N] | K>=6 | K>=8 | K>=10 | K>=12 |
| --- | --- | --- | --- | --- | --- |
| Apr | +0.540 (+2.40%) | +0.27% | +1.99% | **+12.1%** | **+50.2%** |
| Jul | +0.016 (+0.07%) | +0.01% | +0.09% | +0.59% | +3.6% |
| Aug | +0.014 (+0.07%) | +0.01% | +0.08% | +0.53% | +3.3% |
| Sep | +0.006 (+0.03%) | +0.00% | +0.04% | +0.25% | +1.6% |
| Pooled | +0.255 (+1.15%) | +0.13% | +0.96% | **+6.3%** | **+32.2%** |

Latent E[K] pooled: 4.8706 (cap 60) vs 4.9279 (cap 120), +0.0573.

## 3. Workload calibration (frozen thresholds; date-clustered
bootstrap 2,000 / seed 20261001)

| Threshold | pred | obs (events) | diff [95% CI] |
| --- | --- | --- | --- |
| N<9 | 0.04175 | 0.04363 (194) | -0.0019 [-0.0074, +0.0034] |
| N>=19 | 0.84886 | 0.83873 (3,729) | **+0.0101 [+0.0004, +0.0202]** |
| N>=27 | 0.12387 | 0.12888 (573) | -0.0050 [-0.0160, +0.0051] |
| N>=37 | 0.01512 | 0.00000 (0) | **+0.0151 [+0.0132, +0.0171]** |

- **Two CI-excluding calibration defects: the overflow bucket (N>=37)
  and reaching N>=19 (+1.0 pt overprediction).** Both are
  overprediction of workload reach.
- Per-origin: N<9 September diff -0.0132 (underpredicts short outings;
  the known September symptom); N>=19 September +0.0482 (overpredicts
  reaching 19) - September miscalibration runs in BOTH directions
  (too many short outings AND too much reach), consistent with a
  mean-level shift, not a single-tail problem.
- Mean-BF residual (pred E[N] - observed): Apr +0.218, Jul +0.252,
  Aug -0.021, **Sep +0.693**, pooled **+0.270** - systematic
  overprediction of workload length.
- Exact-position mass (positions 1-36): largest deviations at the
  extremes (N=1 +0.0024; N=30 -0.0037); the body (N=9..27) tracks
  well.

## 4. Conditional hazards (observed risk set N>=t)

| Position | risk set | events | obs hazard | pred hazard | diff |
| --- | --- | --- | --- | --- | --- |
| N=1 | 4,446 | 1 | 0.00022 | 0.00267 | +0.0024 |
| N=9 | 4,252 | 37 | 0.00870 | 0.01017 | +0.0015 |
| N=12 | 4,176 | 35 | 0.00838 | 0.00831 | -0.0001 |
| N=18 | 3,890 | 161 | 0.04139 | 0.04577 | +0.0044 |
| N=21 | 3,217 | 352 | 0.10942 | 0.13828 | +0.0289 |
| N=24 | 1,899 | 543 | 0.28594 | 0.28774 | +0.0018 |
| N=27 | 573 | 294 | 0.51309 | 0.58548 | +0.0724 |
| N=30 | 71 | 38 | 0.53521 | 0.34188 | -0.1933 |
| N=33 | 8 | 7 | 0.87500 | 0.07467 | -0.8003 |
| N=36 | 0 | 0 | - | 0.04504 | (no risk set) |

- Body hazards (N=9..27) track the observed conditional termination
  rates well (diffs <= 0.07 on large risk sets).
- **The deep tail (N>=30) rests on 71/8/0 risk-set rows** - the smooth
  hazard continuation is structural extrapolation, not learned. The
  model keeps pitchers "alive" into a region where the empirical risk
  sets are empty or tiny (do not over-read the N=33 diff: 8 rows).

## 5. Count dispersion - CORRECTED DECOMPOSITION (I3b, matching rows)

Pooled: observed Var(K) = 6.5761 vs predicted decomposition
E[latent conditional variance] (5.2380) + Var(latent means) (1.0280)
= 6.2660 -> **ratio 1.049**.

| Origin | obs Var | denominator | ratio | mean residual | P(K>=12) pred vs obs |
| --- | --- | --- | --- | --- | --- |
| Apr | 6.437 | 6.531 | **0.986** | -0.040 | 0.0150 vs 0.0117 (24 ev) |
| Jul | 7.006 | 6.020 | **1.164** | -0.055 | 0.0084 vs 0.0150 (11 ev) |
| Aug | 6.045 | 6.046 | **1.000** | +0.060 | 0.0081 vs 0.0097 (8 ev) |
| Sep | 7.019 | 6.032 | **1.164** | -0.123 | 0.0071 vs 0.0119 (10 ev) |

**This supersedes the earlier dispersion findings.** With the correct
law-of-total-variance denominator (the earlier audit compared against
mean per-row mixture variance, omitting Var(predicted means) across
rows), the pooled residual is **+4.9%, not +23%**: April and August
are fully dispersed; July/September carry a moderate ~16% excess. The
"dispersion diagnostic fires" conclusion from the scored-run receipt
is hereby DOWNGRADED to: spread is essentially adequate; the visible
symptoms are (a) a LOCATION error (September mean residual -0.123 K /
+0.69 BF) and (b) tail underprediction of K>=12 in Jul/Sep - both
consistent with the workload-layer miscalibration, not with a
missing dispersion mechanism. No beta-binomial is indicated.

## 6. Summary and limitations

- **Clearest supported defect: deep-tail overprediction.** The model
  assigns 1.5% pooled mass (April 2.7%) to BF>=37, a region with ZERO
  observed events in 4,446 games and essentially empty empirical risk
  sets beyond N=30. Amplified in April by the short-training hazard
  shape.
- Second defect: systematic overprediction of workload reach (N>=19
  CI-excluding; mean-BF residual +0.27 pooled, September +0.69), with
  the opposite sign at N<9 in September.
- Dispersion: resolved to a ~5% pooled residual (adequate); the
  earlier +23% was a benchmark-definition artifact.
- Limitations: 2023 developmental exposure throughout; the observed
  N>=37 frequency is exactly 0, so tail corrections are identifiable
  only as "remove unsupported mass", not "estimate the true tail";
  sparse-cell uncertainty on N>=27/37 per-origin values; the
  date-clustered bootstrap treats slate dates as the dependence unit
  (documented convention).

## ONE bounded next experiment (proposal; not authorized)

**Empirical deep-tail BF challenger:** hold everything fixed (saved
hazard bodies, I3b count structure, scoring, identities) and replace
ONLY the overflow handling - redistribute each row's P(N>=37) mass
over BF 30..36 proportionally to the TRAINING-population empirical
conditional distribution at those positions (fit-free, strictly
pre-origin data; zero-mass beyond the observed support). Score I5-tail
vs I3b on the identical 4,446 rows with the frozen paired
count-RPS gate (2,000 / seed 20261001), reporting ladder deltas
(ge10/ge12 are where the effect concentrates). Rationale: the audit
shows the defect is ENTRY into an unobserved region with empty risk
sets; the identifiable correction is removal of unsupported mass
toward the empirical boundary, not estimation of a true tail.
April-only effect is expected to be small on pooled RPS but material
on April ladder probabilities - report both, keep cap 60 vs 120
sensitivity disclosed.

## 7. Corrections (owner round, 2026-10-08 — same day, pre-I5)

1. **Sign convention (frozen for all future reporting):** residual =
   ACTUAL minus PREDICTED (repo convention); bias = PREDICTED minus
   ACTUAL. Section 3's 'mean-BF residual' was reported as
   pred - observed: **bias = +0.270 pooled = OVERPREDICTION of mean
   BF by 0.27** (predicted E[N] = 22.1277 vs ACTUAL mean BF =
   21.8581). Per-origin bias: Apr +0.218, Jul +0.252, Aug -0.021,
   Sep +0.693 (all 'positive = model predicts longer outings than
   observed'). Section 5's 'mean residual' (K - predicted mean K):
   Sep -0.123 = the model OVERPREDICTS September mean K by 0.123.
   Both conventions now stated explicitly wherever residuals appear.
2. **Zero observed events is NOT zero true probability.** With 4,446
   Bernoulli observations, the rule-of-three 95% upper bound on the
   true P(N>=37) is ~3/4,446 = **0.067%** (illustrative only: date
   dependence and population selection weaken it). The bootstrap
   interval [+0.0132, +0.0171] quantifies the SAMPLE discrepancy; it
   cannot represent uncertainty about unseen rare events (resampling
   dates from a zero-event sample always reproduces zero). The
   defensible statement is: the sample strongly rejects an AVERAGE
   1.51% forecast for this population; the true tail probability is
   small but not identified as zero.
3. **'The identifiable correction is removal of unsupported mass' is
   DOWNGRADED to a proposed modeling assumption.** Zero observed
   events support rejecting the current 1.51% average, but the
   correct destination/shape of any redistributed mass is an
   assumption requiring explicit justification and credibility
   checks - not an identified fact.
4. **'Hazard bodies unchanged' corrected to:** original body mass at
   BF 1..29 is retained; overflow mass is reassigned into a
   PRESPECIFIED upper-body interval; implied hazards at the
   receiving positions change accordingly; E[N] decreases.
5. **'Fit-free' corrected to 'estimated transformation':** the
   empirical redistribution weights are ESTIMATED from strictly
   pre-origin training data. No model refit occurs, but the
   transformation is data-dependent and carries estimation noise
   (April's training pool is 414 rows - sparse; disclosed below).
6. **September and K-tail mechanisms remain UNRESOLVED** and are not
   addressed by the deep-tail challenger.