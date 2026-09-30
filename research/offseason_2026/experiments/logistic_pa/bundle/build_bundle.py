"""Phase 7.5: build the immutable L3 development bundle WITHOUT refitting.

Coefficients come from the stored Phase 7 record. The intercept was not serialized
at execution time; it is RECOVERED deterministically from stored predictions +
rebuilt features and validated for constancy. Scaling constants are recomputed
deterministically from 2023 features and then frozen in the bundle.
"""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "research/offseason_2026"))
HERE = Path(__file__).resolve().parent
WS = REPO / "research/offseason_2026"
PA1A = WS / "experiments/pa1a_raw_pa"
PP = WS / "experiments/pitcher_prior"
LP = HERE.parent
LG = 0.223813

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

m7 = json.loads((LP / "metrics.json").read_text(encoding="utf-8"))
coefs_named = m7["coefficients"]["L3"]["coefs"]
trip_terms = m7["coefficients"]["L3"]["trip_dummies_and_index"]
beta_base = m7["coefficients"]["L3"]["beta_logitP3"]
ORDER = list(coefs_named)  # exact stored order
print("stored L3 coefs:", len(ORDER), "+ base + 4 trip terms")

# ---- rebuild feature frames exactly as run_phase7 registered ----
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
STD = ["whiff_rate_std", "swstr_rate_std", "chase_rate_std", "zone_rate_std", "contact_rate_std"]

pgs = pg.sort(["pitcher", "game_date", "game_pk"]).with_columns(
    (pl.col("K").cum_sum().over(["pitcher", "season"]) - pl.col("K")).alias("K_curr"),
    (pl.col("PA").cum_sum().over(["pitcher", "season"]) - pl.col("PA")).alias("PA_curr0"))
pgs = pgs.with_columns(pl.col(["K_curr", "PA_curr0"]).first().over(["pitcher", "game_date"]))
prior23 = pg.filter(pl.col("season") == 2023).group_by("pitcher").agg(
    pl.col("K").sum().alias("K_prior"), pl.col("PA").sum().alias("PA_prior"))
pgs = pgs.with_columns(pl.col("game_date").shift(1).over(["pitcher", "season"]).alias("prev_date"))
pgs = pgs.with_columns(pl.col("prev_date").first().over(["pitcher", "game_date"]).alias("prev_date"))
pgs = pgs.with_columns((pl.col("game_date") - pl.col("prev_date")).dt.total_days().alias("gap"))
pgs = pgs.with_columns([
    pl.when(pl.col("prev_date").is_null()).then(15).otherwise(pl.col("gap").clip(1, 15)).alias("days_rest_capped"),
    pl.when(pl.col("prev_date").is_null()).then(1).otherwise(0).cast(pl.Float64).alias("is_season_debut")])
pgs = pgs.with_columns(pl.when(pl.col("is_home") == 1).then(pl.col("home_team")).otherwise(
    pl.col("away_team")).alias("park_team"))
bpa = pl.read_parquet(REPO / "data/processed/batter_games.parquet").select(
    ["game_pk", "batter", "PA", "game_date"]).with_columns(
    pl.col("game_date").dt.year().alias("yr")).sort(["batter", "yr", "game_date", "game_pk"]).with_columns(
    (pl.col("PA").cum_sum().over(["batter", "yr"]) - pl.col("PA")).alias("prior_pa"))

def season_frame(season):
    d = prim.filter(pl.col("season") == season).join(
        pgs.filter(pl.col("season") == season).select(
            ["game_pk", "pitcher", "K_curr", "PA_curr0", "days_rest_capped", "is_season_debut", "park_team"]),
        on=["game_pk", "pitcher"], how="left")
    if season == 2024:
        d = d.join(pp, on=["game_pk", "at_bat_number"], how="left")
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
        "rest": np.nan_to_num(d["days_rest_capped"].to_numpy(), nan=15.0),
        "debut": d["is_season_debut"].to_numpy(),
    }
    X = np.column_stack([np.nan_to_num(cols[c], nan=0.0) for c in ORDER])
    trip = 1 + (d["spi"].to_numpy() - 1) // 9
    X3 = np.column_stack([X, (trip == 2).astype(float), (trip == 3).astype(float),
                          (trip >= 4).astype(float), d["spi"].to_numpy() / 9.0])
    return X3

d23 = season_frame(2023)
d24 = season_frame(2024)
X23 = feats(d23); X24 = feats(d24)
mu = X23.mean(0); sd = X23.std(0) + 1e-9

# ---- recover intercept from stored predictions ----
stored = pl.read_parquet(LP / "pa_predictions.parquet")
stored_l3 = stored.select(["game_pk", "at_bat_number", "L3", "L0"])  # L0 == P3-log5
j = d24.select(["game_pk", "at_bat_number"]).with_columns(
    pl.Series("X_idx", np.arange(d24.height))).join(
    stored_l3, on=["game_pk", "at_bat_number"], how="inner")
assert j.height == d24.height, "stored L3 keys do not cover the 2024 frame"
idx = j["X_idx"].to_numpy()
x0 = np.log(np.clip(j["L0"].to_numpy(), 1e-6, 1 - 1e-6) /
            (1 - np.clip(j["L0"].to_numpy(), 1e-6, 1 - 1e-6)))
eta_no_int = beta_base * x0 + (X24[idx] - mu) / sd @ np.array(
    list(coefs_named.values()) + trip_terms)
p_stored = j["L3"].to_numpy()
logit_stored = np.log(np.clip(p_stored, 1e-12, 1 - 1e-12) / (1 - np.clip(p_stored, 1e-12, 1 - 1e-12)))
resid = logit_stored - eta_no_int
intercept = float(np.median(resid))
spread = float(np.max(np.abs(resid - intercept)))
print(f"intercept recovered: {intercept:.6f} | max |resid spread|: {spread:.2e}")
assert spread < 1e-6, "intercept recovery failed: stored predictions inconsistent with stored coefficients"

# ---- final reproduction: apply full bundle to 2024 features ----
eta = intercept + beta_base * x0 + (X24[idx] - mu) / sd @ np.array(
    list(coefs_named.values()) + trip_terms)
p_rebuilt = np.clip(1 / (1 + np.exp(-eta)), 1e-6, 1 - 1e-6)
max_diff = float(np.max(np.abs(p_rebuilt - p_stored)))
print(f"reproduction max |Δp| vs stored L3: {max_diff:.2e}")
repro_ok = max_diff < 1e-8

# ---- write bundle ----
bd = HERE / "bundle"
bd.mkdir(exist_ok=True)
feature_manifest = {
    "feature_order": ORDER + ["trip_eq_2", "trip_eq_3", "trip_ge_4", "spi_over_9"],
    "families": {
        "F1_platoon": ["same_hand", "b_hand_rate"],
        "F2_batter_discipline": ["b_whiff", "b_swstr", "b_chase"],
        "F3_pitcher_discipline": ["p_whiff_P5", "p_swstr_P5", "p_chase_P5", "p_zone_P5",
                                   "p_contact_P5", "p_whiff_std", "p_swstr_std", "p_chase_std",
                                   "p_zone_std", "p_contact_std"],
        "F4_history": ["log_pa_curr", "log_pa_prior"],
        "F5_park": ["park_k"],
        "F6_rest": ["rest", "debut"],
        "L3_interactions": ["trip_eq_2", "trip_eq_3", "trip_ge_4", "spi_over_9"],
    },
    "status": {"F6_rest": "EXCLUDED_FROM_NEXT_PA_K_MANIFEST (Phase 7 2023-fold ablation ~zero; "
                           "kept eligible for opportunity/TBF research)",
                "F1-F5+trip/index": "FROZEN for next challenger"},
    "definitions": "see logistic_pa/card.json families_L2/interactions_L3; nan_to_num(0) except "
                    "b_hand_rate->LG, park_k->1.0, rest->15.0",
    "allow_extra_columns": True,
}
preprocessing = {"scaler": "z-score using 2023 primary-row mean/std (deterministic, recomputed)",
                  "per_feature": {c: {"mean": float(mu[i]), "std": float(sd[i]), "fill": 0.0}
                                   for i, c in enumerate(ORDER)},
                  "interactions_unscaled": ["trip dummies binary", "spi_over_9 raw"]}
model_card = {
    "model_id": "L3_logistic_pa_dev", "model_version": "phase7-executed",
    "status": "DEVELOPMENT_BASELINE — NOT PRODUCTION_APPROVED",
    "estimator": "sklearn LogisticRegression penalty=l2 C=0.01 solver=lbfgs max_iter=2000",
    "formula": "logit(p) = intercept + 0.9197-style*beta_base*logit(P3_l5) + sum(coef_i * z_i) + trip terms",
    "beta_baseline_logitP3": beta_base,
    "intercept": {"value": intercept, "provenance": "RECOVERED from stored Phase 7 predictions + rebuilt "
                   "features (was not serialized at execution time); constancy validated < 1e-6"},
    "coefficients": {**coefs_named, "trip_dummies_and_index": trip_terms},
    "baseline_dependency": {"model": "P3-log5 (pitcher_prior experiment)", "rollback_target": True,
                             "formula": "(K_prior_season + K_curr + 100*lg)/(PA_prior_season + PA_curr + 100) "
                                        "in odds-form log5, lg=0.223813, m=100 selected on 2023 folds only"},
    "training": {"fit_rows": "2023 primary PA rows (105,225)", "fit_dates": "2023-03-30..2023-10-01",
                  "permitted_scoring_dates": "2024 E1 (<=2024-06-30), E2 (>=2024-07-01)",
                  "selection": "C and families via 2023 chronological folds only"},
    "period_qualifications": ["2024 = development evidence (architecture informed by it)",
                               "no 2025/2026 access", "oracle aggregation only (ACTUAL_TBF_ORACLE)"],
    "known_limitations": ["intercept + scaler not serialized at execution time (recovered/recomputed; "
                           "future bundles must serialize at fit time)",
                           "F6_rest ~zero value; excluded from next manifest",
                           "development-only; no frozen-model, market, or deployability claim"],
    "no_2025_2026_declaration": True,
    "reproduction": {"command": "python research/offseason_2026/experiments/logistic_pa/bundle/build_bundle.py",
                      "max_abs_diff_vs_stored": max_diff, "tolerance": 1e-8, "passed": repro_ok},
    "hashes": {"pa_table": sha(WS / "datasets/pa_table_2023_2024.parquet"),
                "pitcher_games": sha(REPO / "data/processed/pitcher_games.parquet"),
                "pitcher_rolling": sha(REPO / "data/processed/pitcher_rolling.parquet"),
                "park_factors": sha(REPO / "data/processed/park_factors.parquet"),
                "batter_games": sha(REPO / "data/processed/batter_games.parquet"),
                "stored_predictions": sha(LP / "pa_predictions.parquet"),
                "phase7_card": sha(LP / "card.json")},
    "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "polars": pl.__version__},
    "built_utc": datetime.now(timezone.utc).isoformat(),
}
(bd / "feature_manifest.json").write_text(json.dumps(feature_manifest, indent=2), encoding="utf-8")
(bd / "preprocessing_manifest.json").write_text(json.dumps(preprocessing, indent=2), encoding="utf-8")
(bd / "model_card.json").write_text(json.dumps(model_card, indent=2), encoding="utf-8")
bundle_core = {"model_id": model_card["model_id"], "model_version": "phase7-executed",
                "intercept": intercept, "coefficients": {"__BASELINE_LOGIT__": beta_base,
                **{c: coefs_named[c] for c in ORDER}, "trip_dummies_and_index": trip_terms},
                "baseline_column": "P3_l5_logit", "feature_manifest": feature_manifest,
                "feature_manifest_hash": sha(bd / "feature_manifest.json"),
                "preprocessing": {**{c: preprocessing["per_feature"][c] for c in ORDER},
                                   "trip_eq_2": {"mean": 0.0, "std": 1.0, "fill": 0.0},
                                   "trip_eq_3": {"mean": 0.0, "std": 1.0, "fill": 0.0},
                                   "trip_ge_4": {"mean": 0.0, "std": 1.0, "fill": 0.0},
                                   "spi_over_9": {"mean": 0.0, "std": 1.0, "fill": 0.0}},
                "prediction_context": "ACTUAL_BATTER_PREGAME_FEATURES"}
(bd / "model_bundle.json").write_text(json.dumps(bundle_core, indent=2), encoding="utf-8")
outs = {f.name: sha(f) for f in bd.glob("*") if f.is_file()}
(bd / "hashes.json").write_text(json.dumps(outs, indent=2), encoding="utf-8")
print("BUNDLE WRITTEN; reproducible:", repro_ok, f"(max Δp {max_diff:.2e})")



