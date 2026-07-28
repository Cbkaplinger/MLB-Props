# Step 9 findings — per-metric window / column selection

**Status:** Step 9c complete — **targeted P1 physics swap beats 185 on holdout**  
**Date:** 2026-07-27 / 2026-07-28  
**Runners:**
- `models/Strikeout-Model/research/step9_metric_window_select.py`
- `models/Strikeout-Model/research/step9_widen_priority.py`
- `models/Strikeout-Model/research/step9c_short_std_and_p1.py`
- `models/Strikeout-Model/research/print_step9_inventory.py`  
**Artifacts:** `artifacts/feature_research/step9_metric_windows/`,
`artifacts/feature_research/step9_widen/`,
`artifacts/feature_research/step9c_short_std_p1/`

## Why this pass exists

Family leave-outs (Steps 3/8) cannot answer “is `swstr_P5` better than
`swstr_P20`?” or “is `opp_lineup_chase` dead?” Overlapping windows are
correlated; stuffing P3/P5/P10 (and rate P5/P10/P20) into one model is a real
overfit risk. Step 9 is the fine-tooth comb: **per metric**, nested-select at
most one rolling window (plus optional season-to-date `_std`), and probe
**P15/P30** via on-the-fly materialization without rewriting Level 2 defaults.

Season-to-date is already in the frame as `{rate}_std` (expanding within-season
prior rate). It is not a separate `_season_to_date` column.

## Protocol

1. Freeze true production **185** **before** joining research windows.
2. Materialize rate P15/P30 and mean P15/P20 from Level 1 games.
3. For each rate metric, inner-select among `{drop, std_only, Pw, Pw+std, full}`
   with candidates `w ∈ {5,10,15,20,30}` on nested 2023→2024 folds.
4. Static leave-one-column-out for lineup / park / `is_home`.
5. Assemble thin set only when outer folds agree (exact config, or same single
   window). Otherwise **HOLD** the production multi-window bundle.
6. Chrono bake-off vs 185 on k-rate MAE and `expected_K`.

## Rates phase results (clean 185 background)

### Window decisions

| Metric | Decision | Chosen | Note |
|---|---|---|---|
| **hr_rate** | **THIN** | **P15** | Both folds agree — longer than P5/P10/P20 bundle |
| **xBA** | **THIN** | **P30** | Both folds agree |
| **wOBA** | **THIN** | **P5** | Both folds agree |
| **zone_rate** | **THIN** | **P5** | Exact both-fold agree |
| swstr_rate | HOLD | full P5/P10/P20+std | Folds split **P30+std vs P5** — not P20 |
| whiff_rate | HOLD | full | P10 vs P30 |
| k_rate | HOLD | full | P10 vs P20 |
| bb_rate | HOLD | full | P15+std vs P5+std |
| chase_rate | HOLD | full | P10 vs P30 |
| cs_rate | HOLD | full | P15 vs P5 |
| ball_rate | HOLD | full | drop vs full |
| gb_rate | HOLD | full | P10+std vs full |
| xwOBA | HOLD | full | P10 vs P15 |

**Takeaway on overlapping windows:** where folds *agree*, the winner is often a
**single** window — and sometimes **longer** than the defaults (hr P15, xBA P30).
Where they disagree, forcing one window is unstable; keeping the multi-window
bundle is the honest HOLD. `swstr` specifically does **not** crown P5 or P20 —
folds want opposite ends of the span.

### Static / lineup LOCO

No production static column cleared the DROP bar (inner prefers drop **and**
outer MAE improves on **both** folds). Several lineup columns look droppable on
inner selection alone, but outer confirmation says dropping them **hurts**.

| Column | Inner pick | Outer ΔMAE (drop−keep) | Decision |
|---|---|---:|---|
| opp_lineup_chase | drop both | +0.00036 (hurts) | KEEP |
| opp_lineup_k | drop both | +0.00033 | KEEP |
| opp_lineup_whiff | drop both | +0.00010 | KEEP |
| opp_lineup_swstr | drop both | +0.00025 | KEEP |
| park_k_factor | drop both | +0.00025 | KEEP |
| is_home | mixed | +0.00043 | KEEP |

So `opp_lineup_chase` is **not** proven dead weight under the same both-fold
outer rule used in Step 8.

### Bake-off (rates-only thin: 185 → 173)

| Variant | Features | k-rate MAE | expected_K MAE |
|---|---:|---:|---:|
| production_185 | 185 | 0.07863 | 1.773 |
| step9_thin (rates) | 173 | 0.07876 | 1.772 |

Deltas are noise-scale. **Do not re-freeze production from rates-only thin.**
The value of this pass is the per-metric evidence and the window hypotheses,
not a new spine.

## Mean / physics phase

Running: `--means-only` (candidates P3/P5/P10/P15/P20 per physics/usage/mechanics/FIP
stem). Results will update this doc when complete.

## Pickup

```powershell
# Rates + static (done)
python models/Strikeout-Model/research/step9_metric_window_select.py --skip-means

# Mean/physics (in progress / rerun)
python models/Strikeout-Model/research/step9_metric_window_select.py --means-only

# Re-assemble + bake-off only
python models/Strikeout-Model/research/step9_metric_window_select.py --finalize-only
```

## Season boundaries (important)

**Rolling `P{w}` does NOT reset each season.** It is the last *w* starts for
that pitcher across the career calendar (`.over("pitcher")`). Early April can
include prior September.

**Season-to-date `_std` DOES reset each season** (expanding within
`pitcher × season`).

They mix by design: `P{w}` = recent form (can cross years); `_std` = this-season
talent. They are complementary, not the same clock.

## Step 9b widen (priority metrics)

Grid: rates `{5,10,15,20,25,30,35,40}` + `_std` + dual short+long;
means `{15,20,25,30}` for edge-P20 stems.

| Metric | Widen verdict | Chosen | vs full ΔMAE | Note |
|---|---|---|---:|---|
| **xBA** | WINDOW_AGREE | **P30** | +0.00013 | P35/P40 did **not** beat P30 |
| **hr_rate** | WINDOW_AGREE | **P15** | −0.00010 | Confirmed; no need past 15–20 |
| **bb_rate** | WINDOW_AGREE | **P10** (+optional P25 dual) | +0.00019 | Primary window P10 |
| **chase_rate** | WINDOW_AGREE | **P10** | +0.00005 | Dual P10+P30 unstable |
| **sl_hb / sl_usage_vL / st_vaa / ch_ivb** | AGREE | **P20** | mixed | P25/P30 did not displace P20 |
| swstr_rate | DISAGREE | P5 vs P30+std | −0.00024 | Still unresolved |
| whiff_rate | DISAGREE | P10 vs P5+P30 | −0.00047 | Still unresolved |
| xwOBA | DISAGREE | P15 vs P10+P25+std | −0.00014 | Still unresolved |
| k_rate / cs_rate | DISAGREE | mixed | ~0 | Keep production multi-window |
| cu_velo / rel_x_sd | DISAGREE | mid band | ~0 | Hold production P3/P5 |

**Artifacts:** `artifacts/feature_research/step9_widen/`,
`artifacts/feature_research/step9_metric_windows/feature_inventory.csv`,
`metric_window_summary.csv`.

## Step 9c — short+`_std` (all rates) + P1 (all physics/means)

User-directed: test short+season-to-date for every rate; add **P1** so mid-season
pitch redesigns can register.

### Rates: short + `_std`

| Metric | Result |
|---|---|
| **gb_rate** | Both folds → **P10+std** (only clean short+std lock) |
| **bb_rate** | Both want +std but P5 vs P15 — HOLD |
| swstr / whiff / xwOBA / k_rate / cs_rate / chase | Still short-vs-long HOLD — short+std did **not** resolve them |
| zone_rate / wOBA / hr_rate / xBA | Unchanged winners (P5 / P5 / P15 / P30) |

### Physics: P1

Both-fold **P1** winners (replace production P3/P5):

| Metric | Both-fold pick | Outer ΔMAE vs full |
|---|---|---:|
| **ff_velo** | P1 | −0.00039 |
| **cu_vaa** | P1 | −0.00019 |
| **cu_usage_vR** | P1 | +0.00017 |
| **fs_usage_vR** | P1 | +0.00034 |
| **sl_vaa** | P1 | +0.00021 |

Many other stems had P1 on **one** fold only → HOLD (do not force).

### Bake-offs

| Variant | Features | k-rate MAE | expected_K MAE |
|---|---:|---:|---:|
| production_185 | 185 | 0.07863 | 1.773 |
| step9c greedy thin | 156 | 0.07907 | 1.781 | **worse — do not ship** |
| **p1_swap_5** (only the 5 P1 locks) | **180** | **0.07842** | **1.769** | **beats 185** |

**Promote proposal:** ~~add Level-2 `P1`…~~ **LOCKED** as `production` (180
features) — see `docs/research/step10_p1_registry_freeze.md` and
`artifacts/models/lightgbm_krate_20260728_033241.{txt,json}`.

## Direct answers

**Is all data good data?** No. Correlated overlapping windows are especially
wasteful. This screen is how you stop hoping.

**Is 185 “the best”?** Best among what Step 7 locked — yes until Step 9c. The
**P1 five-stem swap (180)** is the first holdout-beating refinement.

**Why weren’t we doing this before?** Step 8 intentionally stayed family-level
on an already-thinned set. That was incomplete for your bar. Step 9 is the
missing comb.

## Exploration map (from rates phase)

### Objective yardstick (how we score anything)

Target is **same-game** `k_rate = K / PA` (`Python.features.TARGET`). Every
candidate window/config is judged by:

1. **Primary:** MAE of predicted `k_rate` vs actual `k_rate` on nested
   chronological folds (inner selects; outer confirms). RMSE / R² logged but
   MAE is the gate.
2. **Product check:** `expected_K = k_rate_hat × projected_tbf` vs actual `K`
   (count MAE) on the chrono bake-off — only after a feature change survives (1).

We do **not** promote on feature↔K correlation alone. If it does not lower
holdout rate MAE under the nested protocol, it is not “better.”

### Widen follow-up (done in Step 9b)

Already run on `{5…40}` (+ dual short/long). Confirmed: **xBA→P30**,
**hr_rate→P15**, **bb/chase→P10**, several slider/change means→**P20**.
Still unresolved (keep production multi-window): **swstr, whiff, xwOBA, k_rate,
cs_rate**. No need to push past P40 for xBA — P35/P40 lost to P30.

### Do **not** widen (keep short / current)

| Metric | Evidence |
|---|---|
| **zone_rate** | Both folds → **P5** |
| **wOBA** | Both folds → **P5** |
| **k_rate** (as a feature) | P10 vs P20 — mid band; season `_std` already covers long memory |

### Default window ranges going forward

Stop shipping overlapping triples. Per stem, build candidates then **pick ≤1
rolling window** (+ optional `_std` for rates):

| Family | Candidate starts | Default pick rule |
|---|---|---|
| Fast form (zone, recent wOBA-ish) | **5–10** | Prefer shortest that wins both outer folds |
| Standard rates (K/BB/CSW-ish) | **10–20** (+ `_std`) | Mid; keep `_std` as season anchor |
| Slow / noisy (xBA, HR%, whiff/swstr talent) | **15–40** | Probe 15/20/30/40; do not also keep P5 |
| Physics means (velo/spin/etc.) | **3–10** (Step 4: P3+P5 beat P10) | Await Step 9 means; do not expand to 30 by default |
| Season memory | **`_std` only** | Already expanding within-season; use instead of P40+ when long memory is the goal |

**Practical build recipe:** for each metric, generate `{5, 10, 15, 20, 30}` (rates)
or `{3, 5, 10, 15}` (means), run Step 9-style nested pick, ship **one** winner.
If folds split short vs long, try **short + `_std`** before reintroducing two
rolling windows.

## Next after Step 9 / 9c / 10

Feature window research is **closed** at production **180**. Do not reopen
greedy thinning. Critical path is Phase 11 model quality
(`docs/research/phase11_model_quality_gates.md`).
