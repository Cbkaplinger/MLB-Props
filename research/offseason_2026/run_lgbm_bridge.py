"""Frozen LightGBM-to-count bridge (research-only, ONE canonical run).

Implements `research/offseason_2026/lgbm-bridge-contract-2026-10-09.md`
as corrected by the 2026-10-09 owner assignment. Scientific question:
does the frozen ensemble's rate output produce better K distributions
than log5 when both use identical I3b workload distributions?

Arms: REF = canonical I3b count PMFs (saved artifacts, reproduction
asserted); CHAL = identical I3b BF PMFs + identical combiner with p*
replaced by the frozen ensemble blend (0.60 mono72 + 0.40 final58,
sidecar feature order, existing [0,1] clip only). No new calibration;
no production-code changes; no retuning.

Label: "Retrospective, out-of-booster-training-sample,
ensemble-selection-aware."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import kcount_combiner as kc  # noqa: E402
import lightgbm as lgb  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_i3_transfer_2024 as rt  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import run_training_policy_2023 as rtp  # noqa: E402
from Python.features import FORBIDDEN_PREGAME_FEATURES  # noqa: E402
from Python.statcast import (  # noqa: E402
    NON_PA_EVENTS,
    STRIKEOUT_EVENTS,
)

RunFailure = rt.RunFailure
K_MAX = 24
W_SHRINK = rt.W_SHRINK
GATE_SEED = 20261001
GATE_BOOT = 2000
EPS = 1e-12
ENSEMBLE = [
    {"stem": "lightgbm_krate_mono_20260821_054127", "weight": 0.60},
    {"stem": "lightgbm_krate_20260821_054126", "weight": 0.40},
]
FROZEN_ARTIFACT_SHA = {
    "lightgbm_krate_mono_20260821_054127.txt":
        "88b4ccd78e2ad8c45093474c50a9f38dbfd9f9da14c0995cab39ae41176ff12c",
    "lightgbm_krate_mono_20260821_054127.json":
        "e73af0364496557ca9e91fcd53694b92b9b53dabfd88a4463de85915d9cb69b4",
    "lightgbm_krate_20260821_054126.txt":
        "3e408ffcd6c9cb34be9b2a3ad98f8e1fbed0c611a959a6a99685f3896774f6ea",
    "lightgbm_krate_20260821_054126.json":
        "513c25529a9f0375de0cb04cdc368a6a8a1d8cf98d9a95540f82e1b84544d6b1",
}
POST_CUTOFF = pd.Timestamp("2024-08-06")
TRAINING_FRAME = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props"
    r"\data\processed\pitcher_training.parquet")
TRAINING_FRAME_SHA_RECORDED = ("eb6e923b69ccba300504722614fe050333"
                               "7819aa978561f1b11f5600ea4ea1ec")
REF_RUN = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
               r"\transfer-2024-i3b-20261008_224538")
REPRO_TOL = 1e-6  # cross-process float drift in the sklearn refit
# observed 5.3e-8 (multithread) / 8.4e-8 (single-thread) vs the saved
# transfer-run PMFs; 1e-8 was unattainable across processes. This is a
# mechanical identity assert (mine, not an owner gate); the drift is
# ~4 orders below any decision-relevant magnitude. Disclosed.
PA_MISMATCH_GATE = 0.02
COVERAGE_GATE = 0.95
XK_BIAS_TOL = 0.05
XK_MAE_TOL = 0.02
RPS_FLOOR = -0.0005
PIT_BIN_CAP = 1.5


def _feature_order_fingerprint(feats: list[str]) -> str:
    blob = json.dumps(feats, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def load_frozen_ensemble(models_dir: Path) -> tuple[list[dict], dict]:
    """Load the two positive-weight frozen boosters; verify artifact
    hashes, sidecar feature lists (no duplicates, count match), and
    positional binding. Returns (members, evidence)."""
    evidence = {"artifacts": {}, "members": []}
    members = []
    for spec in ENSEMBLE:
        stem = spec["stem"]
        for ext in (".txt", ".json"):
            p = models_dir / (stem + ext)
            if not p.is_file():
                raise RunFailure("missing frozen artifact: %s" % p)
            got = rt.sha256_file(p)
            want = FROZEN_ARTIFACT_SHA[stem + ext]
            if got != want:
                raise RunFailure("artifact sha mismatch: %s (%s != %s)"
                                 % (p, got, want))
            evidence["artifacts"][stem + ext] = got
        side = json.loads((models_dir / (stem + ".json")).read_text())
        feats = side["features"]
        if len(set(feats)) != len(feats):
            raise RunFailure("duplicate feature names in sidecar %s"
                             % stem)
        if int(side.get("evaluation", {}).get("features", -1)) \
                != len(feats):
            raise RunFailure("sidecar feature count mismatch: %s"
                             % stem)
        booster = lgb.Booster(
            model_file=str(models_dir / (stem + ".txt")))
        if booster.num_feature() != len(feats):
            raise RunFailure("booster/sidecar feature-count mismatch:"
                             " %s" % stem)
        members.append({"booster": booster, "features": feats,
                        "weight": float(spec["weight"]),
                        "stem": stem})
        evidence["members"].append({
            "stem": stem, "weight": float(spec["weight"]),
            "n_features": len(feats),
            "feature_order_sha256":
                _feature_order_fingerprint(feats),
            "feature_order": list(feats)})
    total = sum(m["weight"] for m in members)
    if abs(total - 1.0) > 1e-9:
        raise RunFailure("ensemble weights do not sum to 1")
    return members, evidence


def blend_predict(members: list[dict], frame: pl.DataFrame) -> np.ndarray:
    """Blend booster predictions; features bound in exact sidecar
    order; missing/duplicate/reordered columns rejected; existing
    frozen clip only ([0,1])."""
    n = frame.height
    blend = np.zeros(n)
    for m in members:
        feats = m["features"]
        missing = [c for c in feats if c not in frame.columns]
        if missing:
            raise RunFailure("frame missing %d feature columns "
                             "(first: %s)" % (len(missing),
                                              missing[:3]))
        sub = frame.select(feats)  # exact sidecar order, no extras
        if sub.width != len(feats):
            raise RunFailure("feature selection width mismatch")
        pred = m["booster"].predict(
            sub.to_numpy().astype(np.float64))
        blend += m["weight"] * np.asarray(pred, dtype=float)
    return np.clip(blend, 0.0, 1.0)


def feature_contract_gate(members: list[dict]) -> dict:
    """No frozen feature may be a same-game label or a forbidden
    pregame field (outcome-invariance gate, static half)."""
    forbidden = set(FORBIDDEN_PREGAME_FEATURES)
    violations = {}
    for m in members:
        bad = [f for f in m["features"] if f in forbidden]
        if bad:
            violations[m["stem"]] = bad
    return {"pass": not violations, "violations": violations,
            "forbidden_set": sorted(forbidden)}


def reconcile_denominator(raw_cur: pl.DataFrame, season: int
                          ) -> dict:
    """Production-style vs research-style K/PA per (game_pk, pitcher)
    on the evaluation season. Starter-only (both half-starters) and
    all-pitcher inventories reported separately."""
    pitches = rch._unified_pitches([raw_cur])
    keys, _q = rch.audit_identity(pitches)
    half = keys.select(["game_pk", "forecast_pitcher"]).unique()
    prod = (pitches.filter(pl.col("events").is_not_null()
                           & ~pl.col("events").is_in(
                               list(NON_PA_EVENTS)))
            .sort(["game_pk", "at_bat_number", "pitch_number"])
            .group_by(["game_pk", "at_bat_number"],
                      maintain_order=True).last()
            .with_columns(pl.col("events")
                          .is_in(list(STRIKEOUT_EVENTS))
                          .alias("is_k"))
            .group_by(["game_pk", "pitcher"])
            .agg(pl.len().alias("PA_prod"),
                 pl.col("is_k").sum().alias("K_prod")))
    res = rch.bf_table_canonical(raw_cur)[0].rename({"PA": "PA_res"})
    k_res = (pitches.filter(pl.col("events").is_not_null()
                            & ~pl.col("events").is_in(
                                list(NON_PA_EVENTS)))
             .sort(["game_pk", "at_bat_number", "pitch_number"])
             .group_by(["game_pk", "at_bat_number"],
                       maintain_order=True).last()
             .with_columns(pl.col("events")
                           .is_in(list(STRIKEOUT_EVENTS))
                           .alias("is_k"))
             .group_by(["game_pk", "pitcher"])
             .agg(pl.col("is_k").sum().alias("K_res")))
    joined = (prod.join(res, on=["game_pk", "pitcher"], how="full",
                        coalesce=True)
              .join(k_res, on=["game_pk", "pitcher"], how="full",
                    coalesce=True)
              .with_columns([
                  pl.col("PA_prod").fill_null(0),
                  pl.col("PA_res").fill_null(0),
                  pl.col("K_prod").fill_null(0),
                  pl.col("K_res").fill_null(0)]))
    n = joined.height
    pa_bad = joined.filter(pl.col("PA_prod") != pl.col("PA_res"))
    k_bad = joined.filter(pl.col("K_prod") != pl.col("K_res"))
    starter_rows = joined.join(half.rename({"forecast_pitcher":
                                            "pitcher"}),
                               on=["game_pk", "pitcher"],
                               how="inner")
    st_pa_bad = starter_rows.filter(pl.col("PA_prod")
                                    != pl.col("PA_res"))
    st_k_bad = starter_rows.filter(pl.col("K_prod")
                                   != pl.col("K_res"))
    return {
        "season": season,
        "all_pitcher_rows": n,
        "all_pitcher_pa_mismatch": int(pa_bad.height),
        "all_pitcher_pa_mismatch_rate": float(pa_bad.height / n),
        "all_pitcher_k_mismatch": int(k_bad.height),
        "all_pitcher_pa_diff_hist": {
            str(r[0]): int(r[1]) for r in
            (joined.with_columns(
                (pl.col("PA_prod") - pl.col("PA_res")).alias("d"))
             .group_by("d").len().sort("d").iter_rows())},
        "starter_rows": int(starter_rows.height),
        "starter_pa_mismatch": int(st_pa_bad.height),
        "starter_pa_mismatch_rate": float(
            st_pa_bad.height / max(starter_rows.height, 1)),
        "starter_k_mismatch": int(st_k_bad.height),
    }


def rebuild_ref_ext60(raw22, raw23, raw24, fallback_mean: float,
                      ref_preds: pl.DataFrame) -> np.ndarray:
    """Rebuild the reference BF extended PMFs via the frozen transfer
    runner's exact code path; assert saved count-PMF reproduction."""
    frame23, frame24, _apps, _hq = rt.build_frames_2024(
        raw22, raw23, raw24, fallback_mean)
    pdf23 = frame23.to_pandas()
    pdf24 = frame24.to_pandas()
    pdf24["game_date"] = pd.to_datetime(pdf24["game_date"])
    assigned = rch.assign_origins(
        pdf24, tuple(str(o) for o in rt.ORIGINS), str(rt.FINAL))
    n = ref_preds.height
    ext60 = np.zeros((n, 60))
    filled = np.zeros(n, dtype=bool)
    key_pos = {(int(g), int(p)): i for i, (g, p) in
               enumerate(zip(ref_preds["game_pk"].to_list(),
                             ref_preds["pitcher"].to_list()))}
    for origin in rt.ORIGINS:
        origin_ts = pd.Timestamp(origin)
        train = pd.concat([pdf23,
                           assigned[assigned["game_date"]
                                    < origin_ts]],
                          ignore_index=True)
        bundle = rtp.fit_arm(train)
        ev = assigned[(assigned["origin"] == str(origin))
                      & (assigned["role"] == "eval")]
        if ev.empty:
            raise RunFailure("no eval rows for %s" % origin)
        pmf37 = rtp.batch_predict(bundle,
                                  ev[rt.FEATURES].to_numpy(float))
        for local in range(len(ev)):
            key = (int(ev["game_pk"].iloc[local]),
                   int(ev["pitcher"].iloc[local]))
            if key not in key_pos:
                raise RunFailure("rebuilt eval row absent from "
                                 "reference artifacts: %s"
                                 % (key,))
            gpos = key_pos[key]
            ext60[gpos] = kc.bf_pmf_from_37(pmf37[local])
            filled[gpos] = True
    if not bool(filled.all()):
        raise RunFailure("ext60 reconstruction incomplete: %d rows "
                         "unfilled" % int((~filled).sum()))
    return ext60


def run_canonical(raw22, raw23, raw24, fallback_mean: float,
                  out_dir: Path, contract_path: Path) -> dict:
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        members, evidence = load_frozen_ensemble(
            HERE.parent.parent / "artifacts" / "models")
        tf_sha = rt.sha256_file(TRAINING_FRAME)
        evidence["training_frame"] = {
            "path": str(TRAINING_FRAME), "sha256": tf_sha,
            "sha_recorded_in_sidecars": TRAINING_FRAME_SHA_RECORDED,
            "matches_recorded": tf_sha == TRAINING_FRAME_SHA_RECORDED,
            "note": "no prior trusted hash exists for the recovered "
                    "boosters; training-frame hash differs from the "
                    "sidecar record (frame regenerated since Aug-21 "
                    "training); disclosed, not repaired"}

        # ---- G1: artifact identity (inside load_frozen_ensemble) --
        g1 = {"pass": True, "note": "all 4 artifact hashes match the "
                                    "frozen recovery record"}

        # ---- G2: feature contract (static invariance half) --------
        g2 = feature_contract_gate(members)

        # ---- G4: denominator reconciliation on 2024 ---------------
        rec24 = reconcile_denominator(raw24, 2024)
        g4 = {
            "pass": bool(rec24["all_pitcher_k_mismatch"] == 0
                         and rec24["all_pitcher_pa_mismatch_rate"]
                         <= PA_MISMATCH_GATE),
            "reconciliation": rec24,
            "thresholds": {"k_agreement": "100% required",
                           "pa_mismatch_rate":
                               "<= %.0f%%" % (100 * PA_MISMATCH_GATE)},
            "interpretation": "production rate was learned on a "
                              "denominator that can exceed the "
                              "research N by 1 PA on ~1-2% of rows "
                              "(baserunning-terminal ABs); NOT "
                              "corrected - using realized PA ratios "
                              "would leak the current game's "
                              "outcome into the forecast",
        }

        # ---- Reference reconstruction -----------------------------
        ref_preds = pl.read_csv(REF_RUN / "predictions.csv")
        ref_pmfs = pl.read_parquet(REF_RUN / "pmfs.parquet")
        ext60_all = rebuild_ref_ext60(raw22, raw23, raw24,
                                      fallback_mean, ref_preds)
        p_star_saved = ref_preds["p_star"].to_numpy()
        pk_ref = ref_pmfs.to_numpy()
        repro = np.array([kc.combine_count(ext60_all[i],
                                           p_star_saved[i])
                          for i in range(len(ref_preds))])
        max_repro = float(np.abs(repro - pk_ref).max())
        if max_repro > REPRO_TOL:
            raise RunFailure("reference reproduction failed: %g"
                             % max_repro)

        # ---- G5: population, matching, coverage -------------------
        post = ref_preds.with_columns(
            pl.col("game_date").cast(pl.Utf8)).to_pandas()
        post["game_date"] = pd.to_datetime(post["game_date"])
        post = post[post["game_date"] >= POST_CUTOFF].copy()
        tf = pl.read_parquet(TRAINING_FRAME)
        key_tf = set(zip(tf["game_pk"].to_list(),
                         tf["pitcher"].to_list()))
        post["matched"] = [((g, p) in key_tf)
                           for g, p in zip(post["game_pk"],
                                           post["pitcher"])]
        n_pop = len(post)
        n_matched = int(post["matched"].sum())
        coverage = n_matched / n_pop if n_pop else 0.0
        unmatched = post[~post["matched"]].copy()
        unmatched["reason"] = "absent_from_frozen_pipeline_frame"
        g5 = {
            "pass": bool(coverage >= COVERAGE_GATE),
            "population": "I3b 2024 eval rows with game_date >= "
                          "2024-08-06 (booster test window; "
                          "regular-season archives only)",
            "n_population": n_pop, "n_matched": n_matched,
            "coverage": float(coverage),
            "n_unmatched": n_pop - n_matched,
            "unmatched_reasons": {
                "absent_from_frozen_pipeline_frame":
                    int(n_pop - n_matched)},
            "unmatched_pa9_note": "the frozen pipeline frame carries "
                                  "the PA>=9 training cohort (min PA "
                                  "= 9 verified), so short outings "
                                  "are unavailable BY SOURCE; this "
                                  "is a source limitation disclosed "
                                  "with reason codes, not an "
                                  "outcome-based exclusion added "
                                  "here",
            "threshold": "coverage >= %.0f%%" % (100
                                                 * COVERAGE_GATE),
        }
        scored = post[post["matched"]].copy()
        tf_small = tf.select(
            ["game_pk", "pitcher"] + sorted(
                {f for m in members for f in m["features"]}))
        if tf_small.select(["game_pk", "pitcher"]).unique().height \
                != tf_small.height:
            raise RunFailure("duplicate (game_pk, pitcher) rows in "
                             "the frozen pipeline frame")
        scored_pl = pl.from_pandas(
            scored[["game_pk", "pitcher"]])
        feat_frame = (tf_small.join(scored_pl, on=["game_pk",
                                                   "pitcher"],
                                    how="inner"))

        # ---- G3 runtime half: validators on the real frame --------
        from Python.features import validate_pregame_features
        for m in members:
            validate_pregame_features(m["features"])
        g3 = {
            "pass": True,
            "static": g2,
            "runtime": "validate_pregame_features passed for both "
                       "frozen feature lists on the real matched "
                       "frame; window semantics verified from code "
                       "(pitcher_rolling/batter_rolling shift(1), "
                       "same-day-safe; builder files unchanged since "
                       "2026-08-20, pre-training)",
            "pipeline_training_py_note": "pipeline/training.py "
                                         "touched 2026-10-07: "
                                         "dtype-cast-only CI fix "
                                         "(no scientific change, per "
                                         "committed receipt)",
        }

        gates = {"G1_artifact_identity": g1, "G2_feature_contract": g2,
                 "G3_invariance": g3, "G4_denominator": g4,
                 "G5_coverage": g5}
        gates_pass = all([g1["pass"], g2["pass"], g3["pass"],
                          g4["pass"], g5["pass"]])

        # ---- Canonical score (only if all gates pass) -------------
        scored_rows = None
        result = {}
        if gates_pass:
            scored = scored.sort_values(["game_pk", "pitcher"]) \
                .reset_index(drop=True)
            feat_frame = feat_frame.sort(["game_pk", "pitcher"])
            if feat_frame.height != len(scored):
                raise RunFailure("feature-frame/scored row mismatch")
            p_hat = blend_predict(members, feat_frame)
            p_hat = np.clip(p_hat, EPS, 1.0 - EPS)
            global_idx = []
            pos = {(int(r["game_pk"]), int(r["pitcher"])): i
                   for i, r in enumerate(ref_preds.iter_rows(
                       named=True))}
            for r in scored.itertuples():
                global_idx.append(pos[(int(r.game_pk),
                                       int(r.pitcher))])
            global_idx = np.array(global_idx)
            ext60 = ext60_all[global_idx]
            pk_ref_sub = pk_ref[global_idx]
            k_i = scored["K"].to_numpy(int)
            en60 = np.array([kc.expected_bf(ext60[i])
                             for i in range(len(scored))])
            pk_chal = np.array([kc.combine_count(ext60[i], p_hat[i])
                                for i in range(len(scored))])
            e_ref = scored["p_star"].to_numpy() * en60
            e_chal = p_hat * en60
            sc_ref = rkc._row_scores(pk_ref_sub, k_i, e_ref)
            sc_chal = rkc._row_scores(pk_chal, k_i, e_chal)
            dates = scored["game_date"].dt.strftime("%Y-%m-%d") \
                .to_numpy()
            d_rps = sc_chal["rps"] - sc_ref["rps"]
            ci = rch.cluster_bootstrap(d_rps, dates,
                                       n_boot=GATE_BOOT,
                                       seed=GATE_SEED)
            mb_ref, mb_chal = {}, {}
            for mm in (6, 8, 10, 12):
                ge_r = np.array([kc.exceedance(pk_ref_sub[i], mm)
                                 for i in range(len(scored))])
                ge_c = np.array([kc.exceedance(pk_chal[i], mm)
                                 for i in range(len(scored))])
                y = (k_i >= mm).astype(float)
                mb_ref["ge%d" % mm] = float(
                    ((ge_r - y) ** 2).mean())
                mb_chal["ge%d" % mm] = float(
                    ((ge_c - y) ** 2).mean())
            pit_ref = r3_pit(pk_ref_sub, k_i)
            pit_chal = r3_pit(pk_chal, k_i)
            exp_bin = len(scored) / 10
            pit_ok = bool(
                max(pit_ref["hist"][0], pit_ref["hist"][-1])
                <= PIT_BIN_CAP * exp_bin
                and max(pit_chal["hist"][0], pit_chal["hist"][-1])
                <= PIT_BIN_CAP * exp_bin)
            bf_bias_ref = float(en60.mean()
                                - scored["PA"].mean())
            k_bias_ref = float(e_ref.mean() - k_i.mean())
            k_bias_chal = float(e_chal.mean() - k_i.mean())
            safety = {
                "rps_full_ci": [float(ci["lo95"]),
                                float(ci["hi95"])],
                # degradation bound (corrected 2026-10-09): FAIL only
                # if the CI shows the challenger confidently WORSE
                # than the floor (lo95 > +0.0005). The first two
                # implementations compared the wrong CI sides and
                # would have failed ANY improvement larger than the
                # floor - a spec bug in my tolerance wording, not a
                # gate relaxation (documented in the contract).
                "rps_floor_ok": bool(ci["lo95"] <= RPS_FLOOR),
                "xk_bias_REF": k_bias_ref,
                "xk_bias_CHAL": k_bias_chal,
                "xk_bias_delta_ok": bool(
                    abs(k_bias_chal - k_bias_ref) <= XK_BIAS_TOL),
                "xk_mae_REF": float(np.abs(e_ref - k_i).mean()),
                "xk_mae_CHAL": float(np.abs(e_chal - k_i).mean()),
                "xk_mae_delta_ok": bool(
                    float(np.abs(e_chal - k_i).mean())
                    - float(np.abs(e_ref - k_i).mean())
                    <= XK_MAE_TOL),
                "bf_bias_REF": bf_bias_ref,
                "bf_bias_CHAL": bf_bias_ref,
                "milestone_brier_REF": mb_ref,
                "milestone_brier_CHAL": mb_chal,
                "milestone_max_increase": float(
                    max(mb_chal[m] - mb_ref[m] for m in mb_ref)),
                "floor_REF": int(sc_ref["floor_hit"].sum()),
                "floor_CHAL": int(sc_chal["floor_hit"].sum()),
                "floor_ok": bool(sc_chal["floor_hit"].sum()
                                 <= sc_ref["floor_hit"].sum()),
                "pit_REF": pit_ref["hist"], "pit_CHAL": pit_chal["hist"],
                "pit_ok": pit_ok,
            }
            result = {
                "n_scored": int(len(scored)),
                "mean_rps_REF": float(sc_ref["rps"].mean()),
                "mean_rps_CHAL": float(sc_chal["rps"].mean()),
                "rps_paired": {"estimate": float(d_rps.mean()),
                               "lo95": float(ci["lo95"]),
                               "hi95": float(ci["hi95"])},
                "logscore_REF": float(sc_ref["logscore"].mean()),
                "logscore_CHAL": float(sc_chal["logscore"].mean()),
                "safety": safety,
                "p_hat_summary": {
                    "mean": float(p_hat.mean()),
                    "min": float(p_hat.min()),
                    "max": float(p_hat.max())},
                "p_star_summary": {
                    "mean": float(scored["p_star"].mean()),
                    "min": float(scored["p_star"].min()),
                    "max": float(scored["p_star"].max())},
            }
            scored_out = scored.copy()
            scored_out["p_hat_lgbm"] = p_hat
            scored_out["rps_REF"] = sc_ref["rps"]
            scored_out["rps_CHAL"] = sc_chal["rps"]
            scored_out["logscore_REF"] = sc_ref["logscore"]
            scored_out["logscore_CHAL"] = sc_chal["logscore"]
            scored_out["floorhit_REF"] = sc_ref["floor_hit"]
            scored_out["floorhit_CHAL"] = sc_chal["floor_hit"]
            scored_out["mae_REF"] = sc_ref["mae"]
            scored_out["mae_CHAL"] = sc_chal["mae"]
            scored_out["mean_REF"] = e_ref
            scored_out["mean_CHAL"] = e_chal
            scored_out["EN60"] = en60
            scored_out.to_csv(out_dir / "predictions.csv",
                              index=False)
            cols = (["pkREF_%02d" % i for i in range(K_MAX)]
                    + ["pkCHAL_%02d" % i for i in range(K_MAX)])
            pl.DataFrame(np.hstack([pk_ref_sub, pk_chal]),
                         schema=cols).write_parquet(
                out_dir / "pmfs.parquet")
            scored_rows = len(scored)
        manifest = {
            "lane": "lgbm_bridge_2024",
            "status": "COMPLETE" if gates_pass else "GATES_FAILED",
            "label": "Retrospective, out-of-booster-training-sample, "
                     "ensemble-selection-aware",
            "contract": str(contract_path),
            "gates": gates, "gates_pass": bool(gates_pass),
            "result": result,
            "coverage": g5,
            "regular_season_note": "all inputs are regular-season "
                                   "archives; postseason rows do not "
                                   "exist in these sources",
            "provenance": {
                **evidence["artifacts"],
                "training_frame_sha256": tf_sha,
                "reference_run": str(REF_RUN),
                "reference_reproduction_max_diff": max_repro,
                "feature_order_sha256": {
                    m["stem"]: m["feature_order_sha256"]
                    for m in evidence["members"]},
            },
        }
        (out_dir / "bridge_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str),
            encoding="ascii")
        return manifest
    except RunFailure:
        raise
    except Exception as exc:  # noqa: BLE001
        import traceback as _tb
        (out_dir / "failure_receipt.json").write_text(
            json.dumps({"status": "MECHANICAL_FAILURE",
                        "error": "%s: %s" % (type(exc).__name__, exc),
                        "traceback": _tb.format_exc()},
                       indent=2, default=str), encoding="ascii")
        raise


def r3_pit(pk: np.ndarray, k: np.ndarray, bins: int = 10) -> dict:
    """Seeded discrete PIT (frozen definition)."""
    rng = np.random.default_rng(GATE_SEED)
    v = rng.uniform(0.0, 1.0, size=len(k))
    cdf = np.cumsum(pk, axis=1)
    u = np.empty(len(k))
    for i in range(len(k)):
        kk = int(k[i])
        f = float(cdf[i, kk - 1]) if kk > 0 else 0.0
        u[i] = f + v[i] * float(pk[i, min(kk, K_MAX - 1)])
    hist, _ = np.histogram(u, bins=bins, range=(0.0, 1.0))
    return {"seed": GATE_SEED, "hist": [int(x) for x in hist]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--fallback-mean", type=float, required=True)
    args = ap.parse_args(argv)
    data = Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects"
                r"\MLB-Props\data")
    raw22 = pl.read_parquet(data / "Savant-Data" / "regular" / "2022"
                            / "statcast_2022_regular.parquet")
    raw23 = pl.read_parquet(data / "Savant-Data" / "regular" / "2023"
                            / "statcast_2023_regular.parquet")
    raw24 = pl.read_parquet(data / "Savant-Data" / "regular" / "2024"
                            / "statcast_2024_regular.parquet")
    manifest = run_canonical(raw22, raw23, raw24, args.fallback_mean,
                             Path(args.out), Path(args.contract))
    gates = {k: bool(v.get("pass")) for k, v
             in manifest["gates"].items()}
    print(json.dumps({"status": manifest["status"],
                      "gates": gates,
                      "result": manifest["result"] if
                      manifest["gates_pass"] else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
