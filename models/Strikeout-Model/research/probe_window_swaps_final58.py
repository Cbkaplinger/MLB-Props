"""Targeted rolling-window swap probe for final58 vs sparse72.

Evaluates one-stem-at-a-time swaps on the walk-forward stack to detect
remaining window headroom before deeper HPO commitment.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, tbf_feature_names

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "window_swap_probe"
WINDOW_RE = re.compile(r"^(.*)_P(\d+)$")


def _load_wf():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feature_window_map(features: list[str]) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for feature in features:
        m = WINDOW_RE.match(feature)
        if not m:
            continue
        out[m.group(1)] = (feature, int(m.group(2)))
    return out


def _evaluate_mean_mae(wf, frame: pd.DataFrame, k_features: list[str], tbf_features: list[str]) -> float:
    maes: list[float] = []
    for name, start, end in wf.DEFAULT_WINDOWS:
        row, _ = wf._run_window(
            frame,
            name=name,
            test_start=start,
            test_end=end,
            k_features=k_features,
            tbf_features=tbf_features,
            tune_alpha=True,
        )
        maes.append(float(row["expected_K_mae"]))
    return float(np.mean(maes))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wf = _load_wf()
    frame = wf._load_frame()
    cols = set(frame.columns)
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))

    f58 = list(resolve_feature_names(frame, "production_final58_consensus"))
    f72 = list(resolve_feature_names(frame, "production_sparse72"))
    m58 = _feature_window_map(f58)
    m72 = _feature_window_map(f72)

    baseline = _evaluate_mean_mae(wf, frame, f58, tbf_features)
    rows: list[dict[str, object]] = [
        {
            "probe": "baseline_final58",
            "mean_expected_k_mae": baseline,
            "delta_vs_baseline": 0.0,
            "swapped_stem": "",
            "from_window": None,
            "to_window": None,
        }
    ]

    for stem in sorted(set(m58) & set(m72)):
        from_feature, from_w = m58[stem]
        _, to_w = m72[stem]
        if from_w == to_w:
            continue
        alt_col = f"{stem}_P{to_w}"
        if alt_col not in cols:
            continue
        candidate = [alt_col if f == from_feature else f for f in f58]
        mae = _evaluate_mean_mae(wf, frame, candidate, tbf_features)
        rows.append(
            {
                "probe": f"swap_{stem}_P{from_w}_to_P{to_w}",
                "mean_expected_k_mae": mae,
                "delta_vs_baseline": mae - baseline,
                "swapped_stem": stem,
                "from_window": from_w,
                "to_window": to_w,
            }
        )

    out = pd.DataFrame(rows).sort_values("mean_expected_k_mae")
    out.to_csv(OUT_DIR / "final58_window_swap_probe.csv", index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_mean_expected_k_mae": baseline,
        "n_probes": int(len(out) - 1),
        "best_probe": out.iloc[0].to_dict() if not out.empty else None,
        "files": {
            "probe_csv": str(OUT_DIR / "final58_window_swap_probe.csv"),
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

