"""Zone-command probe: pitcher location-tendency regions (post hoc, research).

Last unbuilt KSplit idea (#105): do WHERE-pitches-go tendencies carry
k-rate signal beyond stuff? 3 regions from Savant plate_x/plate_z
(Heart/Edge/Chase — documented approximations, not the full 13-cell):
  heart = |x|<0.6 & |z-2.0|<0.7
  chase = |x|>1.1 | |z-2.0|>1.2
  edge  = everything else
Rates are PRIOR-season (2024->2025 universe, 2025->2026 check): zero
leakage, tests the stable-trait hypothesis. Stability gate FIRST
(YoY r>=0.7 + min-n curve, #45 doctrine), then residual_K assoc with
xK-bin stratification (Berkson control, kadj precedent).

Writes artifacts/odds_log/zone_probe_report.json. No live change.
KILL (#106): unstable inputs OR |corr|<=0.05 both raw and stratified.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR, sorted_key  # noqa: E402

SAV = ROOT / "data" / "Savant-Data" / "regular"
MIN_N_CURVE = [100, 300, 500]


def regions(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        (((pl.col("plate_x").abs() < 0.6) & ((pl.col("plate_z") - 2.0).abs() < 0.7))).alias("_heart"),
        (((pl.col("plate_x").abs() > 1.1) | ((pl.col("plate_z") - 2.0).abs() > 1.2))).alias("_chase"),
    ).with_columns(
        pl.when(pl.col("_heart")).then(pl.lit("heart"))
        .when(pl.col("_chase")).then(pl.lit("chase"))
        .otherwise(pl.lit("edge")).alias("region"))


def season_rates(year: int) -> pl.DataFrame:
    df = pl.scan_parquet(SAV / str(year) / f"statcast_{year}_regular.parquet").select(
        ["pitcher", "player_name", "plate_x", "plate_z"]).filter(
        pl.col("plate_x").is_not_null() & pl.col("plate_z").is_not_null()
        & pl.col("pitcher").is_not_null()).collect()
    df = regions(df)
    agg = df.group_by(["pitcher", "player_name"]).agg(
        pl.len().alias("n"),
        (pl.col("region") == "heart").mean().alias("heart"),
        (pl.col("region") == "edge").mean().alias("edge"),
        (pl.col("region") == "chase").mean().alias("chase"))
    agg = agg.with_columns(
        agg["player_name"].map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"))
    return agg


def yoy(a: pl.DataFrame, b: pl.DataFrame, col: str, min_n: int) -> dict:
    j = a.filter(pl.col("n") >= min_n).join(
        b.filter(pl.col("n") >= min_n), on="pitcher", suffix="_b")
    x = j[col].to_numpy().astype(float)
    y = j[f"{col}_b"].to_numpy().astype(float)
    r = float(np.corrcoef(x, y)[0, 1]) if len(x) >= 30 else float("nan")
    return {"n": int(len(x)), "r": r}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    r24, r25, r26 = season_rates(2024), season_rates(2025), season_rates(2026)
    print(f"pitchers: 2024={r24.height} 2025={r25.height} 2026={r26.height}")
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "stability_24_25": {}, "stability_25_26": {}}
    for col in ("heart", "edge", "chase"):
        for mn in MIN_N_CURVE:
            rep["stability_24_25"][f"{col}_n{mn}"] = yoy(r24, r25, col, mn)
            rep["stability_25_26"][f"{col}_n{mn}"] = yoy(r25, r26, col, mn)
    print(json.dumps(rep, indent=1, default=str))

    uni = pl.read_parquet(ODDS_DIR / "universe_panel_live.parquet").filter(
        pl.col("gd").str.slice(0, 4) == "2025").select(
        ["gd", "key", "expected_K", "K", "line", "y"])
    uni = uni.with_columns((pl.col("K").cast(pl.Float64)
                            - pl.col("expected_K").cast(pl.Float64)).alias("resid"))
    prior = r24.select(["key", "heart", "edge", "chase"]).rename(
        {c: f"{c}_prior" for c in ("heart", "edge", "chase")})
    j = uni.join(prior, on="key", how="inner")
    print(f"2025 universe rows with prior rates: {j.height}/{uni.height}")
    xk = j["expected_K"].to_numpy().astype(float)
    res = j["resid"].to_numpy().astype(float)
    assoc: dict = {}
    for col in ("heart_prior", "edge_prior", "chase_prior"):
        v = j[col].to_numpy().astype(float)
        raw = float(np.corrcoef(v, res)[0, 1])
        strat = []
        for lo, hi in ((0, 4), (4, 6), (6, 99)):
            idx = np.where((xk >= lo) & (xk < hi))[0]
            if len(idx) >= 200:
                strat.append(float(np.corrcoef(v[idx], res[idx])[0, 1]))
        assoc[col] = {"n": int(len(v)), "coverage": float(len(v) / uni.height),
                      "corr_raw": raw, "corr_xk_stratified": strat,
                      "max_abs": max([abs(raw)] + [abs(s) for s in strat])}
    rep["assoc_2025_prior_rates"] = assoc
    best = max(v["max_abs"] for v in assoc.values())
    rep["kill"] = ("SURVIVE" if best > 0.05 else "KILL")
    out = ODDS_DIR / "zone_probe_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"best|corr|={best:.4f} kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
