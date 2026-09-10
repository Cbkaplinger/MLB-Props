"""Age-member Brier gate (post hoc, research; spec §4, backlog #59 debt).

#59 kept two age terms on MAE-both-windows, but SOP/spec judge retrain
candidates on universe Brier. Arms, same members/seeds, native splits
(2023-24 chrono + 2025 holdout eval):
  base      : deployed final58 sidecar (58)
  +age      : base + pitcher_age
  +whiffgap : base + age_x_whiff_gap

Judged: MAE (2024-test + 2025-holdout) + universe Brier on 2025-holdout
starts (Poisson + live WS1c-Platt, main-only, three-way vs production).
Keep per term: Brier gain vs base >= 0.0005 (whiff_gap owed this gate;
age confirms its #59 keep).

Writes artifacts/model_quality/age_member_brier/report.json. No live change.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.config import HOLDOUT_SEASON, PITCHER_TRAINING_PATH  # noqa: E402
from Python.count_layer import p_strikeouts_ge  # noqa: E402
from Python.features import TARGET  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import ProbCalibrationBundle  # noqa: E402
from Python.registries import resolve_feature_names  # noqa: E402
from Python.training import (  # noqa: E402
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
)

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PANEL = ROOT / "artifacts" / "odds_log" / "universe_panel.parquet"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
OUT_DIR = ROOT / "artifacts" / "model_quality" / "age_member_brier"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    sidecar58 = [f for f in resolve_feature_names(frame, "research_command_single")
                 if f != "cmd_roll30"]
    arms = {"base": sidecar58,
            "+age": sidecar58 + ["pitcher_age"],
            "+whiffgap": sidecar58 + ["age_x_whiff_gap"]}
    print(f"rows={len(frame)}")

    pool = frame.loc[frame["season"].isin((2023, 2024))].sort_values(
        ["game_date", "player_name"]).reset_index(drop=True)
    hold = frame.loc[(frame["season"] == HOLDOUT_SEASON)
                     & frame[TARGET].notna()].reset_index(drop=True)
    train, val, test = chronological_split(pool)
    print(f"train={len(train)} val={len(val)} test2024={len(test)} hold2025={len(hold)}")

    preds, iters = {}, {}
    mae = {}
    actual_test = test[TARGET].to_numpy(dtype=float)
    actual_hold = hold[TARGET].to_numpy(dtype=float)
    for name, feats in arms.items():
        model = build_model("lightgbm")
        fit_regressor(
            model, "lightgbm",
            lightgbm_matrix(train, feats), train[TARGET],
            train_weight=None,
            validation_features=lightgbm_matrix(val, feats),
            validation_target=val[TARGET],
            validation_weight=None,
            early_stopping_rounds=200,
            log_evaluation_period=0,
        )
        iters[name] = int(model.best_iteration_)
        pt = np.asarray(predict_clipped(model, "lightgbm", test, feats), dtype=float)
        ph = np.asarray(predict_clipped(model, "lightgbm", hold, feats), dtype=float)
        preds[name] = ph
        mae[name] = {"test2024": float(np.mean(np.abs(pt - actual_test))),
                     "hold2025": float(np.mean(np.abs(ph - actual_hold)))}
        print(f"{name:>10}: test={mae[name]['test2024']:.5f} hold={mae[name]['hold2025']:.5f} "
              f"(iters={iters[name]})")

    hold_pks = hold["game_pk"].tolist()
    pmap = {n: dict(zip(hold_pks, preds[n])) for n in arms}
    sc = pl.scan_parquet(SCORED).select(
        ["game_pk", "gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    sc_sel = sc.filter(pl.col("game_pk").is_in(hold_pks))
    print(f"scored join: {sc_sel.height}/{len(hold_pks)} holdout starts")
    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def cal(kr: float, tbf: float, ln: float) -> np.ndarray:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        return maps[ln].transform(np.array([raw]))

    rows = []
    for r in sc_sel.to_dicts():
        if r["game_pk"] not in pmap["base"] or r["projected_tbf"] is None:
            continue
        tbf = float(r["projected_tbf"])
        row = {"gd": r["gd"], "key": r["key_sorted"]}
        for n in arms:
            row[f"kr_{n}"] = float(np.clip(pmap[n][r["game_pk"]], 0.02, 0.5))
        row["kr_prod"] = float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5))
        row["tbf"] = tbf
        rows.append(row)
    brier: dict[str, dict] = {}
    for ln in LINES:
        sub = [r for r in rows]
        pb = np.array([cal(r["kr_base"], r["tbf"], ln)[0] for r in sub])
        pa = np.array([cal(r["kr_+age"], r["tbf"], ln)[0] for r in sub])
        pw = np.array([cal(r["kr_+whiffgap"], r["tbf"], ln)[0] for r in sub])
        pp = np.array([cal(r["kr_prod"], r["tbf"], ln)[0] for r in sub])
        keys = [(r["gd"], r["key"]) for r in sub]
        kidx = {k: i for i, k in enumerate(keys)}
        panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])
        pf = panel.filter(pl.col("line") == ln)
        pmap_y = {(g, k): (y, b) for g, k, y, b in
                  zip(pf["gd"].to_list(), pf["key"].to_list(),
                      pf["y"].to_list(), pf["p_book_close"].to_list())}
        m = [(kidx[k], pmap_y[k][0], pmap_y[k][1]) for k in keys
             if k in pmap_y and pmap_y[k][1] is not None]
        if len(m) < 50:
            continue
        y = np.array([x[1] for x in m])
        bb = np.array([x[2] for x in m])
        idx = [x[0] for x in m]
        brier[str(ln)] = {"n": len(m),
                          "base": float(np.mean((pb[idx] - y) ** 2)),
                          "age": float(np.mean((pa[idx] - y) ** 2)),
                          "whiffgap": float(np.mean((pw[idx] - y) ** 2)),
                          "prod": float(np.mean((pp[idx] - y) ** 2)),
                          "book": float(np.mean((bb - y) ** 2))}
    tot = {"base": [], "age": [], "whiffgap": []}
    ntot = 0
    for ln, b in brier.items():
        for k in tot:
            tot[k].append(b[k] * b["n"])
        ntot += b["n"]
    pooled = {k: sum(v) / ntot for k, v in tot.items()}
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "n_train": len(train), "n_val": len(val),
           "n_test2024": len(test), "n_hold2025": len(hold),
           "iters": iters, "mae": mae, "per_line": brier, "n_brier": ntot,
           "gain_age": pooled["base"] - pooled["age"],
           "gain_whiffgap": pooled["base"] - pooled["whiffgap"],
           "keep_age": bool(pooled["base"] - pooled["age"] >= 0.0005),
           "keep_whiffgap": bool(pooled["base"] - pooled["whiffgap"] >= 0.0005)}
    print(f"Brier n={ntot}: base={pooled['base']:.4f} age={pooled['age']:.4f} "
          f"whiffgap={pooled['whiffgap']:.4f} gain_age={rep['gain_age']:+.5f} "
          f"gain_whiff={rep['gain_whiffgap']:+.5f}")
    print(f"keep_age={rep['keep_age']} keep_whiffgap={rep['keep_whiffgap']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
