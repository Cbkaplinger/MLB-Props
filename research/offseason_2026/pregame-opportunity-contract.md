# Pregame lineup/opportunity contract - FROZEN (2026-10-08)

> **Status: FROZEN 2026-10-08** (owner-authorized ONE scored I3 run,
> labeled a CHRONOLOGICAL FALLBACK DIAGNOSTIC). 17 frozen conventions.
> Reuses the prior feasibility findings; NO new archive search performed.

## Forecast cutoff and clocks

- **Cutoff: 08:00 America/New_York on game day** (the existing ET
  convention; 12:00Z EDT / 13:00Z EST). Storage: UTC tz-aware; display
  and scheduling: America/New_York; labels ET/EST/EDT.
- Everything a deployable arm uses must be knowable at this cutoff.
  Anything first known after the cutoff is category C or D below.

## Evidence categories (owner's A/B/C/D separation)

| Cat | Definition | What we actually have |
| --- | --- | --- |
| **A. Historically timestamp-verified inputs** | Announced lineups with a provable as-of time, for past seasons | **NONE for 2023-2025.** Prior investigation (`docs/reference/lineup_train_serve.md` 2026-07-28; `specs/pa_dataset_contract.md` funnel rule 12 "projected lineup available (mode flag 1-4; ABSENT 2023-25)"; `experiments/tree_pa/lineup_replay_audit.json` lane C "availability-unverified") found no multi-year timestamped announced-lineup archive. No concrete new lead; no new search performed. |
| **B. Deployable historical fallback assumptions** | Strictly-prior inputs reconstructable from approved data that APPROXIMATE the card, labeled as assumptions | (B1) FIRST-NINE-OBSERVED-BATTER PROXY: the first nine distinct batters (first-PA order) observed for the team in its last completed game strictly before the cutoff - knowable at the cutoff by construction; assumptions = order persists AND observed nine approximates the card (substitute contamination possible). (B2) league-average batter (= current L1, already scored). (B3) team aggregate (= L2, already non-separated). |
| **C. Realized-lineup diagnostic inputs** | Actual batters faced / actual order (postgame reconstruction) | Available from Statcast (`is_initial_lineup` proxy). NEVER deployable evidence; oracle/diagnostic labeling only (as C2). |
| **D. Future prospective capture** | Going-forward logged announced lineups with as-of timestamps | RotoGrinders announced order (projected + confirmed) already flows via `Python.daily_lineups` -> `live_assembly`, MLB-ID-resolved; the projection log records `lineup_source`. **New requirement: persist (team, game_pk, order, IDs, as_of UTC ts, projected/confirmed status) to a research lineup table from now on.** |

## Contract fields (per team-game)

- `game_pk`, `team`, `game_date`; `as_of_ts` (UTC, category D only);
  `status` in {projected, confirmed, proxy_fnob, fallback_B2};
  `source`; `slot_1..slot_9` = MLB numeric batter IDs in batting order;
  `n_slots_valid`; DH/EH handling (slot 10 permitted when carded;
  repeated trips cycle the order).
- **Missing-lineup fallback chain:** D confirmed -> D projected ->
  B1 FIRST-NINE-OBSERVED-BATTER PROXY -> B2 (league average). Every
  fallback applied is recorded as a flag; never silently.
- **Strictly-prior player rates:** batter K rates from the frozen PA-K
  pools (w=150, first-pitcher PAs, `game_date < cutoff`); no same-game
  rows; cold start -> league rate (prior_n=0), unchanged.
- **Repeated trips through the order:** opportunity multiset for n
  batters faced = order positions cycled 1..9 repeatedly; heterogeneous
  per-batter p_j handled by a Poisson-binomial over that multiset.
- **Substitutions/uncertainty:** v1 treats the card as deterministic
  for the slots it covers; uncovered probability mass (injury unknowns)
  stays with the fallback flag - NOT modeled as a mixture in v1
  (declared limitation).
- **Starter/role limits:** first-pitcher population only (Q-D4: game
  PA>=9 cohort); openers/bulk followers out of scope until pregame
  role labels exist (unchanged from the PA-K lane).

## I3 readiness pass (2026-10-08, owner round 2 - definitions frozen,
## scored run NOT yet authorized)

### I3b corrected (composition-only comparator)

I3b = homogeneous-probability BF mixture with

  p* = (sum_t S(t) * p_t) / E[N],   S(t) = P(N >= t),

where p_t is I3a's ordered per-opportunity probability and E[N] is the
mean of the same extended BF PMF. I3b therefore uses the same BF PMF
and `combine_count(ext, p*)`. Its expected K equals I3a's E[K] =
sum_t S(t) p_t **by construction**; the runner asserts parity within
1e-12. An unweighted nine-player average is NOT used and does NOT
prove mean parity (early slots get more encounters; the unweighted
average changes expected K).

### B1 resolved: nine batting slots

- The card for a pitcher-game = the opposing team's **first nine
  distinct batters in first-plate-appearance order** from that team's
  most recent game **strictly before the game's calendar date**
  (prior-calendar-day strict rule; same-day doubleheader games are
  NEVER used as the card source - 70 same-day team-game pairs exist in
  2023 and are excluded).
- Slot order = first-PA order (the documented Statcast proxy; no
  historical carded-slot field exists). This proxy can include an
  early substitute replacing a starter - disclosed contamination,
  measurable later against category-D captures.
- DH handled naturally (the batting side's batters, up to 9 distinct).
- Coverage measured on the 4,446 scored rows (read-only audit):
  **100% have a prior-day-or-earlier opposing-team game** (0 B2
  fallbacks); staleness mean 1.18 days (85.0% 1-day, 13.7% 2-day,
  0.7% >3-day, max 6 days); card extractable in 4,860/4,860 2023
  team-games (>=9 distinct batters each).
- First game of season: team's most recent PRIOR game (possibly prior
  season) or B2 league-average if none exists in the approved inputs.
- **No bench substitution simulation** (owner preference, frozen).

### Cutoff audit: clock compatibility (measured + reasoned)

- The saved BF pipeline runs on a **DATE-granular clock** (features
  from games strictly before the eval date), not a verified 8am ET
  clock. 124 of the 4,446 eval games fall ON an origin date; their
  features exclude all same-date games by construction.
- Cutoff-safe by construction: BF features (strictly prior dates),
  team identity (schedule field), rate tables (strictly prior dates),
  B1 cards (strictly prior dates).
- **Unverifiable historically (flagged):** (a) whether every
  prior-date game completed before midnight ET (late West Coast
  finishes, postponed/suspended games resumed later) - date-granular
  data cannot prove completion times; (b) starter identity - the spine
  uses the REALIZED first pitcher (reconstructed postgame), not the
  8am probable starter. Historical probable-starter availability was
  not established by the prior feasibility investigation.
- **Therefore the I3 run, if authorized, is labeled a CHRONOLOGICAL
  FALLBACK DIAGNOSTIC, not a verified historical 8am pregame
  forecast.** Making the lineup component cutoff-safe does not make
  the whole pipeline verified-8am. Category-D prospective capture
  remains the path to a verified pregame clock.

### Arm definitions (frozen, pending scored-run authorization)

| Arm | Exposure | Opportunity model | Deployable |
| --- | --- | --- | --- |
| I1 (frozen benchmark) | saved arm-B BF PMF | homogeneous p_bar (L1), unchanged | yes |
| **I3a** | saved arm-B BF PMF | ordered Poisson-binomial over B1 card slots (per-batter log5 p_j, cycled order, starter faces slot 1 first) | yes (assumption-labeled) |
| **I3b** | saved arm-B BF PMF | homogeneous binomial at p* (expected-K parity with I3a asserted) | yes (assumption-labeled) |
| C2 (unchanged) | realized N | realized lineup | NO - diagnostic |

Primary comparison: **I3a - I1** pooled paired count-RPS (date-
clustered bootstrap 2,000 / seed 20261001; CI entirely below 0 = pass).
Secondary: I3a - I3b (composition/ordering shape at equal expected K).
Retained unchanged: milestone Brier 6/7/8/9/10/12, log-score floor
accounting, cap-120 sensitivity (April tail warning carried forward),
dispersion diagnostics, provenance guard, canonical row identity.

### Implementation + tests (this readiness pass)

- New pure module `research/offseason_2026/lineup_opportunity.py`:
  survival S(t) from the extended BF PMF; ordered opportunity sequence;
  incremental Poisson-binomial prefix DP with the absorbing >=23
  bucket; BF mixture over ordered prefixes; p* comparator; card
  builder (first-9 distinct, first-PA order, fail-loud).
- `tests/test_lineup_opportunity.py`: PB-equal-probs identity vs the
  frozen binomial path; mass conservation; uniform-seq mixture identity
  vs `combine_count`; p* parity; survival monotonicity; card
  ordering/substitute/fail-loud behavior; unweighted-average != p*
  demonstration.

## I3 scored-run freeze amendments (owner round 3, 2026-10-08)

13. **Naming (frozen):** B1 is the FIRST-NINE-OBSERVED-BATTER PROXY -
    the first nine distinct batters observed (first-PA order) in the
    opposing team's most recent prior-calendar-day game. It is NOT a
    verified set of starting batting slots and NOT an announced
    lineup. Substitute contamination (an observed first-nine may
    include an early replacement) and prior-date completion
    limitations are carried into the arm name, manifest, and report.
    "No carded-slot field" means: none in the CURRENTLY APPROVED
    inputs (Statcast). Retrosheet event files distinguish starting
    players from substitutes and carry batting-order positions - a
    future source for better previous-game card reconstruction
    (still no pregame announcement timestamps). Acquisition is NOT
    part of this run.
14. **Mean-parity assertion (frozen):** the parity tested is on the
    LATENT FULL-COUNT mean: E[K]_I3a = sum_t S(t) p_t and
    E[K]_I3b = p* * E[N]; asserted equal within 1e-12. The mean of
    the categorical count representation with the absorbing >=23
    bucket valued at exactly 23 is NOT the parity object - bucket 23
    is tail mass P(K>=23), not exactly-23 strikeouts.
15. **Per-row cutoff disclosure (frozen):** for every scored row the
    runner records the actual opponent-card game_date and the
    rate-estimation origin. Player rates keep the EXISTING strict
    pre-ORIGIN policy (unchanged). Card identities may be newer than
    the rate origin (a game between origin and game_date supplied
    the card) - that is knowable pregame and is allowed; the runner
    reports the count and distribution of card_date > origin rows.
16. **Descriptive diagnostics (frozen definitions + seed):**
    Randomized PIT: U = F(K-1) + V * P(K), V ~ Uniform(0,1),
    numpy default_rng(20261001); reported as a 10-bin pooled
    histogram per arm (I1, I3a) plus mean; descriptive only, never
    a gate. Dispersion: observed Var(K) vs the mixture benchmark
    p(1-p)E[N] + p^2 Var(N), pooled and per origin (law-of-total-
    variance form; the fixed-N binomial ratio reported alongside
    for continuity). Both computed once, never tuned.
17. **I3b-vs-I1 status:** exploratory comparison, reported but not
    gated (not preregistered as a pass/fail criterion).

### Synthetic-test plan (before any scored run)

1. Poisson-binomial DP: identical p_j reproduces `binom_pmf` exactly;
   mass conservation; absorbing-bucket convention identical to
   `combine_count`; order-cycled multiset construction (n mod 9
   boundary cases).
2. Heterogeneous sanity: variance(p_j mixed) <= variance(binomial at
   same mean) asserted on synthetic cases (Poisson-binomial property).
3. Fallback B1 builder: strictly-prior assertion (leak test: perturb
   same-date rows must not change the card); missing-team fallback
   chain order; flags recorded.
4. Runner integration: file-based end-to-end mirroring
   `test_kcount_runner.py` (synthetic artifacts, alignment guard,
   identity, sensitivity block, provenance rejection).

## Blockers (disclosed)

1. Category A empty -> the historical experiment tests a FALLBACK
   assumption (B1 proxy), not announced-lineup value; wording locked
   above.
2. B1 card for a team's first game of the season / after off-days uses
   its most recent prior game (possibly months old) - assumption
   flagged per row.
3. The dispersion residual (Jul/Sep concentration) remains unexplained;
   the I3 lanes do not address it - separate follow-up.
4. 2023 remains developmental; transfer/prospective evidence required
   before any production claim.
