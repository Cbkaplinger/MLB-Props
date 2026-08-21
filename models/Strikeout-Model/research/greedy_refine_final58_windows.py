"""Greedy rolling-window refinement for final58.

At each iteration:
1) test each remaining candidate swap on the current feature list
2) apply the best improving swap only
3) stop when no swap improves expected_K MAE
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

PROBE_PATH = config.OUTPUT_DIR / "model_quality" / "window_swap_probe" / "final58_window_swap_probe.csv"
OUT_DIR = config.OUTPUT_DIR / "model_quality" / "final58_greedy_refined_registry"
OUT_FEATURES = OUT_DIR / "best_features.csv"
OUT_TRACE = OUT_DIR / "greedy_trace.csv"
OUT_SUMMARY = OUT_DIR / "summary.json"
_SWAP_RE = re.compile(r"^swap_(.+)_P(\d+)_to_P(\d+)$")


def _load_wf():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    if not PROBE_PATH.exists():
        raise FileNotFoundError(f"Missing probe file: {PROBE_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    wf = _load_wf()
    frame = wf._load_frame()
    cols = set(frame.columns)
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))

    base = list(resolve_feature_names(frame, "production_final58_consensus"))
    probe = pd.read_csv(PROBE_PATH)
    cands: list[tuple[str, str]] = []
    for probe_name in probe["probe"].astype(str).tolist():
        m = _SWAP_RE.match(probe_name)
        if not m:
            continue
        stem, from_w, to_w = m.group(1), int(m.group(2)), int(m.group(3))
        from_col = f"{stem}_P{from_w}"
        to_col = f"{stem}_P{to_w}"
        if from_col in base and to_col in cols:
            cands.append((from_col, to_col))

    current = list(base)
    current_mae = _evaluate_mean_mae(wf, frame, current, tbf_features)
    trace: list[dict[str, object]] = [
        {"step": 0, "action": "baseline", "mae": current_mae, "delta": 0.0}
    ]

    remaining = list(cands)
    step = 1
    while remaining:
        best = None
        for from_col, to_col in remaining:
            if from_col not in current or to_col in current:
                continue
            candidate = [to_col if f == from_col else f for f in current]
            mae = _evaluate_mean_mae(wf, frame, candidate, tbf_features)
            delta = mae - current_mae
            if best is None or delta < best["delta"]:
                best = {
                    "from_col": from_col,
                    "to_col": to_col,
                    "mae": mae,
                    "delta": delta,
                }
        if best is None or float(best["delta"]) >= 0.0:
            break
        current = [best["to_col"] if f == best["from_col"] else f for f in current]
        current_mae = float(best["mae"])
        trace.append(
            {
                "step": step,
                "action": f"{best['from_col']}->{best['to_col']}",
                "mae": current_mae,
                "delta": float(best["delta"]),
            }
        )
        remaining = [
            (f, t)
            for (f, t) in remaining
            if not (f == best["from_col"] and t == best["to_col"])
        ]
        step += 1

    pd.DataFrame({"feature": current}).to_csv(OUT_FEATURES, index=False)
    pd.DataFrame(trace).to_csv(OUT_TRACE, index=False)
    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_feature_set": "production_final58_consensus",
        "start_mae": trace[0]["mae"],
        "final_mae": current_mae,
        "total_delta": float(current_mae - trace[0]["mae"]),
        "n_swaps_applied": len(trace) - 1,
        "files": {
            "features_csv": str(OUT_FEATURES),
            "trace_csv": str(OUT_TRACE),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(pd.DataFrame(trace).to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

