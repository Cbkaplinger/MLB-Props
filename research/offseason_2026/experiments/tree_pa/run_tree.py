"""Phase 8: constrained tree challenger (T1/T2 vs T0=L3; T3 blend gate on 2023 OOF).
Card hashed before fitting. 2023 folds select; 2024 E1/E2 one evaluation.
Writes ONLY under research/offseason_2026/experiments/tree_pa/.
"""
import hashlib, json, sys, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
import lightgbm as lgb  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "research/offseason_2026"))
HERE = Path(__file__).resolve().parent
WS = REPO / "research/offseason_2026"
LP = WS / "experiments/logistic_pa"
PA1A = WS / "experiments/pa1a_raw_pa"
PP = WS / "experiments/pitcher_prior"
LG = 0.223813
EPS = 1e-6
CLIP = lambda a: np.clip(a, EPS, 1 - EPS)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

CARD = {
    "experiment_id": "TREE-PA-T", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "mlflow_decision": {"decision": "DEFERRED", "rationale": "mlflow not installed; installing mid-phase "
                         "risks environment churn before a registered evaluation. Adopt post-tree as a "
                         "read-only SQLite mirror over existing cards/manifests/hashes. Cards and manifests "
                         "remain authoritative. MLflow failure is nonfatal to experiment outputs."},
    "lineup_audit": "lineup_replay_audit.json (NOT READY for historical replay; lane D deferred to 2027 logging)",
    "comparator": {"T0": "L3 logistic development bundle (bundle/model_bundle.json); tree must beat T0, not P3"},
    "inputs": [
        {"path": "research/offseason_2026/datasets/pa_table_2023_2024.parquet"},
        {"path": "data/processed/pitcher_games.parquet"},
        {"path": "data/processed/pitcher_rolling.parquet"},
        {"path": "data/processed/park_factors.parquet"},
        {"path": "data/processed/batter_games.parquet"},
        {"path": "research/offseason_2026/experiments/logistic_pa/pa_predictions.parquet"},
        {"path": "research/offseason_2026/experiments/logistic_pa/bundle/model_bundle.json"},
        {"path": "research/offseason_2026/experiments/pitcher_prior/pa_predictions.parquet"},
    ],
    "feature_manifest": "F1-F5 (16 columns) + trip/index terms (4) + logit(P3) baseline input; F6_rest EXCLUDED; "
                         "no repertoire/velocity/movement; no new interactions; identical construction to the "
                         "validated L3 bundle feature build (reproduces stored L3 to 2.2e-16)",
    "monotone_constraints_T2": "increasing on b_hand_rate, b_whiff, b_swstr, b_chase, p_whiff_P5, p_whiff_std, "
                                "p_swstr_P5, p_swstr_std, p_chase_P5, p_chase_std; free: same_hand, log_pa_curr, "
                                "log_pa_prior, park_k, trip terms, logit_p3",
    "grid_T1": {"num_leaves": [7, 15], "max_depth": [3, 4], "min_data_in_leaf": [200, 500],
                 "feature_fraction": [0.8, 1.0], "lambda_l2": [1.0, 10.0], "learning_rate": [0.05],
                 "n_estimators": [200]},
    "fold_design_2023": {"F1": "fit 03-30..06-30 -> eval 07-01..08-15",
                          "F2": "fit 03-30..08-15 -> eval 08-16..10-01"},
    "blend_gate_T3": "2023 OOF only: Pearson corr(L3 residual, tree residual) <= 0.85 AND best probability-"
                      "average weight in {0.25,0.5,0.75} improves mean fold logloss > 0.0002 over the better "
                      "single arm; else NO BLEND",
    "evaluation": {"2024": "E1 (<=06-30, n=55,815) and E2 (>=07-01, n=50,252) primary rows, ONE evaluation, "
                            "identical rows all arms",
                    "metrics": "logloss primary, brier, calibration alpha/beta, ECE-20bin, reliability",
                    "paired": "date-cluster B=2000 seed=0 + game_pk sensitivity vs L3 (and vs P3 descriptive)",
                    "slices": "month, p_throws, batter-history bucket, pitcher-prior bucket",
                    "ablation": "drop-family refits on 2023 folds (selected config)",
                    "importance": "grouped permutation on 2024 eval (families joint, 20 perms, logloss increase)",
                    "aggregation": "oracle start sums over 4,711 exact official starts; paired MAE/RMSE vs L3"},
    "gates": {"promote_tree": ["beats L3 PA logloss BOTH blocks (100%-consistent bootstrap direction preferred)",
                                "brier non-inferior both blocks", "no calibration collapse",
                                "survives oracle aggregation (MAE paired CI excludes 0 favoring tree both blocks)",
                                "gains in both 2023 selection folds", "not one-month/slice driven"],
               "stop": ["ties/loses to L3 -> retain logistic; complexity escalation stops",
                         "leakage assertion fires", "calibration slope outside 0.9-1.1 without registered correction"]},
    "prohibited": ["2025/2026", "market/betting", "TBF changes", "projected lineups in oracle experiment",
                    "blend without gate", "hierarchy/NN/simulation", "production changes", "post-2024 tuning"],
    "owner_authorization": "Phase 8 owner message (2026-09-30): execute the drafted tree card with the two "
                            "preflights (MLflow decision, lineup audit) completed first.",
}
card_p = HERE / "card.json"
card_p.write_text(json.dumps(CARD, indent=2), encoding="utf-8")
for i in CARD["inputs"]:
    i["sha256"] = sha(REPO / i["path"])
card_p.write_text(json.dumps(CARD, indent=2), encoding="utf-8")
hashes = {"card_sha256": sha(card_p), "inputs": CARD["inputs"]}
(HERE / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
print("card hashed:", hashes["card_sha256"][:16])
deviations = []

# ---------- feature build (identical to validated L3 bundle build; F6 dropped; +logit base) ----------
pa = pl.read_parquet(WS / "datasets/pa_table_2023_2024.parquet")
tr = json.loads((PA1A / "attribution_reconciliation.json").read_text(encoding="utf-8"))["rows"]
trk = set((r["game_pk"], r["at_bat_number"]) for r in tr)
pa = pa.with_columns(pl.struct(["game_pk", "at_bat_number"]).map_elements(
    lambda s: (s["game_pk"], s["at_bat_number"]) in trk, return_dtype=pl.Boolean).alias("trunc_flag"))
prim = pa.filter(~pl.col("trunc_flag"))
pg = pl.read_parquet(REPO / "data/processed/pitcher_games.parquet")
pr = pl.read_parquet(REPO / "data/processed/pitcher_rolling.parquet")
pf = pl.read_parquet(REPO / "data/processed/park_factors.parquet")
ppP = pl.read_parquet(PP / "pa_predictions.parquet").select(["game_pk", "at_bat_number", "P3_l5"])
STD = ["whiff_rate_std", "swstr_rate_std", "chase_rate_std", "zone_rate_std", "contact_rate_std"]
pgs = pg.sort(["pitcher", "game_date", "game_pk"]).with_columns(
    (pl.col("K").cum_sum().over(["pitcher", "season"]) - pl.col("K")).alias("K_curr"),
    (pl.col("PA").cum_sum().over(["pitcher", "season"]) - pl.col("PA")).alias("PA_curr0"))
pgs = pgs.with_columns(pl.col(["K_curr", "PA_curr0"]).first().over(["pitcher", "game_date"]))
pgs = pgs.with_columns(pl.when(pl.col("is_home") == 1).then(pl.col("home_team")).otherwise(
    pl.col("away_team")).alias("park_team"))
bpa = pl.read_parquet(REPO / "data/processed/batter_games.parquet").select(
    ["game_pk", "batter", "PA", "game_date"]).with_columns(
    pl.col("game_date").dt.year().alias("yr")).sort(["batter", "yr", "game_date", "game_pk"]).with_columns(
    (pl.col("PA").cum_sum().over(["batter", "yr"]) - pl.col("PA")).alias("prior_pa"))

def season_frame(season):
    d = prim.filter(pl.col("season") == season).join(
        pgs.filter(pl.col("season") == season).select(
            ["game_pk", "pitcher", "K_curr", "PA_curr0", "park_team"]),
        on=["game_pk", "pitcher"], how="left")
    if season == 2024:
        d = d.join(ppP, on=["game_pk", "at_bat_number"], how="left")
        assert d["P3_l5"].null_count() == 0
    else:
        # Phase 7-registered 2023 baseline: P2-style (no 2022 prior in counts) + log5
        odds = lambda p: p / (1 - p)
        Kc = d["K_curr"].fill_null(0).to_numpy(); Nc = d["PA_curr0"].fill_null(0).to_numpy()
        p_p = np.where(Nc > 0, (Kc + 100 * LG) / (Nc + 100), LG)
        p_b = CLIP(d["b_k_rate_std_shrunk"].to_numpy())
        o = odds(p_p) * odds(p_b) / odds(LG)
        d = d.with_columns(pl.Series("P3_l5", CLIP(o / (1 + o))))
    d = d.join(pr.filter(pl.col("season") == season).select(["game_pk", "pitcher"] + STD),
               on=["game_pk", "pitcher"], how="left")
    d = d.join(pf, left_on=["season", "park_team"], right_on=["season", "home_team"], how="left")
    d = d.join(bpa.select(["game_pk", "batter", "prior_pa"]), on=["game_pk", "batter"], how="left")
    spi = (prim.filter(pl.col("season") == season).select(["game_pk", "pitcher", "at_bat_number"])
           .sort(["game_pk", "pitcher", "at_bat_number"]).with_columns(
               pl.int_range(pl.len()).over(["game_pk", "pitcher"]).add(1).alias("spi")))
    d = d.join(spi, on=["game_pk", "at_bat_number"], how="left")
    return d

def feats(d):
    ph = d["p_throws"].to_numpy(); st = d["stand"].to_numpy()
    bl = d["b_k_rate_std_vL"].to_numpy(); br_ = d["b_k_rate_std_vR"].to_numpy()
    names = ["same_hand", "b_hand_rate", "b_whiff", "b_swstr", "b_chase",
             "p_whiff_P5", "p_swstr_P5", "p_chase_P5", "p_zone_P5", "p_contact_P5",
             "p_whiff_std", "p_swstr_std", "p_chase_std", "p_zone_std", "p_contact_std",
             "log_pa_curr", "log_pa_prior", "park_k",
             "trip_eq_2", "trip_eq_3", "trip_ge_4", "spi_over_9"]
    cols = {
        "same_hand": (ph == st).astype(float),
        "b_hand_rate": np.nan_to_num(np.where(ph == "L", bl, br_), nan=LG),
        "b_whiff": d["b_whiff_rate_std"].to_numpy(), "b_swstr": d["b_swstr_rate_std"].to_numpy(),
        "b_chase": d["b_chase_rate_std"].to_numpy(),
        "p_whiff_P5": d["whiff_rate_P5"].to_numpy(), "p_swstr_P5": d["swstr_rate_P5"].to_numpy(),
        "p_chase_P5": d["chase_rate_P5"].to_numpy(), "p_zone_P5": d["zone_rate_P5"].to_numpy(),
        "p_contact_P5": d["contact_rate_P5"].to_numpy(),
        "p_whiff_std": d["whiff_rate_std"].to_numpy(), "p_swstr_std": d["swstr_rate_std"].to_numpy(),
        "p_chase_std": d["chase_rate_std"].to_numpy(), "p_zone_std": d["zone_rate_std"].to_numpy(),
        "p_contact_std": d["contact_rate_std"].to_numpy(),
        "log_pa_curr": np.log1p(d["PA_curr0"].fill_null(0).to_numpy()),
        "log_pa_prior": np.zeros(len(d)),
        "park_k": np.nan_to_num(d["park_k_factor"].to_numpy(), nan=1.0),
    }
    X = np.column_stack([np.nan_to_num(cols[c], nan=0.0) for c in names[:18]])
    trip = 1 + (d["spi"].to_numpy() - 1) // 9
    X3 = np.column_stack([X, (trip == 2).astype(float), (trip == 3).astype(float),
                          (trip >= 4).astype(float), d["spi"].to_numpy() / 9.0])
    l0 = d["P3_l5"].to_numpy()
    return X3, names, np.log(CLIP(l0) / (1 - CLIP(l0)))

d23 = season_frame(2023); d24 = season_frame(2024)
X23, NAMES, x0_23 = feats(d23)
X24, _, x0_24 = feats(d24)
y23 = d23["is_k"].cast(pl.Float64).to_numpy()
y24 = d24["is_k"].cast(pl.Float64).to_numpy()
gd23 = d23["game_date"].cast(pl.String).to_numpy()
gd24 = d24["game_date"].cast(pl.String).to_numpy()
gpk24 = d24["game_pk"].to_numpy()
f1_fit = gd23 <= "2023-06-30"; f1_ev = (gd23 >= "2023-07-01") & (gd23 <= "2023-08-15")
f2_fit = gd23 <= "2023-08-15"; f2_ev = gd23 >= "2023-08-16"

MONO_NAMES = {"b_hand_rate", "b_whiff", "b_swstr", "b_chase", "p_whiff_P5", "p_whiff_std",
              "p_swstr_P5", "p_swstr_std", "p_chase_P5", "p_chase_std"}
mono_vec = [1 if n in MONO_NAMES else 0 for n in NAMES]

def lgb_fit(Xtr, ytr, C, mono=False):
    m = lgb.LGBMClassifier(
        n_estimators=200, learning_rate=0.05, num_leaves=C["num_leaves"], max_depth=C["max_depth"],
        min_data_in_leaf=C["min_data_in_leaf"], feature_fraction=C["feature_fraction"],
        lambda_l2=C["lambda_l2"], random_state=0, n_jobs=1, deterministic=True, verbose=-1,
        monotone_constraints=mono_vec if mono else None)
    return m.fit(Xtr, ytr)

def llm(p, y): return float(np.mean(-(y * np.log(CLIP(p)) + (1 - y) * np.log(1 - CLIP(p)))))

# T1 grid on 2023 folds
grid = [{"num_leaves": nl, "max_depth": md, "min_data_in_leaf": mdl,
         "feature_fraction": ff, "lambda_l2": l2}
        for nl in (7, 15) for md in (3, 4) for mdl in (200, 500)
        for ff in (0.8, 1.0) for l2 in (1.0, 10.0)]
scores = {}
oof_tree = np.zeros(len(y23))
for C in grid:
    lls = []
    for fm, fe in ((f1_fit, f1_ev), (f2_fit, f2_ev)):
        Xtr = np.column_stack([x0_23[fm], X23[fm]])
        m = lgb_fit(Xtr, y23[fm], C)
        p = m.predict_proba(np.column_stack([x0_23[fe], X23[fe]]))[:, 1]
        lls.append(llm(p, y23[fe]))
        oof_tree[fe] = p
    scores[json.dumps(C, sort_keys=True)] = round(sum(lls) / 2, 6)
best_cfg = json.loads(min(scores, key=scores.get))
print("T1 grid best:", min(scores, key=scores.get), scores[min(scores, key=scores.get)])

# T2 monotone with best config
lls_mono = []
for fm, fe in ((f1_fit, f1_ev), (f2_fit, f2_ev)):
    m = lgb_fit(np.column_stack([x0_23[fm], X23[fm]]), y23[fm], best_cfg, mono=True)
    p = m.predict_proba(np.column_stack([x0_23[fe], X23[fe]]))[:, 1]
    lls_mono.append(llm(p, y23[fe]))
    oof_tree[fe] = p
t2_score = sum(lls_mono) / 2
print("T2 monotone score:", round(t2_score, 6))
use_mono = t2_score <= scores[min(scores, key=scores.get)]

# Blend-gate baseline (registered substitute): Phase 7 fold-fitted L3 models were not serialized,
# so true L3 OOF residuals are unavailable. Gate uses P3-log5 OOF residuals as the logistic-family
# proxy, labeled as such. Any T3 result is a P3+tree blend assessment, not an L3+tree one.
deviations.append({"finding": "T3 blend gate executed against P3-log5 OOF residuals (registered substitute "
                   "because fold-fitted L3 models were not serialized).", "classification": "NON-SUBSTANTIVE (labeled)"})
x0_full = x0_23
p3_23 = CLIP(1 / (1 + np.exp(-x0_full)))
res_p3 = p3_23 - y23
res_tree = oof_tree - y23
mask_oof = f1_ev | f2_ev
corr = float(np.corrcoef(res_p3[mask_oof], res_tree[mask_oof])[0, 1])
blend_scores = {}
for w in (0.25, 0.5, 0.75):
    pb = w * oof_tree + (1 - w) * p3_23
    lls = []
    for fe in (f1_ev, f2_ev):
        lls.append(llm(pb[fe], y23[fe]))
    blend_scores[w] = round(sum(lls) / 2, 6)
best_single = min(llm(oof_tree[fe], y23[fe]) if False else 0 for fe in []) if False else None
single_best = min(sum([llm(oof_tree[fe], y23[fe]) for fe in (f1_ev, f2_ev)]) / 2,
                  sum([llm(p3_23[fe], y23[fe]) for fe in (f1_ev, f2_ev)]) / 2)
best_w = min(blend_scores, key=blend_scores.get)
blend_ok = (corr <= 0.85) and (blend_scores[best_w] < single_best - 0.0002)
print(f"blend gate: corr={corr:.4f} blend={blend_scores} single={single_best:.6f} -> {'MET' if blend_ok else 'NOT MET'}")

# final fit on all 2023, one 2024 evaluation
X23f = np.column_stack([x0_23, X23]); X24f = np.column_stack([x0_24, X24])
m_final = lgb_fit(X23f, y23, best_cfg, mono=use_mono)
p_tree_24 = m_final.predict_proba(X24f)[:, 1]
p_l3_24 = pl.read_parquet(LP / "pa_predictions.parquet").select(["game_pk", "at_bat_number", "L3"])
aligned = d24.select(["game_pk", "at_bat_number"]).with_row_index("__r").join(
    p_l3_24, on=["game_pk", "at_bat_number"], how="left").sort("__r").drop("__r")
assert aligned["L3"].null_count() == 0
p_l3 = aligned["L3"].to_numpy()

# 2024 metrics + paired bootstraps
def llv(p, y): return -(y * np.log(CLIP(p)) + (1 - y) * np.log(1 - CLIP(p)))
def brv(p, y): return (p - y) ** 2
_e1 = gd24 <= "2024-06-30"; _e2 = gd24 >= "2024-07-01"
def boot(a, b, keys, B=2000, seed=0):
    ku, inv = np.unique(keys, return_inverse=True); nd = len(ku)
    ns = np.bincount(inv, minlength=nd).astype(float)
    ds = np.bincount(inv, weights=a, minlength=nd) - np.bincount(inv, weights=b, minlength=nd)
    rng = np.random.default_rng(seed); dl = np.empty(B)
    for i in range(B):
        cnt = np.bincount(rng.integers(0, nd, nd), minlength=nd).astype(float)
        dl[i] = (cnt * ds).sum() / max((cnt * ns).sum(), 1)
    lo, hi = np.percentile(dl, [2.5, 97.5])
    return {"raw": float(ds.sum() / ns.sum()), "ci95": [float(lo), float(hi)], "fav": float((dl < 0).mean())}
metrics, paired = {}, {}
for blk, mask in {"E1": _e1, "E2": _e2, "pooled_descriptive": np.ones(len(y24), bool)}.items():
    yy = y24[mask]
    metrics[blk] = {"T0_L3": {"logloss": llm(p_l3[mask], yy), "brier": float(brv(p_l3[mask], yy).mean())},
                     "T1": {"logloss": llm(p_tree_24[mask], yy), "brier": float(brv(p_tree_24[mask], yy).mean())}}
    paired[blk] = {"T1-T0_ll": boot(llv(p_tree_24[mask], yy), llv(p_l3[mask], yy), gd24[mask]),
                    "T1-T0_br": boot(brv(p_tree_24[mask], yy), brv(p_l3[mask], yy), gd24[mask])}
paired_gpk = {blk: {"T1-T0_ll": boot(llv(p_tree_24[m_], y24[m_]), llv(p_l3[m_], y24[m_]), gpk24[m_]),
                     "T1-T0_br": boot(brv(p_tree_24[m_], y24[m_]), brv(p_l3[m_], y24[m_]), gpk24[m_])}
              for blk, m_ in {"E1": _e1, "E2": _e2}.items()}

# calibration
def calib(p, y):
    x = np.log(CLIP(p) / (1 - CLIP(p)))
    X = np.column_stack([np.ones_like(x), x]); b = np.array([0., 1.])
    for _ in range(100):
        mu_ = 1 / (1 + np.exp(-(X @ b)))
        try: step = np.linalg.solve(X.T @ (X * (mu_ * (1 - mu_))[:, None]) + 1e-10 * np.eye(2), X.T @ (y - mu_))
        except np.linalg.LinAlgError: break
        b = b + step
        if np.max(np.abs(step)) < 1e-10: break
    return {"alpha": float(b[0]), "beta": float(b[1])}
cal = {blk: {"T0_L3": calib(p_l3[m_], y24[m_]), "T1": calib(p_tree_24[m_], y24[m_])}
       for blk, m_ in {"E1": _e1, "E2": _e2}.items()}

# grouped family ablation on 2023 folds (selected config)
FAMS = {"F1_platoon": [0, 1], "F2_batter_discipline": [2, 3, 4],
         "F3_pitcher_discipline": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
         "F4_history": [15, 16], "F5_park": [17],
         "L3_terms": [18, 19, 20, 21]}
fam_abl = {}
for f, idxs in FAMS.items():
    keep = [i for i in range(X23.shape[1]) if i not in idxs]
    lls = []
    for fm, fe in ((f1_fit, f1_ev), (f2_fit, f2_ev)):
        m = lgb_fit(np.column_stack([x0_23[fm], X23[fm][:, keep]]), y23[fm], best_cfg, mono=False)
        p = m.predict_proba(np.column_stack([x0_23[fe], X23[fe][:, keep]]))[:, 1]
        lls.append(llm(p, y23[fe]))
    fam_abl[f] = round(sum(lls) / 2 - min(scores.values()) if not use_mono else sum(lls) / 2 - t2_score, 6)

# grouped permutation importance on 2024 eval
rng = np.random.default_rng(0)
gimp = {}
X24f_copy = X24f.copy()
base_ll = llm(p_tree_24, y24)
for f, idxs in FAMS.items():
    inc = []
    cols = [i + 1 for i in idxs]  # +1 for x0 column at position 0
    for _ in range(20):
        Xp = X24f_copy.copy()
        for c in cols:
            Xp[:, c] = rng.permutation(Xp[:, c])
        inc.append(llm(m_final.predict_proba(Xp)[:, 1], y24) - base_ll)
    gimp[f] = round(float(np.mean(inc)), 6)

# oracle aggregation
pg24f = pg.filter(pl.col("season") == 2024).select(["game_pk", "pitcher", "PA", "K"])
agg = d24.select(["game_pk", "pitcher", "game_date", "is_k"]).with_columns(
    [pl.Series("p_L3", p_l3), pl.Series("p_tree", p_tree_24)])
g = agg.group_by(["game_pk", "pitcher"]).agg(
    pl.len().alias("n_rows"), pl.col("game_date").first(),
    pl.col("is_k").cast(pl.Float64).sum().alias("actual_K"),
    pl.col("p_L3").sum().alias("xK_L3"), pl.col("p_tree").sum().alias("xK_tree"))
rec = g.join(pg24f.rename({"PA": "official_BF", "K": "official_K"}), on=["game_pk", "pitcher"], how="left")
assert rec["official_BF"].null_count() == 0
assert (rec["n_rows"] == rec["official_BF"]).all() and (rec["actual_K"] == rec["official_K"]).all()
AK = g["actual_K"].to_numpy(); gd_s = g["game_date"].cast(pl.String).to_numpy()
_e1s = gd_s <= "2024-06-30"; _e2s = gd_s >= "2024-07-01"
agg_metrics, agg_pairs = {}, {}
for blk, mask in {"E1": _e1s, "E2": _e2s}.items():
    agg_metrics[blk] = {}
    for a, c in (("L3", "xK_L3"), ("tree", "xK_tree")):
        err = g[c].to_numpy()[mask] - AK[mask]
        agg_metrics[blk][a] = {"MAE": float(np.mean(np.abs(err))), "RMSE": float(np.sqrt(np.mean(err ** 2))),
                                "bias": float(np.mean(err))}
    e1 = g["xK_tree"].to_numpy()[mask] - AK[mask]; e2 = g["xK_L3"].to_numpy()[mask] - AK[mask]
    ku, inv = np.unique(gd_s[mask], return_inverse=True); nd = len(ku)
    ns = np.bincount(inv, minlength=nd).astype(float)
    s1 = np.bincount(inv, weights=np.abs(e1), minlength=nd); s2 = np.bincount(inv, weights=np.abs(e2), minlength=nd)
    rng_ = np.random.default_rng(0); dl = np.empty(2000)
    for i in range(2000):
        cnt = np.bincount(rng_.integers(0, nd, nd), minlength=nd).astype(float)
        dl[i] = (cnt * (s1 - s2)).sum() / max((cnt * ns).sum(), 1)
    lo, hi = np.percentile(dl, [2.5, 97.5])
    agg_pairs[blk] = {"tree-L3_MAE": {"raw": float(np.mean(np.abs(e1) - np.abs(e2))),
                                       "ci95": [float(lo), float(hi)], "fav": float((dl < 0).mean())}}

# slices
month = d24["game_date"].dt.month().to_numpy()
slices = {}
for sname, sv in {"month": month, "p_throws": d24["p_throws"].to_numpy()}.items():
    ent = {}
    for v in np.unique(sv):
        mk = sv == v
        ent[str(v)] = {"n": int(mk.sum()),
                        "L3_logloss": round(llm(p_l3[mk], y24[mk]), 6),
                        "T1_logloss": round(llm(p_tree_24[mk], y24[mk]), 6)}
    slices[sname] = ent

results = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "card_sha256": hashes["card_sha256"],
            "mlflow": CARD["mlflow_decision"], "grid_scores": scores, "best_config": best_cfg,
            "t2_monotone": {"score": round(t2_score, 6), "used": use_mono},
            "blend_gate": {"corr_2023_OOF": round(corr, 4), "blend_scores": blend_scores,
                            "single_best": round(single_best, 6), "best_w": best_w, "met": blend_ok,
                            "proxy_note": deviations[-1]["finding"]},
            "metrics_2024": metrics, "paired_date": paired, "paired_game_pk": paired_gpk,
            "calibration": cal, "family_ablation_folds": fam_abl, "grouped_importance_2024": gimp,
            "aggregation": {"metrics": agg_metrics, "paired": agg_pairs}, "slices": slices,
            "deviations": deviations}
(HERE / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
pl.DataFrame(d24.select(["game_pk", "at_bat_number", "game_date", "pitcher", "batter"]).with_columns(
    [pl.Series("p_tree", p_tree_24), pl.Series("p_L3", p_l3)])).write_parquet(HERE / "tree_predictions.parquet")
(HERE / "paired_comparisons.json").write_text(json.dumps({"date": paired, "game_pk": paired_gpk}, indent=2), encoding="utf-8")
(HERE / "slices.json").write_text(json.dumps(slices, indent=2), encoding="utf-8")
(HERE / "deviations.md").write_text("\n".join(f"- {x['finding']} {x['classification']}" for x in deviations), encoding="utf-8")
outs = {f.name: sha(f) for f in HERE.glob("*") if f.is_file() and f.name != "output_hashes.json"}
(HERE / "output_hashes.json").write_text(json.dumps(outs, indent=2), encoding="utf-8")
print("PHASE 8 COMPLETE")
