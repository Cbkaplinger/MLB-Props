"""Command option-A retest (post hoc, research; backlog #45/#52).

The fair fight #52 was denied: command data starts in 2024, so the native
2023-24-train split gave it ~2 months of signal (KILL-narrow: 2024 +0.0004,
2025 -0.0002). Option-A spends the holdout for this challenger ONLY:
train on 2024+2025, judge on 2026-clean. Standing splits are untouched
(config.TRAIN_SEASONS is never modified; this script filters its own frame).

Arms (single-feature rule, same members, same seeds):
  base : deployed final58 sidecar (58, no command)
  cmd  : base + cmd_roll30 (58+1)

Judged on 2026: MAE delta + universe Brier (Poisson + live WS1c-Platt) on the
same joined subset, three-way vs the production bundle's stored k_rate_pred.
Kill: cmd-vs-base universe Brier gain < 0.0005 on 2026.

Writes artifacts/model_quality/command_optionA/report.json. No live change.
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

from Python.config import PITCHER_TRAINING_PATH  # noqa: E402
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
OUT_DIR = ROOT / "artifacts" / "model_quality" / "command_optionA"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
TRAIN_SEASONS_A = (2024, 2025)
TEST_SEASON_A = 2026


def fit_arm(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    model = build_model("lightgbm")
    fit_regressor(
        model, "lightgbm",
        lightgbm_matrix(train, features), train[TARGET],
        train_weight=None,
        validation_features=lightgbm_matrix(val, features),
        validation_target=val[TARGET],
        validation_weight=None,
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    if "cmd_roll30" not in frame.columns:
        raise ValueError("L3 has no cmd_roll30 — rebuild L3 with command join first")
    base_feats = [f for f in resolve_feature_names(frame, "research_command_single")
                  if f != "cmd_roll30"]
    cmd_feats = list(resolve_feature_names(frame, "research_command_single"))
    assert "cmd_roll30" in cmd_feats and len(cmd_feats) == len(base_feats) + 1
    print(f"base={len(base_feats)} cmd={len(cmd_feats)} rows={len(frame)}")

    pool = frame.loc[frame["season"].isin(TRAIN_SEASONS_A)].sort_values(
        ["game_date", "player_name"]).reset_index(drop=True)
    test = frame.loc[(frame["season"] == TEST_SEASON_A)
                     & frame[TARGET].notna()].sort_values(
        ["game_date", "player_name"]).reset_index(drop=True)
    train, val, _discard = chronological_split(pool)
    print(f"train={len(train)} val={len(val)} test2026={len(test)} "
          f"(cutoffs {train['game_date'].max().date()} / {test['game_date'].min().date()})")

    models = {}
    preds = {}
    for name, feats in (("base", base_feats), ("cmd", cmd_feats)):
        models[name] = fit_arm(train, val, feats)
        preds[name] = np.asarray(predict_clipped(models[name], "lightgbm", test, feats),
                                 dtype=float)
    actual = test[TARGET].to_numpy(dtype=float)
    mae = {k: float(np.mean(np.abs(preds[k] - actual))) for k in preds}
    print(f"MAE 2026: base={mae['base']:.5f} cmd={mae['cmd']:.5f} "
          f"delta={mae['base'] - mae['cmd']:+.5f}")

    # Universe Brier on the 2026 test subset (production TBF both arms — fair).
    sc = pl.scan_parquet(SCORED).select(
        ["game_pk", "gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    sc_sel = sc.filter(pl.col("game_pk").is_in(test["game_pk"].tolist()))
    print(f"scored join: {sc_sel.height}/{len(test)} test starts")
    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def cal(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        return float(maps[ln].transform(np.array([raw]))[0])

    pred_map = dict(zip(test["game_pk"].tolist(), zip(preds["base"], preds["cmd"])))
    rows = []
    for r in sc_sel.to_dicts():
        if r["game_pk"] not in pred_map or r["projected_tbf"] is None:
            continue
        pb, pc = pred_map[r["game_pk"]]
        tbf = float(r["projected_tbf"])
        for ln in LINES:
            rows.append({"gd": r["gd"], "key": r["key_sorted"], "line": float(ln),
                         "p_base": cal(float(np.clip(pb, 0.02, 0.5)), tbf, ln),
                         "p_cmd": cal(float(np.clip(pc, 0.02, 0.5)), tbf, ln),
                         "p_prod": cal(float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5)), tbf, ln)})
    cand = pl.DataFrame(rows)
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])
    # Main-market only: alt rows carry no devigged p_book_close, and scoring
    # challengers on alt shape while scoring the book on main flatters us.
    cmpf = cand.join(panel, on=["gd", "key", "line"], how="inner").filter(
        pl.col("p_book_close").is_not_null())
    y = cmpf["y"].to_numpy().astype(float)
    brier = {}
    for col in ("p_base", "p_cmd", "p_prod", "p_book_close"):
        p = cmpf[col].to_numpy().astype(float)
        m = np.isfinite(p) & np.isfinite(y)
        brier[col] = {"brier": float(np.mean((p[m] - y[m]) ** 2)), "n": int(m.sum())}
    gain = brier["p_base"]["brier"] - brier["p_cmd"]["brier"]
    print(f"Brier n={brier['p_cmd']['n']}: base={brier['p_base']['brier']:.4f} "
          f"cmd={brier['p_cmd']['brier']:.4f} prod={brier['p_prod']['brier']:.4f} "
          f"book={brier['p_book_close']['brier']:.4f} gain={gain:+.5f}")

    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "split": f"train{TRAIN_SEASONS_A}_test{TEST_SEASON_A}",
           "n_train": len(train), "n_val": len(val), "n_test": len(test),
           "n_features": {"base": len(base_feats), "cmd": len(cmd_feats)},
           "mae_2026": mae, "mae_delta": mae["base"] - mae["cmd"],
           "brier": brier, "gain_cmd_vs_base": gain,
           "kill": "SURVIVE" if gain >= 0.0005 else "KILL"}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
