"""Phase 7: regularized logistic PA challenger (L0-L3). Card hashed BEFORE fitting.
Fits on 2023 chronological folds only; one registered 2024 E1/E2 evaluation.
Writes ONLY under research/offseason_2026/experiments/logistic_pa/.
"""
import hashlib, json, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
WS = REPO / "research/offseason_2026"
PA1A = WS / "experiments/pa1a_raw_pa"
PP = WS / "experiments/pitcher_prior"
EPS = 1e-6
LG = 0.223813
CLIP = lambda a: np.clip(a, EPS, 1 - EPS)
ODDS = lambda a: (lambda c: c / (1 - c))(CLIP(a))

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def tree():
    import subprocess
    return {"dirty_paths": subprocess.run(["git","status","--porcelain"],capture_output=True,text=True,cwd=REPO).stdout.count("\n"),
            "head": subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,cwd=REPO).stdout.strip()}

# ---------- card (immutable once hashed) ----------
CARD = {
    "experiment_id": "LOGISTIC-PA-L", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "git": tree(),
    "label": "Trained logistic PA challenger research; development only; no production or betting claim",
    "inputs": [
        {"path": "research/offseason_2026/datasets/pa_table_2023_2024.parquet"},
        {"path": "data/processed/pitcher_games.parquet"},
        {"path": "data/processed/pitcher_rolling.parquet"},
        {"path": "data/processed/batter_games.parquet"},
        {"path": "data/processed/park_factors.parquet"},
        {"path": "research/offseason_2026/experiments/pitcher_prior/pa_predictions.parquet"},
        {"path": "research/offseason_2026/experiments/pa1a_raw_pa/per_pa.parquet"},
        {"path": "research/offseason_2026/experiments/pa1a_raw_pa/attribution_reconciliation.json"},
    ],
    "populations": {"fit": "2023 primary rows (105,225; truncated excluded; label+features only)",
                    "eval": "2024 E1 (55,815) and E2 (50,252) primary rows, identical across arms, ONE evaluation",
                    "aggregation": "4,711 official-starter starts, exact BF reconciliation"},
    "arms": {
        "L0": "P3-log5 (promoted Phase 6 baseline): 2024 = pitcher_prior P3_l5; 2023 = same formula from counts",
        "L1a": "logit(p) = a + 1*logit(p_L0)  (offset fixed, intercept only) - PRE-REGISTERED both modes",
        "L1b": "logit(p) = a + b*logit(p_L0)  (both estimated) - PRE-REGISTERED both modes; b-mode PRIMARY",
        "L2": "logit(p) = a + b*logit(p_L0) + g'x, ridge logistic on standardized x",
        "L3": "L2 + trip dummies (2,3,4+) + starter_pa_index/9 linear (pre-registered limited interactions)",
    },
    "families_L2": {
        "F1_platoon": ["same_hand_indicator", "b_hand_rate (b_vL if p_throws=L else b_vR)"],
        "F2_batter_discipline": ["b_whiff_rate_std", "b_swstr_rate_std", "b_chase_rate_std"],
        "F3_pitcher_discipline": ["whiff_rate_P5", "swstr_rate_P5", "chase_rate_P5", "zone_rate_P5",
                                   "contact_rate_P5", "whiff_rate_std*", "swstr_rate_std*", "chase_rate_std*",
                                   "zone_rate_std*", "contact_rate_std* (* joined from pitcher_rolling; both "
                                   "windows included by pre-registration; no per-window post-hoc selection)"],
        "F4_history_confidence": ["log1p(PA_curr)", "log1p(PA_prior_season)"],
        "F5_park": ["park_k_factor (prior-season EB, board-safe)"],
        "F6_rest": ["days_rest_capped (debut->15)", "is_season_debut"],
    },
    "interactions_L3": ["trip dummies 2/3/4+", "starter_pa_index/9"],
    "excluded_families": ["repertoire/velocity/movement (prior lift failed + schema drift risk)", "TTO beyond L3 terms",
                          "k_rate level (baseline input; excluded to avoid double-counting)", "weather/catcher/umpire"],
    "fold_design_2023": {"F1": "fit 03-30..06-30 -> eval 07-01..08-15", "F2": "fit 03-30..08-15 -> eval 08-16..10-01",
                          "uses": ["C grid {0.01,0.03,0.1,0.3,1,3} selection (mean fold eval logloss)",
                                    "family ablation (drop-one mean fold eval logloss delta)",
                                    "coefficient stability (F1-fit vs F2-fit signs/values)",
                                    "OOF permutation importance (20 perms/family, joint column permutation, "
                                    "mean eval logloss increase across folds)"]},
    "regularization": "L2 ridge, sklearn lbfgs, standardized on training fold; L1 arms C=1e6",
    "metrics": ["logloss primary", "brier", "CITL", "calib alpha/beta", "ECE-20bin fixed bins",
                 "reliability", "paired date-cluster bootstrap (B=2000, seed=0) vs L0",
                 "game_pk-cluster sensitivity", "slices: month, hand, batter-history, pitcher-history",
                 "oracle start-level MAE/RMSE/bias + paired bootstraps for promoted arm vs L0"],
    "promotion_gates": ["beats L0 PA logloss in BOTH E1 and E2", "brier improves or non-material degradation",
                         "no calibration collapse", "improves beyond L1b", "stable across months/major slices",
                         "survives oracle aggregation", "reproducible serving-safe construction"],
    "prohibited": ["trees/NN/PB", "projected lineups", "frozen TBF", "2025/2026", "calibration fitting for prediction",
                    "policy/betting", "production changes", "post-hoc feature addition", "pooled-only selection",
                    "dataset modification"],
}
card_p = HERE / "card.json"
card_p.write_text(json.dumps(CARD, indent=2), encoding="utf-8")
hashes = {"card_sha256": sha(card_p)}
# freeze input hashes into hashes.json now (before fitting)
for i in CARD["inputs"]:
    p = REPO / i["path"]
    i["sha256"] = sha(p)
card_p.write_text(json.dumps(CARD, indent=2), encoding="utf-8")
hashes["card_sha256"] = sha(card_p)
hashes["inputs"] = CARD["inputs"]
(HERE / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
print("card hashed:", hashes["card_sha256"][:16])
deviations = []

# ---------- data build ----------
pa = pl.read_parquet(WS / "datasets/pa_table_2023_2024.parquet")
tr = json.loads((PA1A / "attribution_reconciliation.json").read_text(encoding="utf-8"))["rows"]
trk = set((r["game_pk"], r["at_bat_number"]) for r in tr)
pa = pa.with_columns(pl.struct(["game_pk", "at_bat_number"]).map_elements(
    lambda s: (s["game_pk"], s["at_bat_number"]) in trk, return_dtype=pl.Boolean).alias("trunc_flag"))
prim = pa.filter(~pl.col("trunc_flag"))
pg = pl.read_parquet(REPO / "data/processed/pitcher_games.parquet")
pr = pl.read_parquet(REPO / "data/processed/pitcher_rolling.parquet")
pf = pl.read_parquet(REPO / "data/processed/park_factors.parquet")
pp = pl.read_parquet(PP / "pa_predictions.parquet").select(["game_pk", "at_bat_number", "P3_l5"])
STD_COLS = ["whiff_rate_std", "swstr_rate_std", "chase_rate_std", "zone_rate_std", "contact_rate_std"]

# season-to-date prior counts within each season (for L0 on 2023 and features)
pgs = pg.sort(["pitcher", "game_date", "game_pk"]).with_columns(
    (pl.col("K").cum_sum().over(["pitcher", "season"]) - pl.col("K")).alias("K_curr"),
    (pl.col("PA").cum_sum().over(["pitcher", "season"]) - pl.col("PA")).alias("PA_curr0"))
pgs = pgs.with_columns(pl.col(["K_curr", "PA_curr0"]).first().over(["pitcher", "game_date"]))
prior23 = pg.filter(pl.col("season") == 2023).group_by("pitcher").agg(
    pl.col("K").sum().alias("K_prior"), pl.col("PA").sum().alias("PA_prior"))
# rest features
pgs = pgs.with_columns(pl.col("game_date").shift(1).over(["pitcher", "season"]).alias("prev_date"))
pgs = pgs.with_columns(pl.col("prev_date").first().over(["pitcher", "game_date"]).alias("prev_date"))
pgs = pgs.with_columns([
    (pl.col("game_date") - pl.col("prev_date")).dt.total_days().alias("gap")])
pgs = pgs.with_columns([
    pl.when(pl.col("prev_date").is_null()).then(15).otherwise(pl.col("gap").clip(1, 15)).alias("days_rest_capped"),
    pl.when(pl.col("prev_date").is_null()).then(1).otherwise(0).cast(pl.Float64).alias("is_season_debut")])
pgs = pgs.with_columns(pl.when(pl.col("is_home") == 1).then(pl.col("home_team")).otherwise(pl.col("away_team")).alias("park_team"))

d = prim.filter(pl.col("season") == 2024).join(pgs.filter(pl.col("season") == 2024).select(
    ["game_pk", "pitcher", "K_curr", "PA_curr0", "days_rest_capped", "is_season_debut", "park_team"]),
    on=["game_pk", "pitcher"], how="left")
d = d.join(prior23.rename({"PA_prior": "PA_prior_season"}), on="pitcher", how="left")
d23 = prim.filter(pl.col("season") == 2023).join(
    pgs.filter(pl.col("season") == 2023).select(
        ["game_pk", "pitcher", "K_curr", "PA_curr0", "days_rest_capped", "is_season_debut", "park_team"]),
    on=["game_pk", "pitcher"], how="left")
d = d.join(pp, on=["game_pk", "at_bat_number"], how="left")
d = d.join(pr.select(["game_pk", "pitcher"] + STD_COLS), on=["game_pk", "pitcher"], how="left")
d23 = d23.join(pr.filter(pl.col("season") == 2023).select(["game_pk", "pitcher"] + STD_COLS),
               on=["game_pk", "pitcher"], how="left")
d = d.join(pf.rename({"home_team": "park_team"}), left_on=["season", "park_team"], right_on=["season", "park_team"], how="left")
d23 = d23.join(pf, left_on=["season", "park_team"], right_on=["season", "home_team"], how="left")

def build_l0(dd, season):
    if season == 2024:
        p_p = np.where(dd["PA_curr"].fill_null(0).to_numpy() + dd["PA_prior_season"].fill_null(0).to_numpy() > 0,
                        (dd["K_prior"].fill_null(0).to_numpy() if "K_prior" in dd.columns else 0), 0)  # placeholder
        return dd["P3_l5"].to_numpy()
    return None

# L0 for 2024 = P3_l5; L0 for 2023 = same formula (no prior season => P2-style)
def l0_2023(dd):
    Kc = dd["K_curr"].fill_null(0).to_numpy(); Nc = dd["PA_curr0"].fill_null(0).to_numpy()
    p_p = np.where(Nc > 0, (Kc + 100 * LG) / (Nc + 100), LG)
    p_b = CLIP(dd["b_k_rate_std_shrunk"].to_numpy())
    o = ODDS(p_p) * ODDS(p_b) / ODDS(LG)
    return CLIP(o / (1 + o))

d = d.with_columns(pl.col("game_date").dt.month().alias("month"))
d23 = d23.with_columns(pl.col("game_date").dt.month().alias("month"))
# sequence fields
both = pl.concat([d.select(["game_pk","pitcher","at_bat_number","season"]),
                  d23.select(["game_pk","pitcher","at_bat_number","season"])]).sort(
    ["game_pk","pitcher","at_bat_number"]).with_columns(
    pl.int_range(pl.len()).over(["game_pk","pitcher"]).add(1).alias("spi"))
spi_map = both.select(["game_pk","at_bat_number","spi"])
d = d.join(spi_map, on=["game_pk","at_bat_number"], how="left")
d23 = d23.join(spi_map, on=["game_pk","at_bat_number"], how="left")

# batter prior-PA (diagnostic) - joined BEFORE any predictions are computed (row alignment)
bpa = pl.read_parquet(REPO/"data/processed/batter_games.parquet").select(
    ["game_pk","batter","PA","game_date"]).with_columns(pl.col("game_date").dt.year().alias("yr")).sort(
    ["batter","yr","game_date","game_pk"]).with_columns(
    (pl.col("PA").cum_sum().over(["batter","yr"]) - pl.col("PA")).alias("prior_pa"))
d = d.join(bpa.select(["game_pk","batter","prior_pa"]), on=["game_pk","batter"], how="left")

def feat_matrix(df):
    ph = df["p_throws"].to_numpy(); st = df["stand"].to_numpy()
    same = (ph == st).astype(float)
    bl = df["b_k_rate_std_vL"].to_numpy(); br_ = df["b_k_rate_std_vR"].to_numpy()
    bhand = np.where(ph == "L", bl, br_)
    cols = {
        "same_hand": same,
        "b_hand_rate": np.nan_to_num(bhand, nan=LG),
        "b_whiff": df["b_whiff_rate_std"].to_numpy(), "b_swstr": df["b_swstr_rate_std"].to_numpy(),
        "b_chase": df["b_chase_rate_std"].to_numpy(),
        "p_whiff_P5": df["whiff_rate_P5"].to_numpy(), "p_swstr_P5": df["swstr_rate_P5"].to_numpy(),
        "p_chase_P5": df["chase_rate_P5"].to_numpy(), "p_zone_P5": df["zone_rate_P5"].to_numpy(),
        "p_contact_P5": df["contact_rate_P5"].to_numpy(),
        "p_whiff_std": df["whiff_rate_std"].to_numpy(), "p_swstr_std": df["swstr_rate_std"].to_numpy(),
        "p_chase_std": df["chase_rate_std"].to_numpy(), "p_zone_std": df["zone_rate_std"].to_numpy(),
        "p_contact_std": df["contact_rate_std"].to_numpy(),
        "log_pa_curr": np.log1p(df["PA_curr0"].fill_null(0).to_numpy()),
        "log_pa_prior": np.log1p(df["PA_prior_season"].fill_null(0).to_numpy()) if "PA_prior_season" in df.columns else np.zeros(len(df)),
        "park_k": np.nan_to_num(df["park_k_factor"].to_numpy(), nan=1.0),
        "rest": np.nan_to_num(df["days_rest_capped"].to_numpy(), nan=15.0),
        "debut": df["is_season_debut"].to_numpy(),
    }
    return cols

FAM = {"F1_platoon": ["same_hand", "b_hand_rate"],
       "F2_batter_discipline": ["b_whiff", "b_swstr", "b_chase"],
       "F3_pitcher_discipline": ["p_whiff_P5", "p_swstr_P5", "p_chase_P5", "p_zone_P5", "p_contact_P5",
                                  "p_whiff_std", "p_swstr_std", "p_chase_std", "p_zone_std", "p_contact_std"],
       "F4_history": ["log_pa_curr", "log_pa_prior"],
       "F5_park": ["park_k"], "F6_rest": ["rest", "debut"]}
def X_of(df, fams, l3=False):
    cols = feat_matrix(df)
    names = [c for f in fams for c in FAM[f]]
    X = np.column_stack([np.nan_to_num(cols[c], nan=0.0) for c in names])
    if l3:
        trip = df["spi"].to_numpy()
        t = 1 + (trip - 1) // 9
        X = np.column_stack([X, (t == 2).astype(float), (t == 3).astype(float), (t >= 4).astype(float),
                             trip / 9.0])
    return X, names

def fit_lr(X, y, C):
    return LogisticRegression(penalty="l2", C=C, solver="lbfgs", max_iter=2000).fit(X, y)

def prep(df):
    y = df["is_k"].cast(pl.Float64).to_numpy()
    l0 = df["P3_l5"].to_numpy() if "P3_l5" in df.columns and df["P3_l5"].null_count() == 0 and df["season"][0] == 2024 else l0_2023(df)
    x0 = np.log(CLIP(l0) / (1 - CLIP(l0)))
    return y, l0, x0

y24, l0_24, x0_24 = prep(d)
y23, l0_23, x0_23 = prep(d23)
X23, names = X_of(d23, list(FAM), l3=False)
X23_3, names3 = X_of(d23, list(FAM), l3=True)
X24, _ = X_of(d, list(FAM), l3=False)
X24_3, _ = X_of(d, list(FAM), l3=True)

gd23 = d23["game_date"].cast(pl.String).to_numpy()
f1_fit = gd23 <= "2023-06-30"; f1_ev = (gd23 >= "2023-07-01") & (gd23 <= "2023-08-15")
f2_fit = gd23 <= "2023-08-15"; f2_ev = gd23 >= "2023-08-16"
C_GRID = [0.01, 0.03, 0.1, 0.3, 1, 3]

def fold_eval(Xtr, ytr, x0tr, Xev, yev, x0ev, C, with_base=True):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Ztr = (Xtr - mu) / sd; Zev = (Xev - mu) / sd
    Xtr_ = np.column_stack([x0tr, Ztr]) if with_base else Ztr
    Xev_ = np.column_stack([x0ev, Zev]) if with_base else Zev
    m = LogisticRegression(penalty="l2", C=C, solver="lbfgs", max_iter=2000).fit(Xtr_, ytr)
    p = CLIP(m.predict_proba(Xev_)[:, 1])
    return p, m

def llm(p, y): return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))

# C selection on 2023 folds (L2 and L3)
selC = {}
for nm, (Xa, Xb) in {"L2": (X23, X23), "L3": (X23_3, X23_3)}.items():
    scores = {}
    for C in C_GRID:
        p1, _ = fold_eval(Xa[f1_fit], y23[f1_fit], x0_23[f1_fit], Xa[f1_ev], y23[f1_ev], x0_23[f1_ev], C)
        p2v, _ = fold_eval(Xb[f2_fit], y23[f2_fit], x0_23[f2_fit], Xb[f2_ev], y23[f2_ev], x0_23[f2_ev], C)
        scores[C] = (llm(p1, y23[f1_ev]) + llm(p2v, y23[f2_ev])) / 2
    bestC = min(scores, key=scores.get)
    selC[nm] = {"scores": {str(k): round(v, 6) for k, v in scores.items()}, "selected": bestC}
print("C selection:", json.dumps(selC["L2"]["scores"]), "-> L2", selC["L2"]["selected"],
      "| L3", selC["L3"]["selected"])

# L1 arms fit on 2023 (unregularized), evaluate 2024
def fit_l1(mode):
    Xtr = np.column_stack([x0_23]) if mode == "a" else np.column_stack([np.ones_like(x0_23), x0_23])
    Xtr = Xtr if mode == "a" else Xtr
    if mode == "a":
        m = LogisticRegression(penalty=None, fit_intercept=True, solver="lbfgs", max_iter=2000).fit(
            x0_23.reshape(-1, 1), y23)
    else:
        m = LogisticRegression(penalty=None, fit_intercept=True, solver="lbfgs", max_iter=2000).fit(
            x0_23.reshape(-1, 1), y23)
    # a: coefficient fixed 1 -> implement as offset: p = sigmoid(a + x0) => fit intercept-only on offset
    return m

# L1a: p = sigmoid(alpha + x0): fit intercept-only logistic with offset x0 via trick: feature = x0 with coef fixed
# implement manually (Newton) to fix coefficient:
def fit_offset(y, x0):
    b = 0.0
    for _ in range(200):
        eta = b + x0
        mu = 1 / (1 + np.exp(-eta))
        g = (y - mu).sum()
        h = -(mu * (1 - mu)).sum()
        step = g / h
        b -= step
        if abs(step) < 1e-10:
            break
    return b

b_offset = fit_offset(y23, x0_23)
m_l1b = LogisticRegression(penalty=None, solver="lbfgs", max_iter=2000).fit(x0_23.reshape(-1, 1), y23)
print("L1a alpha:", round(b_offset, 4), "| L1b alpha/beta:",
      round(float(m_l1b.intercept_[0]), 4), round(float(m_l1b.coef_[0][0]), 4))

# family ablation + permutation importance on folds (L2 with selected C)
C2 = selC["L2"]["selected"]
fam_names = {f: [names.index(c) for c in FAM[f]] for f in FAM}
ablation = {}
for f in FAM:
    keep = [i for i in range(len(names)) if i not in fam_names[f]]
    Xtr_ab = X23[np.ix_(f1_fit, keep)]; Xev_ab = X23[np.ix_(f1_ev, keep)]
    p_ab, _ = fold_eval(X23[f1_fit][:, keep], y23[f1_fit], x0_23[f1_fit], X23[f1_ev][:, keep],
                        y23[f1_ev], x0_23[f1_ev], C2)
    full_p, _ = fold_eval(X23[f1_fit], y23[f1_fit], x0_23[f1_fit], X23[f1_ev], y23[f1_ev], x0_23[f1_ev], C2)
    Xtr_ab2 = X23[f2_fit][:, keep]
    p_ab2, _ = fold_eval(X23[f2_fit][:, keep], y23[f2_fit], x0_23[f2_fit], X23[f2_ev][:, keep],
                         y23[f2_ev], x0_23[f2_ev], C2)
    full_p2, _ = fold_eval(X23[f2_fit], y23[f2_fit], x0_23[f2_fit], X23[f2_ev], y23[f2_ev], x0_23[f2_ev], C2)
    ablation[f] = {"f1_logloss_delta_drop": round(llm(p_ab, y23[f1_ev]) - llm(full_p, y23[f1_ev]), 6),
                    "f2_logloss_delta_drop": round(llm(p_ab2, y23[f2_ev]) - llm(full_p2, y23[f2_ev]), 6)}
print("family ablation (positive = family helps):", json.dumps(ablation))

rng = np.random.default_rng(0)
perm_imp = {}
for f in FAM:
    inc = []
    for fold_mask_fit, fold_mask_ev in ((f1_fit, f1_ev), (f2_fit, f2_ev)):
        p_full, m_full = fold_eval(X23[fold_mask_fit], y23[fold_mask_fit], x0_23[fold_mask_fit],
                                    X23[fold_mask_ev], y23[fold_mask_ev], x0_23[fold_mask_ev], C2)
        base = llm(p_full, y23[fold_mask_ev])
        Xev_p = X23[fold_mask_ev].copy()
        for _ in range(20):
            for cidx in fam_names[f]:
                Xev_p[:, cidx] = rng.permutation(Xev_p[:, cidx])
            p_p_, _ = fold_eval(X23[fold_mask_fit], y23[fold_mask_fit], x0_23[fold_mask_fit],
                                 Xev_p, y23[fold_mask_ev], x0_23[fold_mask_ev], C2)
            inc.append(llm(p_p_, y23[fold_mask_ev]) - base)
    perm_imp[f] = {"mean_logloss_increase": round(float(np.mean(inc)), 6)}
print("permutation importance:", json.dumps(perm_imp))

# final fits on all 2023, one 2024 evaluation
mu, sd = X23.mean(0), X23.std(0) + 1e-9
Z23 = (X23 - mu) / sd; Z24 = (X24 - mu) / sd
Z23_3 = (X23_3 - mu[: -0 or None]) if False else (X23_3 - X23_3.mean(0)) / (X23_3.std(0) + 1e-9)
Z24_3 = (X24_3 - X23_3.mean(0)) / (X23_3.std(0) + 1e-9)
mods = {}
mods["L2"] = LogisticRegression(penalty="l2", C=C2, solver="lbfgs", max_iter=2000).fit(
    np.column_stack([x0_23, Z23]), y23)
C3 = selC["L3"]["selected"]
mods["L3"] = LogisticRegression(penalty="l2", C=C3, solver="lbfgs", max_iter=2000).fit(
    np.column_stack([x0_23, Z23_3]), y23)
preds = {
    "L0": l0_24,
    "L1a": CLIP(1 / (1 + np.exp(-(b_offset + x0_24)))),
    "L1b": CLIP(m_l1b.predict_proba(x0_24.reshape(-1, 1))[:, 1]),
    "L2": CLIP(mods["L2"].predict_proba(np.column_stack([x0_24, Z24]))[:, 1]),
    "L3": CLIP(mods["L3"].predict_proba(np.column_stack([x0_24, Z24_3]))[:, 1]),
}
coef_report = {
    "L2": {"beta_logitP3": float(mods["L2"].coef_[0][0]),
            "coefs": {nm_: float(mods["L2"].coef_[0][i + 1]) for i, nm_ in enumerate(names)}},
    "L3": {"beta_logitP3": float(mods["L3"].coef_[0][0]),
            "coefs": {nm_: float(mods["L3"].coef_[0][i + 1]) for i, nm_ in enumerate(names)},
            "trip_dummies_and_index": [float(v) for v in mods["L3"].coef_[0][len(names) + 1:]]},
    "fold_stability": {},
}
# fold coefficient stability (L2)
cs = {}
for fm in (f1_fit, f2_fit):
    m_f = LogisticRegression(penalty="l2", C=C2, solver="lbfgs", max_iter=2000).fit(
        np.column_stack([x0_23[fm], (X23[fm] - mu) / sd]), y23[fm])
    cs["f1" if fm is f1_fit else "f2"] = [float(v) for v in m_f.coef_[0]]
signs = [int(np.sign(cs["f1"][i])) == int(np.sign(cs["f2"][i])) for i in range(1, len(names) + 1)]
coef_report["fold_stability"] = {"sign_agreement": f"{sum(signs)}/{len(signs)}",
                                  "f1": cs["f1"], "f2": cs["f2"]}

# 2024 evaluation
def rel(p, yy):
    BINS = np.arange(0, 1.0001, 0.05)
    idx = np.clip(np.searchsorted(BINS, p, side="right") - 1, 0, 19)
    rows = []
    for b_ in range(20):
        m_ = idx == b_
        rows.append({"bin_lo": float(BINS[b_]), "bin_hi": float(BINS[b_ + 1]), "n": int(m_.sum()),
                     "ks": int(yy[m_].sum()), "mean_p": float(p[m_].mean()) if m_.any() else None,
                     "obs_rate": float(yy[m_].mean()) if m_.any() else None,
                     "abs_gap": float(abs(yy[m_].mean() - p[m_].mean())) if m_.any() else None})
    return rows, sum(r["n"] / len(yy) * r["abs_gap"] for r in rows if r["n"] > 0)

def calib(p, yy):
    x = np.log(CLIP(p) / (1 - CLIP(p)))
    if np.var(x) < 1e-12: return {"alpha": None, "beta": None}
    X = np.column_stack([np.ones_like(x), x]); b = np.array([0., 1.])
    for _ in range(100):
        mu_ = 1 / (1 + np.exp(-(X @ b)))
        try: step = np.linalg.solve(X.T @ (X * (mu_ * (1 - mu_))[:, None]) + 1e-10 * np.eye(2), X.T @ (yy - mu_))
        except np.linalg.LinAlgError: break
        b = b + step
        if np.max(np.abs(step)) < 1e-10: break
    return {"alpha": float(b[0]), "beta": float(b[1])}

def llv(p, yy): return -(yy * np.log(p) + (1 - yy) * np.log(1 - p))
def brv(p, yy): return (p - yy) ** 2
gd24 = d["game_date"].cast(pl.String).to_numpy()
gpk24 = d["game_pk"].to_numpy()
_e1 = gd24 <= "2024-06-30"; _e2 = gd24 >= "2024-07-01"

def boot(pairs, keys, B=2000, seed=0):
    ku, inv = np.unique(keys, return_inverse=True); nd = len(ku)
    ns = np.bincount(inv, minlength=nd).astype(float)
    rng_ = np.random.default_rng(seed)
    out = {}
    for dn, (a, b_) in pairs.items():
        ds = np.bincount(inv, weights=a, minlength=nd) - np.bincount(inv, weights=b_, minlength=nd)
        dl = np.empty(B)
        for i in range(B):
            cnt = np.bincount(rng_.integers(0, nd, nd), minlength=nd).astype(float)
            dl[i] = (cnt * ds).sum() / max((cnt * ns).sum(), 1)
        lo, hi = np.percentile(dl, [2.5, 97.5])
        out[dn] = {"raw": float(ds.sum() / ns.sum()), "ci95": [float(lo), float(hi)],
                    "fav": float((dl < 0).mean())}
    return out

metrics, relout, boots = {}, {}, {}
yy24 = y24
for blk, mask in {"E1": _e1, "E2": _e2, "pooled_descriptive": np.ones(len(y24), bool)}.items():
    m = {}
    for a, p in preds.items():
        pm = p[mask]
        e = {"n": int(mask.sum()), "ks": int(yy24[mask].sum()), "observed_rate": float(yy24[mask].mean()),
             "mean_pred": float(pm.mean()), "logloss": float(llv(pm, yy24[mask]).mean()),
             "brier": float(brv(pm, yy24[mask]).mean()),
             "bias": float((pm - yy24[mask]).mean())}
        e.update(calib(pm, yy24[mask]))
        rows_, ece = rel(pm, yy24[mask]); e["ece_20bin"] = ece
        m[a] = e
        if blk != "pooled_descriptive":
            relout[f"{blk}|{a}"] = rows_
    metrics[blk] = m
    pairs = {f"{a}-{b_}": (llv(preds[a][mask], yy24[mask]), llv(preds[b_][mask], yy24[mask]))
             for a, b_ in [("L1b","L0"),("L2","L0"),("L3","L0"),("L2","L1b"),("L3","L1b"),("L1a","L0")]}
    pairs_br = {f"{a}-{b_}_br": (brv(preds[a][mask], yy24[mask]), brv(preds[b_][mask], yy24[mask]))
                for a, b_ in [("L1b","L0"),("L2","L0"),("L3","L0"),("L2","L1b"),("L3","L1b")]}
    boots[blk] = {**boot(pairs, gd24[mask]), **boot(pairs_br, gd24[mask])}
boots_gpk = {blk: {**boot({f"{a}-{b_}": (llv(preds[a][m_], yy24[m_]), llv(preds[b_][m_], yy24[m_]))
                  for a, b_ in [("L1b","L0"),("L2","L0"),("L3","L0"),("L2","L1b"),("L3","L1b")]}, gpk24[m_]),
                  **boot({f"{a}-{b_}_br": (brv(preds[a][m_], yy24[m_]), brv(preds[b_][m_], yy24[m_]))
                  for a, b_ in [("L2","L0"),("L3","L0"),("L2","L1b"),("L3","L1b")]}, gpk24[m_])}
           for blk, m_ in {"E1": _e1, "E2": _e2}.items()}

# slices
bpa = pl.read_parquet(REPO/"data/processed/batter_games.parquet").select(
    ["game_pk","batter","PA","game_date"]).with_columns(pl.col("game_date").dt.year().alias("yr")).sort(
    ["batter","yr","game_date","game_pk"]).with_columns(
    (pl.col("PA").cum_sum().over(["batter","yr"]) - pl.col("PA")).alias("prior_pa"))
d = d.join(bpa.select(["game_pk","batter","prior_pa"]), on=["game_pk","batter"], how="left")
bp = d["prior_pa"].fill_null(0).to_numpy()
b_bucket = np.where(bp==0, "0_pa", np.where(bp<50, "1-49_pa", np.where(bp<150, "50-149_pa", ">=150_pa")))
month = d["month"].to_numpy()
ph = d["PA_prior_season"].fill_null(0).to_numpy()
p_bucket = np.where(ph==0, "no_prior", np.where(ph<50, "1-49", np.where(ph<150, "50-149", ">=150")))
slices = {}
for sname, sv in {"month": month, "hand": d["p_throws"].to_numpy(),
                   "batter_history_bucket": b_bucket, "pitcher_prior_bucket": p_bucket}.items():
    ent = {}
    for v in np.unique(sv):
        mk = sv==v
        e = {"n": int(mk.sum()), "sparse": bool(mk.sum()<2000 or yy24[mk].sum()<400)}
        for a in ("L0","L1b","L2","L3"):
            e[f"{a}_logloss"] = round(float(llv(preds[a][mk], yy24[mk]).mean()), 6)
        ent[str(v)] = e
    slices[sname] = ent

# oracle aggregation for promoted candidates (L2, L3) vs L0 — aligned frame, no post-pred joins
pg24f = pg.filter(pl.col("season")==2024).select(["game_pk","pitcher","PA","K"])
agg = d.select(["game_pk","pitcher","game_date","is_k"]).with_columns(
    [pl.Series(a, preds[a]) for a in ("L0","L1b","L2","L3")])
g = agg.group_by(["game_pk","pitcher"]).agg(
    pl.len().alias("n_rows"), pl.col("game_date").first(),
    pl.col("is_k").cast(pl.Float64).sum().alias("actual_K"),
    *[pl.col(a).sum().alias(f"xK_{a}") for a in ("L0","L1b","L2","L3")])
AK = g["actual_K"].to_numpy()
gd_s = g["game_date"].cast(pl.String).to_numpy()
_e1s = gd_s <= "2024-06-30"; _e2s = gd_s >= "2024-07-01"
recchk = g.join(pg24f.rename({"PA":"official_BF","K":"official_K"}), on=["game_pk","pitcher"], how="left")
assert recchk["official_BF"].null_count() == 0
assert (recchk["n_rows"] == recchk["official_BF"]).all() and (recchk["actual_K"] == recchk["official_K"]).all()
agg_metrics = {}
for blk, mask in {"E1": _e1s, "E2": _e2s}.items():
    agg_metrics[blk] = {}
    for a in ("L0","L1b","L2","L3"):
        err = g[f"xK_{a}"].to_numpy()[mask] - AK[mask]
        agg_metrics[blk][a] = {"MAE": float(np.mean(np.abs(err))), "RMSE": float(np.sqrt(np.mean(err**2))),
                                "bias": float(np.mean(err))}
agg_pairs = {}
for blk, mask in {"E1": _e1s, "E2": _e2s}.items():
    pp_ = {}
    for a1, a2 in [("L2","L0"),("L3","L0"),("L1b","L0")]:
        e1 = g[f"xK_{a1}"].to_numpy()[mask] - AK[mask]; e2 = g[f"xK_{a2}"].to_numpy()[mask] - AK[mask]
        ku, inv = np.unique(gd_s[mask], return_inverse=True); nd = len(ku)
        ns = np.bincount(inv, minlength=nd).astype(float)
        s1 = np.bincount(inv, weights=np.abs(e1), minlength=nd); s2 = np.bincount(inv, weights=np.abs(e2), minlength=nd)
        rng_ = np.random.default_rng(0); dl = np.empty(2000)
        for i in range(2000):
            cnt = np.bincount(rng_.integers(0, nd, nd), minlength=nd).astype(float)
            dl[i] = (cnt*(s1-s2)).sum()/max((cnt*ns).sum(), 1)
        lo, hi = np.percentile(dl, [2.5, 97.5])
        pp_[f"{a1}-{a2}_MAE"] = {"raw": float(np.mean(np.abs(e1)-np.abs(e2))), "ci95": [float(lo), float(hi)],
                                  "fav": float((dl<0).mean())}
    agg_pairs[blk] = pp_

results = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "card_sha256": hashes["card_sha256"],
           "C_selection": selC, "L1a_alpha": b_offset,
           "L1b": {"alpha": float(m_l1b.intercept_[0]), "beta": float(m_l1b.coef_[0][0])},
           "family_ablation_folds": ablation, "permutation_importance_folds": perm_imp,
           "coefficients": coef_report, "metrics_2024": metrics, "slices": slices,
           "paired_date": boots, "paired_game_pk": boots_gpk, "aggregation": {"metrics": agg_metrics, "paired": agg_pairs},
           "deviations": deviations}
(HERE/"metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
pl.DataFrame([dict(r, arm_block=k) for k, rows_ in relout.items() for r in rows_]).write_parquet(HERE/"reliability.parquet")
preds_out = d.select(["game_pk","at_bat_number","game_date","pitcher","batter","month"]).with_columns(
    [pl.Series(a, preds[a]) for a in preds])
preds_out.write_parquet(HERE/"pa_predictions.parquet")
(HERE/"deviations.md").write_text("\n".join(f"- {x}" for x in deviations) or "none", encoding="utf-8")
outs = {f.name: sha(f) for f in HERE.glob("*") if f.is_file() and f.name != "output_hashes.json"}
(HERE/"output_hashes.json").write_text(json.dumps(outs, indent=2), encoding="utf-8")
print("PHASE 7 COMPLETE")





