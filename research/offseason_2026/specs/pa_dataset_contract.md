# PA dataset contract (frozen spec — audit §§W, AB, AA)

Converter: `statcast.plate_appearances` semantics (filter `events` not-null and
not in `NON_PA_EVENTS`; terminal = last by `pitch_number`; source
`src/Python/statcast.py:501-519`). No new converter code; funnel reuses it.

## Row contract

- PK `(game_pk, at_bat_number)` + observed `pitcher`, `batter` (never joined IDs).
- Target `is_k = events IN {strikeout, strikeout_double_play}`.
- Eligible: `is_pa` true; regular season (`game_type = R`); pitcher and batter IDs
  non-null; pitcher ∈ `pitcher_games` keys for that `game_pk` (starter population);
  game PA ≥ 9 for that pitcher (Q-D4 cohort); all features strictly `< PA start`
  (first-pitch time ordering; rolling uses game-date granularity + same-date
  first-collapse, never same-game rows).
- Exclusions: postseason/spring/exhibition; `NON_PA` outcomes; null terminal event
  (~0.06%/yr, quarantine); `truncated_pa` (~0.17%/yr, quarantine — not a completed
  PA); mid-PA pitcher/batter substitution (≤0.035%/yr, quarantine, never impute);
  unresolved IDs; opener/bulk/scratch games (out-of-scope family, pregame role
  flags decide before expansion).
- `field_error` (~0.6%/yr) counts as PA (batter reached). `PA=0` pinch remnants
  (15 rows total) excluded by the starter-game join.
- Required raw: `game_pk/at_bat_number/pitch_number/events/pitcher/batter/stand/
  p_throws/inning_topbot/game_date/home_team/away_team/zone/description/type`.
- Optional: velo/spin/IVB/HB/VAA/location/xwoba/delta_run_exp/hc_x.
- Availability ts: PA first-pitch; features `< ts`. Assertions: one terminal row
  per PA; IDs constant within PA; K from closed event set. Dup terminal → fail-loud.
  Missing terminal → quarantine. Versioning: `statcast pull manifest (files+hashes)
  + converter version` recorded on every dataset manifest.

## Funnel rules (report counts + overlap per rule, by season)

1 terminal event exists · 2 eligible PA (`is_pa`) · 3 K label assignable ·
4 pitcher ID valid · 5 batter ID valid · 6 game type regular ·
7 pitcher ∈ starter keys · 8 role passes (game PA≥9) ·
9 pre-PA pitcher history exists (`k_rate_P5` non-null; nulls kept, never dropped) ·
10 pre-PA batter history exists (`k_rate_std` non-null; nulls kept) ·
11 handedness known (`stand`, `p_throws` non-null) ·
12 projected lineup available (mode flag 1–4; ABSENT 2023–25 → mode 3/4 only) ·
13 nine slots valid · 14 odds/start eval match (joinable; coverage flag, not filter) ·
15 final populations: (a) all eligible training PAs, (b) odds-evaluable PAs.

## Cohort (Q-D4)

First population: `PA≥9` first-pitcher games only. Language conditional
("first pitchers who faced ≥9"). Bulks, opener-followers, resumed-suspended PAs
out of scope until pregame role labels exist. Bias note: excluded PA<9 K-rate
0.238 vs included 0.220 — metrics upward-selected; say so on every report.

## Rookie policy (Q-D1 default)

Expanding empirical-Bayes shrinkage at current strengths (batter 200 PA; FB 1000;
park 500) + missingness flags kept + live debut-flag contradiction fixed
(`prior_start_date.is_null() → is_season_debut=1`, rest nulls, never force 0).
Hand splits std-only (no short windows). Challenger: prior-season carry-forward
vs plain league fallback, tuned in 23–24 folds only. Falsifiers in audit §AB.

## League baseline (Q-D2)

Canonical: all-regular-season-MLB-PA (`is_pa`), both hands, all roles; expanding
cumulative strictly prior-date (DH-safe) + prior-completed-season scalar fallback
(current value 0.2238). Overall only — hand/slot/pitch-type priors separate.
HR/FB league and park factor stay separate (different denominators). Scored-subset
globals (ladder_sim/v4) research-only, never train/serve.
