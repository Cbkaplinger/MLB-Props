"""Per-term age ablation (post hoc, research; backlog #38 debt, spec §6 step 1).

#38 added 4 age terms at once (SURVIVE-narrow) — attribution owed. Arms,
same members/seeds, native splits (2023-24 chrono train/val/test + 2025
holdout eval):
  base : deployed final58 sidecar (58)
  +1 term each : pitcher_age, pitcher_age2, age_x_whiff_gap, age_x_velo_gap
  full : base + all 4 (reference, reproduces #38 directionally)

Keep rule per term: directionally better MAE on BOTH 2024-test AND 2025
holdout. Dropped terms leave the retrain spec; survivors earn a universe
Brier gate at retrain time.

Writes artifacts/model_quality/age_per_term/report.json. No live change.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.config import HOLDOUT_SEASON, PITCHER_TRAINING_PATH  # noqa: E402
from Python.features import TARGET  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.registries import resolve_feature_names  # noqa: E402
from Python.training import (  # noqa: E402
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
)

OUT_DIR = ROOT / "artifacts" / "model_quality" / "age_per_term"
TERMS = ["pitcher_age", "pitcher_age2", "age_x_whiff_gap", "age_x_velo_gap"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    missing = [t for t in TERMS if t not in frame.columns]
    if missing:
        raise ValueError(f"L3 missing age terms: {missing}")
    sidecar58 = [f for f in resolve_feature_names(frame, "research_command_single")
                 if f != "cmd_roll30"]
    arms = {"base": sidecar58}
    for t in TERMS:
        arms[f"+{t}"] = sidecar58 + [t]
    arms["full62"] = sidecar58 + TERMS
    print(f"arms={list(arms)} rows={len(frame)}")

    pool = frame.loc[frame["season"].isin((2023, 2024))].sort_values(
        ["game_date", "player_name"]).reset_index(drop=True)
    hold = frame.loc[(frame["season"] == HOLDOUT_SEASON)
                     & frame[TARGET].notna()].reset_index(drop=True)
    train, val, test = chronological_split(pool)
    print(f"train={len(train)} val={len(val)} test2024={len(test)} "
          f"hold2025={len(hold)}")

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "arms": {}, "keep": []}
    base_test_mae = base_hold_mae = None
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
        pt = np.asarray(predict_clipped(model, "lightgbm", test, feats), dtype=float)
        ph = np.asarray(predict_clipped(model, "lightgbm", hold, feats), dtype=float)
        t_mae = float(np.mean(np.abs(pt - test[TARGET].to_numpy(dtype=float))))
        h_mae = float(np.mean(np.abs(ph - hold[TARGET].to_numpy(dtype=float))))
        rep["arms"][name] = {"n_feats": len(feats), "mae_2024test": t_mae,
                             "mae_2025hold": h_mae}
        print(f"{name:>16}: 2024test={t_mae:.5f} 2025hold={h_mae:.5f} "
              f"(iters={model.best_iteration_})")
        if name == "base":
            base_test_mae, base_hold_mae = t_mae, h_mae
    assert base_test_mae is not None and base_hold_mae is not None
    for name, r in rep["arms"].items():
        if name in ("base", "full62"):
            continue
        r["d_test"] = base_test_mae - r["mae_2024test"]
        r["d_hold"] = base_hold_mae - r["mae_2025hold"]
        keep = r["d_test"] > 0 and r["d_hold"] > 0
        r["keep"] = bool(keep)
        if keep:
            rep["keep"].append(name)
    f = rep["arms"]["full62"]
    print(f"full62 vs base: d_test={base_test_mae - f['mae_2024test']:+.5f} "
          f"d_hold={base_hold_mae - f['mae_2025hold']:+.5f}")
    print(f"KEEP: {rep['keep']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
