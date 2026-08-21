"""Model-form scan on sparse architecture (monotone/robust/blend).

Compares k-rate variants while keeping the same TBF layer:
- baseline LightGBM regression
- monotonic-constraint LightGBM
- LightGBM regression_l1
- LightGBM huber
- blend: 50/50 sparse40 baseline + plus_xwoba baseline
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
from Python.count_layer import expected_strikeouts
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, tbf_feature_names
from Python.training import build_model, fit_regressor, lightgbm_matrix, metrics, predict_clipped, predict_nonnegative

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "deep_feature_review"


def _load_wf():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fit_k_model(
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    objective: str = "regression",
    monotone_constraints: list[int] | None = None,
):
    params: dict[str, object] = {"objective": objective}
    if monotone_constraints is not None:
        params["monotone_constraints"] = monotone_constraints
        params["monotone_constraints_method"] = "advanced"
    model = build_model(
        "lightgbm",
        lightgbm_verbosity=-1,
        lightgbm_params=params,
    )
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        train[TARGET],
        validation_features=lightgbm_matrix(val, features),
        validation_target=val[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model


def _monotone_constraints(features: list[str]) -> list[int]:
    positive_stems = {
        "k_rate_",
        "opp_lineup_k",
        "opp_lineup_whiff",
        "opp_lineup_swstr",
        "opp_lineup_chase",
        "park_k_factor",
    }
    out: list[int] = []
    for feature in features:
        if any(feature == stem or feature.startswith(stem) for stem in positive_stems):
            out.append(1)
        else:
            out.append(0)
    return out


def _fit_tbf(train: pd.DataFrame, features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[features], train["PA"])
    upper = float(train["PA"].quantile(0.999))
    return model, upper


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wf = _load_wf()
    frame = wf._load_frame()
    sparse40 = list(resolve_feature_names(frame, "production_sparse40"))
    plus_x = list(resolve_feature_names(frame, "production_plus_xwoba_luck"))
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    mono = _monotone_constraints(sparse40)

    variants = (
        "baseline_sparse40",
        "monotone_sparse40",
        "l1_sparse40",
        "huber_sparse40",
        "blend_sparse40_plusx",
    )
    rows: list[dict[str, object]] = []
    for variant in variants:
        maes: list[float] = []
        k_rate_maes: list[float] = []
        for name, start, end in wf.DEFAULT_WINDOWS:
            s = pd.Timestamp(start)
            e = pd.Timestamp(end)
            train = frame[frame["game_date"] < s]
            test = frame[(frame["game_date"] >= s) & (frame["game_date"] < e)]
            cut = int(len(train) * 0.85)
            fit = train.iloc[:cut]
            val = train.iloc[cut:]

            tbf_model, tbf_upper = _fit_tbf(train, tbf_features)
            tbf_hat = predict_nonnegative(tbf_model, "ridge", test, tbf_features, upper=tbf_upper)

            if variant == "blend_sparse40_plusx":
                m_sparse = _fit_k_model(fit, val, sparse40, objective="regression")
                m_plus = _fit_k_model(fit, val, plus_x, objective="regression")
                k_hat = 0.5 * predict_clipped(m_sparse, "lightgbm", test, sparse40) + 0.5 * predict_clipped(
                    m_plus, "lightgbm", test, plus_x
                )
            elif variant == "monotone_sparse40":
                m = _fit_k_model(
                    fit,
                    val,
                    sparse40,
                    objective="regression",
                    monotone_constraints=mono,
                )
                k_hat = predict_clipped(m, "lightgbm", test, sparse40)
            elif variant == "l1_sparse40":
                m = _fit_k_model(fit, val, sparse40, objective="regression_l1")
                k_hat = predict_clipped(m, "lightgbm", test, sparse40)
            elif variant == "huber_sparse40":
                m = _fit_k_model(fit, val, sparse40, objective="huber")
                k_hat = predict_clipped(m, "lightgbm", test, sparse40)
            else:
                m = _fit_k_model(fit, val, sparse40, objective="regression")
                k_hat = predict_clipped(m, "lightgbm", test, sparse40)

            expected = expected_strikeouts(k_hat, tbf_hat)
            maes.append(float(metrics(test["K"], expected, clip_to_unit_interval=False)["mae"]))
            k_rate_maes.append(float(metrics(test[TARGET], k_hat)["mae"]))
        rows.append(
            {
                "variant": variant,
                "wf_expected_k_mae_mean": float(np.mean(maes)),
                "wf_expected_k_mae_std": float(np.std(maes, ddof=0)),
                "wf_k_rate_mae_mean": float(np.mean(k_rate_maes)),
            }
        )

    out = pd.DataFrame(rows).sort_values("wf_expected_k_mae_mean")
    out_path = OUT_DIR / "sparse40_model_variant_scan.csv"
    out.to_csv(out_path, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file": str(out_path),
        "best_variant": out.iloc[0].to_dict() if not out.empty else None,
    }
    (OUT_DIR / "sparse40_model_variant_scan_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(out.to_string(index=False))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

