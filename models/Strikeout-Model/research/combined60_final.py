"""Combined-60 final (post hoc, research; spec §6 step 4, backlog #64).

First genuine bundle challenger since August. Arms, same members/seeds,
native splits (2023-24 chrono + 2025 holdout eval + 2026 clean verdict):
  base     : deployed final58 sidecar (58)
  final60  : base + pitcher_age + age_x_whiff_gap (60)

Judged: MAE (2024-test + 2025-holdout) + universe Brier on 2025-holdout AND
2026-clean starts (Poisson + live WS1c-Platt, main-only, three-way vs
production bundle). Both windows must clear +0.0005 — 2026-clean is the
verdict per #45 doctrine (2025-holdout is now model-selected; 2026 is not).

Writes artifacts/model_quality/combined60/report.json. No live change.
Survive here -> walk-forward confirm -> ledger-gate -> weekly pack -> sign-off.
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
OUT_DIR = ROOT / "artifacts" / "model_quality" / "combined60"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    sidecar58 = [f for f in resolve_feature_names(frame, "research_command_single")
                 if f != "cmd_roll30"]
    arms = {"base": sidecar58,
            "final60": sidecar58 + ["pitcher_age", "age_x_whiff_gap"]}
    print(f"rows={len(frame)}")

    pool = frame.loc[frame["season"].isin((2023, 2024))].sort_values(
        ["game_date", "player_name"]).reset_index(drop=True)
    hold = frame.loc[(frame["season"] == HOLDOUT_SEASON)
                     & frame[TARGET].notna()].reset_index(drop=True)
    clean = frame.loc[(frame["season"] == 2026)
                      & frame[TARGET].notna()].reset_index(drop=True)
    train, val, test = chronological_split(pool)
    print(f"train={len(train)} val={len(val)} test2024={len(test)} "
          f"hold2025={len(hold)} clean2026={len(clean)}")

    preds, iters, mae = {}, {}, {}
    actual_test = test[TARGET].to_numpy(dtype=float)
    actual_hold = hold[TARGET].to_numpy(dtype=float)
    actual_clean = clean[TARGET].to_numpy(dtype=float)
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
        pc = np.asarray(predict_clipped(model, "lightgbm", clean, feats), dtype=float)
        preds[name] = {"hold": ph, "clean": pc}
        mae[name] = {"test2024": float(np.mean(np.abs(pt - actual_test))),
                     "hold2025": float(np.mean(np.abs(ph - actual_hold))),
                     "clean2026": float(np.mean(np.abs(pc - actual_clean)))}
        print(f"{name:>8}: test={mae[name]['test2024']:.5f} hold={mae[name]['hold2025']:.5f} "
              f"clean={mae[name]['clean2026']:.5f} (iters={iters[name]})")

    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}
    sc = pl.scan_parquet(SCORED).select(
        ["game_pk", "gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])

    def gate(eval_frame: pd.DataFrame, pred_dict: dict, tag: str) -> dict:
        pks = eval_frame["game_pk"].tolist()
        pmap = {n: dict(zip(pks, pred_dict[n])) for n in arms}
        sc_sel = sc.filter(pl.col("game_pk").is_in(pks))
        print(f"{tag} scored join: {sc_sel.height}/{len(pks)}")
        rows = []
        for r in sc_sel.to_dicts():
            if r["game_pk"] not in pmap["base"] or r["projected_tbf"] is None:
                continue
            tbf = float(r["projected_tbf"])
            row = {"gd": r["gd"], "key": r["key_sorted"], "tbf": tbf,
                   "kr_prod": float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5))}
            for n in arms:
                row[f"kr_{n}"] = float(np.clip(pmap[n][r["game_pk"]], 0.02, 0.5))
            rows.append(row)
        out: dict[str, dict] = {}
        ntot, acc = 0, {"base": 0.0, "final60": 0.0}
        for ln in LINES:
            keys = [(rr["gd"], rr["key"]) for rr in rows]
            kidx = {k: i for i, k in enumerate(keys)}
            pf = panel.filter(pl.col("line") == ln)
            pmap_y = {(g, k): (y, b) for g, k, y, b in
                      zip(pf["gd"].to_list(), pf["key"].to_list(),
                          pf["y"].to_list(), pf["p_book_close"].to_list())}
            m = [(kidx[k], pmap_y[k][0], pmap_y[k][1]) for k in keys
                 if k in pmap_y and pmap_y[k][1] is not None]
            if len(m) < 50:
                continue
            ntot += len(m)
            for n in arms:
                se = 0.0
                for i, y, _ in m:
                    raw = float(p_strikeouts_ge(
                        ln, k_rate=np.array([rows[i][f"kr_{n}"]]),
                        projected_tbf=np.array([rows[i]["tbf"]]), family="poisson")[0])
                    p = float(maps[ln].transform(np.array([raw]))[0])
                    se += (p - y) ** 2
                acc[n] += se
        res = {"n": ntot, "base": acc["base"] / ntot if ntot else None,
               "final60": acc["final60"] / ntot if ntot else None}
        res["gain"] = (res["base"] - res["final60"]) if ntot else None
        print(f"{tag} Brier n={ntot}: base={res['base']:.4f} final60={res['final60']:.4f} "
              f"gain={res['gain']:+.5f}")
        return res

    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "iters": iters, "mae": mae,
           "holdout": gate(hold, {n: preds[n]["hold"] for n in arms}, "hold2025"),
           "clean": gate(clean, {n: preds[n]["clean"] for n in arms}, "clean2026")}
    rep["survive"] = bool(rep["holdout"]["gain"] is not None
                          and rep["clean"]["gain"] is not None
                          and rep["holdout"]["gain"] >= 0.0005
                          and rep["clean"]["gain"] >= 0.0005)
    print(f"survive={rep['survive']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
