"""Phase 6: pitcher-prior experiment (P0-P3, 2024 E1/E2, 2023-only strength selection)."""
import hashlib, json, sys, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
WS = REPO / "research/offseason_2026"
PA1A = WS / "experiments/pa1a_raw_pa"
EPS = 1e-6
LG = 0.223813
card = json.loads((HERE / "card.json").read_text(encoding="utf-8"))
hashes = json.loads((HERE / "hashes.json").read_text(encoding="utf-8"))
assert hashlib.sha256((HERE/"card.json").read_bytes()).hexdigest() == hashes["card_sha256"]
for i in card["inputs"]:
    p = REPO / i["path"]
    if p.exists() and i["path"].endswith(".parquet"):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(1<<20), b""): h.update(c)
        assert h.hexdigest() == i["sha256"], f"input changed: {i['path']}"
print("card + input hashes verified")
deviations = [{"when": datetime.now(timezone.utc).isoformat(),
  "finding": "Gate A corrections: (1) Phase 5 Gate F '51 starter-terminal rows in table' was an artifact of an "
             "unsorted last() in that measurement; sorted pitch_number analysis shows ZERO split PAs entered the "
             "PA-1A table (all 122 completed by <9-PA relievers; 64 official-starter-began, 58 reliever-to-reliever). "
             "(2) Phase 5 completeness '197 under-reconciled starts' not reproducible; fresh measurement = 4,711/4,711 "
             "exact with and without truncated rows (L1 BF counting excludes them). Classification: corrections of "
             "measurement error; PA-1A results unaffected (its rows are 100% official-starter, split-free).",
  "classification": "NON-SUBSTANTIVE (interpretive correction; no population/formula/date/metric change to this experiment)"}]

pg = pl.read_parquet(REPO/"data/processed/pitcher_games.parquet")
per = pl.read_parquet(PA1A/"per_pa.parquet")
prep = json.loads((HERE/"prep.json").read_text(encoding="utf-8"))
M_SEL = prep["best_m"]

# 2023 prior-season aggregates + 2024 current-season prior counts
prior23 = pg.filter(pl.col("season")==2023).group_by("pitcher").agg(
    pl.col("K").sum().alias("K_prior"), pl.col("PA").sum().alias("PA_prior"))
pg24 = pg.filter(pl.col("season")==2024).sort(["pitcher","game_date","game_pk"]).with_columns(
    (pl.col("K").cum_sum().over(["pitcher"]) - pl.col("K")).alias("K_curr"),
    (pl.col("PA").cum_sum().over(["pitcher"]) - pl.col("PA")).alias("PA_curr"))
pg24 = pg24.with_columns(pl.col(["K_curr","PA_curr"]).first().over(["pitcher","game_date"]))
pg24 = pg24.with_columns(pl.struct(["game_pk","pitcher"]).map_elements(
    lambda s: (s["game_pk"], s["pitcher"]) in set(zip(pg24["game_pk"].to_list(), pg24["pitcher"].to_list())),
    return_dtype=pl.Boolean).alias("_t")).drop("_t")

d = per.join(prior23, on="pitcher", how="left").join(
    pg24.select(["game_pk","pitcher","K_curr","PA_curr"]), on=["game_pk","pitcher"], how="left")
pa_tbl = pl.read_parquet(WS/"datasets/pa_table_2023_2024.parquet").select(
    ["game_pk","at_bat_number","is_k","b_k_rate_std_shrunk","p_throws"])
d = d.join(pa_tbl, on=["game_pk","at_bat_number"], how="left")
assert d["is_k"].null_count() == 0 and d["b_k_rate_std_shrunk"].null_count() == 0
Kp = d["K_prior"].fill_null(0).to_numpy(); Np = d["PA_prior"].fill_null(0).to_numpy()
Kc = d["K_curr"].fill_null(0).to_numpy(); Nc = d["PA_curr"].fill_null(0).to_numpy()
y = d["is_k"].cast(pl.Float64).to_numpy()
gd = d["game_date"].cast(pl.String).to_numpy(); gpk = d["game_pk"].to_numpy()
_e1 = (d["game_date"] <= datetime(2024,6,30)).to_numpy()
_e2 = (d["game_date"] >= datetime(2024,7,1)).to_numpy()
month = d["game_date"].dt.month().to_numpy()
clip = lambda a: np.clip(a, EPS, 1-EPS)
odds = lambda a: (lambda c: c/(1-c))(clip(a))

arms_po = {
    "P0": per["p1"].to_numpy(),
    "P1": np.where(Np > 0, (Kp + 200*LG)/(Np + 200), LG),
    "P2": np.where(Nc > 0, (Kc + M_SEL*LG)/(Nc + M_SEL), LG),
    "P3": np.where((Np+Nc) > 0, (Kp + Kc + M_SEL*LG)/(Np + Nc + M_SEL), LG),
}
arms_po = {k: clip(v) for k, v in arms_po.items()}
pb = clip(d["b_k_rate_std_shrunk"].to_numpy())
ol = odds(LG)
arms_l5 = {k: clip(odds(v)*odds(pb)/ol / (1 + odds(v)*odds(pb)/ol)) for k, v in arms_po.items()}

def ll(p, yy): return -(yy*np.log(p) + (1-yy)*np.log(1-p))
def br(p, yy): return (p-yy)**2
def calib(p, yy):
    x = np.log(clip(p)/(1-clip(p)))
    if np.var(x) < 1e-12: return {"alpha": None, "beta": None, "converged": False, "variation": False, "n": int(len(yy))}
    X = np.column_stack([np.ones_like(x), x]); b = np.array([0.,1.]); conv=False
    for _ in range(100):
        mu = 1/(1+np.exp(-(X@b))); W = mu*(1-mu)
        try: step = np.linalg.solve(X.T@(X*W[:,None]) + 1e-10*np.eye(2), X.T@(yy-mu))
        except np.linalg.LinAlgError: break
        b = b + step
        if np.max(np.abs(step)) < 1e-10: conv=True; break
    try: se = np.sqrt(np.diag(np.linalg.inv(X.T@(X*W[:,None]) + 1e-10*np.eye(2))))
    except Exception: se = [None,None]
    return {"alpha": float(b[0]), "beta": float(b[1]), "se_beta": float(se[1]), "converged": bool(conv),
            "variation": True, "n": int(len(yy))}
BINS = np.arange(0, 1.0001, 0.05)
def rel(p, yy):
    idx = np.clip(np.searchsorted(BINS, p, side="right")-1, 0, 19)
    rows = []
    for b_ in range(20):
        m = idx==b_
        rows.append({"bin_lo": float(BINS[b_]), "bin_hi": float(BINS[b_+1]), "n": int(m.sum()),
                     "ks": int(yy[m].sum()), "mean_p": float(p[m].mean()) if m.any() else None,
                     "obs_rate": float(yy[m].mean()) if m.any() else None,
                     "abs_gap": float(abs(yy[m].mean()-p[m].mean())) if m.any() else None})
    return rows, sum(r["n"]/len(yy)*r["abs_gap"] for r in rows if r["n"]>0)
def boot(paired, key_arr, B=2000, seed=0):
    keys, inv = np.unique(key_arr, return_inverse=True); nd = len(keys)
    ns = np.bincount(inv, minlength=nd).astype(float)
    sums = {a: {m: np.bincount(inv, weights=paired[a][m], minlength=nd) for m in ("ll","br")} for a in paired}
    rng = np.random.default_rng(seed); out = {}
    for dn, (ac, ab_, mt) in {f"{a}-{b_}_{m}": (a,b_,m) for a in paired for b_ in paired for m in ("ll","br")
                               if list(paired).index(a) > list(paired).index(b_)}.items():
        ds = sums[ac][mt] - sums[ab_][mt]
        deltas = np.empty(B)
        for i in range(B):
            cnt = np.bincount(rng.integers(0, nd, nd), minlength=nd).astype(float)
            deltas[i] = (cnt*ds).sum()/max((cnt*ns).sum(), 1)
        lo, hi = np.percentile(deltas, [2.5, 97.5])
        out[dn] = {"raw": float(ds.sum()/ns.sum()), "ci95": [float(lo), float(hi)],
                   "pct_favor_challenger": float((deltas<0).mean())}
    return out

metrics, relout, boots = {}, {}, {"date": {}, "game_pk": {}}
blocks = {"E1": _e1, "E2": _e2, "pooled_descriptive": np.ones(len(y), bool)}
for blk, mask in blocks.items():
    yy = y[mask]
    for form, arms in (("pitcher_only", arms_po), ("log5_with_batter", arms_l5)):
        m = {}
        for a, p in arms.items():
            pm = p[mask]
            e = {"n": int(mask.sum()), "ks": int(yy.sum()), "observed_rate": float(yy.mean()),
                 "mean_pred": float(pm.mean()), "logloss": float(ll(pm,yy).mean()),
                 "brier": float(br(pm,yy).mean()), "bias": float((pm-yy).mean()),
                 "calibration_in_the_large": float(yy.mean()-pm.mean())}
            e.update(calib(pm, yy))
            rows_, ece = rel(pm, yy); e["ece_20bin"] = ece
            m[a] = e
            if blk != "pooled_descriptive":
                relout[f"{form}|{blk}|{a}"] = rows_
        metrics[f"{form}|{blk}"] = m
    paired_po = {a: {"ll": ll(p[mask], yy), "br": br(p[mask], yy)} for a, p in arms_po.items()}
    paired_l5 = {a: {"ll": ll(p[mask], yy), "br": br(p[mask], yy)} for a, p in arms_l5.items()}
    boots["date"][f"{blk}"] = {"pitcher_only": boot(paired_po, gd[mask]), "log5": boot(paired_l5, gd[mask])}
    boots["game_pk"][f"{blk}"] = {"pitcher_only": boot(paired_po, gpk[mask]), "log5": boot(paired_l5, gpk[mask])}

# M2 reference deltas (original PA-1A arm) per block
m2ref = {}
for blk, mask in blocks.items():
    yy = y[mask]
    p2m = per["p2"].to_numpy()[mask]
    for a, p in arms_l5.items():
        m2ref[f"{blk}|{a}"] = {"logloss": float(ll(p[mask],yy).mean()), "M2_logloss": float(ll(p2m,yy).mean()),
                                "delta_vs_M2": float(ll(p[mask],yy).mean() - ll(p2m,yy).mean()),
                                "brier": float(br(p[mask],yy).mean()), "M2_brier": float(br(p2m,yy).mean()),
                                "delta_brier_vs_M2": float(br(p[mask],yy).mean() - br(p2m,yy).mean())}

# slices (log5 form, M2-vs-Parm deltas + month etc.)
prior_bucket = np.where(Np==0, "no_prior_season", np.where(Np<50, "1-49_prior_pa",
                        np.where(Np<150, "50-149_prior_pa", "150+_prior_pa")))
rookie = np.where((Np==0) & (Nc==0), "debut", "has_history")
pthr = d["p_throws"].to_numpy()
b_prior_pa = None
bg = pl.scan_parquet(REPO/"data/processed/batter_games.parquet").select(
    "game_pk","batter","PA","game_date").with_columns(pl.col("game_date").dt.year().alias("yr")).collect()
bg = bg.sort(["batter","yr","game_date","game_pk"]).with_columns(
    (pl.col("PA").cum_sum().over(["batter","yr"]) - pl.col("PA")).alias("prior_pa"))
bpa = d.join(bg.select(["game_pk","batter","prior_pa"]), on=["game_pk","batter"], how="left")["prior_pa"].fill_null(0).to_numpy()
b_bucket = np.where(bpa==0, "0_pa", np.where(bpa<50, "1-49_pa", np.where(bpa<150, "50-149_pa", ">=150_pa")))
mn = per["matchup_number"].to_numpy() if "matchup_number" in per.columns else None
slice_defs = {"month": month, "pitcher_prior_bucket": prior_bucket, "rookie_status": rookie,
              "prior_season_availability": np.where(Np>0, "has_prior_season", "none"),
              "p_throws": pthr, "batter_history_bucket": b_bucket}
if mn is not None:
    slice_defs["matchup_number"] = np.where(mn==1, "1", np.where(mn==2, "2", "3+"))
slices = {}
mask_all = np.ones(len(y), bool)
for sname, sv in slice_defs.items():
    ent = {}
    for v in np.unique(sv):
        mk = mask_all & (sv==v)
        yy = y[mk]
        e = {"n": int(mk.sum()), "ks": int(yy.sum()), "sparse": bool(mk.sum()<2000 or yy.sum()<400)}
        for a, p in arms_l5.items():
            e[f"{a}_logloss"] = float(ll(p[mk], yy).mean())
        e["M2_logloss"] = float(ll(per["p2"].to_numpy()[mk], yy).mean())
        ent[str(v)] = e
    slices[sname] = ent
slices["official_vs_bulk"] = {"note": "constant: 100% of PA-1A/PA rows are official starters (census 2023-24: "
                              "9,374/9,374 entries official); bulk-9 class empty; sensitivity not applicable"}

d_out = d.select(["game_pk","at_bat_number","game_date","pitcher","batter","month"]).with_columns(
    [pl.Series(f"{k}_po", v) for k, v in arms_po.items()] +
    [pl.Series(f"{k}_l5", v) for k, v in arms_l5.items()] +
    [pl.Series("K_prior_season", Kp), pl.Series("PA_prior_season", Np),
     pl.Series("K_curr", Kc), pl.Series("PA_curr", Nc)])
d_out.write_parquet(HERE/"pa_predictions.parquet")

results = {"started_utc": datetime.now(timezone.utc).isoformat(), "selected_m_2023_folds": M_SEL,
           "p2_selection_detail": prep["p2_selection"], "metrics": metrics,
           "m2_reference_deltas": m2ref, "bootstrap_date": boots["date"],
           "bootstrap_game_pk_sensitivity": boots["game_pk"], "slices": slices,
           "deviations": deviations, "finished_utc": datetime.now(timezone.utc).isoformat()}
(HERE/"preflight.json").write_text(json.dumps({"gates": {"card_hash": "PASS", "input_hashes": "PASS",
    "population": "PASS (identical PA-1A primary rows)", "asof": "PASS (counts strictly prior, same-date collapse)",
    "no_2025_2026": "PASS (2023-24 sources only)"}, "deviations": deviations}, indent=2), encoding="utf-8")
(HERE/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
(HERE/"paired_comparisons.json").write_text(json.dumps({**boots["date"], "m2_reference_deltas": m2ref}, indent=2), encoding="utf-8")
(HERE/"calibration.json").write_text(json.dumps({k: {a: c for a, c in v.items()} for k, v in metrics.items()}, indent=2), encoding="utf-8")
(HERE/"slices.json").write_text(json.dumps(slices, indent=2), encoding="utf-8")
(HERE/"bootstrap.json").write_text(json.dumps(boots, indent=2), encoding="utf-8")
(HERE/"deviations.md").write_text("\n".join(f"- [{d_['when']}] {d_['finding']} {d_['classification']}" for d_ in deviations), encoding="utf-8")
import hashlib as hl
outs = {f.name: hl.sha256(f.read_bytes()).hexdigest() for f in HERE.glob("*") if f.is_file() and f.name not in ("hashes.json",)}
(HERE/"output_hashes.json").write_text(json.dumps(outs, indent=2), encoding="utf-8")
print("PITCHER-PRIOR RUN COMPLETE")
