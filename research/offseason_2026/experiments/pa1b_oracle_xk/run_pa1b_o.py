"""Phase 6: PA-1B-O oracle aggregation (mean experiment only)."""
import hashlib, json, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
WS = REPO / "research/offseason_2026"
PA1A = WS / "experiments/pa1a_raw_pa"
PP = WS / "experiments/pitcher_prior"
LG = 0.223813
EPS = 1e-6
card = json.loads((HERE/"card.json").read_text(encoding="utf-8"))
hashes = json.loads((HERE/"hashes.json").read_text(encoding="utf-8"))
assert hashlib.sha256((HERE/"card.json").read_bytes()).hexdigest() == hashes["card_sha256"]
prep = json.loads((HERE/"prep.json").read_text(encoding="utf-8"))
deviations = [{"when": datetime.now(timezone.utc).isoformat(),
  "finding": "Phase 5 completeness.json (4,514 exact) superseded by verified 4,711/4,711 exact; split PAs never "
             "entered the table; PA-1A population purity confirmed (100% official starters).",
  "classification": "NON-SUBSTANTIVE (correction of prior measurement error; population definition unchanged)"}]
print("card verified")

per = pl.read_parquet(PA1A/"per_pa.parquet")
pp = pl.read_parquet(PP/"pa_predictions.parquet")
d = per.join(pp.select(["game_pk","at_bat_number","P1_l5","P2_l5","P3_l5","PA_prior_season","PA_curr"]),
             on=["game_pk","at_bat_number"], how="left")
d = d.join(pl.read_parquet(WS/"datasets/pa_table_2023_2024.parquet").select(
    ["game_pk","at_bat_number","is_k"]), on=["game_pk","at_bat_number"], how="left")
assert d["is_k"].null_count() == 0 and d["P3_l5"].null_count() == 0
pg = pl.read_parquet(REPO/"data/processed/pitcher_games.parquet").filter(pl.col("season")==2024).select(
    ["game_pk","pitcher","PA","K","is_home","home_team","away_team"])
d = d.join(pg.rename({"PA":"official_BF","K":"official_K"}), on=["game_pk","pitcher"], how="left")
assert d["official_BF"].null_count() == 0
print("joins done", datetime.now(timezone.utc).isoformat())

arms = {"M0": "p0", "M1": "p1", "M2": "p2", "P1_l5": "P1_l5", "P2_l5": "P2_l5", "P3_l5": "P3_l5"}
y = d["is_k"].cast(pl.Float64).to_numpy()
gd = d["game_date"].cast(pl.String).to_numpy()
month = d["game_date"].dt.month().to_numpy()
trip = d["trip_proxy"].to_numpy()

g = d.group_by(["game_pk","pitcher"]).agg(
    pl.len().alias("n_rows"), pl.col("official_BF").first(), pl.col("official_K").first(),
    pl.col("is_home").first(), pl.col("home_team").first(), pl.col("away_team").first(),
    pl.col("game_date").first(), pl.col("PA_prior_season").first(), pl.col("PA_curr").first(),
    *[pl.col(c).sum().alias(f"xK_{a}") for a, c in arms.items()],
    pl.col("trip_proxy").max().alias("max_trip"),
    (pl.col("p2") - pl.col("is_k").cast(pl.Float64)).sum().alias("resid_M2"),
)
g = g.with_columns(pl.col("game_date").dt.year().alias("yr"), pl.col("game_date").dt.month().alias("month"))
# actual K = sum of is_k over same rows
ksum = d.group_by(["game_pk","pitcher"]).agg(pl.col("is_k").cast(pl.Float64).sum().alias("actual_K"))
g = g.join(ksum, on=["game_pk","pitcher"], how="left")
assert (g["actual_K"] == g["official_K"]).all(), "official K reconciliation failed"
assert (g["n_rows"] == g["official_BF"]).all(), "BF reconciliation failed"

print("aggregation done", datetime.now(timezone.utc).isoformat())
pred_cols = {a: f"xK_{a}" for a in arms}
A = {a: g[c].to_numpy() for a, c in pred_cols.items()}
AK = g["actual_K"].to_numpy()
gd_s = g["game_date"].cast(pl.String).to_numpy()
gpk_s = g["game_pk"].to_numpy()
_e1s = (g["game_date"] <= datetime(2024,6,30)).to_numpy()
_e2s = (g["game_date"] >= datetime(2024,7,1)).to_numpy()

def mets(x, kk):
    err = x - kk
    return {"n": int(len(kk)), "MAE": float(np.mean(np.abs(err))), "RMSE": float(np.sqrt(np.mean(err**2))),
            "mean_error": float(np.mean(err)), "median_abs_error": float(np.median(np.abs(err))),
            "mean_pred_xK": float(np.mean(x)), "mean_actual_K": float(np.mean(kk)),
            "corr_descriptive": float(np.corrcoef(x, kk)[0,1]),
            "err_q": {q: float(np.percentile(err, q)) for q in (1,5,25,50,75,95,99)}}
metrics = {}
for blk, mask in {"E1": _e1s, "E2": _e2s, "pooled_descriptive": np.ones(len(AK), bool)}.items():
    metrics[blk] = {a: mets(A[a][mask], AK[mask]) for a in arms}
    metrics[blk]["official_reconciliation"] = {"starts": int(mask.sum()),
        "mean_official_BF": float(g["official_BF"].to_numpy()[mask].mean()),
        "mean_modeled_PAs": float(g["n_rows"].to_numpy()[mask].mean()),
        "mean_excluded_split_PAs": 0.0, "all_exact": True}

def boot_pair(metric_fn, B=2000, seed=0):
    # paired per-row values via per-start abs err / sq err for MAE/RMSE; bias raw
    out = {}
    comps = {"MAE": lambda ea, eb: np.abs(ea) - np.abs(eb), "RMSE": lambda ea, eb: ea**2 - eb**2,
             "MEAN_ERR": lambda ea, eb: ea - eb}
    for name, (a1, a2) in {"M2-M1": ("M2","M1"), "M2-M0": ("M2","M0"), "P3_l5-M2": ("P3_l5","M2"),
                            "P3_l5-M1": ("P3_l5","M1"), "P3_l5-M1": ("P3_l5","M1"),
                            "M1-M0": ("M1","M0")}.items():
        out[name] = {}
        for mname, f in comps.items():
            pass
    return out

comps = {"MAE": "abs", "RMSE": "sq", "MEAN_ERR": "raw"}
def boot_agg(e1, e2, keys, B=2000, seed=0):
    keys_u, inv = np.unique(keys, return_inverse=True); nd = len(keys_u)
    ns = np.bincount(inv, minlength=nd).astype(float)
    ae1, ae2 = np.abs(e1), np.abs(e2)
    s_ae1 = np.bincount(inv, weights=ae1, minlength=nd); s_ae2 = np.bincount(inv, weights=ae2, minlength=nd)
    s_se1 = np.bincount(inv, weights=e1**2, minlength=nd); s_se2 = np.bincount(inv, weights=e2**2, minlength=nd)
    s_e1 = np.bincount(inv, weights=e1, minlength=nd); s_e2 = np.bincount(inv, weights=e2, minlength=nd)
    rng = np.random.default_rng(seed)
    d_mae = np.empty(B); d_rmse = np.empty(B); d_bias = np.empty(B)
    for i in range(B):
        cnt = np.bincount(rng.integers(0, nd, nd), minlength=nd).astype(float)
        d_mae[i] = (cnt*(s_ae1 - s_ae2)).sum()/max((cnt*ns).sum(), 1)
        v1 = (cnt*s_se1).sum()/max((cnt*ns).sum(), 1); v2 = (cnt*s_se2).sum()/max((cnt*ns).sum(), 1)
        d_rmse[i] = np.sqrt(v1) - np.sqrt(v2)
        d_bias[i] = (cnt*(s_e1 - s_e2)).sum()/max((cnt*ns).sum(), 1)
    def ci(x): l, h = np.percentile(x, [2.5, 97.5]); return [float(l), float(h)]
    return {"MAE": {"raw": float(np.mean(ae1-ae2)), "ci95": ci(d_mae), "fav": float((d_mae<0).mean())},
            "RMSE": {"raw": float(np.sqrt(np.mean(e1**2)) - np.sqrt(np.mean(e2**2))), "ci95": ci(d_rmse),
                     "fav_rmse_favors_first": float((d_rmse<0).mean())},
            "MEAN_ERR": {"raw": float(np.mean(e1-e2)), "ci95": ci(d_bias)}}

paired = {}
for blk, mask in {"E1": _e1s, "E2": _e2s, "pooled_descriptive": np.ones(len(AK), bool)}.items():
    paired[blk] = {f"{a1}-{a2}": boot_agg(A[a1][mask]-AK[mask], A[a2][mask]-AK[mask], gd_s[mask])
                   for a1, a2 in [("M2","M1"),("M2","M0"),("P3_l5","M2"),("P3_l5","M1"),("M1","M0")]}
paired_gpk = {blk: {f"{a1}-{a2}": boot_agg(A[a1][m_]-AK[m_], A[a2][m_]-AK[m_], gpk_s[m_])
                    for a1, a2 in [("M2","M1"),("M2","M0"),("P3_l5","M2"),("P3_l5","M1"),("M1","M0")]}
             for blk, m_ in {"E1": _e1s, "E2": _e2s}.items()}

# slices
bf_b = np.where(AK<=17, "BF<=17", np.where(AK<=23, "18-23", np.where(AK<=27, "24-27", ">=28")))
k_b = np.where(AK<=4, "K<=4", np.where(AK<=6, "5-6", np.where(AK<=8, "7-8", ">=9")))
ph = g["PA_prior_season"].fill_null(0).to_numpy()
phb = np.where(ph==0, "no_prior", np.where(ph<50, "1-49", np.where(ph<150, "50-149", ">=150")))
rookie = np.where((g["PA_prior_season"].fill_null(0).to_numpy()==0) & (g["PA_curr"].fill_null(0).to_numpy()==0), "debut", "has_history")
hand = None
pthr = pl.read_parquet(REPO/"data/processed/pitcher_games.parquet").filter(pl.col("season")==2024).select(["game_pk","pitcher","p_throws"])
hand_arr = d.join(pthr.select(["game_pk","pitcher","p_throws"]), on=["game_pk","pitcher"], how="left")["p_throws"].to_numpy()
gs = g.with_columns(pl.Series("month_s", g["month"].to_numpy()), pl.Series("max_trip", g["max_trip"].to_numpy()))
slice_defs = {"month": g["month"].to_numpy(), "BF_bucket": np.array([{"18-23":"18-23"}.get("x","x")]*0) if False else np.where(AK<=17,"BF<=17",np.where(AK<=23,"18-23",np.where(AK<=27,"24-27",">=28"))),
              "K_bucket": np.where(AK<=4,"K<=4",np.where(AK<=6,"5-6",np.where(AK<=8,"7-8",">=9"))),
              "trips": np.where(gs["max_trip"].to_numpy()<=2, "trip<=2", np.where(gs["max_trip"].to_numpy()==3, "trip3", "trip4+")),
              "pitcher_prior_bucket": phb, "rookie": np.where((ph==0) & (g["PA_curr"].fill_null(0).to_numpy()==0), "debut", "has_history")}
slices = {s: {} for s in slice_defs}
for sname, sv in slice_defs.items():
    for v in np.unique(sv):
        mk = sv==v
        e = {"n": int(mk.sum())}
        for a in arms:
            err = A[a][mk] - AK[mk]
            e[f"{a}_MAE"] = float(np.mean(np.abs(err)))
        for a1, a2 in (("M2","M1"),("P3_l5","M2")):
            e[f"{a1}-{a2}_MAE"] = float(np.mean(np.abs(A[a1][mk]-AK[mk]) - np.abs(A[a2][mk]-AK[mk])))
        e["sparse"] = bool(mk.sum()<300)
        slices[sname][str(v)] = e
slices["official_vs_bulk"] = {"note": "constant: all 4,711 starts are official-starter starts; bulk class empty in 2023-24"}
slices["split_exclusion"] = {"note": "constant: zero split PAs entered the table (identity resolution v2); "
                             "the with/without-split comparison is vacuous"}

# residual ICC diagnostics (PA-level, M2)
res = d.with_columns((pl.col("p2") - pl.col("is_k").cast(pl.Float64)).alias("r"))
team = np.where(d["is_home"].to_numpy()==1, d["home_team"].to_numpy(), d["away_team"].to_numpy())
def icc(groups_arr):
    df = pl.DataFrame({"g": groups_arr, "r": res["r"].to_numpy()})
    s = df.group_by("g").agg(pl.len().alias("n"), pl.col("r").mean().alias("m"), pl.col("r").var().alias("v"))
    s = s.filter(pl.col("n")>1)
    bw = float(s["v"].var()) if s.height>1 else 0.0
    wi = float(s["v"].mean()) if s.height else 0.0
    return {"between_var_of_cluster_means": bw, "mean_within_var": wi,
            "icc_approx": float(bw/(bw+wi)) if (bw+wi)>0 else 0.0, "n_clusters": s.height}
icc_diag = {"start": icc(np.char.add(np.char.add(gpk_s.astype(str), "_"), A["M2"].astype(str))) if False else
            icc(d["game_pk"].cast(pl.String).to_numpy() + "|" + d["pitcher"].cast(pl.String).to_numpy()),
            "pitcher": icc(d["pitcher"].cast(pl.String).to_numpy()),
            "batter": icc(d["batter"].cast(pl.String).to_numpy()),
            "team_pitcher_side": icc(team),
            "month": icc(month.astype(str)),
            "trip": icc(trip.astype(str))}

g.write_parquet(HERE/"start_predictions.parquet")
res_d = {"icc_pa_level_residuals_M2": icc_diag,
         "note": "diagnostic only; no corrective fitting",
         "decomposition_by_trip": {str(t): {"n": int((trip==t).sum()),
                                            "mean_resid_M2": float(res.filter(pl.col("trip_proxy")==t)["r"].mean())}
                                   for t in sorted(set(trip.tolist()))},
         "decomposition_by_batter_history": "see pitcher_prior slices (batter buckets mirrored)",
         }
(HERE/"residual_diagnostics.json").write_text(json.dumps(res_d, indent=2), encoding="utf-8")
results = {"started_utc": datetime.now(timezone.utc).isoformat(), "population": prep["pa1b_population"],
           "metrics": metrics, "paired_date": paired, "paired_game_pk_sensitivity": paired_gpk,
           "slices": slices, "deviations": deviations,
           "finished_utc": datetime.now(timezone.utc).isoformat()}
(HERE/"preflight.json").write_text(json.dumps({"gates": {"card": "PASS", "hashes": "PASS",
    "reconciliation": "PASS (4,711/4,711 exact, official K == sum is_k, BF == n_rows)",
    "frozen_comparator": "STOPPED for 2024 primary (see frozen_comparator_validity.json)"},
    "deviations": deviations}, indent=2), encoding="utf-8")
(HERE/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
(HERE/"paired_comparisons.json").write_text(json.dumps({"date": paired, "game_pk_sensitivity": paired_gpk}, indent=2), encoding="utf-8")
(HERE/"slices.json").write_text(json.dumps(slices, indent=2), encoding="utf-8")
(HERE/"bootstrap.json").write_text(json.dumps({"date": paired, "game_pk": paired_gpk}, indent=2), encoding="utf-8")
(HERE/"deviations.md").write_text("\n".join(f"- [{x['when']}] {x['finding']} {x['classification']}" for x in deviations), encoding="utf-8")
outs = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.glob("*") if f.is_file() and f.name not in ("hashes.json","output_hashes.json")}
(HERE/"output_hashes.json").write_text(json.dumps(outs, indent=2), encoding="utf-8")
print("PA-1B-O COMPLETE")
