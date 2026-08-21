"""Leave-family-out ablation focused on new interaction feature registries."""

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

SUITE_DIR = config.OUTPUT_DIR / "feature_research" / "interaction_family_ablation"
FEATURE_SETS: tuple[str, ...] = (
    "research_csw_finish_all",
    "research_xwoba_luck_all",
    "research_air_profile_all",
    "research_interactions_all",
)


def _load_leave_family_module():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "leave_family_out_ablation.py"
    spec = importlib.util.spec_from_file_location("leave_family_out_ablation", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    leave_family = _load_leave_family_module()
    rows: list[dict[str, object]] = []
    aggregate_parts: list[pd.DataFrame] = []
    for feature_set in FEATURE_SETS:
        out_dir = config.OUTPUT_DIR / "feature_research" / f"leave_family_out_{feature_set}"
        print(f"[ablation] running {feature_set} ...", flush=True)
        leave_family.main(("ridge", "lightgbm"), feature_set=feature_set, output_dir=out_dir)
        agg = pd.read_csv(out_dir / "aggregate.csv")
        agg["feature_set"] = feature_set
        aggregate_parts.append(agg)
        full_rows = agg[agg["configuration"] == "full"]
        for _, row in full_rows.iterrows():
            rows.append(
                {
                    "feature_set": feature_set,
                    "model": str(row["model"]),
                    "mean_mae_full": float(row["mean_mae"]),
                    "mean_rmse_full": float(row["mean_rmse"]),
                    "mean_r2_full": float(row["mean_r2"]),
                    "output_dir": str(out_dir),
                }
            )

    summary = pd.DataFrame(rows).sort_values(["model", "mean_mae_full"])
    all_agg = pd.concat(aggregate_parts, ignore_index=True)
    all_agg.to_csv(SUITE_DIR / "all_drop_configs.csv", index=False)
    summary.to_csv(SUITE_DIR / "full_model_comparison.csv", index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": list(FEATURE_SETS),
        "files": {
            "full_model_comparison": str(SUITE_DIR / "full_model_comparison.csv"),
            "all_drop_configs": str(SUITE_DIR / "all_drop_configs.csv"),
        },
    }
    (SUITE_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    print(f"Wrote {SUITE_DIR}")


if __name__ == "__main__":
    main()
