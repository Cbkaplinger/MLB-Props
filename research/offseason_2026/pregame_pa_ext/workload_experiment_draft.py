"""Workload personalization experiment draft (NOT EXECUTED).

W0: pooled league BF probabilities, using the same strictly-prior history
    policy as the existing bf-workload-v1 (all completed starts strictly
    before the forecast date, add-one smoothing over 37 categories,
    registered overflow/tail conversion).
W1: existing bf-workload-v1 pitcher-specific BF forecasts (unchanged).

Both arms share: identical PA probabilities (keyed forecast table from
the accepted baseline), identical projected lineups, identical assessment
starts (registered 2,509 cohort), identical count aggregation (24-bucket
support), and identical scoring (kc.count_rps).

The ONLY difference between W0 and W1 is whether the per-start BF
probability vector is pitcher-specific (W1) or pooled from the training
population (W0). History policy, cutoff rule, smoothing, support, and
tail conventions are symmetric by construction.

Primary contrast: delta = RPS(W1) - RPS(W0) per start on identical keys.
Negative delta favors pitcher-specific workload personalization.
Positive delta favors the pooled control.

Implementation sketch (using existing machinery):
  1. Read pa_table (y column) for the declared history window
     (2023-01-01..assessment_start per start).
  2. Compute pooled empirical BF37 from all strictly-prior training rows
     (add-one smoothing over 37 categories, registered tail conversion).
  3. Compute pitcher-specific BF37 from each pitcher's strictly-prior
     completed starts (>= 10 prior starts; else pooled fallback).
  4. Feed W0-pooled and W1-pitcher BF37 vectors through the SAME
     keyed forecast table's p_k values and kc.combine_count machinery.
  5. Score both arms with kc.count_rps on the registered cohort.
  6. Paired contrast via bl.paired_contrast.

Status: DRAFT ONLY. Not executed. Requires explicit owner authorization
for real-data access to construct the pooled control from training rows.
"""
