"""Print Step 9 feature inventory + widen verdicts."""

from __future__ import annotations

import pandas as pd

from Python import config

inv = pd.read_csv(
    config.OUTPUT_DIR / "feature_research" / "step9_metric_windows" / "feature_inventory.csv"
)
ms = pd.read_csv(
    config.OUTPUT_DIR
    / "feature_research"
    / "step9_metric_windows"
    / "metric_window_summary.csv"
)
widen = pd.read_csv(
    config.OUTPUT_DIR / "feature_research" / "step9_widen" / "verdicts.csv"
)
bake = pd.read_csv(
    config.OUTPUT_DIR / "feature_research" / "step9_metric_windows" / "bakeoff.csv"
)
wmap = widen.set_index("metric")[
    ["decision", "chosen", "fold_configs", "mean_delta_mae_vs_full"]
].to_dict("index")

print("=" * 72)
print(f"PRODUCTION FEATURE COUNT: {len(inv)}")
print("BAKEOFF (Step9 assembled thin vs 185):")
print(bake.to_string(index=False))
print("=" * 72)
print("FEATURES BY FAMILY (production 185)")
print("=" * 72)
for family, group in inv.groupby("family", sort=True):
    print(f"\n### {family} ({len(group)} features)")
    for row in group.itertuples(index=False):
        print(f"  {row.feature:28s}  window={row.window}")

print("\n" + "=" * 72)
print("METRIC-LEVEL OPTIMAL WINDOWS (Step 9 + Step 9b widen)")
print("=" * 72)
for family, group in ms.groupby("family", sort=True):
    print(f"\n### {family}")
    for row in group.itertuples(index=False):
        w = wmap.get(row.metric)
        if w is not None:
            opt = (
                f"WIDEN {w['decision']}: {w['chosen']} "
                f"(fold_cfgs={w['fold_configs']}, "
                f"dMAE={w['mean_delta_mae_vs_full']:+.5f})"
            )
        else:
            opt = (
                f"Step9 {row.step9_decision}: {row.step9_optimal_window} "
                f"[{row.fold_selections}]"
            )
        print(
            f"  {row.metric:22s}  prod={str(row.production_windows):20s}  {opt}"
        )

print("\n" + "=" * 72)
print("STILL NEEDS EXPLORATION (unresolved after widen)")
print("=" * 72)
still = widen[widen["decision"] == "DISAGREE"]
print(still.to_string(index=False) if len(still) else "none")
print("\nConfirmed long/mid winners (no further grid needed):")
print(
    widen[widen["decision"].isin(["AGREE", "WINDOW_AGREE"])][
        ["metric", "chosen", "mean_delta_mae_vs_full"]
    ].to_string(index=False)
)
