"""kAdj member test (post hoc, research; spec §6 step 2, backlog #60).

Single-feature rule, native splits (2023-24 chrono train/val/test + 2025
holdout eval), same members/seeds/early-stopping. Arms:
  base : deployed final58 sidecar (58)
  kadj : base + kadj (58+1; nulls kept, LightGBM-native)

kadj is computed in-frame via the pipeline join (no L3 rebuild needed).
Judged: MAE on 2024-test + 2025-holdout, then universe Brier (Poisson +
live WS1c-Platt, main-market only) three-way vs the production bundle.
Kill: universe Brier gain vs base < 0.0005 (SOP default).

Writes artifacts/model_quality/kadj_member/report.json. No live change.
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
from Python.pipeline.training import _join_kadj_features  # noqa: E402
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
OUT_DIR = ROOT / "artifacts" / "model_quality" / "kadj_member"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    l3 = pl.read_parquet(PITCHER_TRAINING_PATH)
    print(f"L3 rows: {l3.height}")
    l3k = _join_kadj_features(l3)
    assert l3k.height == l3.height
    frame = l3k.to_pandas()
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    if "kadj" not in frame.columns:
        raise ValueError("kadj join produced no column")

    base_feats = [f for f in resolve_feature_names(frame, "research_command_single")
                  if f != "cmd_roll30"]
    kadj_feats = base_feats + ["kadj"]
    assert len(kadj_feats) == len(base_feats) + 1
    print(f"base={len(base_feats)} kadj={len(kadj_feats)}")

    pool = frame.loc[frame["season"].isin((2023, 2024))].sort_values(
        ["game_date", "player_name"]).reset_index(drop=True)
    hold = frame.loc[(frame["season"] == HOLDOUT_SEASON)
                     & frame[TARGET].notna()].reset_index(drop=True)
    train, val, test = chronological_split(pool)
    print(f"train={len(train)} val={len(val)} test2024={len(test)} "
          f"hold2025={len(hold)}")

    preds, iters = {}, {}
    for name, feats in (("base", base_feats), ("kadj", kadj_feats)):
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
        preds[name] = {
            "test": np.asarray(predict_clipped(model, "lightgbm", test, feats), dtype=float),
            "hold": np.asarray(predict_clipped(model, "lightgbm", hold, feats), dtype=float),
        }
    actual_test = test[TARGET].to_numpy(dtype=float)
    actual_hold = hold[TARGET].to_numpy(dtype=float)
    mae = {k: {"test2024": float(np.mean(np.abs(preds[k]["test"] - actual_test))),
               "hold2025": float(np.mean(np.abs(preds[k]["hold"] - actual_hold)))}
           for k in preds}
    print(f"MAE base test={mae['base']['test2024']:.5f} hold={mae['base']['hold2025']:.5f}")
    print(f"MAE kadj test={mae['kadj']['test2024']:.5f} hold={mae['kadj']['hold2025']:.5f} "
          f"iters={iters}")

    # Universe Brier on holdout-season starts (production TBF both arms).
    test_pks = hold["game_pk"].tolist()
    base_map = dict(zip(test_pks, preds["base"]["hold"]))
    kadj_map = dict(zip(test_pks, preds["kadj"]["hold"]))
    sc = pl.scan_parquet(SCORED).select(
        ["game_pk", "gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    sc_sel = sc.filter(pl.col("game_pk").is_in(test_pks))
    print(f"scored join: {sc_sel.height}/{len(test_pks)} holdout starts")
    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def cal(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        return float(maps[ln].transform(np.array([raw]))[0])

    rows = []
    for r in sc_sel.to_dicts():
        if r["game_pk"] not in kadj_map or r["projected_tbf"] is None:
            continue
        tbf = float(r["projected_tbf"])
        for ln in LINES:
            rows.append({"gd": r["gd"], "key": r["key_sorted"], "line": float(ln),
                         "p_base": cal(float(np.clip(base_map[r["game_pk"]], 0.02, 0.5)), tbf, ln),
                         "p_kadj": cal(float(np.clip(kadj_map[r["game_pk"]], 0.02, 0.5)), tbf, ln),
                         "p_prod": cal(float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5)), tbf, ln)})
    cand = pl.DataFrame(rows)
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])
    cmpf = cand.join(panel, on=["gd", "key", "line"], how="inner").filter(
        pl.col("p_book_close").is_not_null())
    y = cmpf["y"].to_numpy().astype(float)
    brier = {}
    for col in ("p_base", "p_kadj", "p_prod", "p_book_close"):
        p = cmpf[col].to_numpy().astype(float)
        m = np.isfinite(p) & np.isfinite(y)
        brier[col] = {"brier": float(np.mean((p[m] - y[m]) ** 2)), "n": int(m.sum())}
    gain = brier["p_base"]["brier"] - brier["p_kadj"]["brier"]
    print(f"Brier n={brier['p_kadj']['n']}: base={brier['p_base']['brier']:.4f} "
          f"kadj={brier['p_kadj']['brier']:.4f} prod={brier['p_prod']['brier']:.4f} "
          f"book={brier['p_book_close']['brier']:.4f} gain={gain:+.5f}")

    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "n_train": len(train), "n_val": len(val),
           "n_test2024": len(test), "n_hold2025": len(hold),
           "iters": iters, "mae": mae,
           "mae_delta_hold": mae["base"]["hold2025"] - mae["kadj"]["hold2025"],
           "brier": brier, "gain_kadj_vs_base": gain,
           "kill": "SURVIVE" if gain >= 0.0005 else "KILL"}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
