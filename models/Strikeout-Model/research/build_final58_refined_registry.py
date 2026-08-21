"""Build refined final58 registry from proven window swaps."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config
from Python.registries import resolve_feature_names

PROBE_PATH = config.OUTPUT_DIR / "model_quality" / "window_swap_probe" / "final58_window_swap_probe.csv"
OUT_DIR = config.OUTPUT_DIR / "model_quality" / "final58_refined_registry"
OUT_FEATURES = OUT_DIR / "best_features.csv"
OUT_SUMMARY = OUT_DIR / "summary.json"
_SWAP_RE = re.compile(r"^swap_(.+)_P(\d+)_to_P(\d+)$")


def main() -> None:
    if not PROBE_PATH.exists():
        raise FileNotFoundError(f"Missing probe results: {PROBE_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    frame = pl.read_parquet(config.PITCHER_TRAINING_PATH).head(5).to_pandas()
    features = list(resolve_feature_names(frame, "production_final58_consensus"))
    probe = pd.read_csv(PROBE_PATH)
    improving = probe[probe["delta_vs_baseline"] < 0].copy()
    improving = improving.sort_values("delta_vs_baseline")

    swap_applied: list[dict[str, object]] = []
    for row in improving.to_dict(orient="records"):
        probe_name = str(row.get("probe", ""))
        m = _SWAP_RE.match(probe_name)
        if not m:
            continue
        stem, from_w, to_w = m.group(1), int(m.group(2)), int(m.group(3))
        from_col = f"{stem}_P{from_w}"
        to_col = f"{stem}_P{to_w}"
        if from_col in features and to_col not in features:
            features = [to_col if f == from_col else f for f in features]
            swap_applied.append(
                {
                    "stem": stem,
                    "from_col": from_col,
                    "to_col": to_col,
                    "delta_vs_baseline": float(row["delta_vs_baseline"]),
                }
            )

    pd.DataFrame({"feature": features}).to_csv(OUT_FEATURES, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_feature_set": "production_final58_consensus",
        "n_features_out": len(features),
        "n_swaps_applied": len(swap_applied),
        "swaps_applied": swap_applied,
        "feature_file": str(OUT_FEATURES),
    }
    OUT_SUMMARY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

