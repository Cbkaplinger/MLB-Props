"""Deep feature review for frozen production model + window micro-search.

Outputs:
- artifacts/model_quality/deep_feature_review/legacy_feature_attribution.csv
- artifacts/model_quality/deep_feature_review/window_micro_search.csv
- artifacts/model_quality/deep_feature_review/summary.json
"""

from __future__ import annotations

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
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, tbf_feature_names
from Python.training import (
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
)

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "deep_feature_review"
WINDOW_STEMS = (
    "xwoba_minus_woba",
    "pull_air_allowed_rate",
    "oppo_air_allowed_rate",
    "center_air_allowed_rate",
    "iffb_rate",
)
WINDOW_SUFFIX_ORDER = ("P3", "P5", "P7", "P10", "P14", "P20", "std")


def _load_walkforward_module():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fit_legacy_model(frame: pd.DataFrame, features: list[str]):
    train, validation, test = chronological_split(frame)
    model = build_model("lightgbm", lightgbm_verbosity=-1)
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        train[TARGET],
        validation_features=lightgbm_matrix(validation, features),
        validation_target=validation[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model, train, validation, test


def _legacy_feature_attribution(frame: pd.DataFrame) -> pd.DataFrame:
    features = list(resolve_feature_names(frame, "production"))
    model, _, _, test = _fit_legacy_model(frame, features)
    y = test[TARGET].to_numpy(dtype=float)
    base_pred = predict_clipped(model, "lightgbm", test, features)
    base_mae = float(metrics(y, base_pred)["mae"])

    booster = model.booster_
    gain = booster.feature_importance(importance_type="gain")
    split = booster.feature_importance(importance_type="split")

    x_test = lightgbm_matrix(test, features)
    shap_raw = booster.predict(x_test, pred_contrib=True)
    shap = np.asarray(shap_raw, dtype=float)[:, : len(features)]
    shap_abs_mean = np.abs(shap).mean(axis=0)

    rng = np.random.default_rng(42)
    perm_deltas: list[float] = []
    for feature in features:
        perm = test.copy()
        vals = perm[feature].to_numpy(copy=True)
        rng.shuffle(vals)
        perm[feature] = vals
        pred = predict_clipped(model, "lightgbm", perm, features)
        mae = float(metrics(y, pred)["mae"])
        perm_deltas.append(mae - base_mae)

    out = pd.DataFrame(
        {
            "feature": features,
            "gain_importance": gain,
            "split_importance": split,
            "mean_abs_shap": shap_abs_mean,
            "perm_delta_mae": perm_deltas,
        }
    ).sort_values("mean_abs_shap", ascending=False)
    out["shap_rank"] = np.arange(1, len(out) + 1)
    out["base_test_mae"] = base_mae
    return out


def _available_suffixes(frame: pd.DataFrame, stem: str) -> list[str]:
    out: list[str] = []
    for suffix in WINDOW_SUFFIX_ORDER:
        col = f"{stem}_{suffix}"
        if col in frame.columns:
            out.append(suffix)
    return out


def _replace_stem_window(features: list[str], stem: str, suffix: str) -> list[str]:
    target = f"{stem}_{suffix}"
    pruned = [
        feature for feature in features if not feature.startswith(f"{stem}_")
    ]
    if target not in pruned:
        pruned.append(target)
    return pruned


def _evaluate_feature_list(
    wf,
    frame: pd.DataFrame,
    *,
    k_features: list[str],
    tbf_features: list[str],
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
            tune_alpha=True,
        )
        maes.append(float(row["expected_K_mae"]))
    return float(np.mean(maes))


def _window_micro_search(wf, frame: pd.DataFrame) -> pd.DataFrame:
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    current = list(resolve_feature_names(frame, "production_plus_xwoba_luck"))
    base_mae = _evaluate_feature_list(
        wf,
        frame,
        k_features=current,
        tbf_features=tbf_features,
    )
    rows: list[dict[str, object]] = [
        {
            "step": 0,
            "stem": "baseline",
            "suffix": "current",
            "mean_expected_k_mae": base_mae,
            "delta_vs_start": 0.0,
        }
    ]
    step = 1
    running_best = current
    running_best_mae = base_mae
    for stem in WINDOW_STEMS:
        suffixes = _available_suffixes(frame, stem)
        if not suffixes:
            rows.append(
                {
                    "step": step,
                    "stem": stem,
                    "suffix": "missing",
                    "mean_expected_k_mae": np.nan,
                    "delta_vs_start": np.nan,
                }
            )
            step += 1
            continue
        best_suffix = None
        best_mae = float("inf")
        best_features = running_best
        for suffix in suffixes:
            candidate = _replace_stem_window(running_best, stem, suffix)
            mae = _evaluate_feature_list(
                wf,
                frame,
                k_features=candidate,
                tbf_features=tbf_features,
            )
            rows.append(
                {
                    "step": step,
                    "stem": stem,
                    "suffix": suffix,
                    "mean_expected_k_mae": mae,
                    "delta_vs_start": mae - base_mae,
                }
            )
            if mae < best_mae:
                best_mae = mae
                best_suffix = suffix
                best_features = candidate
        rows.append(
            {
                "step": step,
                "stem": stem,
                "suffix": f"chosen:{best_suffix}",
                "mean_expected_k_mae": best_mae,
                "delta_vs_start": best_mae - base_mae,
            }
        )
        running_best = best_features
        running_best_mae = best_mae
        step += 1

    rows.append(
        {
            "step": step,
            "stem": "final",
            "suffix": "greedy_selected",
            "mean_expected_k_mae": running_best_mae,
            "delta_vs_start": running_best_mae - base_mae,
            "n_features_final": len(running_best),
        }
    )
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wf = _load_walkforward_module()
    frame = wf._load_frame()

    attribution = _legacy_feature_attribution(frame)
    attribution_path = OUT_DIR / "legacy_feature_attribution.csv"
    attribution.to_csv(attribution_path, index=False)

    window = _window_micro_search(wf, frame)
    window_path = OUT_DIR / "window_micro_search.csv"
    window.to_csv(window_path, index=False)

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {
            "legacy_feature_attribution_csv": str(attribution_path),
            "window_micro_search_csv": str(window_path),
        },
        "top_legacy_shap_features": attribution.head(20)["feature"].tolist(),
        "lowest_legacy_shap_features": attribution.tail(20)["feature"].tolist(),
        "window_final_row": (
            window[window["stem"] == "final"].tail(1).to_dict(orient="records")[0]
            if not window.empty
            else None
        ),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(attribution.head(20).to_string(index=False))
    print("\nWindow micro-search:")
    print(window.to_string(index=False))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()

