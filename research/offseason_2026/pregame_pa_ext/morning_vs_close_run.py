"""Frozen morning-vs-near-close evaluation (owner-ordered, protocol
frozen at e5a2ccc; run at b2a4298).

Cohort: the published morning_close_cohort_v1 (2,109 starts, key hash
aadc2d2a3caa104fd6629c7b7057d8de422d4b0aa6afe51c3de75d404495d5aa).
Each market scored at ITS OWN quoted line (different lines are
different binary contracts). Model probabilities: the frozen count
layer's PMFs (count_agg_eval_v1, unchanged). No tuning.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2\research\offseason_2026")
sys.path.insert(0, r"C:\Users\ckaplinger\MLB-Props-Research\odds-coverage-v1")
from pregame_pa_ext import adapter as ad
from pregame_pa_ext import batt_recency as br
from pregame_pa_ext import market_eval_k as mk
from pregame_pa_ext import m0_multiclass as m0
import join_coverage as jc

import kcount_combiner as kc

OUT = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
           r"\diagnostics\morning_vs_close_v1_attempt11")
OUT.mkdir(exist_ok=False)

# ---- the frozen cohort keys ------------------------------------------
cohort = pl.read_parquet(r"C:\Users\ckaplinger\MLB-Props-Research"
                         r"\pregame-pa-ext-v2\diagnostics"
                         r"\morning_close_cohort_v1"
                         r"\morning_close_overlap_cohort.parquet")
key_rows = ["%d|%s|%d" % (r["game_pk"], r["side"], r["pitcher"])
            for r in cohort.select("game_pk", "side", "pitcher")
            .sort("game_pk", "side", "pitcher").iter_rows(named=True)]
cohort_hash = hashlib.sha256("\n".join(key_rows).encode()).hexdigest()
stored = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"
              r"\diagnostics\morning_close_cohort_v1"
              r"\cohort_key_hash.txt").read_text(encoding="utf-8").strip()
assert cohort_hash == stored, f"cohort hash drift: {cohort_hash}"
print("cohort: 2,109 starts, key hash", cohort_hash[:16], flush=True)

# ---- verified quotes: own-player filter + near-close/morning ----------
starts_out, odds, meta = jc.build_task_frames(
    Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data"
         r"\Odds-Historical\theoddsapi\book_lines_pitcher.parquet"),
    Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data"
         r"\Odds-Historical\theoddsapi\snapshot_envelope.parquet"),
    ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet",
    ["pitcher_strikeouts"], window_start="2024-07-01",
    window_end="2025-06-30")
odds = odds.join(
    starts_out.select("game_pk", "pitcher_key", "first_pitch_ts",
                      "has_commence"),
    on="game_pk", how="inner")
odds = mk.verified_odds_for_start(odds).filter(pl.col("has_commence"))
odds = odds.with_columns(
    pl.col("quote_timestamp").str.to_datetime(time_zone="UTC",
                                              strict=False)
    .alias("quote_timestamp")).filter(
    pl.col("quote_timestamp").is_not_null())

near_close = mk.select_near_close(odds)  # vendor close clock (T-5)
morning = (odds.filter(pl.col("snapshot") == "morning")
           .filter(pl.col("quote_timestamp") < pl.col("first_pitch_ts"))
           .sort("quote_timestamp").unique(
               subset=["game_pk", "pitcher", "book", "line", "side"],
               keep="last"))

cons_close = mk.consensus_over_probs(near_close).rename(
    {"pitcher": "quoted_key", "line": "line_close",
     "p_over": "p_over_close", "n_books": "n_books_close"})
cons_morn = mk.consensus_over_probs(morning).rename(
    {"pitcher": "quoted_key", "line": "line_morning",
     "p_over": "p_over_morning", "n_books": "n_books_morning"})
# map the vendor quoted key to the MLBAM start identity; the consensus
# carries no team side (it is per quoted pitcher), so drop nothing else
key_map = starts_out.select("game_pk", "pitcher_key", pl.col("pitcher").alias("pitcher_id"))
cons_close = (cons_close.join(key_map, left_on=["game_pk",
                                                "quoted_key"],
                              right_on=["game_pk", "pitcher_key"],
                              how="inner")
              )
cons_morn = (cons_morn.join(key_map, left_on=["game_pk",
                                              "quoted_key"],
                            right_on=["game_pk", "pitcher_key"],
                            how="inner")
             )

# ---- model PMFs + the frozen cohort ----------------------------------
pmfs = pl.read_parquet(r"C:\Users\ckaplinger\MLB-Props-Research"
                       r"\pregame-pa-ext-v2\diagnostics"
                       r"\count_agg_eval_v1\count_agg_eval_v1.parquet")

joined = (cohort.join(pmfs, on=["game_pk", "side", "pitcher"],
                      how="inner")
          .join(cons_close.select("game_pk", "pitcher_id", "line_close",
                                  "p_over_close", "n_books_close")
                  .rename({"pitcher_id": "pitcher"}),
                on=["game_pk", "pitcher"], how="inner")
          .join(cons_morn.select("game_pk", "pitcher_id", "line_morning",
                                 "p_over_morning", "n_books_morning")
                  .rename({"pitcher_id": "pitcher"}),
                on=["game_pk", "pitcher"], how="inner"))
print("common cohort scored:", joined.height, flush=True)
coverage = {
    "cohort_starts": int(cohort.height),
    "cohort_key_hash": cohort_hash,
    "scored_common": int(joined.height),
    "drops": {
        "no_model_pmf": int(cohort.height
                            - cohort.join(pmfs, on=["game_pk", "side",
                                                    "pitcher"],
                                          how="inner").height),
        "no_near_close_consensus": int(
            cohort.join(pmfs, on=["game_pk", "side", "pitcher"],
                        how="inner")
            .join(cons_close.select("game_pk", "pitcher_id")
                  .rename({"pitcher_id": "pitcher"}),
                  on=["game_pk", "pitcher"], how="anti").height),
        "no_morning_consensus": int(
            cohort.join(pmfs, on=["game_pk", "side", "pitcher"],
                        how="inner")
            .join(cons_morn.select("game_pk", "pitcher_id")
                  .rename({"pitcher_id": "pitcher"}),
                  on=["game_pk", "pitcher"], how="anti").height),
    },
    "join_meta": meta,
}

eps = 1e-12
o = joined["realized_k"].to_numpy().astype(float)


def score(line_col, p_col):
    line = joined[line_col].to_numpy()
    over = (joined["realized_k"].to_numpy() > line).astype(float)
    p = joined[p_col].to_numpy()
    ll = float(-(over * np.log(p + eps)
                 + (1 - over) * np.log(1 - p + eps)).mean())
    br = float(((p - over) ** 2).mean())
    return over, p, ll, br


# model at each market's own line
model_morn = []
model_close = []
for r in joined.iter_rows(named=True):
    pmf = np.asarray(r["pmf_baseline"], dtype=np.float64)
    model_morn.append(mk.model_p_over(pmf, float(r["line_morning"])))
    model_close.append(mk.model_p_over(pmf, float(r["line_close"])))
model_morn = np.asarray(model_morn)
model_close = np.asarray(model_close)

rows = []
oc, pc_m, pc_c, o_m, o_c = None, None, None, None, None
for tag, line_c, p_c_col in (("morning", "line_morning",
                              "p_over_morning"),
                             ("near_close", "line_close",
                              "p_over_close")):
    line = joined[line_c].to_numpy()
    over = (joined["realized_k"].to_numpy() > line).astype(float)
    p_mkt = joined[p_c_col].to_numpy()
    p_mod = model_morn if tag == "morning" else model_close
    ll_mkt = float(-(over * np.log(p_mkt + eps)
                     + (1 - over) * np.log(1 - p_mkt + eps)).mean())
    ll_mod = float(-(over * np.log(p_mod + eps)
                     + (1 - over) * np.log(1 - p_mod + eps)).mean())
    br_mkt = float(((p_mkt - over) ** 2).mean())
    br_mod = float(((p_mod - over) ** 2).mean())
    rows.append({"market": tag, "n": int(joined.height),
                 "model_log_loss": ll_mod, "market_log_loss": ll_mkt,
                 "model_brier": br_mod, "market_brier": br_mkt,
                 "delta_model_minus_market": ll_mod - ll_mkt})

# paired slate-date CIs (model - market) per market
cmp_mod = br.load_registered_comparison()
dates = joined["game_date"].to_list()
blocks = joined["block"].to_list()
for tag, p_mkt_col, p_mod in (("morning", "p_over_morning",
                               model_morn),
                              ("near_close", "p_over_close",
                               model_close)):
    line = joined[("line_morning" if tag == "morning"
                   else "line_close")].to_numpy()
    over = (joined["realized_k"].to_numpy() > line).astype(float)
    ll_mkt = -(over * np.log(joined[p_mkt_col].to_numpy() + eps)
               + (1 - over) * np.log(1 - joined[p_mkt_col].to_numpy()
                                     + eps))
    ll_mod = -(over * np.log(p_mod + eps)
               + (1 - over) * np.log(1 - p_mod + eps))
    r = cmp_mod.slate_date_draws({"model": ll_mod, "market": ll_mkt},
                                 dates, blocks, n_boot=2000,
                                 seed=20261001)
    d = r[:, 0] - r[:, 1]
    for row in rows:
        if row["market"] == tag:
            row["delta_model_minus_market_ci95"] = [
                float(np.percentile(d, 2.5)),
                float(np.percentile(d, 97.5))]

print()
print("== TWO-ROW TABLE (common cohort, each market at its own line) ==")
for row in rows:
    print(f"  {row['market']:>10}: n={row['n']} "
          f"model ll={row['model_log_loss']:.4f} "
          f"market ll={row['market_log_loss']:.4f} "
          f"delta={row['delta_model_minus_market']:+.4f} "
          f"CI={row['delta_model_minus_market_ci95']}")
    print(f"              model brier={row['model_brier']:.4f} "
          f"market brier={row['market_brier']:.4f}")

# ---- complete-cohort near-close baseline (SEPARATE) -------------------
ev = pl.read_parquet(r"C:\Users\ckaplinger\MLB-Props-Research"
                     r"\pregame-pa-ext-v2\diagnostics"
                     r"\market_eval_k_v3_fullkey_attempt2"
                     r"\market_eval_k_v1.parquet")
tAll = ev
oc = (tAll["realized_k"].to_numpy()
      > tAll["line"].to_numpy()).astype(float)
pc = tAll["p_over"].to_numpy()
pmc = tA_pmod = None
pmc = tAll.join(pmfs.select("game_pk", "side", "pitcher",
                            "pmf_baseline"),
                on=["game_pk", "side", "pitcher"],
                how="left") if False else None
# model p_over for the complete cohort is already in the parquet
pmc = tAll["p_over_model"].to_numpy()
ll_c = float(-(oc * np.log(pc + eps)
               + (1 - oc) * np.log(1 - pc + eps)).mean())
ll_m = float(-(oc * np.log(pmc + eps)
               + (1 - oc) * np.log(1 - pmc + eps)).mean())
print()
print("== COMPLETE-cohort near-close baseline (SEPARATE, n=%d) =="
      % tAll.height)
print(f"  close: ll={ll_c:.4f}  model: ll={ll_m:.4f}  "
      f"delta={ll_m - ll_c:+.4f}")

# ---- write-once outputs ------------------------------------------------
out_rows = pl.DataFrame({
    "game_pk": joined["game_pk"], "side": joined["side"],
    "pitcher": joined["pitcher"], "game_date": joined["game_date"],
    "block": joined["block"], "realized_k": joined["realized_k"],
    "line_morning": joined["line_morning"],
    "p_over_morning": joined["p_over_morning"],
    "line_close": joined["line_close"],
    "p_over_close": joined["p_over_close"],
    "p_over_model_morning": model_morn,
    "p_over_model_close": model_close,
})
out_rows.write_parquet(OUT / "morning_vs_close_v1_attempt11.parquet")
report = {"rows": rows, "coverage": coverage,
          "complete_cohort_near_close": {
              "n": int(tAll.height), "close_ll": ll_c, "model_ll": ll_m,
              "delta": ll_m - ll_c},
          "code_sha": "b2a4298",
          "cohort_hash": cohort_hash}
(OUT / "metrics.json").write_text(json.dumps(report, indent=1,
                                              sort_keys=True),
                                  encoding="utf-8")
print("written:", OUT)
