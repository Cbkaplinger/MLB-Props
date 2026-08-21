"""Run walk-forward suite for CSW/SwStr interaction candidate families.

This extends the existing Phase 11.B walk-forward protocol by comparing the
frozen production feature set against experimental interaction families:

- CSW finishability family (two-strike CSW and related gaps)
- xwOBA minus wOBA "luck" family

Outputs:
- artifacts/model_quality/interaction_feature_suite/summary.csv
- artifacts/model_quality/interaction_feature_suite/summary.json
- artifacts/model_quality/interaction_feature_suite/by_window.csv
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config
from Python.registries import resolve_feature_names


def _load_walkforward_module():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

SUITE_DIR = config.OUTPUT_DIR / "model_quality" / "interaction_feature_suite"
EXPERIMENTS: tuple[str, ...] = (
    "production",
    "research_csw_finish_all",
    "research_csw_finish_p5",
    "research_csw_finish_p10",
    "research_csw_finish_p20",
    "research_xwoba_luck_all",
    "research_air_profile_all",
    "research_air_profile_p5",
    "research_air_profile_p10",
    "research_air_profile_p20",
    "research_interactions_all",
    "research_interactions_p5",
    "research_interactions_p10",
    "research_interactions_p20",
)


def _run_experiment(feature_set: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    wf = _load_walkforward_module()
    out_dir = config.OUTPUT_DIR / "model_quality" / f"phase11b_walkforward_{feature_set}"
    wf.main(
        dry_run=False,
        tune_alpha=True,
        feature_set=feature_set,
        output_dir=out_dir,
    )
    outer = pd.read_csv(out_dir / "outer_results.csv")
    outer["feature_set"] = feature_set
    outer["output_dir"] = str(out_dir)
    with (out_dir / "metadata.json").open("r", encoding="utf-8") as f:
        md = json.load(f)
    row = pd.DataFrame(
        [
            {
                "feature_set": feature_set,
                "n_k_features": int(md.get("n_features_k_rate", 0)),
                "expected_K_mae_mean": float(md.get("expected_K_mae_mean", float("nan"))),
                "expected_K_mae_std": float(md.get("expected_K_mae_std", float("nan"))),
                "pass_expected_K_vs_baseline": bool(md.get("pass_expected_K_vs_baseline", False)),
                "output_dir": str(out_dir),
            }
        ]
    )
    return row, outer


def main() -> None:
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    wf = _load_walkforward_module()
    # Validate that all requested feature sets resolve on the current frame.
    frame = wf._load_frame()
    for feature_set in EXPERIMENTS:
        _ = resolve_feature_names(frame, feature_set)

    summary_rows: list[pd.DataFrame] = []
    window_rows: list[pd.DataFrame] = []
    for feature_set in EXPERIMENTS:
        print(f"[suite] running {feature_set} ...", flush=True)
        summary, outer = _run_experiment(feature_set)
        summary_rows.append(summary)
        window_rows.append(
            outer[
                [
                    "feature_set",
                    "window",
                    "expected_K_mae",
                    "k_rate_mae",
                    "tbf_mae",
                ]
            ].copy()
        )

    summary_df = pd.concat(summary_rows, ignore_index=True).sort_values(
        "expected_K_mae_mean"
    )
    base_mae = float(
        summary_df.loc[summary_df["feature_set"] == "production", "expected_K_mae_mean"].iloc[0]
    )
    summary_df["delta_vs_production_mae"] = (
        summary_df["expected_K_mae_mean"] - base_mae
    )
    by_window = pd.concat(window_rows, ignore_index=True)
    by_window = by_window.merge(
        by_window[by_window["feature_set"] == "production"][
            ["window", "expected_K_mae"]
        ].rename(columns={"expected_K_mae": "production_expected_K_mae"}),
        on="window",
        how="left",
    )
    by_window["delta_vs_production_mae"] = (
        by_window["expected_K_mae"] - by_window["production_expected_K_mae"]
    )

    summary_df.to_csv(SUITE_DIR / "summary.csv", index=False)
    by_window.to_csv(SUITE_DIR / "by_window.csv", index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "experiments": list(EXPERIMENTS),
        "best_by_mean_mae": summary_df.iloc[0].to_dict() if not summary_df.empty else None,
        "files": {
            "summary_csv": str(SUITE_DIR / "summary.csv"),
            "by_window_csv": str(SUITE_DIR / "by_window.csv"),
        },
    }
    (SUITE_DIR / "summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    print(summary_df.to_string(index=False))
    print(f"Wrote {SUITE_DIR}")


if __name__ == "__main__":
    main()
