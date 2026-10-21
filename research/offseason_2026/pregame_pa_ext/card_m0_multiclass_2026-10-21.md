# PRE-REGISTRATION CARD (DESIGN ONLY) — M0: multi-class PA outcome model
# (pregame-pa-ext-v2 lane, 2026-10-21)
#
# STATUS: PROPOSED DESIGN — NOT IMPLEMENTED, NOT EXECUTED, NO REAL OUTCOMES
# READ. This card specifies the design for expanding the PA-level model
# from binary strikeout to multi-class outcome prediction. Implementation
# requires Chat 2 review of this card plus explicit owner authorization.
# The decision-flip diagnostic (card_decision_flip_2026-10-21.md) must be
# reviewed before this card proceeds.

## 1. Motivation

The current model predicts a binary outcome: strikeout or not. The
question is whether modelling the FULL outcome taxonomy (strikeout, walk,
ball-in-play subtypes) improves the count distribution through better
per-PA probability structure, without sacrificing the K marginal.

## 2. Outcome taxonomy mapping from Statcast events

The frozen pa_table carries `y` (1 = strikeout event, 0 = otherwise) and
the raw Statcast `events` field maps to the following TAXONOMY (the
multi-class labels):

| class | label | Statcast events mapped |
| --- | --- | --- |
| 0 | strikeout | strikeout, strikeout_double_play |
| 1 | walk_or_hbp | walk, intentional_walk, hit_by_pitch, catcher_interf |
| 2 | field_out | field_out, force_out, fielders_choice, fielders_choice_out, field_error, runner_double_play, other_out, sacrifice_bunt, sacrifice_bunt_double_play, sacrifice_fly, sacrifice_fly_double_play, triple_play |
| 3 | hit | single, double, triple, home_run, ground_rule_double |
| 4 | caught_stealing_or_pickoff | caught_stealing, pickoff_1b, pickoff_2b, pickoff_3b, caught_stealing_picked_off |

Classes 0 and 1 are outcome-independent (pitcher/batter interaction
without a batted ball). Class 2 and 3 depend on defence and ballpark
(acknowledged limitation). Class 4 is a baserunner event, not a PA
outcome in the traditional sense but IS recorded by Statcast as a
pitch-level event.

CLASSIFICATION: class 0 (strikeout) is the same target as the frozen
binary model. Classes 1-4 are the non-K outcomes that the binary model
collapses into a single 0.

## 3. Features (unchanged from L3/H3)

Same 8 features as the frozen FEAT_H3: p_pitcher_prior_w150,
p_batter_prior_w150, lg_rate, n_prior_pitcher, n_prior_batter,
cold_start, ew_pitcher, ew_batter. No new features. Same as-of
construction. Same strictly-prior cutoff.

## 4. Model family (same as the frozen recipe)

StandardScaler + LogisticRegression(C=1.0, max_iter=1000) adapted to
multinomial (softmax) on the 8 features. The model family is unchanged;
only the output changes from binary sigmoid to multinomial softmax.
Per-class calibration (Platt scaling) is applied post-hoc if the raw
softmax probabilities are miscalibrated for any class (pre-declared:
apply per-class sigmoid calibration on the calibration sub-block, same
as the frozen recipe's CAL convention).

## 5. Fit and evaluation blocks

Same as the frozen recipe: per dev block (block_2024H2, block_2025H1),
train = realized PA rows from 2023-01-01..block cal_first, cal =
last 60 days before train_end. Same training-row lineage (frozen recipe's
realized-PA fit lineage with original PA identity). confirm_2025H2
protected. The population is the same 4,823 eligible dev starts.

## 6. Primary endpoints (Holm m=2)

### Endpoint 1: K marginal non-inferiority

The multi-class model's implied K probability — P(class 0 | features) —
must be NON-INFERIOR to the frozen binary model's K probability on the
82,817 dev evaluation PAs (same keys, same frozen ledger).

- Non-inferiority margin: the multi-class K probability's log loss must
  be no worse than the binary model's log loss + 0.005 (a pre-declared
  tolerance that allows minor degradation from the multi-class output
  structure while ensuring the K signal is not lost).
- Test: paired log-loss difference (binary K from the multi-class
  softmax P(class=0) vs the frozen binary model's K probability).
  Paired slate-date bootstrap n=2000 seed 20261001.
- PASS: the upper bound of the 95% CI on the delta is < +0.005.
- FAIL: the upper bound is >= +0.005 -> the K marginal is inferior ->
  STOP.

### Endpoint 2: count-RPS improvement

The multi-class model's count distribution (converting the multi-class
PA probabilities to count distributions via the registered aggregation)
must IMPROVE count-RPS over the binary + registered aggregation.

- The multi-class count distribution: for each BF slot, the probability
  of a strikeout is P(class=0); the count PMF uses the same registered
  aggregation but with the multi-class-implied K probability.
- Test: paired count-RPS difference (multi-class vs the frozen binary
  + registered aggregation), same paired bootstrap machinery.
- PASS: the point estimate favours the multi-class model (delta < 0).
- FAIL: the point estimate favours the baseline or is indistinguishable
  -> no count-layer improvement -> close.

### Holm m=2

Both endpoints are tested simultaneously; Holm step-down at family level
0.05 across the TWO pre-declared contrasts. If either endpoint fails,
the candidate is closed.

## 7. Per-class calibration handling for rare classes

Rare classes (class 4: caught_stealing_or_pickoff; and to a lesser
extent class 3: hits) have very few training observations. The approach:
- Report per-class training counts in the receipt.
- If a class has < 50 training PAs in a block, flag it as SPARSE in the
  receipt; the per-class calibration must use the pooled calibration
  set (not per-class) for sparse classes.
- If any class has 0 training PAs, the model is invalid for that class
  and the STOP condition triggers (the taxonomy is too granular for the
  available data; a coarser taxonomy would need a new card).

## 8. Stop condition

- If the K marginal (endpoint 1) FAILS non-inferiority: STOP. The
  multi-class model loses too much K signal. No further evaluation.
- If any class has 0 training PAs: STOP (taxonomy too granular).
- If the count-RPS (endpoint 2) shows no improvement: CLOSE the
  candidate; the frozen binary + registered aggregation stands.
- If BOTH endpoints pass: report the result as a development-only
  diagnostic. No promotion without the separate gate.

## 9. Provenance requirements

Same as the batter-history diagnostic: immutable receipt_initial.json
written FIRST, receipt_final.json chained by sha256, consumed/context
input classification, write-once outputs, failure records preserved,
no in-place repair.

## 10. Synthetic tests required (before any real-data use)

- Taxonomy mapping correctness: synthetic PA rows with known Statcast
  events map to the correct class labels.
- Normalization: multi-class softmax probabilities sum to 1 per PA.
- Non-inferiority machinery: the paired log-loss delta computation and
  bootstrap are correct.
- Per-class calibration: the sigmoid calibration recovers known
  synthetic calibration curves.
- Sparse-class handling: classes with < 50 PAs are flagged.
- Block isolation: confirm_2025H2 never enters training or evaluation.
- Receipt completeness: all mandatory sections present.
