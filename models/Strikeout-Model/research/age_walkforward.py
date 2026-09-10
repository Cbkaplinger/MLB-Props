"""Base+age walk-forward confirm (post hoc, research; spec §5, backlog #65).

Rolling origin, k-rate only (production TBF both arms — isolates the
feature, same as every ablation). Arms, same seeds:
  base : deployed final58 sidecar (58)
  age59: base + pitcher_age (59)

Folds (train = rows strictly before test start; never split a date):
  F1 train<2024-06-01 test 2024-06-01..2024-08-01 (in-train sanity)
  F2 train<2024-08-01 test 2024-08-01..2024-10-01 (in-train sanity)
  F3 train<2025-06-01 test 2025-06-01..2025-08-01 (trains on spent 2025-H1)
  F4 train<2026-01-01 test 2026-04-01..2026-06-01 (trains on spent 2025)
  F5 train<2026-06-15 test 2026-06-15..2026-09-08 (trains on spent 2025+26H1)
F3-F5 spend holdout/clean rows in TRAIN — labeled, standard for
confirmation (this judges verdict stability across regimes, not a fresh
unbiased estimate; the unbiased gates were #64 + combined60).

Per fold: universe Brier (Poisson + live WS1c-Platt, main-only) + MAE.
Pre-registered SURVIVE: pooled gain >= 0.0005 AND no fold < -0.001.

Writes artifacts/model_quality/age_walkforward/report.json. No live change.
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
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
)

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PANEL = ROOT / "artifacts" / "odds_log" / "universe_panel.parquet"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
OUT_DIR = ROOT / "artifacts" / "model_quality" / "age_walkforward"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
FOLDS = [
    ("F1", "2024-06-01", "2024-06-01", "2024-08-01"),
    ("F2", "2024-08-01", "2024-08-01", "2024-10-01"),
    ("F3", "2025-06-01", "2025-06-01", "2025-08-01"),
    ("F4", "2026-01-01", "2026-04-01", "2026-06-01"),
    ("F5", "2026-06-15", "2026-06-15", "2026-09-08"),
]


def date_cut(values: pd.Series, frac: float) -> pd.Timestamp:
    """Largest date with at most frac of rows strictly before it (never splits)."""
    ordered = values.sort_values().reset_index(drop=True)
    return ordered.iloc[max(int(len(ordered) * frac) - 1, 0)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    sidecar58 = [f for f in resolve_feature_names(frame, "research_command_single")
                 if f != "cmd_roll30"]
    arms = {"base": sidecar58, "age59": sidecar58 + ["pitcher_age"]}
    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}
    sc = pl.scan_parquet(SCORED).select(
        ["game_pk", "gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "folds": {}}
    pool_gain, pool_n = 0.0, 0
    for name, train_end, test_start, test_end in FOLDS:
        tr_all = frame.loc[frame["game_date"] < train_end].sort_values("game_date")
        te = frame.loc[(frame["game_date"] >= test_start)
                       & (frame["game_date"] < test_end)
                       & frame[TARGET].notna()].reset_index(drop=True)
        if len(tr_all) < 500 or len(te) < 100:
            rep["folds"][name] = {"skipped": True, "n_train": len(tr_all), "n_test": len(te)}
            print(f"{name}: SKIPPED (train={len(tr_all)} test={len(te)})")
            continue
        vcut = date_cut(tr_all["game_date"], 0.85)
        tr = tr_all.loc[tr_all["game_date"] < vcut]
        va = tr_all.loc[tr_all["game_date"] >= vcut]
        preds = {}
        iters = {}
        for arm, feats in arms.items():
            model = build_model("lightgbm")
            fit_regressor(
                model, "lightgbm",
                lightgbm_matrix(tr, feats), tr[TARGET],
                train_weight=None,
                validation_features=lightgbm_matrix(va, feats),
                validation_target=va[TARGET],
                validation_weight=None,
                early_stopping_rounds=200,
                log_evaluation_period=0,
            )
            iters[arm] = int(model.best_iteration_)
            preds[arm] = np.asarray(predict_clipped(model, "lightgbm", te, feats), dtype=float)
        actual = te[TARGET].to_numpy(dtype=float)
        mae = {a: float(np.mean(np.abs(preds[a] - actual))) for a in arms}
        pmap = {a: dict(zip(te["game_pk"].tolist(), preds[a])) for a in arms}
        sc_sel = sc.filter(pl.col("game_pk").is_in(te["game_pk"].tolist()))
        rows = []
        for r in sc_sel.to_dicts():
            if r["game_pk"] not in pmap["base"] or r["projected_tbf"] is None:
                continue
            tbf = float(r["projected_tbf"])
            rows.append({"gd": r["gd"], "key": r["key_sorted"], "tbf": tbf,
                         "kr_base": float(np.clip(pmap["base"][r["game_pk"]], 0.02, 0.5)),
                         "kr_age": float(np.clip(pmap["age59"][r["game_pk"]], 0.02, 0.5))})
        se_b = se_a = 0.0
        n = 0
        for ln in LINES:
            keys = [(rr["gd"], rr["key"]) for rr in rows]
            kidx = {k: i for i, k in enumerate(keys)}
            pf = panel.filter(pl.col("line") == ln)
            ys = {(g, k): y for g, k, y, b in
                  zip(pf["gd"].to_list(), pf["key"].to_list(),
                      pf["y"].to_list(), pf["p_book_close"].to_list()) if b is not None}
            for k in keys:
                if k not in ys:
                    continue
                i, y = kidx[k], ys[k]
                for kr_col, acc in (("kr_base", "b"), ("kr_age", "a")):
                    raw = float(p_strikeouts_ge(
                        ln, k_rate=np.array([rows[i][kr_col]]),
                        projected_tbf=np.array([rows[i]["tbf"]]), family="poisson")[0])
                    p = float(maps[ln].transform(np.array([raw]))[0])
                    if acc == "b":
                        se_b += (p - y) ** 2
                    else:
                        se_a += (p - y) ** 2
                n += 1
        gain = (se_b - se_a) / n if n else None
        rep["folds"][name] = {"n_train": len(tr_all), "n_test": len(te), "n_brier": n,
                              "iters": iters,
                              "mae_base": mae["base"], "mae_age": mae["age59"],
                              "brier_base": se_b / n if n else None,
                              "brier_age": se_a / n if n else None, "gain": gain}
        if gain is not None:
            pool_gain += (se_b - se_a)
            pool_n += n
        print(f"{name}: n_brier={n} mae {mae['base']:.5f}->{mae['age59']:.5f} "
              f"brier gain={gain:+.5f}" if gain is not None else f"{name}: no join")
    rep["pooled_gain"] = pool_gain / pool_n if pool_n else None
    worst = min((f["gain"] for f in rep["folds"].values() if f.get("gain") is not None),
                default=None)
    rep["worst_fold"] = worst
    rep["survive"] = bool(rep["pooled_gain"] is not None and rep["pooled_gain"] >= 0.0005
                          and worst is not None and worst >= -0.001)
    print(f"pooled_gain={rep['pooled_gain']:+.5f} worst={worst:+.5f} survive={rep['survive']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
