"""Walk-forward sensitivity + local effect report for anomaly rolling policy."""

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
OUT_ROOT = ROOT / "artifacts" / "model_quality" / "anomaly_policy_sensitivity"
LINES = ("3_5", "4_5", "5_5", "6_5", "7_5")
BACKFILL_SCRIPT = ROOT / "scripts" / "backfill_historical_exit_anomaly_overrides.py"


def _build_training_variant(use_policy: bool, data_root: Path, medium_weight: float | None) -> Path:
    processed = data_root / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    if medium_weight is not None:
        os.environ["MLB_PROPS_EXIT_ANOMALY_WEIGHT_MEDIUM"] = str(medium_weight)
    else:
        os.environ.pop("MLB_PROPS_EXIT_ANOMALY_WEIGHT_MEDIUM", None)

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
    cmd = [sys.executable, str(WF_SCRIPT), "--output-dir", str(output_dir)]
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)
    return json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))


def _local_effects(base_pred_path: Path, scen_pred_path: Path) -> dict:
    key_cols = ["window", "game_pk", "pitcher", "game_date"]
    b = pl.read_parquet(base_pred_path)
    s = pl.read_parquet(scen_pred_path)
    cols = ["expected_K", *[f"p_over_{line}" for line in LINES]]
    joined = b.select([*key_cols, *cols]).join(
        s.select([*key_cols, *cols]),
        on=key_cols,
        how="inner",
        suffix="_scen",
    )
    if joined.is_empty():
        return {"rows": 0}
    out: dict[str, float | int] = {"rows": int(joined.height)}
    diff = (pl.col("expected_K_scen") - pl.col("expected_K")).abs()
    out["mean_abs_expected_K_delta"] = float(joined.select(diff.mean()).item())
    out["max_abs_expected_K_delta"] = float(joined.select(diff.max()).item())
    out["pct_abs_expected_K_delta_ge_0_10"] = float(
        joined.select((diff >= 0.10).mean()).item()
    )
    out["pct_abs_expected_K_delta_ge_0_25"] = float(
        joined.select((diff >= 0.25).mean()).item()
    )

    flip_exprs = [
        (
            (pl.col(f"p_over_{line}") >= 0.5)
            != (pl.col(f"p_over_{line}_scen") >= 0.5)
        )
        for line in LINES
    ]
    any_flip = pl.any_horizontal(flip_exprs)
    out["pct_any_line_side_flip"] = float(joined.select(any_flip.mean()).item())
    out["n_any_line_side_flip"] = int(joined.select(any_flip.sum()).item())
    return out


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    scenarios: list[tuple[str, bool, float | None]] = [
        ("baseline", False, None),
        ("policy_m025", True, 0.25),
        ("policy_m050", True, 0.50),
        ("policy_m075", True, 0.75),
    ]

    results: dict[str, dict] = {}
    for name, use_policy, medium in scenarios:
        data_root = OUT_ROOT / f"{name}_data"
        wf_out = OUT_ROOT / f"{name}_wf"
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
        print(f"Building {name}...", flush=True)
        _build_training_variant(use_policy, data_root, medium)
        print(f"Running walk-forward {name}...", flush=True)
        meta = _run_walkforward(data_root, wf_out)
        results[name] = {
            "expected_K_mae_mean": meta.get("expected_K_mae_mean"),
            "expected_K_mae_std": meta.get("expected_K_mae_std"),
            "n_windows": meta.get("n_windows"),
            "training_artifact_sha256": meta.get("training_artifact_sha256"),
            "medium_weight": medium,
        }

    baseline = results["baseline"]
    base_pred = OUT_ROOT / "baseline_wf" / "walkforward_predictions.parquet"
    for name, *_ in scenarios:
        if name == "baseline":
            continue
        scen_pred = OUT_ROOT / f"{name}_wf" / "walkforward_predictions.parquet"
        results[name]["delta_vs_baseline"] = {
            "expected_K_mae_mean": float(results[name]["expected_K_mae_mean"]) - float(baseline["expected_K_mae_mean"]),
            "expected_K_mae_std": float(results[name]["expected_K_mae_std"]) - float(baseline["expected_K_mae_std"]),
        }
        results[name]["local_effects_vs_baseline"] = _local_effects(base_pred, scen_pred)

    best = min(
        [k for k in results if k != "baseline"],
        key=lambda k: (results[k]["expected_K_mae_mean"], abs(results[k]["medium_weight"] - 0.5)),
    )
    summary = {
        "as_of": date.today().isoformat(),
        "baseline": baseline,
        "scenarios": {k: v for k, v in results.items() if k != "baseline"},
        "best_policy_variant": best,
        "recommendation": (
            best
            if float(results[best]["expected_K_mae_mean"]) < float(baseline["expected_K_mae_mean"])
            else "no_change_keep_current_policy"
        ),
    }

    out_path = OUT_ROOT / "sensitivity_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
