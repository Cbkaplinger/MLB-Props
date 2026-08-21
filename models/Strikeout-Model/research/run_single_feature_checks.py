"""Single-feature LOFO + permutation checks for shortlisted columns.

Runs on the same walk-forward windows used by Phase 11.B so we can quantify:
1) retrain-without-feature (LOFO)
2) hold-model-fixed permutation delta on test
"""

from __future__ import annotations

import argparse
import importlib.util
import json
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
from Python.count_layer import expected_strikeouts, fit_count_layer_kappa
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, tbf_feature_names
from Python.training import metrics, predict_clipped, predict_nonnegative


def _load_walkforward_module():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evaluate_mean_mae(
    wf,
    frame: pd.DataFrame,
    *,
    k_features: list[str],
    tbf_features: list[str],
    tune_alpha: bool,
) -> float:
    maes: list[float] = []
    for name, start, end in wf.DEFAULT_WINDOWS:
        row, _ = wf._run_window(
            frame,
            name=name,
            test_start=start,
            test_end=end,
            k_features=k_features,
            tbf_features=tbf_features,
            tune_alpha=tune_alpha,
        )
        maes.append(float(row["expected_K_mae"]))
    return float(np.mean(maes))


def _permutation_delta(
    wf,
    frame: pd.DataFrame,
    *,
    feature: str,
    k_features: list[str],
    tbf_features: list[str],
    tune_alpha: bool,
    seed: int,
) -> float:
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    for _, test_start, test_end in wf.DEFAULT_WINDOWS:
        start = pd.Timestamp(test_start)
        end = pd.Timestamp(test_end)
        train = frame[frame["game_date"] < start]
        test = frame[(frame["game_date"] >= start) & (frame["game_date"] < end)]
        fit, val = wf._chrono_val_split(train)
        k_model = wf._fit_krate(fit, val, k_features)
        tbf_model, _, tbf_upper = wf._fit_tbf(
            train, fit, val, tbf_features, tune_alpha=tune_alpha
        )
        k_hat_train = predict_clipped(k_model, "lightgbm", train, k_features)
        kappa = fit_count_layer_kappa(
            k=train["K"], pa=train["PA"], k_rate=k_hat_train
        )

        k_hat_base = predict_clipped(k_model, "lightgbm", test, k_features)
        tbf_hat = predict_nonnegative(
            tbf_model, "ridge", test, tbf_features, upper=tbf_upper
        )
        base_expected = expected_strikeouts(k_hat_base, tbf_hat)
        base_mae = metrics(test["K"], base_expected, clip_to_unit_interval=False)["mae"]

        permuted = test.copy()
        values = permuted[feature].to_numpy(copy=True)
        rng.shuffle(values)
        permuted[feature] = values
        k_hat_perm = predict_clipped(k_model, "lightgbm", permuted, k_features)
        perm_expected = expected_strikeouts(k_hat_perm, tbf_hat)
        perm_mae = metrics(
            test["K"], perm_expected, clip_to_unit_interval=False
        )["mae"]
        deltas.append(float(perm_mae - base_mae))
    return float(np.mean(deltas))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-set", default="research_air_profile_all")
    parser.add_argument("--feature", action="append", default=[])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tune-alpha", action="store_true")
    args = parser.parse_args()

    wf = _load_walkforward_module()
    frame = wf._load_frame()
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    k_features = list(resolve_feature_names(frame, args.feature_set))
    extras = [feature for feature in k_features if feature not in set(resolve_feature_names(frame, "production"))]
    shortlist = args.feature if args.feature else extras
    shortlist = [feature for feature in shortlist if feature in k_features]
    if not shortlist:
        raise ValueError("no shortlist features found in selected feature set")

    baseline = _evaluate_mean_mae(
        wf,
        frame,
        k_features=k_features,
        tbf_features=tbf_features,
        tune_alpha=args.tune_alpha,
    )
    rows: list[dict[str, object]] = []
    for feature in shortlist:
        lofo_features = [column for column in k_features if column != feature]
        lofo_mae = _evaluate_mean_mae(
            wf,
            frame,
            k_features=lofo_features,
            tbf_features=tbf_features,
            tune_alpha=args.tune_alpha,
        )
        perm_delta = _permutation_delta(
            wf,
            frame,
            feature=feature,
            k_features=k_features,
            tbf_features=tbf_features,
            tune_alpha=args.tune_alpha,
            seed=args.seed,
        )
        rows.append(
            {
                "feature_set": args.feature_set,
                "feature": feature,
                "baseline_expected_K_mae": baseline,
                "lofo_expected_K_mae": lofo_mae,
                "delta_lofo_minus_baseline": lofo_mae - baseline,
                "delta_perm_minus_baseline": perm_delta,
            }
        )

    out_dir = config.OUTPUT_DIR / "feature_research" / f"single_feature_checks_{args.feature_set}"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(rows).sort_values("delta_lofo_minus_baseline", ascending=False)
    result.to_csv(out_dir / "single_feature_checks.csv", index=False)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "feature_set": args.feature_set,
                "n_features": len(shortlist),
                "baseline_expected_K_mae": baseline,
                "files": {
                    "single_feature_checks_csv": str(out_dir / "single_feature_checks.csv"),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(result.to_string(index=False))
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
