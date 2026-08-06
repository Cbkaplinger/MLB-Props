"""Score the frozen k-rate × TBF stack on post-freeze / out-of-selection seasons.

Fits nothing. Loads frozen LightGBM + Ridge TBF, scores ``pitcher_training``
rows, and compares to actual K / PA / k_rate.

Partitions (documented in ``docs/reference/post_freeze_holdout.md``):

- ``post_freeze``: ``game_date >= FREEZE_DATE`` (true post-lock monitoring)
- ``season_2025``: all 2025 rows (contaminated development history — reference only)
- ``season_2026_pre_freeze``: 2026 rows with ``game_date < FREEZE_DATE``

Example:
    python production/post_freeze_holdout.py
    python production/post_freeze_holdout.py --min-pa 9
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.features import TARGET  # noqa: E402
from Python.live_assembly import (  # noqa: E402
    DEFAULT_KRATE_STEM,
    DEFAULT_TBF_JOBLIB,
    score_frame,
)

# Feature registry locked 2026-08-03 (artifact stem …155401; TBF still …035607).
FREEZE_DATE = date(2026, 8, 3)
OUT_DIR = config.OUTPUT_DIR / "holdout" / "post_freeze"


def _metrics(y: np.ndarray, yhat: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, yhat)),
        "rmse": float(mean_squared_error(y, yhat) ** 0.5),
        "r2": float(r2_score(y, yhat)) if len(y) > 1 else float("nan"),
    }


def _partition_mask(frame: pd.DataFrame, name: str) -> pd.Series:
    d = pd.to_datetime(frame["game_date"]).dt.date
    season = frame["season"].astype(int)
    if name == "post_freeze":
        return pd.Series([x >= FREEZE_DATE for x in d], index=frame.index)
    if name == "season_2025":
        return season == 2025
    if name == "season_2026_pre_freeze":
        return (season == 2026) & pd.Series(
            [x < FREEZE_DATE for x in d], index=frame.index
        )
    raise ValueError(name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-pa", type=int, default=9)
    parser.add_argument("--k-rate-stem", type=Path, default=DEFAULT_KRATE_STEM)
    parser.add_argument("--tbf-joblib", type=Path, default=DEFAULT_TBF_JOBLIB)
    args = parser.parse_args()

    if not config.PITCHER_TRAINING_PATH.exists():
        raise SystemExit(
            f"Missing {config.PITCHER_TRAINING_PATH}. Run production/refresh_features.py first."
        )

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = frame.dropna(subset=[TARGET, "K", "PA", "game_date"]).copy()
    frame = frame.loc[frame["PA"] >= args.min_pa].reset_index(drop=True)

    scored, report = score_frame(
        frame,
        krate_stem=args.k_rate_stem,
        tbf_joblib=args.tbf_joblib,
    )
    # Align predictions back onto the filtered frame index.
    scored = scored.reset_index(drop=True)
    frame = frame.reset_index(drop=True)
    for col in ("k_rate_pred", "projected_tbf", "expected_K"):
        frame[col] = scored[col].to_numpy()

    partitions = ("post_freeze", "season_2026_pre_freeze", "season_2025")
    summary: dict[str, object] = {
        "freeze_date": FREEZE_DATE.isoformat(),
        "min_pa": args.min_pa,
        "k_rate_model": report["k_rate_model"],
        "tbf_model": report["tbf_model"],
        "k_rate_sha256": report["k_rate_sha256"],
        "tbf_sha256": report["tbf_sha256"],
        "training_max_date": str(frame["game_date"].max().date()),
        "partitions": {},
    }

    detail_rows: list[pd.DataFrame] = []
    for name in partitions:
        mask = _partition_mask(frame, name)
        part = frame.loc[mask]
        if part.empty:
            summary["partitions"][name] = {"n": 0, "note": "no rows yet"}
            continue
        y_rate = part[TARGET].to_numpy(dtype=float)
        y_k = part["K"].to_numpy(dtype=float)
        y_pa = part["PA"].to_numpy(dtype=float)
        block = {
            "k_rate": _metrics(y_rate, part["k_rate_pred"].to_numpy(dtype=float)),
            "expected_K": _metrics(y_k, part["expected_K"].to_numpy(dtype=float)),
            "projected_tbf": _metrics(y_pa, part["projected_tbf"].to_numpy(dtype=float)),
            "date_min": str(part["game_date"].min().date()),
            "date_max": str(part["game_date"].max().date()),
        }
        summary["partitions"][name] = block
        tagged = part[
            [
                "game_date",
                "season",
                "pitcher",
                "player_name",
                "K",
                "PA",
                TARGET,
                "k_rate_pred",
                "projected_tbf",
                "expected_K",
            ]
        ].copy()
        tagged["partition"] = name
        detail_rows.append(tagged)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if detail_rows:
        pl.from_pandas(pd.concat(detail_rows, ignore_index=True)).write_parquet(
            OUT_DIR / "scored_rows.parquet"
        )
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
