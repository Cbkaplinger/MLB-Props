import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2\research\offseason_2026")
from pregame_pa_ext import adapter as ad

W_PRIOR = 150
HALF_LIFE_DAYS = 90.0
FEATURES = ["p_pitcher_prior_w150", "p_batter_prior_w150", "lg_rate",
            "n_prior_pitcher", "n_prior_batter", "cold_start",
            "ew_pitcher", "ew_batter"]

pa = ad.load_pa_table()
ledger = pl.read_parquet(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
                         r"\outputs\projected_pa_probs_v1.parquet")

# ---- frozen state tables (the shared as-of source) -------------------
p_state = ad.entity_daily_state(pa, "pitcher")
b_state = ad.entity_daily_state(pa, "batter")
lg_state = ad.league_daily_state(pa)


def feature_request(requests: pl.DataFrame) -> pl.DataFrame:
    """THE SHARED AS-OF FEATURE-REQUEST INTERFACE (proposal P0):
    requests = (pitcher_id, batter_id, as_of_date) triples - ANY triple,
    no realized appearance required. Built from the frozen state tables
    via the FROZEN attach_prior_features function itself (same as-of
    rule, same w150/EW formulas, same cold-start semantics). The caller's
    _rid row identity is preserved."""
    req = requests.rename(
        {"pitcher_id": "pitcher", "batter_id": "batter",
         "as_of_date": "game_date"})
    return ad.attach_prior_features(req, p_state, b_state, lg_state)


# ---- (a) compatibility against the preserved ledger ------------------
sample = ledger.filter(pl.col("exclusion_reason").is_null()).sample(
    n=3000, seed=20261022)
sample = sample.with_row_index("_rid")
req = sample.select(
    pl.col("_rid"),
    pl.col("pitcher").alias("pitcher_id"),
    pl.col("batter").alias("batter_id"),
    pl.col("game_date").alias("as_of_date"), "game_pk", "slot")
got = feature_request(req)
cmp = got.join(
    sample.select("_rid", "game_pk", "slot", *FEATURES),
    on="_rid", how="left", suffix="_ledger")
mismatches = {}
for f in FEATURES:
    a = cmp[f].to_numpy().astype(float)
    b = cmp[f + "_ledger"].to_numpy().astype(float)
    both_nan = np.isnan(a) & np.isnan(b)
    d = np.where(both_nan, 0.0, np.abs(a - b))
    n_mism = int((d > 1e-9).sum())
    mismatches[f] = {"n_mismatch": n_mism, "max_abs_diff":
                     float(np.nanmax(d)) if np.isfinite(d).any() else 0.0}
print("== (a) ledger compatibility (n=%d sampled slots) ==" % cmp.height)
for f, m in mismatches.items():
    print(f"  {f:24s} mismatches={m['n_mismatch']:5d} "
          f"max_diff={m['max_abs_diff']:.2e}")

# ---- (b) independent historical calculation (no attach_prior_features)
def independent_request(reqs: pl.DataFrame) -> pl.DataFrame:
    """Second implementation: direct asof joins against the state
    tables with the formulas written out inline."""
    p = p_state.rename({"game_date": "p_date", "prior_k": "pk",
                        "prior_n": "pn", "ew_k": "pwk",
                        "ew_den": "pwd", "pitcher": "pitcher_id"})
    b = b_state.rename({"game_date": "b_date", "prior_k": "bk",
                        "prior_n": "bn", "ew_k": "bwk",
                        "ew_den": "bwd", "batter": "batter_id"})
    lg = lg_state.rename({"game_date": "l_date"})
    out = (reqs.sort("as_of_date")
           .join_asof(p.sort("p_date"), left_on="as_of_date",
                      right_on="p_date", by="pitcher_id",
                      strategy="backward")
           .join_asof(b.sort("b_date"), left_on="as_of_date",
                      right_on="b_date", by="batter_id",
                      strategy="backward")
           .join_asof(lg.sort("l_date"), left_on="as_of_date",
                      right_on="l_date", strategy="backward"))
    return out.with_columns(
        (((pl.col("pk").fill_null(0) + W_PRIOR * pl.col("lg_rate"))
          / (pl.col("pn").fill_null(0) + W_PRIOR))
         .alias("p_pitcher_prior_w150_ind"),
         (((pl.col("bk").fill_null(0) + W_PRIOR * pl.col("lg_rate"))
           / (pl.col("bn").fill_null(0) + W_PRIOR))
          .alias("p_batter_prior_w150_ind")),
         pl.when(pl.col("pwd").fill_null(0) > 0)
         .then(pl.col("pwk").fill_null(0) / pl.col("pwd"))
         .otherwise(pl.col("lg_rate")).alias("ew_pitcher_ind"),
         pl.when(pl.col("bwd").fill_null(0) > 0)
         .then(pl.col("bwk").fill_null(0) / pl.col("bwd"))
         .otherwise(pl.col("lg_rate")).alias("ew_batter_ind"),
         ((pl.col("pn").fill_null(0) == 0)
          | (pl.col("bn").fill_null(0) == 0)).cast(pl.Int8)
         .alias("cold_start_ind"),
         pl.col("pn").fill_null(0).alias("n_prior_pitcher_ind"),
         pl.col("bn").fill_null(0).alias("n_prior_batter_ind"),
         pl.col("lg_rate").alias("lg_rate_ind")))


ind = independent_request(sample.select(
    pl.col("pitcher").alias("pitcher_id"),
    pl.col("batter").alias("batter_id"),
    pl.col("game_date").alias("as_of_date"), "game_pk", "slot"))
cmp2 = ind.join(sample.select("game_pk", "slot", *FEATURES),
                on=["game_pk", "slot"], how="left", suffix="_ledger")
pairs = [("p_pitcher_prior_w150_ind", "p_pitcher_prior_w150"),
         ("p_batter_prior_w150_ind", "p_batter_prior_w150"),
         ("ew_pitcher_ind", "ew_pitcher"),
         ("ew_batter_ind", "ew_batter"),
         ("cold_start_ind", "cold_start"),
         ("n_prior_pitcher_ind", "n_prior_pitcher"),
         ("n_prior_batter_ind", "n_prior_batter"),
         ("lg_rate_ind", "lg_rate")]
print()
print("== (b) independent implementation vs ledger (n=%d) =="
      % cmp2.height)
mismatches2 = {}
for a_col, l_col in pairs:
    a = cmp2[a_col].to_numpy().astype(float)
    b = cmp2[l_col].to_numpy().astype(float)
    both_nan = np.isnan(a) & np.isnan(b)
    d = np.where(both_nan, 0.0, np.abs(a - b))
    n_mism = int((d > 1e-9).sum())
    mismatches2[l_col] = {"n_mismatch": n_mism,
                          "max_abs_diff": float(np.nanmax(d))
                          if np.isfinite(d).any() else 0.0}
    print(f"  {l_col:24s} mismatches={n_mism:5d} "
          f"max_diff={mismatches2[l_col]['max_abs_diff']:.2e}")

# ---- (c) adversarial cases -------------------------------------------
print()
print("== (c) adversarial requests ==")
adv = pl.DataFrame({
    "pitcher_id": [657277, 657277, 999999999, 657277, 657277],
    "batter_id": [999999999, 669194, 669194, 669194, 669194],
    "as_of_date": [date(2025, 5, 1), date(2025, 5, 1),
                   date(2025, 5, 1), date(2022, 3, 15),
                   date(2026, 12, 1)],
})
adv_named = adv.rename({"pitcher_id": "pitcher",
                        "batter_id": "batter",
                        "as_of_date": "game_date"})
adv_out = ad.attach_prior_features(adv_named, p_state, b_state, lg_state)
labels = ["batter never in data (cold)",
          "both known (normal pregame request)",
          "pitcher never in data (cold)",
          "date before any data (early)",
          "date after the data ends (future)"]
for i, r in enumerate(adv_out.iter_rows(named=True)):
    print(f"  {labels[i]}: cold_start={r['cold_start']} "
          f"p_pitcher={r['p_pitcher_prior_w150']} "
          f"p_batter={r['p_batter_prior_w150']} "
          f"ew_p={r['ew_pitcher']} n_prior_p={r['n_prior_pitcher']}")

# batters who did NOT appear in the game but exist in history: a real
# roster batter not in the projected lineup
led = ledger.filter((pl.col("game_pk") == 744795)
                    & (pl.col("exclusion_reason").is_null()))
in_game_batters = set(led["batter"].to_list())
pa_game = pa.filter(pl.col("game_pk") == 744795)
not_in_lineup = [b for b in pa_game["batter"].unique().to_list()
                 if b not in in_game_batters][:3]
if not_in_lineup:
    reqs = pl.DataFrame({
        "pitcher_id": [led["pitcher"][0]] * len(not_in_lineup),
        "batter_id": not_in_lineup,
        "as_of_date": [led["game_date"][0]] * len(not_in_lineup)})
    o = ad.attach_prior_features(
        reqs.rename({"pitcher_id": "pitcher", "batter_id": "batter",
                     "as_of_date": "game_date"}),
        p_state, b_state, lg_state)
    print(f"  batters in the game but NOT in the projected lineup "
          f"(n={len(not_in_lineup)}): features constructed without any "
          f"realized-appearance requirement: "
          + ", ".join(f"p_batter={r['p_batter_prior_w150']}"
                      for r in o.iter_rows(named=True)))

# ---- preserve results -------------------------------------------------
out = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
           r"\diagnostics\feature_request_p0")
out.mkdir(exist_ok=True)
cmp.write_parquet(out / "ledger_compatibility_sample.parquet")
cmp2.write_parquet(out / "independent_implementation_sample.parquet")
adv_out.write_parquet(out / "adversarial_cases.parquet")
report = {"ledger_compat": mismatches, "independent_compat":
          mismatches2, "n_sampled": int(cmp.height)}
(out / "p0_report.json").write_text(json.dumps(report, indent=1),
                                    encoding="utf-8")
print()
print("written:", out)
