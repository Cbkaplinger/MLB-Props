"""Extended robustness suite for sparse max-lift candidates.

Runs:
1) K-local monotone sweep at K={48,56,64,72,80}.
2) Seed robustness on top configs.
3) Window perturbation robustness (+/- 7 days).
4) Family composition + window-coverage audit for top-72 features.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timedelta, timezone
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
from Python.training import (
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
    predict_nonnegative,
)

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "max_lift_robustness_suite"
ATTR_PATH = config.OUTPUT_DIR / "model_quality" / "deep_feature_review" / "legacy_feature_attribution.csv"
DICT_PATH = config.OUTPUT_DIR / "feature_research" / "feature_dictionary.csv"
K_LOCAL = (48, 56, 64, 72, 80)
SEEDS = (7, 11, 19, 29, 41)
BASELINE_PARAMS = {
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 2.0,
}
_SUFFIX_RE = re.compile(r"_(P\d+|std)$")


def _load_wf():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _constraint_vector(features: list[str], mode: str) -> list[int]:
    if mode == "none":
        return [0] * len(features)
    positive = (
        "k_rate_",
        "opp_lineup_k",
        "opp_lineup_whiff",
        "opp_lineup_swstr",
        "opp_lineup_chase",
        "park_k_factor",
    )
    negative_refined = ("opp_lineup_zcontact", "opp_lineup_bb")
    out: list[int] = []
    for feature in features:
        if any(feature == s or feature.startswith(s) for s in positive):
            out.append(1)
        elif mode == "refined_signed" and any(
            feature == s or feature.startswith(s) for s in negative_refined
        ):
            out.append(-1)
        else:
            out.append(0)
    return out


def _fit_k_model(
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    objective: str,
    constraint_mode: str,
    seed: int = 11,
):
    params = dict(BASELINE_PARAMS)
    params["objective"] = objective
    params["seed"] = seed
    params["feature_fraction_seed"] = seed
    params["bagging_seed"] = seed
    params["data_random_seed"] = seed
    if float(params.get("subsample", 1.0)) < 1.0:
        params.setdefault("bagging_freq", 1)
    constraints = _constraint_vector(features, constraint_mode)
    if any(v != 0 for v in constraints):
        params["monotone_constraints"] = constraints
        params["monotone_constraints_method"] = "advanced"
    model = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=params)
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


def _fit_tbf(train: pd.DataFrame, tbf_features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[tbf_features], train["PA"])
    upper = float(train["PA"].quantile(0.999))
    return model, upper


def _eval_windows(
    frame: pd.DataFrame,
    features: list[str],
    windows: list[tuple[str, pd.Timestamp, pd.Timestamp]],
    *,
    objective: str,
    constraint_mode: str,
    seed: int,
) -> tuple[float, float, float, int]:
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    ek_maes: list[float] = []
    kr_maes: list[float] = []
    n_used = 0
    for _, start, end in windows:
        train = frame[frame["game_date"] < start]
        test = frame[(frame["game_date"] >= start) & (frame["game_date"] < end)]
        if train.empty or test.empty:
            continue
        cut = int(len(train) * 0.85)
        fit = train.iloc[:cut]
        val = train.iloc[cut:]
        if fit.empty or val.empty:
            continue
        k_model = _fit_k_model(
            fit,
            val,
            features,
            objective=objective,
            constraint_mode=constraint_mode,
            seed=seed,
        )
        tbf_model, tbf_upper = _fit_tbf(train, tbf_features)
        k_hat = predict_clipped(k_model, "lightgbm", test, features)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", test, tbf_features, upper=tbf_upper)
        expected = expected_strikeouts(k_hat, tbf_hat)
        ek_maes.append(float(metrics(test["K"], expected, clip_to_unit_interval=False)["mae"]))
        kr_maes.append(float(metrics(test[TARGET], k_hat)["mae"]))
        n_used += 1
    return (
        float(np.mean(ek_maes)),
        float(np.std(ek_maes, ddof=0)),
        float(np.mean(kr_maes)),
        n_used,
    )


def _to_windows(wf_windows: list[tuple[str, str, str]]) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    return [
        (name, pd.Timestamp(start), pd.Timestamp(end))
        for name, start, end in wf_windows
    ]


def _shift_windows(
    windows: list[tuple[str, pd.Timestamp, pd.Timestamp]], days: int
) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    delta = timedelta(days=days)
    return [(name, start + delta, end + delta) for name, start, end in windows]


def _family_and_window_audit(frame: pd.DataFrame, top_features: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    dictionary = pd.read_csv(DICT_PATH)
    fam_map = dictionary.set_index("feature")["family"].astype(str).to_dict()
    fam_rows = [{"feature": f, "family": fam_map.get(f, "unknown")} for f in top_features]
    fam = (
        pd.DataFrame(fam_rows)
        .groupby("family", as_index=False)
        .size()
        .rename(columns={"size": "n_features"})
        .sort_values(["n_features", "family"], ascending=[False, True])
    )

    cols = set(frame.columns)
    stem_rows: list[dict[str, object]] = []
    for feature in top_features:
        stem = _SUFFIX_RE.sub("", feature)
        if any(r["stem"] == stem for r in stem_rows):
            continue
        available = [
            suffix
            for suffix in ("P1", "P3", "P5", "P10", "P20", "std")
            if f"{stem}_{suffix}" in cols
        ]
        stem_rows.append(
            {
                "stem": stem,
                "feature_in_top72": feature,
                "available_windows": ",".join(available),
                "n_available_windows": len(available),
            }
        )
    stems = pd.DataFrame(stem_rows).sort_values(
        ["n_available_windows", "stem"], ascending=[False, True]
    )
    return fam, stems


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wf = _load_wf()
    frame = wf._load_frame()
    prod = set(resolve_feature_names(frame, "production"))
    ranked = pd.read_csv(ATTR_PATH)["feature"].astype(str).tolist()
    ranked = [f for f in ranked if f in prod]
    default_windows = _to_windows(wf.DEFAULT_WINDOWS)

    # 1) K-local monotone sweep
    rows: list[dict[str, object]] = []
    for k in K_LOCAL:
        features = ranked[:k]
        for mode in ("none", "coarse_positive", "refined_signed"):
            ek_mean, ek_std, kr_mean, n_used = _eval_windows(
                frame,
                features,
                default_windows,
                objective="regression",
                constraint_mode=mode,
                seed=11,
            )
            rows.append(
                {
                    "k_features": k,
                    "constraint_mode": mode,
                    "objective": "regression",
                    "seed": 11,
                    "windows_used": n_used,
                    "wf_expected_k_mae_mean": ek_mean,
                    "wf_expected_k_mae_std": ek_std,
                    "wf_k_rate_mae_mean": kr_mean,
                }
            )
    k_local = pd.DataFrame(rows).sort_values("wf_expected_k_mae_mean")
    k_local_path = OUT_DIR / "k_local_monotone_sweep.csv"
    k_local.to_csv(k_local_path, index=False)

    # 2) Seed robustness on top 3 configs
    top_cfgs = k_local.head(3).to_dict(orient="records")
    seed_rows: list[dict[str, object]] = []
    for cfg in top_cfgs:
        features = ranked[: int(cfg["k_features"])]
        for seed in SEEDS:
            ek_mean, ek_std, kr_mean, n_used = _eval_windows(
                frame,
                features,
                default_windows,
                objective=str(cfg["objective"]),
                constraint_mode=str(cfg["constraint_mode"]),
                seed=int(seed),
            )
            seed_rows.append(
                {
                    "k_features": int(cfg["k_features"]),
                    "constraint_mode": str(cfg["constraint_mode"]),
                    "objective": str(cfg["objective"]),
                    "seed": int(seed),
                    "windows_used": n_used,
                    "wf_expected_k_mae_mean": ek_mean,
                    "wf_expected_k_mae_std": ek_std,
                    "wf_k_rate_mae_mean": kr_mean,
                }
            )
    seed_df = pd.DataFrame(seed_rows)
    seed_path = OUT_DIR / "seed_robustness.csv"
    seed_df.to_csv(seed_path, index=False)
    seed_summary = (
        seed_df.groupby(["k_features", "constraint_mode", "objective"], as_index=False)
        .agg(
            wf_expected_k_mae_mean=("wf_expected_k_mae_mean", "mean"),
            wf_expected_k_mae_std_across_seeds=("wf_expected_k_mae_mean", "std"),
            wf_k_rate_mae_mean=("wf_k_rate_mae_mean", "mean"),
        )
        .sort_values("wf_expected_k_mae_mean")
    )
    seed_summary_path = OUT_DIR / "seed_robustness_summary.csv"
    seed_summary.to_csv(seed_summary_path, index=False)

    # 3) Window perturbation robustness on best config
    best = seed_summary.iloc[0].to_dict()
    best_k = int(best["k_features"])
    best_mode = str(best["constraint_mode"])
    best_features = ranked[:best_k]
    win_rows: list[dict[str, object]] = []
    for shift in (-7, 0, 7):
        shifted = _shift_windows(default_windows, shift)
        ek_mean, ek_std, kr_mean, n_used = _eval_windows(
            frame,
            best_features,
            shifted,
            objective="regression",
            constraint_mode=best_mode,
            seed=11,
        )
        win_rows.append(
            {
                "k_features": best_k,
                "constraint_mode": best_mode,
                "window_shift_days": shift,
                "windows_used": n_used,
                "wf_expected_k_mae_mean": ek_mean,
                "wf_expected_k_mae_std": ek_std,
                "wf_k_rate_mae_mean": kr_mean,
            }
        )
    win_df = pd.DataFrame(win_rows).sort_values("window_shift_days")
    win_path = OUT_DIR / "window_shift_robustness.csv"
    win_df.to_csv(win_path, index=False)

    # 4) Family composition + window-coverage audit for top-72
    top72 = ranked[:72]
    fam_df, stem_df = _family_and_window_audit(frame, top72)
    top72_path = OUT_DIR / "top72_features.csv"
    pd.DataFrame({"feature": top72}).to_csv(top72_path, index=False)
    fam_path = OUT_DIR / "top72_family_counts.csv"
    stem_path = OUT_DIR / "top72_stem_window_coverage.csv"
    fam_df.to_csv(fam_path, index=False)
    stem_df.to_csv(stem_path, index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "best_config_after_seed_robustness": {
            "k_features": best_k,
            "constraint_mode": best_mode,
            "objective": "regression",
        },
        "files": {
            "k_local_monotone_sweep_csv": str(k_local_path),
            "seed_robustness_csv": str(seed_path),
            "seed_robustness_summary_csv": str(seed_summary_path),
            "window_shift_robustness_csv": str(win_path),
            "top72_features_csv": str(top72_path),
            "top72_family_counts_csv": str(fam_path),
            "top72_stem_window_coverage_csv": str(stem_path),
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(k_local.to_string(index=False))
    print("\nSeed robustness summary:")
    print(seed_summary.to_string(index=False))
    print("\nWindow-shift robustness:")
    print(win_df.to_string(index=False))
    print(f"\nWrote {OUT_DIR}")


if __name__ == "__main__":
    main()

