# I5 deep-tail challenger - FROZEN (2026-10-08)

> **Status: FROZEN 2026-10-08** (owner-authorized ONE scored run).
> Benchmark = I3b (recorded developmental benchmark). Informed by
> `bf-origin-tail-audit-2026-10-08.md` (sections 7 = owner corrections).
> AUDIT-INFORMED DEVELOPMENTAL SELECTION on 2023 - no production or
> independently validated claim.
>
> **Owner clarifications frozen:** (a) the receiving interval 30..33
> was SELECTED DURING DEVELOPMENT (April's training max is 30; 33 is
> supported by later training pools - 33 is NOT independently
> determined from April's available data); per-origin redistribution
> weights use only strict-pre-origin counts; April has ONE qualifying
> training event (very weak basis for a tail shape - disclosed).
> (b) **each row's canonical I3b p* remains FIXED** - only the BF PMF
> changes; recomputing p* under the modified BF PMF is a legitimate
> LATER integration choice and is NOT done silently here. (c)
> Existing body mass at BF 34..36 is retained. (d) The empty-tail
> fallback (retain I3b geometric tail + flag) remains frozen.

## 1. Question

Does replacing the geometric-tail overflow handling with a
training-empirical reassignment of the deep-tail mass improve the
count forecast - specifically its deep-position body and ladder
probabilities - versus the frozen I3b benchmark?

## 2. Training-tail evidence (strictly pre-origin, 2023 hazard-fit
population ONLY - 2022 enters the BF lane via history features, never
as hazard-fit rows; pool definition matches the training-policy
manifest counts)

| Training pool | n | max N | N>=30 | N>=33 | N>=35 | N>=36 | N>=37 | slot counts 30..36 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| < 2023-04-15 | 414 | **30** | 1 (0.24%) | 0 | 0 | 0 | 0 | [1,0,0,0,0,0,0] |
| < 2023-07-01 | 2,460 | **33** | 30 (1.22%) | 2 | 0 | 0 | 0 | [12,9,7,2,0,0,0] |
| < 2023-08-01 | 3,194 | **33** | 40 (1.25%) | 2 | 0 | 0 | 0 | [19,10,9,2,0,0,0] |
| < 2023-09-01 | 4,016 | **33** | 57 (1.42%) | 4 | 0 | 0 | 0 | [30,13,10,4,0,0,0] |

- **Zero training games at N>=35 in every origin; N>=36/37 = 0
  everywhere.** The frozen geometric tail spreads ~1.5% mass into
  37..60 - a region with no training support whatsoever.
- Sparse-cell disclosure: April's pool is 414 rows with ONE game at
  N=30; the weights are noisy estimates (see limitations).

## 3. Frozen challenger definition (ONE recipe; no tail-recipe search)

**I5-tail:** per row, take the saved 37-category arm-B BF PMF and
apply `kcount_combiner.reassign_overflow(pmf37, lo=30, hi=33,
weights)`, where weights = the strictly-pre-origin training empirical
counts at N=30,31,32,33 for that row's origin (table above,
normalized to sum 1):

| Origin | w(N=30) | w(31) | w(32) | w(33) |
| --- | --- | --- | --- | --- |
| Apr | 4/4 | 0 | 0 | 0 |
| Jul | 12/30 | 9/30 | 7/30 | 2/30 |
| Aug | 19/40 | 10/40 | 9/40 | 2/40 |
| Sep | 30/57 | 13/57 | 10/57 | 4/57 |

- Interval **[30, 33]** justified by training evidence alone: it is
  the deep interval with nonzero training mass whose upper end equals
  the training maximum (33). **Never chosen from any evaluation-origin
  maximum.**
- **Empty-tail fallback:** if an origin's interval contained zero
  training games, the frozen fallback is to RETAIN the I3b geometric
  tail for that origin + flag. (No origin triggers it here.)
- **Estimated transformation, not fit-free:** weights are estimated
  from 414-4,016 training rows per origin; April weights rest on ONE
  observed game (disclosed; no smoothing - the recipe is deliberately
  simple and frozen before scoring).

### Precisely which PMF/hazard quantities change

- Changed: extended-PMF entries at BF 30..33 (gain the overflow mass);
  entries BF 37..60 (become zero); implied hazards at BF 30..33
  (receiving positions); implied hazards at BF 34..60 (survivor mass
  gone -> zero). E[N] decreases; cap-120 sensitivity becomes moot for
  this arm (no mass beyond 33 under either cap).
- Unchanged: body mass at BF 1..29; original body mass AT the
  receiving positions (reassignment adds on top of it); the arm-B
  hazard FIT (no refit); K-count structure, p* form, scoring,
  identities.

## 4. Frozen evaluation (audit-informed developmental selection)

- Rows: the identical 4,446 eval pitcher-games; canonical artifact
  lineage (BF artifacts + I3b saved PMFs, reproduction asserted).
- **Primary: paired count-RPS (I5-tail - I3b), date-clustered
  bootstrap 2,000 / seed 20261001; CI entirely below 0 = pass.**
- Secondary (prespecified): BF-lane RPS on the same rows (BF support
  1..36+overflow vs I3b's handling); **mean-BF bias** (bias =
  predicted - actual; reported with both means; positive =
  overprediction); short-outing calibration (P(N<9) predicted vs
  observed, pooled + per origin); K>=10 and K>=12 reliability
  (predicted vs observed frequencies + event counts) and their
  ABSOLUTE probability changes under I5; log-score floor counts;
  cap-120 sensitivity becomes moot (documented, not tuned).
- Interpretation ceiling: this is an audit-informed developmental
  selection on 2023 - no production claim, no independent validation.

## 5. Tests (all green before scoring)

Implemented in `kcount_combiner.reassign_overflow` +
`tests/test_kcount_combiner.py` (18 green):
mass conservation to 1e-12; nonnegativity; overflow bucket zeroed;
receiving-position gains = overflow x normalized weight; body 1..29
untouched; CDF monotonicity; E[N] strictly decreases with bounded
drop; exceedance non-increase at m>=30 (ladder monotonicity); weight
and interval validation errors. Runner-level: strict training cutoff
(weights frozen per origin from pre-origin pools), empty-tail
fallback flag, unchanged row identities (kc_row/pred_row_idx
lineage), provenance hashes (contract, code, BF/I3 artifacts,
inputs).

## 6. Limitations (disclosed)

1. April weights rest on ONE training game at N=30 - high estimation
   noise; the recipe is frozen anyway (simple, prespecified).
2. Zero observed N>=37 in EVAL does not identify the true tail as
   zero (rule-of-three ~0.067% illustrative bound); the challenger
   REMOVES unsupported mass per the frozen assumption - a modeling
   choice, not an identified fact.
3. One eval row reaches N=34 (September) - outside the training
   support; I5 assigns it zero BF-side mass above 33 (K-side impact
   bounded by the count structure).
4. 2023 developmental throughout; transfer/prospective evidence
   required before any production claim.
