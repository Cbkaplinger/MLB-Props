# I4 prior-starting-card source experiment - FROZEN (2026-10-08)

> **Status: FROZEN 2026-10-08** (owner-authorized bounded sequence:
> acquisition -> validation -> ONE scored run, conditional on mapping
> readiness; BLOCKED + return if correspondence cannot be verified).
> Benchmark = the recorded I3b developmental form
> (see `i3-closeout-2026-10-08.md` section 3).

## Question

Does the previous game's **actual starting card** (batting slots
1..9 from Retrosheet start records) improve the count-layer forecast
over the frozen **FIRST-NINE-OBSERVED-BATTER PROXY** (I3b), with
everything else held fixed?

- This improves the historical FALLBACK card only. It does NOT make
  today's lineup historically known at 8am, does NOT establish
  announced-lineup value, and carries the existing availability
  limitations (date-granular clock, realized-starter identity).
- **No verified-8am or announced-lineup claim** (frozen wording).

## Arms (identical rows: the 4,446 eval pitcher-games)

| Arm | Opportunity source | Count structure |
| --- | --- | --- |
| **I3b (benchmark, frozen)** | first-nine-observed proxy, prior-calendar-day game | homogeneous at p* |
| **I4** | previous completed game's actual starting slots 1..9 (Retrosheet `start` records; substitutes excluded; non-batting pitcher slot excluded) | homogeneous at p*_I4 (same p* formula) |

Held FIXED: saved BF PMFs (no refit), log5/rate tables (w=150,
strict pre-origin pools), survival weighting, homogeneous count
structure, support/cap conventions, scoring, bootstrap, and
evaluation identities. The ONLY change is the card source.

- Missing/failed mapping -> frozen fallback to the I3b proxy card
  for that row, flagged (never silent, never outcome-based).
- Primary: paired count-RPS I4 - I3b, date-clustered bootstrap 2,000 /
  seed 20261001, CI entirely below 0 = pass.
- Reported alongside: source coverage (%), changed cards (% of rows
  where I4 card differs from proxy card), rate changes (mean |p*_I4 -
  p*_proxy|), staleness distribution, per-origin scores, milestone
  Brier 6/7/8/9/10/12, cap-120 sensitivity, log-floor counts,
  provenance hashes.

## Acquisition request (narrowly scoped - NO data fetched)

| Item | Specification |
| --- | --- |
| Source | Retrosheet event files ("event" archives), regular seasons **2022 and 2023 only** (previous-game cards for April 2023 rows can point into late 2022; no offseason play). Start + sub records carry batting positions and game-number identifiers. |
| Size estimate | ~60 team-season event files, on the order of 5-20 MB compressed total (verify at download; small relative to the odds lake). |
| Licensing / attribution | Retrosheet's standard license: free for research use WITH the required attribution notice; no commercial resale. Attribution file to be committed alongside the raw archive. |
| ID mapping | Players: Retrosheet ID <-> MLBAM ID via the **Chadwick person register** (already on the approved external-research list; small CSV). Verify mapping coverage on the 2023 card population; report unmatched counts (fallback applies). |
| Game mapping | Retrosheet game id `{HOME3}.YYYYMMDD{0,1,2}` -> MLB `game_pk` via (home team, date, game-number) matched against the Statcast schedule. **Verification requirement: report the exact 2023 match rate; the doubleheader game-number -> game_pk ordering correspondence must be VERIFIED against the schedule, not assumed** (the I3 tie-break used larger game_pk; Retrosheet uses explicit game numbers 1/2). Suspended games: use Retrosheet's recorded bookkeeping date; any ambiguity -> fallback + flag. |
| Storage | `data/Retrosheet/raw/{season}/` + sha256 manifest; raw files are source of truth (re-parseable). |
| Exclusions | None outcome-based. Card eligibility = prior completed game with 9 valid batting slots; otherwise frozen fallback. |

## Synthetic tests (before any scored run)

1. Parser: `start`/`sub` records -> ordered slots 1..9; substitutes
   never displace an earlier start slot in the CARD (they enter only
   via `sub` records and are excluded from the starting card);
   non-batting pitcher slot never appears (2022-23 universal DH -
   assert no pitcher id among slots).
2. Doubleheader handling: game-number ordering drives "most recent
   prior game"; same-day other DH game excluded (calendar-strict rule
   unchanged).
3. ID mapping: Chadwick crossover completeness on synthetic mixed-ID
   populations; unmapped -> fallback + flag (no silent drops).
4. Fallback chain: missing mapping / <9 valid slots -> I3b proxy card
   + flag; leak test (perturbing same-date rows cannot change any
   card); provenance hash discipline identical to I3.
5. Parity structure: p*_I4 computed with the SAME survival weighting;
   latent E[K] parity not needed here (both arms homogeneous), but
   the p* formula and count structure must be byte-identical to I3b.

## Blockers / disclosed limitations

1. Acquisition requires owner authorization (request above; nothing
   fetched yet).
2. A true starting card is still not an announced pregame lineup;
   the card-informed-average mechanism remains a hypothesis
   (closeout section 2).
3. If I4 changes scores, the change may come from either better
   cards OR from removing proxy-specific signals - the experiment
   reports changed-card overlap to help attribute this, but full
   attribution may require the prospective logger.
