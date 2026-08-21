"""Constrained combo swap refinement for final58.

Searches small swap combinations (k<=3) from improving single-swap pool,
then re-evaluates walk-forward expected_K MAE to identify robust candidates.
"""

from __future__ import annotations

import importlib.util
import itertools
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
OUT_DIR = config.OUTPUT_DIR / "model_quality" / "final58_combo_refined_registry"
OUT_RESULTS = OUT_DIR / "combo_results.csv"
OUT_FEATURES = OUT_DIR / "best_features.csv"
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


def _apply_swaps(base: list[str], swaps: list[tuple[str, str]]) -> list[str] | None:
    out = list(base)
    for from_col, to_col in swaps:
        if from_col not in out:
            return None
        if to_col in out and to_col != from_col:
            return None
        out = [to_col if f == from_col else f for f in out]
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not PROBE_PATH.exists():
        raise FileNotFoundError(f"Missing {PROBE_PATH}")

    wf = _load_wf()
    frame = wf._load_frame()
    cols = set(frame.columns)
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))

    base = list(resolve_feature_names(frame, "production_final58_consensus"))
    baseline_mae = _evaluate_mean_mae(wf, frame, base, tbf_features)

    probe = pd.read_csv(PROBE_PATH)
    improving = probe[probe["delta_vs_baseline"] < 0].copy().sort_values("delta_vs_baseline")
    # Keep top-8 strongest single-swap improvements to stay constrained.
    improving = improving.head(8)
    swap_pool: list[tuple[str, str, str, float]] = []
    for row in improving.to_dict(orient="records"):
        name = str(row["probe"])
        m = _SWAP_RE.match(name)
        if not m:
            continue
        stem, from_w, to_w = m.group(1), int(m.group(2)), int(m.group(3))
        from_col = f"{stem}_P{from_w}"
        to_col = f"{stem}_P{to_w}"
        if from_col in base and to_col in cols:
            swap_pool.append((from_col, to_col, stem, float(row["delta_vs_baseline"])))

    rows: list[dict[str, object]] = [
        {
            "combo_size": 0,
            "combo_label": "baseline",
            "mae": baseline_mae,
            "delta_vs_baseline": 0.0,
            "swaps": "",
        }
    ]
    best_features = list(base)
    best_mae = baseline_mae
    best_label = "baseline"

    for k in (1, 2, 3):
        for combo in itertools.combinations(swap_pool, k):
            swaps = [(c[0], c[1]) for c in combo]
            cand = _apply_swaps(base, swaps)
            if cand is None:
                continue
            mae = _evaluate_mean_mae(wf, frame, cand, tbf_features)
            delta = mae - baseline_mae
            label = ";".join(f"{c[0]}->{c[1]}" for c in combo)
            rows.append(
                {
                    "combo_size": k,
                    "combo_label": label,
                    "mae": mae,
                    "delta_vs_baseline": delta,
                    "swaps": label,
                }
            )
            if mae < best_mae:
                best_mae = mae
                best_features = cand
                best_label = label

    out = pd.DataFrame(rows).sort_values(["mae", "combo_size"])
    out.to_csv(OUT_RESULTS, index=False)
    pd.DataFrame({"feature": best_features}).to_csv(OUT_FEATURES, index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_mae": baseline_mae,
        "best_mae": best_mae,
        "best_delta": float(best_mae - baseline_mae),
        "best_combo_label": best_label,
        "n_candidates_tested": int(len(out)),
        "files": {
            "combo_results_csv": str(OUT_RESULTS),
            "best_features_csv": str(OUT_FEATURES),
        },
    }
    OUT_SUMMARY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.head(12).to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

