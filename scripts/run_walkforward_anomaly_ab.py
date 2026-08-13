"""Run walk-forward A/B: baseline vs anomaly-policy rolling updates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.pipeline import rolling, training  # noqa: E402

WF_SCRIPT = ROOT / "Models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
OUT_ROOT = ROOT / "artifacts" / "model_quality" / "anomaly_policy_ab"
BACKFILL_SCRIPT = ROOT / "scripts" / "backfill_historical_exit_anomaly_overrides.py"


def _build_training_variant(use_policy: bool, data_root: Path) -> Path:
    processed = data_root / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    pitcher_games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    batter_games = pl.read_parquet(config.BATTER_GAMES_PATH)
    park = pl.read_parquet(config.PARK_FACTORS_PATH)
    bullpen_team_games = (
        pl.read_parquet(config.BULLPEN_TEAM_GAMES_PATH)
        if config.BULLPEN_TEAM_GAMES_PATH.exists()
        else None
    )
    bullpen_appearances = (
        pl.read_parquet(config.BULLPEN_APPEARANCES_PATH)
        if config.BULLPEN_APPEARANCES_PATH.exists()
        else None
    )

    pr = rolling.build_pitcher_rolling(
        pitcher_games,
        keep_raw=False,
        bullpen_team_games=bullpen_team_games,
        bullpen_appearances=bullpen_appearances,
        use_exit_anomaly_policy=use_policy,
    )
    br = rolling.build_batter_rolling(batter_games, keep_raw=False)
    pt = training.build_pitcher_training(pr, br, park)
    out = processed / "pitcher_training.parquet"
    pt.write_parquet(out)
    return out


def _run_walkforward(data_root: Path, output_dir: Path) -> dict:
    env = os.environ.copy()
    env["MLB_PROPS_DATA_DIR"] = str(data_root)
    env["MLB_PROPS_EXIT_ANOMALY_OVERRIDE_PATH"] = str(
        data_root / "exit_anomaly_overrides_hist.csv"
    )
    cmd = [
        sys.executable,
        str(WF_SCRIPT),
        "--output-dir",
        str(output_dir),
    ]
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)
    meta_path = output_dir / "metadata.json"
    return json.loads(meta_path.read_text(encoding="utf-8"))


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    base_data = OUT_ROOT / "baseline_data"
    policy_data = OUT_ROOT / "policy_data"
    base_out = OUT_ROOT / "baseline_wf"
    policy_out = OUT_ROOT / "policy_wf"

    for data_root in (base_data, policy_data):
        subprocess.run(
            [
                sys.executable,
                str(BACKFILL_SCRIPT),
                "--start-season",
                "2023",
                "--end-season",
                "2024",
                "--output-path",
                str(data_root / "exit_anomaly_overrides_hist.csv"),
            ],
            check=True,
            cwd=str(ROOT),
        )

    _build_training_variant(False, base_data)
    _build_training_variant(True, policy_data)

    base_meta = _run_walkforward(base_data, base_out)
    policy_meta = _run_walkforward(policy_data, policy_out)

    keys = [
        "expected_K_mae_mean",
        "expected_K_mae_std",
        "n_windows",
    ]
    summary = {
        "as_of": date.today().isoformat(),
        "baseline": {k: base_meta.get(k) for k in keys},
        "policy_v1": {k: policy_meta.get(k) for k in keys},
        "delta_policy_minus_baseline": {
            k: (
                float(policy_meta.get(k)) - float(base_meta.get(k))
                if isinstance(base_meta.get(k), (int, float))
                and isinstance(policy_meta.get(k), (int, float))
                else None
            )
            for k in keys
        },
    }
    summary["recommendation"] = (
        "policy_v1"
        if summary["delta_policy_minus_baseline"]["expected_K_mae_mean"] is not None
        and summary["delta_policy_minus_baseline"]["expected_K_mae_mean"] < 0
        else "baseline_or_no_change"
    )

    out_json = OUT_ROOT / "ab_summary.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out_json}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
