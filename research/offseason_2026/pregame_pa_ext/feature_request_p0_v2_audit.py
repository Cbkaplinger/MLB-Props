"""P0 corrected audit — identity-safe, non-overwriting (owner order
2026-10-22, after the review of cd5ce8b).

Fixes vs the first P0 script:
- stable request IDs (_rid) carried through EVERY path; all comparison
  joins keyed on _rid; one-to-one assertions (unique requests, exactly
  one result per request, no fan-out);
- one-sided null/NaN treated as explicit mismatches;
- adversarial outputs labeled by request ID, not position;
- NEW write-once output directory (the original feature_request_p0/
  directory is preserved with PRESERVED_MANIFEST.json).

What each part verifies (and does not):
- Part A: the FROZEN attach_prior_features chain vs the preserved
  ledger (keyed). Tests attachment, not the state tables.
- Part B: an independently-coded formula implementation vs the ledger
  (keyed). Still consumes the shared state tables — it verifies
  attachment/formulas, not the historical state itself.
- Part C: for surviving discrepancies, historical PA rows are
  enumerated DIRECTLY from the pa_table and counts/K/EW computed
  inline (entity_daily_state NOT used) — the only part that tests the
  historical state contract.
"""
import hashlib
import json
import sys
from datetime import date
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
OUT = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
           r"\diagnostics\feature_request_p0_v4")
OUT.mkdir(exist_ok=False)

pa = ad.load_pa_table()
ledger = pl.read_parquet(r"C:\Users\ckaplinger\MLB-Props-Research"
                         r"\pregame-pa-ext-v2\outputs"
                         r"\projected_pa_probs_v1.parquet")
p_state = ad.entity_daily_state(pa, "pitcher")
b_state = ad.entity_daily_state(pa, "batter")
lg_state = ad.league_daily_state(pa)


def one_to_one(df: pl.DataFrame, key: str, tag: str) -> None:
    dup = df.group_by(key).agg(pl.len().alias("n")).filter(
        pl.col("n") > 1).height
    if dup:
        raise ValueError(f"{tag}: fan-out on {key}: {dup} duplicated")


# ---- sampled requests (exact recipe) ---------------------------------
sample = (ledger.filter(pl.col("exclusion_reason").is_null())
          .sample(n=3000, seed=20261022)
          .with_row_index("_rid"))
req = sample.select("_rid", pl.col("pitcher").alias("pitcher_id"),
                    pl.col("batter").alias("batter_id"),
                    pl.col("game_date").alias("as_of_date"),
                    "game_pk", "slot")
one_to_one(req, "_rid", "requests")

# ---- Part A: frozen attach_prior_features (keyed) ---------------------
gotA = ad.attach_prior_features(
    req.rename({"pitcher_id": "pitcher", "batter_id": "batter",
                "as_of_date": "game_date"}),
    p_state, b_state, lg_state)
one_to_one(gotA, "_rid", "partA-output")
cmp = gotA.join(sample.select("_rid", *FEATURES), on="_rid",
                how="inner", suffix="_ledger", validate="1:1")
print("Part A rows:", cmp.height, flush=True)


def count_mism(df, a_col, b_col):
    a = df[a_col].to_numpy().astype(float)
    b = df[b_col].to_numpy().astype(float)
    one_sided = np.isnan(a) ^ np.isnan(b)
    both = ~(np.isnan(a) | np.isnan(b))
    d = np.where(both, np.abs(a - b), 0.0)
    hard = (d > 1e-9) | one_sided
    return int(hard.sum()), int(one_sided.sum()), \
        (float(d.max()) if len(d) and np.isfinite(d).any() else 0.0)


resA = {}
for f in FEATURES:
    n_hard, n_one, _ = count_mism(cmp, f, f + "_ledger")
    resA[f] = {"hard_mismatch": n_hard, "one_sided_null": n_one}
print("== Part A: frozen fn vs ledger (keyed _rid) ==")
for f, m in resA.items():
    print(f"  {f:24s} hard={m['hard_mismatch']:4d} "
          f"one_sided_null={m['one_sided_null']:3d}")

# ---- Part B: independent formulas (keyed, 1:1) ------------------------
p_s = p_state.rename({"game_date": "p_date", "prior_k": "pk",
                      "prior_n": "pn", "ew_k": "pwk", "ew_den": "pwd",
                      "pitcher": "pitcher_id"})
b_s = b_state.rename({"game_date": "b_date", "prior_k": "bk",
                      "prior_n": "bn", "ew_k": "bwk", "ew_den": "bwd",
                      "batter": "batter_id"})
lg_s = lg_state.rename({"game_date": "l_date"})
ind = (req.sort("as_of_date")
       .join_asof(p_s.sort("p_date"), left_on="as_of_date",
                  right_on="p_date", by="pitcher_id",
                  strategy="backward")
       .join_asof(b_s.sort("b_date"), left_on="as_of_date",
                  right_on="b_date", by="batter_id",
                  strategy="backward")
       .join_asof(lg_s := lg_state.rename({"game_date": "l_date"})
                  .sort("l_date"), left_on="as_of_date",
                  right_on="l_date", strategy="backward")
       .with_columns(
    ((pl.col("pk").fill_null(0) + W_PRIOR * pl.col("lg_rate"))
     / (pl.col("pn").fill_null(0) + W_PRIOR)).alias("ind_ppw"),
    ((pl.col("bk").fill_null(0) + W_PRIOR * pl.col("lg_rate"))
     / (pl.col("bn").fill_null(0) + W_PRIOR)).alias("ind_rpw"),
    pl.when(pl.col("pwd").fill_null(0) > 0)
    .then(pl.col("pwk").fill_null(0) / pl.col("pwd"))
    .otherwise(pl.col("lg_rate")).alias("ind_ewp"),
    pl.when(pl.col("bwd").fill_null(0) > 0)
    .then(pl.col("bwk").fill_null(0) / pl.col("bwd"))
    .otherwise(pl.col("lg_rate")).alias("ind_ewb"),
    ((pl.col("pn").fill_null(0) == 0)
     | (pl.col("bn").fill_null(0) == 0)).cast(pl.Int8)
    .alias("ind_cold"),
    pl.col("pn").fill_null(0).alias("ind_np"),
    pl.col("bn").fill_null(0).alias("ind_nb"),
    pl.col("lg_rate").alias("ind_lg")))
one_to_one(ind, "_rid", "partB")
cmpB = ind.join(sample.select("_rid", *FEATURES), on="_rid",
                how="inner", suffix="_ledger", validate="1:1")
pairs = [("ind_ppw", "p_pitcher_prior_w150"),
         ("ind_rpw", "p_batter_prior_w150"),
         ("ind_ewp", "ew_pitcher"), ("ind_ewb", "ew_batter"),
         ("ind_cold", "cold_start"), ("ind_np", "n_prior_pitcher"),
         ("ind_nb", "n_prior_batter"), ("ind_lg", "lg_rate")]
resB = {}
for a_col, l_col in pairs:
    n_hard, n_one, _ = count_mism(cmpB, a_col, l_col)
    resB[l_col] = {"hard_mismatch": n_hard, "one_sided_null": n_one}
print("== Part B: independent formulas vs ledger (keyed _rid) ==")
for f, m in resB.items():
    print(f"  {f:24s} hard={m['hard_mismatch']:4d} "
          f"one_sided={m['one_sided_null']:3d}")

# ---- Part C: historical-row reconstruction for surviving mismatches ---
mism_ids = cmpB.filter(
    (pl.col("ind_np") != pl.col("n_prior_pitcher"))
    | pl.col("n_prior_pitcher").is_null()
    | pl.col("ind_np").is_null())["_rid"].to_list()
print()
print("== Part C: surviving n_prior mismatches:", len(mism_ids),
      "==", flush=True)
# independent historical enumeration DIRECTLY from the pa_table
# (no entity_daily_state): rows strictly before as_of per entity
pa_idx = pa.with_row_index("_pai")
recon_rows = []
for rid in mism_ids[:20]:  # bounded sample of 20
    r = sample.filter(pl.col("_rid") == rid).row(0, named=True)
    pitcher, batter = r["pitcher"], r["batter"]
    gdate = r["game_date"]
    p_rows = pa_idx.filter((pl.col("pitcher") == pitcher)
                           & (pl.col("game_date") < gdate))
    b_rows = pa_idx.filter((pl.col("batter") == batter)
                           & (pl.col("game_date") < gdate))
    d = gdate - date(1970, 1, 1)
    # inline EW (90d half-life, weights 2^(dnum/90), strictly prior)
    def ew(rows, ycol):
        if rows.height == 0:
            return None, 0.0
        w = 2.0 ** ((rows["game_date"] - date(1970, 1, 1))
                    .dt.total_days() / HALF_LIFE_DAYS)
        return float((w * rows[ycol].cast(pl.Float64)).sum()
                     / w.sum()), float(w.sum())
    p_before_k = int(p_rows["y"].sum())
    p_rows_hist = pa_idx.filter((pl.col("pitcher") == pitcher)
                                & (pl.col("game_date") < gdate)
                                & (pl.col("game_date")
                                   >= date(1970, 1, 1)))
    ew_p, den_p = ew(p_rows_hist, "y")
    b_rows_hist = pa_idx.filter((pl.col("batter") == batter)
                                & (pl.col("game_date") < gdate))
    ew_b, den_b = ew(b_rows_hist, None) if False else \
        (float((p_rows_hist if False else b_rows_hist)
               .with_columns((2.0 ** ((pl.col("game_date")
                                       - pl.date(1970, 1, 1))
                              .dt.total_days() / HALF_LIFE_DAYS))
                             .alias("_w"))
               .select((pl.col("_w") * pl.col("y").cast(pl.Float64))
                       .sum()).item()), float(b_rows_hist.height))
    lg_rate = float(lg_state.filter(pl.col("game_date") < gdate)
                    ["lg_rate"][-1]) \
        if lg_state.filter(pl.col("game_date") < gdate).height else None
    recon = {
        "n_prior_pitcher": p_rows_hist.height,
        "n_prior_batter": b_rows_hist.height,
        "p_pitcher_prior_w150": ((p_rows_hist["y"].sum()
                                  + W_PRIOR * lg_rate)
                                 / (p_rows_hist.height + W_PRIOR)),
        "p_batter_prior_w150": ((b_rows_hist["y"].sum()
                                 + W_PRIOR * lg_rate)
                                / (b_rows_hist.height + W_PRIOR)),
        "ew_pitcher": ew_p, "ew_batter": ew_b,
        "cold_start": int((p_rows_hist.height == 0)
                          | (b_rows_hist.height == 0)),
    }
    led = sample.filter(pl.col("_rid") == rid).row(0, named=True)
    got_row = cmpB.filter(pl.col("_rid") == rid).row(0, named=True)
    recon_rows.append({
        "_rid": rid, "game_pk": r["game_pk"], "pitcher": r["pitcher"],
        "batter": r["batter"], "as_of": str(gdate),
        "ledger_n_prior_pitcher": led["n_prior_pitcher"],
        "ind_impl_n_prior": got_row["ind_np"],
        "historical_rows_n_prior": recon["n_prior_pitcher"],
        "ledger_p_rate": r["p_pitcher_prior_w150"],
        "historical_p_rate": recon["p_pitcher_prior_w150"],
    })
    print(f"  rid={rid} gpk={r['game_pk']} pitcher={r['pitcher']} "
          f"as_of={gdate}: ledger={recon['n_prior_pitcher']} "
          f"ind_impl={got_row['ind_np']} "
          f"hist_rows={recon['n_prior_pitcher']}", flush=True)
if recon_rows:
    pl.DataFrame(recon_rows).write_parquet(
        OUT / "partC_historical_reconciliation.parquet")

# ---- write-once outputs ------------------------------------------------
cmpA_path = OUT / "partA_frozen_vs_ledger.parquet"
cmp.write_parquet(cmpA_path)
cmp.write_parquet(OUT / "partA_frozen_vs_ledger.parquet")
cmpB.write_parquet(OUT / "partB_independent_vs_ledger.parquet")
adv_out = ad.attach_prior_features(
    pl.DataFrame({
        "_rid": ["adv1_cold_batter", "adv2_normal", "adv3_cold_pitcher",
                 "adv4_pre_data", "adv5_post_data"],
        "pitcher": [657277, 657277, 999999999, 657277, 657277],
        "batter": [999999999, 669194, 669194, 669194, 669194],
        "game_date": [date(2025, 5, 1), date(2025, 5, 1),
                      date(2025, 5, 1), date(2022, 3, 15),
                      date(2026, 12, 1)]}),
    p_state, b_state, lg_state)
adv_out.write_parquet(OUT / "adversarial_cases.parquet")
report = {"partA": resA, "partB": resB,
          "partC_n_surviving": len(mism_ids),
          "partC_sampled": min(len(mism_ids), 20),
          "note": "one-sided null/NaN counted as explicit mismatch"}
(OUT / "p0_v2_report.json").write_text(json.dumps(report, indent=1),
                                       encoding="utf-8")
print("written:", OUT)
