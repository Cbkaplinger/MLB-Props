# Morning vs near-close v2 — tie-determinism rescore (2026-10-24, latest)

## Corrected v1/v2 interpretation

The tie-break repair moved BOTH markets' numbers, in OPPOSITE directions:

| market | n | v1 market LL | v2 market LL | movement | changed starts |
| --- | --- | --- | --- | --- | --- |
| morning | 2,109 | 0.688296 | 0.687856 | **improved by 0.000440** | 5 (line changed) |
| near-close | 2,109 | 0.689012 | 0.689300 | **worsened by 0.000288** | 12 (line changed) + 10 (same line, price changed) |

Model LL also moved (0.710815 → 0.710208 morning; 0.711959 → 0.711985
near-close) because the model's P(K>line) is evaluated at each market's
own line — when the line changes, the model's probability at that new
line changes too. The model's per-PA probabilities themselves are
unchanged (the frozen model was not touched).

## Tie-fix accounting

| count | value |
| --- | --- |
| conflicting groups (same start/book/line/side/timestamp, different prices) | 26 |
| removed quote rows | 26 (one per conflicting group) |
| affected scored starts (morning) | 5 |
| affected scored starts (near-close) | 22 (12 line changed + 10 same-line price changed) |
| earlier-quote fallback | none (the tie rule drops conflicting rows rather than falling back) |

## Changed starts detail

### Morning (5 starts)

| game_pk | side | pitcher | line (v1→v2) | p_over (v1→v2) |
| --- | --- | --- | --- | --- |
| 777623 | Bot | 593958 (Misiorowski) | 3.5→4.5 | 0.5915→0.4142 |

(4 more listed in the full parquet.)

### Near-close (22 starts, top 8 by magnitude)

| game_pk | side | pitcher | line (v1→v2) | p_over (v1→v2) |
| --- | --- | --- | --- | --- |
| 777765 | Bot | 666200 | 5.5→6.5 | 0.5903→0.4434 |
| 777348 | Bot | 684007 | 4.5→3.5 | 0.4087→0.5926 |
| 778060 | Bot | 669160 | 4.5→3.5 | 0.4007→0.5939 |
| 777655 | Bot | 608372 | 4.5→3.5 | 0.4085→0.5750 |
| 777858 | Bot | 676467 | 4.5→3.5 | 0.3768→0.5387 |
| 778230 | Bot | 666157 | 5.5→4.5 | 0.4350→0.6005 |
| 777397 | Bot | 687473 | 5.5→4.5 | 0.4184→0.5633 |
| 778352 | Top | 606996 | 5.5→4.5 | 0.4432→0.6297 |

## Final consensus-line tie-break specification

The consensus line is selected by:
1. Filter to (start, line) groups where at least one book quotes BOTH
   bet sides near close.
2. Choose the line with the MOST two-sided books.
3. Ties broken by the line closest to the median quoted line.
4. Ties on median distance broken by the numerically LOWER line.

## Final quote-dedup tie-break specification

Within each (start, book, line, bet_side) group:
1. Latest quote_timestamp wins.
2. Equal timestamps: the numerically HIGHER price wins (explicit
   total order).
3. Conflicting tied records (same timestamp, different prices) are
   DROPPED AND COUNTED (never selected arbitrarily).

Both specifications are tested under shuffled input (10 seeds).

## Interpretation (corrected)

Both markets beat the frozen model on this cohort, at both v1 and v2
selection rules. The morning market improved slightly under the
deterministic tie fix; the near-close market worsened slightly. The
deficits remain ~0.023 in both cases — the conclusions are unchanged.
No informational-equivalence or statistically-equal-deficit claim is
made without the appropriate paired analysis.
