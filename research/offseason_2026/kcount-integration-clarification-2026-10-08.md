# K-count integration: dated interpretation clarification (2026-10-08)

> Owner-directed post-integration clarification. The frozen prereg
> (`kcount-integration-prereg.md`, sha `796a3606...`) and the original
> scored outputs in
> `MLB-Props-Research\kcount-integration-20261008_152747\` are UNCHANGED.
> This document only clarifies interpretation, using the saved artifacts
> read-only. Supersedes the corresponding wording in the 2026-10-08
> backlog receipt.

## 1. What the scored result does and does not establish

Established (developmental, 2023): **preserving workload uncertainty
improves the combined strikeout-count distribution versus plugging in
one rounded BF forecast, at the same strikeout-rate input.** It does
NOT establish production superiority or a betting edge, and it must not
be compared with the earlier BF-lane RPS reduction (different outcomes,
different supports).

### Absolute scores and relative reduction (I1 vs C1(L1))

| Slice | n | I1 RPS | C1(L1) RPS | paired diff | relative reduction |
| --- | --- | --- | --- | --- | --- |
| 2023-04-15 | 2,046 | 1.33239 | 1.34678 | -0.01439 | 1.069% |
| 2023-07-01 | 734 | 1.30451 | 1.31277 | -0.00826 | 0.629% |
| 2023-08-01 | 822 | 1.26926 | 1.27566 | -0.00640 | 0.501% |
| 2023-09-01 | 844 | 1.29929 | 1.31213 | -0.01284 | 0.978% |
| **Pooled** | 4,446 | **1.30983** | **1.32144** | **-0.01161** | **0.879%** |

I2 vs C1(L2): pooled 1.30428 vs 1.31546, relative 0.8495% - the
uncertainty benefit is consistent across both opponent assumptions.
I2 vs I1 remains non-separated.

### C2 information decomposition (corrected)

The receipt called C2 a "realized-lineup oracle"; earlier drafts said
"realized-N oracle". The runner code is decisive: C2 uses
`point_exposure_pmf(realized PA, realized-lineup p_bar)` - it changes
**BOTH** components:

1. workload: the BF PMF is replaced by the realized N (actual batters
   faced - an outcome of the game); and
2. opportunity composition: homogeneous p_bar is replaced by the
   equal-weight mean of per-batter log5 probabilities over the ACTUAL
   batters faced (realized lineup identity; rates remain strictly
   prior - no realized per-PA outcomes enter p_bar).

C2 is therefore a COMBINED oracle, and **its gap is not an estimate of
improvement attainable from a pregame lineup source** - the
information advantages have not been separated. Corrected wording:
"The combined oracle has substantially better scores (+0.106 RPS vs
I1), but its information advantages (workload vs lineup composition)
have not yet been separated."

### Cap-120 sensitivity, absolute AND relative (I1 ladder means)

| Slice | milestone | cap 60 | cap 120 | abs | rel |
| --- | --- | --- | --- | --- | --- |
| April | ge6 | 0.38899 | 0.38979 | +0.00080 | +0.20% |
| April | ge8 | 0.14904 | 0.15152 | +0.00248 | +1.66% |
| April | ge10 | 0.04721 | 0.05220 | +0.00499 | +10.57% |
| April | ge12 | 0.01628 | 0.02366 | +0.00738 | **+45.31%** |
| Jul | ge12 | 0.00889 | 0.00920 | +0.00030 | +3.42% |
| Aug | ge12 | 0.00835 | 0.00862 | +0.00027 | +3.21% |
| Sep | ge12 | 0.00741 | 0.00753 | +0.00012 | +1.60% |
| Pooled | ge10 | 0.04252 | 0.04490 | +0.00239 | +5.61% |
| Pooled | ge12 | 0.01191 | 0.01543 | +0.00352 | **+29.53%** |

(Full per-origin ge6/8/10/12 tables in the run manifest
`sensitivity_pooled.ladder` + `predictions.csv` columns
`ge{m}_60_/ge{m}_120_`.) Rare-event probabilities remain materially
dependent on the BF-tail support assumption, overwhelmingly through
April. Event counts are thin at the top: K>=12 observed 24/11/8/10
(Apr/Jul/Aug/Sep), 53 pooled - ge12 reliability claims will be noisy
regardless.

### Overflow mass (the driver of the April flag)

Mean P(N>=37) in the saved arm-B PMFs: April 0.02746 (max 0.11387;
1,439/2,046 rows >1%), Jul 0.00627, Aug 0.00445, Sep 0.00328, pooled
0.01512 (1,800 rows >1%). April's short pre-origin training produces
flat hazard tails -> large overflow -> the support assumption moves
April means (delta E[N] = +0.540).

### Artifact alignment: canonical identities CONFIRMED, zero residual

Two independent layers:

1. **Key layer (canonical):** every saved predictions.csv row carries
   (origin, game_pk, pitcher, game_date); all 4,446 joined exactly to
   the 2023 first-pitcher spine, game_date exact-match, saved PA ==
   recomputed terminal-PA count on every row.
2. **Positional layer (pmfs.parquet <-> predictions.csv):** every row's
   saved arm-B PMF reproduces BOTH saved functionals rps_B (max diff
   0.0) and q_B (1.1e-16). Equivalence-class audit: grouping all 4,446
   rows by (PA, q_B, rps_B) yields **4,446 distinct classes, max class
   size 1** - no two rows share the same functional fingerprint, so no
   permutation of pmf rows can reproduce the saved arrays. The
   positional pairing is uniquely pinned; there is NO residual identity
   ambiguity. (This is in addition to the writer-code provenance: both
   artifacts were written from the same in-memory frame in one process
   by the committed, sha-recorded training-policy runner.)

## 2. Dispersion diagnostic: corrected benchmark

The scored-run diagnostic compared observed count variance against
`n_C1 * p_bar * (1 - p_bar)` - a FIXED-N binomial benchmark. That is
the wrong benchmark for a BF mixture: workload uncertainty itself adds
variance. Under the model (law of total variance, fixed p):

  Var(K) = p(1-p) E[N] + p^2 Var(N).

Recomputation from the saved artifacts (descriptive only; no
recalibration, no new gate):

| Slice | observed Var(K) | mixture benchmark | obs/mix | fixed-N benchmark | obs/fixedN |
| --- | --- | --- | --- | --- | --- |
| Pooled | 6.5761 | 5.3430 | **1.231** | 3.8225 | 1.720 |
| Apr | 6.4370 | 5.8751 | 1.096 | 3.8806 | 1.659 |
| Jul | 7.0059 | 4.9915 | **1.404** | 3.8373 | 1.826 |
| Aug | 6.0451 | 4.8593 | 1.244 | 3.7546 | 1.610 |
| Sep | 7.0190 | 4.8300 | **1.453** | 3.7350 | 1.879 |

By p_bar band (pooled), splitting observed variance into mean predicted
mixture variance + within-band mean-mixing + residual:

| Band | n | obs | obs/mix | mean-mixing | residual (obs - mix - mixing) |
| --- | --- | --- | --- | --- | --- |
| [0,0.18) | 317 | 3.788 | 0.965 | 0.120 | -0.257 |
| [0.18,0.21) | 1,242 | 5.237 | 1.134 | 0.218 | +0.399 |
| [0.21,0.24) | 1,794 | 6.280 | 1.204 | 0.502 | +0.564 |
| [0.24,0.28) | 785 | 6.704 | 1.043 | 0.310 | -0.033 |
| [0.28,1] | 308 | 7.161 | 0.929 | 0.308 | -0.852 |

Corrected interpretation:

- The original "1.21x-1.67x underdispersion" was mostly an artifact of
  the fixed-N benchmark. Against the model's OWN mixture variance the
  residual excess is **+23% pooled**, and it is NOT uniform: two bands
  are at or BELOW 1.0, and the excess concentrates in the middle band
  and in the July (+40%) and September (+45%) origins - the same
  origins where the BF-lane underprediction (q-gap) persists.
- This pattern is consistent with **origin-level mean miscalibration
  inherited from the BF lane**, not with generic Bernoulli-independence
  failure. Known batter heterogeneity would NOT widen the distribution
  (a Poisson-binomial at the same mean has variance <= binomial), so
  the residual is more plausibly shared latent rate variation,
  workload-dependence, or miscalibration - mechanisms to be separated
  BEFORE any beta-binomial v2.
- Note on the benchmark's numerics: the mixture variance here uses the
  BF mixture identity (exact) rather than the truncated count PMF (the
  absorbing >=23 bucket would understate tail variance negligibly; the
  two agree to <0.1% on these artifacts). Within-band mean-mixing is
  accounted separately above and is small (0.12-0.50 absolute).
- Status: descriptive clarification ONLY. No recalibration, no
  beta-binomial fitting, no new pass/fail gate.
