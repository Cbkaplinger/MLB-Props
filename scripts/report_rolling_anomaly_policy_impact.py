"""Compare pitcher rolling features with vs without anomaly contamination policy."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.pipeline.rolling import (  # noqa: E402
    EXIT_ANOMALY_ROLLING_POLICY_VERSION,
    EXIT_ANOMALY_ROLLING_WEIGHTS,
    build_pitcher_rolling,
)

OUT_PATH = ROOT / "artifacts" / "projection_log" / "rolling_anomaly_policy_impact.json"
K_RATE_P5_WARN_ABS_DELTA = 0.005
ROWS_CHANGED_WARN_RATE = 0.01


def main() -> None:
    pitcher_games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    baseline = build_pitcher_rolling(pitcher_games, keep_raw=False, use_exit_anomaly_policy=False)
    policy = build_pitcher_rolling(pitcher_games, keep_raw=False, use_exit_anomaly_policy=True)

    keys = ["game_pk", "pitcher", "game_date"]
    compare_cols = [c for c in ["k_rate_P5", "k_rate_P10", "k_rate_P20", "PA_P5", "Outs_P5"] if c in baseline.columns and c in policy.columns]
    if not compare_cols:
        raise RuntimeError("Expected rolling columns missing for comparison.")

    joined = baseline.select([*keys, *compare_cols]).join(
        policy.select([*keys, *compare_cols]),
        on=keys,
        how="inner",
        suffix="_policy",
    )
    diffs = joined.with_columns(
        (pl.col(col + "_policy") - pl.col(col)).alias(col + "_delta")
        for col in compare_cols
    )
    delta_cols = [c + "_delta" for c in compare_cols]
    changed_any = pl.any_horizontal([pl.col(c).abs() > 1e-12 for c in delta_cols]).alias("changed")
    changed = diffs.with_columns(changed_any).filter(pl.col("changed"))

    summary = {
        "as_of": date.today().isoformat(),
        "policy_version": EXIT_ANOMALY_ROLLING_POLICY_VERSION,
        "policy_weights": EXIT_ANOMALY_ROLLING_WEIGHTS,
        "rows_total": int(joined.height),
        "rows_changed_any_feature": int(changed.height),
        "change_rate": float(changed.height / joined.height) if joined.height else 0.0,
        "mean_abs_delta": {},
        "max_abs_delta": {},
    }
    for c in delta_cols:
        summary["mean_abs_delta"][c] = float(diffs.select(pl.col(c).abs().mean()).item())
        summary["max_abs_delta"][c] = float(diffs.select(pl.col(c).abs().max()).item())
    k_p5 = float(summary["max_abs_delta"].get("k_rate_P5_delta", 0.0))
    warn_reasons: list[str] = []
    if k_p5 >= K_RATE_P5_WARN_ABS_DELTA:
        warn_reasons.append(
            f"max_abs_k_rate_P5_delta {k_p5:.6f} >= {K_RATE_P5_WARN_ABS_DELTA:.6f}"
        )
    if float(summary["change_rate"]) >= ROWS_CHANGED_WARN_RATE:
        warn_reasons.append(
            f"changed_row_rate {float(summary['change_rate']):.4%} >= {ROWS_CHANGED_WARN_RATE:.2%}"
        )
    summary["status"] = "WARN" if warn_reasons else "PASS"
    summary["status_reasons"] = warn_reasons

    sample = (
        changed.select([*keys, *delta_cols])
        .sort("game_date", descending=True)
        .head(20)
        .to_dicts()
    )
    payload = {"summary": summary, "sample_changed_rows": sample}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
