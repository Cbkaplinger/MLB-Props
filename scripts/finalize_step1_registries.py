"""Export registry CSVs for the frozen LightGBM / Ridge feature sets.

Example:
    python scripts/finalize_step1_registries.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config  # noqa: E402
from Python.features import TARGET  # noqa: E402
from Python.registries import (  # noqa: E402
    FEATURE_SETS,
    pre_freeze_248_features,
    production_features,
    registry_metadata,
    ridge_vif_features,
    write_registry_csv,
)

OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "step1_registries"


def _load_dev_frame() -> pd.DataFrame:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    return (
        frame.loc[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )


def _missingness_by_season(frame: pd.DataFrame, features: tuple[str, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for season, part in frame.groupby("season"):
        for feature in features:
            series = part[feature]
            rows.append(
                {
                    "season": int(season),
                    "feature": feature,
                    "n_rows": len(part),
                    "missing_pct": float(series.isna().mean() * 100.0),
                    "cold_start_note": (
                        "early-season / short-history nulls expected for rolling "
                        "windows; lineup rates null when opposing batter priors "
                        "are unavailable"
                    ),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    frame = _load_dev_frame()
    sets = {
        "production": production_features(frame),
        "pre_freeze_248": pre_freeze_248_features(frame),
        "ridge_vif": ridge_vif_features(frame),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, features in sets.items():
        write_registry_csv(
            OUTPUT_DIR / f"{name}_registry.csv",
            features,
            feature_set=name,
            decision="keep",
        )
        print(f"{name}: {len(features)} features")

    missing = _missingness_by_season(frame, sets["pre_freeze_248"])
    missing.to_csv(OUTPUT_DIR / "missingness_by_season.csv", index=False)
    high = (
        missing.groupby("feature", as_index=False)["missing_pct"]
        .max()
        .sort_values("missing_pct", ascending=False)
    )
    high.to_csv(OUTPUT_DIR / "missingness_by_season_feature_max.csv", index=False)

    metadata = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "feature_sets": {
            name: registry_metadata(name, features)
            for name, features in sets.items()
        },
        "supported_feature_sets": list(FEATURE_SETS),
        "decisions": {
            "production": (
                "Frozen LightGBM registry after Step 7: drop mean-family "
                "*_P10 on pitch_physics / pitch_usage / mechanics / fip_xfip."
            ),
            "pre_freeze_248": "Prior full allow-list retained for comparisons.",
            "ridge_vif": (
                "Phase-1 VIF reduction minus xFIP_P5; keep xwOBA_P5 residual."
            ),
        },
        "missingness_features_max_gt_50pct": int((high["missing_pct"] > 50).sum()),
    }
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"Wrote registries to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
