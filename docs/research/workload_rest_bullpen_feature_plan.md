# Workload, rest, bullpen, and TBF feature plan

**Status:** Phase A + A.1 + B + C implemented; Phase D **interim policy frozen**
(`docs/research/phase_d_population_findings.md`) — pregame role labels still open  
**Date:** 2026-07-27  
**Priority:** after Step 7 freeze; primary home is projected TBF, not k-rate.  
**Phase A/B write-up:** `docs/research/tbf_spine_phase_ab.md`  
**First TBF fit:** `docs/research/tbf_first_model_findings.md`

This note captures lineup / batters-faced / rest / bullpen design so the ideas
survive across sessions. Implementation belongs on the **projected-TBF /
workload** track, not as ad-hoc dumps into the k-rate allow-list.

## What exists today

| Concept | Current behavior |
|---|---|
| Opposing offense | **Individual batters**, collapsed to lineup aggregates. Level 1 has per-batter games; Level 2 rolls each batter; Level 3 joins the opponent’s first nine (`is_initial_lineup`) and builds means / research order-weighted stats. **Not** team-wide roster rolls. |
| Starter TBF | Same-game `PA` is a **label/oracle only**. Level 2/3 emit lagged `PA_P*` / `Outs_P*` / `Pitches_P*` plus rest covariates. Fitted `projected_tbf` via `Models/TBF-Model/train.py`. |
| Bullpen usage | **Phase C (+ enrich):** appearance log + flat L1–L3d pitches / arms / unique / L–R / B2B / max / heavy. |
| Days of rest | **Phase A + A.1:** `days_rest`, `days_rest_capped`, `is_season_debut`, `rest_is_long_gap`, `rest_gap_severity`, `is_career_mlb_debut`. |
| Nested bullpen event lists | **Staging only** (`bullpen_appearances.parquet`). Model inputs are flat scalars — Ridge/LGBM cannot consume nested lists. |

## Design principles

1. **Leakage:** same-game `PA` / `Outs` / `Pitches` / bullpen pitches never enter
   prediction features. Only lagged / as-of priors.
2. **Offense context stays lineup-based** — the nine announced (live) or first-PA
   (historical) hitters — not franchise batting averages.
3. **Workload features serve TBF / early-hook risk first**; promote into k-rate
   only after nested confirmation.
4. **Flat features only** in training frames. Nested structures
   `(name, pitches, date, …)` are staging data, not columns.

## Phase A — starter days of rest (done)

Build from starter appearance dates in `pitcher_games.parquet` (prefer our
calendar over raw Savant rest):

1. Within season, sort `(pitcher, game_date)`.
2. `days_rest = game_date − previous_appearance_date`.
3. Season debut / no prior in-season appearance → `null` + `is_season_debut=1`
   (do **not** carry ~180-day offseason rest; spring training is absent).
4. Long-gap rule: if `days_rest > 15`, set `days_rest_capped = 15` and
   `rest_is_long_gap = 1`. Do **not** null rest — trees/Ridge need the
   “this isn’t a normal turn” signal.
5. Join onto `pitcher_training` on `(game_pk, pitcher)`.

### Phase A.1 — long-gap severity + rookies (done)

EDA (2023–2025, `PA ≥ 9`): normal PA ≈ 22.9; season debut ≈ 19.7; long gap ≈ 19.3.
Long gaps systematically undershoot stale `PA_P5` (≈ −1.2 to −2.1 by gap length).
Cold starts (`PA_P5` null) ≈ 19.1; Opening Day veterans with prior MLB rolls ≈ 20.3.

| Feature | Meaning |
|---|---|
| `rest_gap_severity` | 0 = normal/debut; 1 = 16–35d; 2 = 36–60d; 3 = 61+d |
| `is_career_mlb_debut` | First starter row in loaded MLB history (no MiLB) |

**Rookies:** no minor-league pulls. Cold start = null volume rolls + career/season
debut flags; impute with league/role priors at train time if needed. Live pitch
caps (70–85 on TJ returns) stay a **pregame override**, not a Statcast inference.

**Long-gap situations (locked):**

| Situation | Model | Live override |
|---|---|---|
| Normal turn (4–6d) | `days_rest_capped` | none |
| Gap >15d (IL/rehab/phantom) | cap + `rest_is_long_gap` + severity | optional “returning / limit” |
| Tommy John / long rehab | same; severity 3 when ≥61d | slate veto + pitch-limit hint |
| Bereavement (~3–7d) | usually normalish rest | none |
| All-Star break | long-gap flag (raw gap) | optional later `is_post_asb` |

## Phase B — projected TBF spine (done)

1. Roll prior-only `PA_P*` / `Outs_P*` / `Pitches_P*` from Level 1.
2. Join onto existing `pitcher_training.parquet`.
3. Target = same-game `PA`; score props with **projected** TBF only.
4. Rest (A/A.1) as TBF covariates.

## Phase C — team bullpen usage (done)

**Definition:** bullpen = anyone who pitched in a game who is **not** that
game’s starter (1st-inning starter key).

Level 1 artifact: `bullpen_team_games.parquet`

```text
(team, game_date, game_pk, bullpen_pitchers_used, bullpen_pitches)
```

Pregame flat features for a **starter** row (his team, as-of before first pitch):

| Feature family | Examples |
|---|---|
| Volume / arms | `bullpen_pitches_L*`, `bullpen_pitchers_used_L*`, `bullpen_appearances_L*`, `bullpen_unique_arms_L*` |
| Handedness | `bullpen_L_pitches_L*`, `bullpen_R_pitches_L*` |
| Intensity | `bullpen_b2b_arms_L*`, `bullpen_max_pitches_L*`, `bullpen_heavy_outings_L*` (≥30 pitches) |

Lookbacks sum team games with `game_date ∈ [asof − W, asof)` (same-game excluded;
missing window → 0). Join key is pitcher team (`home_team` if `is_home` else
`away_team`), never `opp_team`.

**Nested lists:** keep as `bullpen_appearances.parquet` for EDA / live UI. Do not
feed variable-length pitcher lists into Ridge/LGBM — encode as flats (above).
Optional later: fixed top-K freshest-arm slots (still flat columns).

**TBF model freeze:** **Ridge** on **`workload_context_bullpen`** (thin:
pitches + arms L1–L3d only). Rich enrichment is ablation-only
(`workload_context_bullpen_rich`). Elastic Net / Poisson / LightGBM checked —
no clear win. Promote bullpen into k-rate only after a nested check.
## Phase D — opener / piggyback population

**Interim policy frozen** — full write-up: `docs/research/phase_d_population_findings.md`.

`PA ≥ 9` remains the research estimand. ~**3.5%** of 2023–2024 first-pitcher
appearances are excluded. Pregame role labels are still required before pristine
v1 claims; bullpen features do not fix selection bias.

## Suggested build order (post-freeze)

1. ~~Phase A rest + Phase B lagged workload~~ — done.
2. ~~Fit a first projected-TBF model~~ — done.
3. ~~Phase A.1 gap severity / career debut + Phase C bullpen~~ — done.
4. ~~Re-fit TBF; Ridge + thin bullpen wins~~ — **frozen**.
5. ~~**Next:** `expected_K = frozen_k_rate × projected_tbf`~~ — first eval done
   (`docs/research/count_layer_findings.md`).
6. ~~Phase D opener/piggyback audit + interim policy~~ — done
   (`docs/research/phase_d_population_findings.md`). Pregame role labels still open.
7. Live slate assembly using projected TBF + count-layer probs.

## Architecture decisions (2026-07-27)

1. **Flat TBF spine** — one projected-`PA` model feeding many props
   (`expected_K = k_rate × projected_tbf`, later outs/BB/hits via rates × TBF).
2. **Opener / piggyback** — interim policy: keep `PA ≥ 9` research estimand;
   ~3.5% excluded; score announced starters live only with out-of-support flags
   until pregame role exists (`docs/research/phase_d_population_findings.md`).
3. **Feature sharing with k-rate** — avoid dumping the full 185-feature k-rate
   matrix into TBF. Prefer small shared context + TBF-specific volume/rest/bullpen.
4. **Long-gap rest** — keep `days_rest_capped` + `rest_is_long_gap` + severity.
   Live overrides (IL return / TJ / bereavement) are a **user/pregame flag**.
5. **Bullpen (Phase C)** — shared covariate; build once as flat team features.
6. **No MiLB for debuts** — rookies use null volume + debut flags only.
7. **MAE context** — starter PA SD ≈ 3.6; train-mean MAE ≈ 2.76; `PA_P5`-only
   MAE ≈ 2.61; first Ridge ≈ 2.50. Judge lifts vs those baselines / markets.

### Explicit non-goals

- Feeding nested name/pitch lists into the rate model
- Replacing lineup aggregates with team offense rolls
- Using same-game bullpen or same-game PA as features
- Pulling minor-league stats for MLB debuts
- Blocking Phase 11 / live hardening on bullpen feature work (parallel track)
