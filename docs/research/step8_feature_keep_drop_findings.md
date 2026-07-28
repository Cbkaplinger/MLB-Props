# Step 8 findings — feature keep/drop on frozen 185 + error interpretation

**Status:** complete — **no family prune cleared the bar; keep production 185**  
**Date:** 2026-07-27  
**Runners:**
- `models/Strikeout-Model/research/leave_family_out_ablation.py --feature-set production --models lightgbm`
- `models/Strikeout-Model/research/step8_keep_drop.py`  
**Artifacts:** `artifacts/feature_research/leave_family_out_production/`,
`artifacts/feature_research/step8_keep_drop/`

## Verdict

On the **already window-thinned 185-feature** LightGBM production set, nested
leave-family-out does **not** support dropping any feature family under a
strict rule: MAE must improve on **both** outer folds.

Cumulative greedy prune dropped **zero** families. Chrono bake-off of
“pruned” vs 185 is identical (same feature list). **Do not open a new registry
freeze** from this screen.

The large cut already happened in Steps 4/7 (248 → 185). Further family
surgery on 185 is noise-scale, not a new edge source.

## Family decisions (LightGBM, production 185)

Positive ΔMAE = dropping the family **hurt** (family is useful).

| Family | Decision | Mean ΔMAE | Both-fold? |
|---|---|---:|---|
| **lineup** | **KEEP** | +0.00317 | hurts both (strongest) |
| pitch_physics | KEEP | +0.00085 | hurts both |
| mechanics | KEEP | +0.00056 | hurts both |
| park | KEEP | +0.00052 | hurts both |
| context | KEEP | +0.00052 | hurts both |
| pitch_usage | KEEP | +0.00039 | hurts both |
| fip_xfip | KEEP | +0.00021 | hurts both (barely on h2) |
| expected_contact | KEEP | +0.00018 | hurts both |
| **rates** | **HOLD** | +0.00005 | mixed (helps h1, hurts h2) |

**DROP:** none.

Note vs Step 3 (248): `drop_fip_xfip` then looked slightly helpful
(mean ΔMAE ≈ −0.00029). After the mean-window thin to 185, dropping FIP/xFIP
**hurts**. Do not carry the old FIP-drop recommendation onto the frozen set
without a new both-fold win.

### Structural checks

| Configuration | Mean ΔMAE | Note |
|---|---:|---|
| drop all rolling (keep STD/static) | +0.00162 | Rolling still load-bearing overall |
| drop all STD (keep rolling/static) | −0.00013 | Mixed folds; not a freeze change |

## Bake-off (chrono test ≥ 2024-08-06)

| Variant | k-rate MAE | expected_K MAE | Features |
|---|---:|---:|---:|
| production_185 | 0.0787 | 1.790 | 185 |
| pruned | 0.0787 | 1.790 | 185 (unchanged) |

`expected_K = k_rate × Ridge projected_tbf` (thin bullpen).

## Pickup

```powershell
python models/Strikeout-Model/research/step8_keep_drop.py
python models/Strikeout-Model/research/leave_family_out_ablation.py --feature-set production --models lightgbm
```

---

## How wrong is the strikeout system? (layman)

You combine two models:

```text
expected_K ≈ predicted_k_rate × projected_tbf
```

### A. Producing “correct” values

| Piece | What a miss means | Chrono test size |
|---|---|---|
| **k-rate** | Wrong strikeout **percentage** | MAE ≈ **0.079** (~7.9 percentage points) |
| **TBF** | Wrong **batters faced** | MAE ≈ **2.5 PA** |
| **expected_K** | Wrong **strikeout count** | MAE ≈ **1.79 K** |

On a typical start you’re often about **two strikeouts** off on the count —
useful signal, still noisy baseball, not a crystal ball.

**Are rate and TBF independent?** Not really. A quick hook shortens TBF *and*
can change K%; ace stuff can raise K% *and* lengthen the leash. Multiplying
assumes a first-order product: “given what we know pregame, expected K is
roughly rate × volume.” We do **not** fully model their covariance. Errors can
**stack** on the same game (high rate miss + high TBF miss). That’s why we
score **expected_K vs actual K** and line Brier, not rate MAE alone.

Product error is **not** “rate MAE × TBF MAE.” A 0.08 rate miss on 22 PA is
already ~1.8 K of count error before TBF noise.

### B. Edge without burning the user

Edge ≠ low MAE. Edge means your probabilities are **calibrated** (when you say
58% over 5.5, overs hit ~58% over time) and you only bet when that diverges
from the market after vig.

On chrono test, picking the side with p≥0.5 at 4.5/5.5 is only modestly above
a base-rate coin flip; **Brier (~0.21–0.22)** is the better “don’t screw the
user” metric than headline accuracy.

Safeguards already in this repo:

1. Never use same-game PA in the prop (no oracle TBF).
2. Don’t treat recycled 2025 as a pristine final test.
3. Opener / `PA≥9` selection bias remains an honesty caveat (Phase D).
4. Count layer is research-scored, not a bankroll product.

**Cutting features further on 185** did not unlock a new MAE cliff. Subsequent
Step 9c/10 locked a targeted P1 physics swap to **180**
(`docs/research/step10_p1_registry_freeze.md`). Further family drops remain closed.
**Next:** Phase 11 model quality (tune / walk-forward / calibrate) — not live
assembly and not another ablation pass
(`docs/research/phase11_model_quality_gates.md`).
