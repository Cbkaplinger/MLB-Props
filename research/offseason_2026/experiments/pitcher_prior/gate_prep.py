"""Phase 6 prep: Gate A (pitcher identity v2), Gate B (frozen comparator validity),
Gate C (cards P + O, hashed), P2 strength selection (2023 folds only),
PA-1B-O population recalculation. Writes ONLY under authorized experiment dirs.
"""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import polars as pl

REPO = Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props")
WS = REPO / "research/offseason_2026"
PA1A = WS / "experiments/pa1a_raw_pa"
PP = WS / "experiments/pitcher_prior"
OB = WS / "experiments/pa1b_oracle_xk"
PP.mkdir(exist_ok=True); OB.mkdir(exist_ok=True)
NON_PA = {"caught_stealing_2b","caught_stealing_3b","caught_stealing_home","pickoff_1b","pickoff_2b","pickoff_3b",
          "pickoff_caught_stealing_2b","pickoff_caught_stealing_3b","pickoff_caught_stealing_home",
          "stolen_base_2b","stolen_base_3b","stolen_base_home","wild_pitch","passed_ball","other_out"}

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def tree():
    import subprocess
    n = subprocess.run(["git","status","--porcelain"],capture_output=True,text=True,cwd=REPO).stdout.count("\n")
    head = subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,cwd=REPO).stdout.strip()
    return {"dirty_paths": n, "head": head}

# ---------- official starters (first pitch of each half of inning 1) ----------
t_all = []
for y in (2023, 2024):
    t = pl.scan_parquet(REPO/f"data/Savant-Data/regular/{y}/statcast_{y}_regular.parquet").select(
        "game_pk","at_bat_number","pitch_number","pitcher","inning","inning_topbot","events","game_date").collect()
    t_all.append(t)
t = pl.concat(t_all).sort(["game_pk","inning","inning_topbot","at_bat_number","pitch_number"])
firstp = t.filter((pl.col("inning")==1)).group_by(["game_pk","inning_topbot"]).agg(
    pl.col("pitcher").first().alias("official_starter"), pl.col("game_date").first())
off_keys = set(zip(firstp["game_pk"].to_list(), firstp["official_starter"].to_list()))
print("official starter entries derived:", len(off_keys))

# ---------- role census on pitcher_games (the >=9-PA population) ----------
pg = pl.read_parquet(REPO/"data/processed/pitcher_games.parquet")
pg = pg.with_columns(pl.struct(["game_pk","pitcher"]).map_elements(
    lambda s: (s["game_pk"], s["pitcher"]) in off_keys, return_dtype=pl.Boolean).alias("is_official_starter"))
census = pg.group_by(["season","is_official_starter"]).agg(pl.len().alias("entries"), pl.col("PA").sum().alias("pas"))
print("census:", census.sort(["season","is_official_starter"]).to_dicts())
census_dict = {f"{r['season']}|{'official' if r['is_official_starter'] else 'bulk9'}": {"entries": r["entries"], "pas": int(r["pas"])} for r in census.iter_rows(named=True)}

# ---------- Gate A: identity v2 for the 122 split PAs ----------
art_v1 = json.loads((PA1A/"attribution_reconciliation.json").read_text(encoding="utf-8"))
t2 = t.join(firstp.select(["game_pk","inning_topbot","official_starter"]), on=["game_pk","inning_topbot"], how="left")
rows_v2 = []
for r in art_v1["rows"]:
    gp, abn, fp_id, cp_id = r["game_pk"], r["at_bat_number"], r["first_pitcher_id"], r["completing_pitcher_id"]
    hit = t2.filter((pl.col("game_pk")==gp) & (pl.col("at_bat_number")==abn))
    off_starter = int(hit["official_starter"][0]) if hit.height and hit["official_starter"][0] is not None else None
    if off_starter is None:
        rel = "UNKNOWN_ROLE"
    elif cp_id == off_starter:
        rel = "COMPLETER_IS_OFFICIAL_STARTER"
    elif fp_id == off_starter:
        rel = "OFFICIAL_STARTER_BEGAN_RELIEVER_COMPLETED"
    else:
        rel = "NEITHER_IS_OFFICIAL_STARTER"
    rows_v2.append({**r, "official_starter_id": off_starter,
                    "first_pitcher_role": "OFFICIAL_STARTER" if (off_starter is not None and fp_id==off_starter) else "UNKNOWN_ROLE",
                    "modeled_pitcher_id": cp_id,
                    "official_result_pitcher_id": cp_id,
                    "terminal_pitcher_id": cp_id,
                    "pitcher_role_class_completer": "OFFICIAL_STARTER" if (off_starter is not None and cp_id==off_starter) else "BULK_RELIEVER_9PA",
                    "role_relationship": rel})
from collections import Counter
rel_counts = Counter(r["role_relationship"] for r in rows_v2)
rel_k = Counter((r["role_relationship"], r["is_k"]) for r in rows_v2)
print("role relationships:", dict(rel_counts))
identity = {
    "artifact": "pitcher identity resolution v2 (Phase 6 Gate A); supersedes v1 classification detail without overwriting it",
    "v1_artifact_sha256": (PA1A/"attribution_sha.txt").read_text(encoding="utf-8"),
    "official_starter_definition": "pitcher who delivered the first pitch of inning 1 for his team-side "
                                   "(MLB: the starting pitcher is the pitcher who delivers the first pitch); "
                                   "opener = official starter by this definition; bulk reliever never is",
    "modeled_pitcher_definition_in_repo": "pitcher_games entry = pitcher with >=9 BF in the game "
                                          "(MIN_STARTER_BATTERS_FACED); NOT necessarily the official starter; "
                                          "this resolves the Phase 5.5 terminology conflict: the 51 "
                                          "'starter-terminal' rows have the >=9-PA pitcher as completer, "
                                          "which is the official starter in some rows and a bulk reliever in others",
    "role_relationship_counts": dict(rel_counts),
    "role_relationship_k_counts": {f"{c}|is_k={k}": v for (c,k),v in rel_k.items()},
    "census_pitcher_games": census_dict,
    "pa_table_row_note": "PA-1A rows are PAs whose completing pitcher has >=9 BF in the game; official-starter "
                         "share of PA-1A rows measured in prep.json",
    "rows": rows_v2,
}
(PP/"pitcher_identity_resolution.json").write_text(json.dumps(identity, indent=1), encoding="utf-8")
print("identity rows:", len(rows_v2), "sha:", sha(PP/"pitcher_identity_resolution.json")[:16])

# ---------- P2 strength selection on 2023 folds only ----------
pg23 = pg.filter(pl.col("season")==2023).sort(["pitcher","game_date","game_pk"]).with_columns(
    (pl.col("K").cum_sum().over(["pitcher"]) - pl.col("K")).alias("K_prior"),
    (pl.col("PA").cum_sum().over(["pitcher"]) - pl.col("PA")).alias("PA_prior"))
pg23 = pg23.with_columns(pl.col(["K_prior","PA_prior"]).first().over(["pitcher","game_date"]))  # same-date collapse approx
lg = 0.223813
pa = pl.read_parquet(WS/"datasets/pa_table_2023_2024.parquet")
trunc23 = set()
pa23 = pa.filter(pl.col("season")==2023)
# truncated 2023 keys from v1 artifact rows
for r in json.loads((PA1A/"attribution_reconciliation.json").read_text(encoding="utf-8"))["rows"]:
    if r["season"]==2023: trunc23.add((r["game_pk"], r["at_bat_number"]))
pa23 = pa23.with_columns(pl.struct(["game_pk","at_bat_number"]).map_elements(
    lambda s: (s["game_pk"], s["at_bat_number"]) in trunc23, return_dtype=pl.Boolean).alias("trunc_flag"))
prim23 = pa23.filter(~pl.col("trunc_flag"))
j = prim23.join(pg23.select(["game_pk","pitcher","K_prior","PA_prior"]), on=["game_pk","pitcher"], how="left")
kcur = j["K_prior"].fill_null(0).to_numpy(); ncur = j["PA_prior"].fill_null(0).to_numpy()
y23 = j["is_k"].cast(pl.Float64).to_numpy()
eps = 1e-6
def plogloss(p, yy): return float(np.mean(-(yy*np.log(np.clip(p,eps,1-eps)) + (1-yy)*np.log(1-np.clip(p,eps,1-eps)))))
sel = {}
for m in (100, 200, 300):
    p = (kcur + m*lg) / (ncur + m)
    sel[f"m={m}"] = {"logloss_2023_pooled": round(plogloss(p, y23), 6)}
best_m = min(sel, key=lambda k: sel[k]["logloss_2023_pooled"])
best_m_val = int(best_m.split("=")[1])
print("P2 2023-fold selection:", sel, "-> selected", best_m)

# ---------- 2024 prior-season aggregates (from 2023) ----------
pg24prior = pg.filter(pl.col("season")==2023).group_by("pitcher").agg(
    pl.col("K").sum().alias("K_prior_season"), pl.col("PA").sum().alias("PA_prior_season"))
lg_prior_2023 = float(pg.filter(pl.col("season")==2023).select((pl.col("K").sum()/pl.col("PA").sum())).item())

# ---------- 2024 current-season prior counts ----------
pg24 = pg.filter(pl.col("season")==2024).sort(["pitcher","game_date","game_pk"]).with_columns(
    (pl.col("K").cum_sum().over(["pitcher"]) - pl.col("K")).alias("K_curr"),
    (pl.col("PA").cum_sum().over(["pitcher"]) - pl.col("PA")).alias("PA_curr"))
pg24 = pg24.with_columns(pl.col(["K_curr","PA_curr"]).first().over(["pitcher","game_date"]))

# ---------- PA-1B-O population recalculation ----------
pa24 = pa.filter(pl.col("season")==2024)
split_keys = set((r["game_pk"], r["at_bat_number"]) for r in rows_v2 if r["season"]==2024)
pa24 = pa24.with_columns(pl.struct(["game_pk","at_bat_number"]).map_elements(
    lambda s: (s["game_pk"], s["at_bat_number"]) in split_keys, return_dtype=pl.Boolean).alias("split_pa"))
tr24 = set((r["game_pk"], r["at_bat_number"]) for r in json.loads((PA1A/"attribution_reconciliation.json").read_text(encoding="utf-8"))["rows"] if r["season"]==2024)
pa24 = pa24.with_columns(pl.struct(["game_pk","at_bat_number"]).map_elements(
    lambda s: (s["game_pk"], s["at_bat_number"]) in tr24, return_dtype=pl.Boolean).alias("trunc_flag"))
prim24 = pa24.filter(~pl.col("trunc_flag"))
# official starter map per (game_pk, pitcher) via firstp
off_map = {(g,s) for g,s in zip(firstp["game_pk"].to_list(), firstp["official_starter"].to_list())}
prim24x = prim24.join(pg.select(["game_pk","pitcher","PA","is_official_starter"]).rename({"PA":"official_BF"}),
                      on=["game_pk","pitcher"], how="left")
g24 = (prim24x.filter(~pl.col("split_pa")).group_by(["game_pk","pitcher"]).agg(
        pl.len().alias("n_rows"), pl.col("official_BF").first(), pl.col("is_official_starter").first(),
        pl.col("game_date").first(), pl.col("game_date").dt.month().first().alias("month"))
       .with_columns((pl.col("n_rows")==pl.col("official_BF")).alias("exact")))
pop = {
    "all_completing_starts_2024": g24.height,
    "official_starter_starts": int(g24.filter(pl.col("is_official_starter")).height),
    "bulk9_starts_excluded": int((~g24["is_official_starter"]).sum()),
    "exact_and_official_and_nosplit": int(g24.filter(pl.col("exact") & pl.col("is_official_starter")).height),
    "pa1a_4514_note": "Phase 5 count included >=9-PA bulk pitchers and did not exclude split PAs at start level",
    "primary_starts": int(g24.filter(pl.col("exact") & pl.col("is_official_starter")).height),
}
print("PA-1B-O population:", json.dumps(pop))
census_rows = prim24x.group_by("is_official_starter").agg(pl.len().alias("rows"), pl.col("is_k").sum().alias("ks")).to_dicts()
print("PA-1A row official-starter share:", census_rows)

# ---------- Gate B: frozen comparator temporal manifest ----------
frozen = {
    "verdict_for_2024_comparison": "DESCRIPTIVE_TRAIN_OVERLAP_ONLY_NOT_PRIMARY",
    "clean_comparison_period": "2025 (deferred; not run this phase)",
    "components": [
        {"component": "LightGBM member sparse72_monotone", "artifact": "artifacts/models/lightgbm_krate_mono_20260821_054127",
         "fit": "train <=2024-06-08; val 2024-06-09..08-05; test >=2024-08-06 (sidecar cutoffs)",
         "status_2024": "REPLAYABLE_BUT_TRAIN_OVERLAP"},
        {"component": "LightGBM member final58", "artifact": "artifacts/models/lightgbm_krate_20260821_054126",
         "fit": "same cutoffs", "status_2024": "REPLAYABLE_BUT_TRAIN_OVERLAP"},
        {"component": "Ensemble weights 0/0.60/0.40", "artifact": "production/ops/live_krate_ensemble.json",
         "selection": "2026-08-21 sweep on 2026-era ROI (source csv aug21_deduped)",
         "status_2024": "REPLAYABLE_BUT_SELECTION_EXPOSED"},
        {"component": "TBF Ridge", "artifact": "artifacts/models/tbf_pa_ridge_workload_context_bullpen_20260728_035607.joblib",
         "fit": "2023-24 only (audit L1194)", "status_2024": "REPLAYABLE_BUT_TRAIN_OVERLAP (fits within 2024)"},
        {"component": "Count layer", "artifact": "count_layer.py poisson", "fit": "structural",
         "status_2024": "REPLAYABLE_AND_OOF_VALID"},
        {"component": "WS1c calibration", "artifact": "prob_calibration_ws1c_platt_20260910_012559",
         "fit": "fit_cutoff 2026-09-03", "status_2024": "REPLAYABLE_BUT_SELECTION_EXPOSED"},
        {"component": "OOF frozen predictions for 2024", "status": "NOT_FOUND (no stored 2024 production predictions; "
         "historical_scores are 2025-26 live logs)"},
    ],
    "decision": "Frozen comparator arm STOPPED for 2024 primary; descriptive-train-overlap replay deferred; "
                "first clean frozen comparison = 2025 validation.",
}
(OB/"frozen_comparator_validity.json").write_text(json.dumps(frozen, indent=1), encoding="utf-8")

# ---------- Gate C: cards ----------
COMMON = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(), "git": tree(),
    "inputs": [
        {"path": "research/offseason_2026/datasets/pa_table_2023_2024.parquet", "sha256": sha(WS/"datasets/pa_table_2023_2024.parquet")},
        {"path": "data/processed/pitcher_games.parquet", "sha256": sha(REPO/"data/processed/pitcher_games.parquet")},
        {"path": "research/offseason_2026/experiments/pa1a_raw_pa/per_pa.parquet", "sha256": sha(PA1A/"per_pa.parquet")},
        {"path": "research/offseason_2026/experiments/pa1a_raw_pa/card.json", "sha256": (json.loads((PA1A/"hashes.json").read_text(encoding="utf-8")))["pa1a_card_sha256"]},
        {"path": "research/offseason_2026/experiments/pa1a_raw_pa/attribution_reconciliation.json", "sha256": (PA1A/"attribution_sha.txt").read_text(encoding="utf-8")},
    ],
    "bootstrap": {"primary": {"cluster": "game_date", "B": 2000, "seed": 0, "ci": "percentile 95"},
                  "sensitivity": {"cluster": "game_pk"}, "fav_convention": "% replicates favoring challenger; negative deltas favor second arm"},
    "clip": "[1e-6, 1-1e-6] on all arm outputs; no tuning",
    "prohibited": ["2025/2026 scoring", "projected lineups", "count distributions (PB)", "calibration fitting for prediction",
                   "policy/ROI/CLV/Sharpe", "trained models (logistic/LGBM/CatBoost/hierarchical/neural)",
                   "frozen-TBF use", "production modification", "dataset modification", "PA-1A output modification",
                   "post-hoc variant addition", "git state changes"],
}
CARD_P = {
    "experiment_id": "PITCHER-PRIOR-P", "label": "Pitcher cold-start repair research; development only",
    **COMMON,
    "league_prior": "0.223813 (ratified; used as shrinkage target and fallback in ALL P arms for comparability)",
    "arms": {
        "P0": "p = coalesce(k_rate_std, 0.223813) [identical to PA-1A M1]",
        "P1": {"formula": "p = (K_prior_season + 200*lg)/(PA_prior_season + 200)",
               "prior_source": "pitcher_games 2023 rows (>=9-PA appearances) aggregated per pitcher",
               "fallback": "0.223813 when PA_prior_season==0 (no prior season / prior role below eligibility)",
               "known_limitation": "prior includes any >=9-PA appearance (mixed roles inseparable historically); "
                                    "relief-only priors not separable; disclosed"},
        "P2": {"formula": "p = (K_curr + m*lg)/(PA_curr + m)",
               "m_selection": "m in {100,200,300} selected by 2023-only pitcher-only logloss (two chronological "
                               "2023 blocks pooled), NEVER on 2024 E1/E2",
               "selected_m": best_m_val, "selection_detail": sel,
               "fallback": "0.223813 when PA_curr==0"},
        "P3": {"formula": "p = (K_prior_season + K_curr + m_sel*lg)/(PA_prior_season + PA_curr + m_sel)",
               "m_sel": best_m_val,
               "fallback": "0.223813 when total history == 0"},
        "P4": "OMITTED before hashing: no exact pre-registered short-deviation formulation exists in repo evidence",
    },
    "forms": "each arm evaluated pitcher-only AND in log5 with the unchanged PA-1A batter component (b_k_rate_std_shrunk)",
    "evaluation": {"blocks": "E1 2024-03-28..06-30 (n=55,815); E2 2024-07-01..09-30 (n=50,252); primary population = PA-1A primary 2024 rows, identical rows across arms",
                    "metrics": "logloss primary; brier, CITL, alpha/beta, ECE-20bin secondary; paired date-cluster bootstrap; game_pk sensitivity",
                    "slices": ["month","pitcher_history_bucket(prior-season PA: none/1-49/50-149/150+)","rookie_status(no prior season AND PA_curr==0)",
                               "prior_season_availability","pitcher handedness","batter_history_bucket","matchup_number","official-starter vs bulk9 sensitivity"]},
    "selection_rule": "at most one arm promoted for development; qualifies only if: improves M2 logloss in BOTH blocks; "
                      "brier not materially worse in either; improves early-season buckets; no late-season material "
                      "degradation; calibration not materially worse; not confined to one month/subset; pregames "
                      "reproducible; deterministic. Order: both-block logloss stability > early-season gain > brier > "
                      "calibration > simplicity > fallback dependence. Pooled never decisive.",
    "outputs": ["card.json","hashes.json","prep.json","pitcher_identity_resolution.json","pa_predictions.parquet",
                "metrics.json","paired_comparisons.json","calibration.json","slices.json","bootstrap.json",
                "deviations.md","report.md"],
}
CARD_O = {
    "experiment_id": "PA-1B-O", "label": "Oracle opportunity decomposition; not pregame xK, not actionable replay",
    **COMMON,
    "population_primary": {
        "definition": "2024 starts where modeled pitcher == official starter; primary PA-1A rows; split PAs EXCLUDED; "
                       "no truncated rows; row count == official_BF (pitcher_games PA, canonical proxy for official BF); "
                       ">=1 row",
        "recalculated": pop,
        "difference_vs_phase5_4514": "documented in prep.json",
    },
    "sensitivity_populations": ["starts including reconciled split PAs", "bulk9-pitcher starts (nontraditional role)",
                                 "197 non-exact-reconciliation starts (only if target reconciles)"],
    "arms": ["M0","M1","M2 (original PA-1A per_pa.parquet predictions)","each P-arm log5 (transparency)",
             "selected repaired baseline if promoted"],
    "aggregation": "oracle_xK_a = sum(p_a_t over included rows of the start); actual_K = sum(is_k) over the same rows",
    "metrics": ["MAE","RMSE","mean_error","median_abs_error","mean_pred_xK","mean_actual_K","correlation(descriptive)","error quantiles"],
    "slices": ["E1/E2","actual BF bucket (<=17/18-23/24-27/>=28)","actual K bucket","trips","month",
               "pitcher-history bucket","rookie status","handedness","official vs bulk9","with/without split exclusion"],
    "paired_comparisons": ["M2-M1","M2-M0","selected-M2","selected-M1","each valid PA arm vs frozen comparator IF temporally valid (NOT the case for 2024; see frozen_comparator_validity.json)"],
    "frozen_comparator": "STOPPED for 2024 primary: train/selection overlap (members fit <=2024-06-08; weights+WS1c 2026). "
                          "DESCRIPTIVE_TRAIN_OVERLAP only; clean comparison deferred to 2025.",
    "residual_diagnostics": "per-start residuals + within-cluster ICC by start/pitcher/batter/team/month/trip; diagnostic only, no corrective fitting",
    "outputs": ["card.json","hashes.json","preflight.json","start_predictions.parquet","metrics.json",
                "paired_comparisons.json","slices.json","bootstrap.json","residual_diagnostics.json",
                "frozen_comparator_validity.json","deviations.md","report.md"],
}
for d, card in ((PP, CARD_P), (OB, CARD_O)):
    (d/"card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    hh = {"card_sha256": sha(d/"card.json"), "inputs": card["inputs"]}
    (d/"hashes.json").write_text(json.dumps(hh, indent=2), encoding="utf-8")
    print(d.name, "card sha:", hh["card_sha256"][:16])

prep = {"best_m": best_m_val, "p2_selection": sel, "lg_prior_2023": lg_prior_2023,
        "pa1b_population": pop, "pa1a_row_official_share": census_rows,
        "census": census_dict, "role_relationships": dict(rel_counts)}
(PP/"prep.json").write_text(json.dumps(prep, indent=2), encoding="utf-8")
(OB/"prep.json").write_text(json.dumps(prep, indent=2), encoding="utf-8")
print("PREP COMPLETE")
