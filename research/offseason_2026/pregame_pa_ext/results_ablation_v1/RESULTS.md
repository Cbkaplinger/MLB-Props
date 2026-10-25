# RESULTS — feature-set ablation v1 (real data, dev blocks, walk-forward)
# (2026-10-22; model metrics ONLY per owner order - the market gap is
#  never used for selection)
#
# CORRECTION (2026-10-22, final): the count-RPS column below was
# computed on a SMALL, SKEWED subset - starts where all NINE projected
# batters happened to record a realized PA (117/2,314 + 160/2,509 =
# 277/4,823, 5.7%). The 1.29880/1.28419 figures cited in an interim
# report were WITHDRAWN (they were sourced from the invalid 4,477-key
# lineup diagnostic, not this ablation).
# CANONICAL count-RPS on the INTENDED cohort (all 4,823 eligible
# starts, ledger-projected nine slots, same fits/settings; committed
# runner ablation_count_rps.py, write-once bundle
# ablation_count_rps_canonical_v1/): PITCHER-only 1.33354, FULL
# 1.31602 - FULL beats PITCHER-only by -0.0175 (paired CI
# [-0.0252, -0.0097]). Chat 2's independent reproduction: 1.33457 /
# 1.31744 (same direction; ~0.001 delta vs the canonical bundle
# pending reconciliation via the published per-start outputs). The
# frozen binary's registered 1.31761 is reported alongside; claiming
# improvement over it requires identical keys + a paired estimate
# (not yet established). The "batter features hurt the count layer"
# finding is RETRACTED as an artifact of slot coverage. The
# multiclass and K-marginal log-loss columns (all eval PAs, 82,817)
# stand unchanged.

Setup: train = 2023-01-01..(block train_end - 60d), eval = the
registered dev starts' pitcher-matched PAs (82,817) per block;
model family = the registered StandardScaler + multinomial
LogisticRegression(C=1.0); one pre-declared score per layer.

| set | multiclass LL | K-marginal LL | count-RPS |
| --- | --- | --- | --- |
| LEAGUE (class frequencies) | 1.23756 | 0.52042 | 1.46914 |
| PITCHER (5 pitcher-side) | 1.23192 | 0.51550 | **1.32294** |
| FULL (frozen 8) | 1.22305 | 0.50733 | 1.34526 |
| FULL, EW half-life 30d | 1.22325 | 0.50752 | 1.34675 |
| FULL, EW half-life 60d | 1.22310 | 0.50738 | 1.34644 |
| FULL, EW half-life 90d (registered) | 1.22305 | 0.50733 | 1.34526 |
| FULL, EW half-life 180d | 1.22303 | 0.50728 | 1.34103 |

## Readings

1. PITCHER features carry most of the per-PA gain
   (1.23756 -> 1.23192); the three batter features add a further
   0.0089 multiclass LL (1.23192 -> 1.22305).
2. **The EW half-life is a dead lever**: 30/60/90/180 span 0.0002
   multiclass LL (EW180 marginally best by 2e-5 = noise). The
   registered 90d choice stands; do not tune it.
3. **Count-RPS ordering INVERTS the log-loss ordering**: PITCHER-only
   (1.32294) beats FULL (1.34526) on the count distribution while
   losing on per-PA log loss. All multinomial variants are worse on
   count-RPS than the frozen binary count layer (1.31761 from the
   registered run) - consistent with M0's finding that the four-class
   K marginal adds nothing at the count level.
4. Selection by model metrics: the frozen FULL set is confirmed for
   per-PA probability work; PITCHER-only is the better count-layer
   arm. No new features are adopted by this ablation.
