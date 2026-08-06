"""Phase 11.B — walk-forward stack backtest: k_rate × TBF → expected_K → lines.

Expanding chronological windows on 2023–2024 only. At each step both the
LightGBM k-rate model and Ridge TBF are fit on past rows only, then scored on
a future block. Component MAE and line Brier are first-class outputs.

Uses baseline LightGBM defaults (11.A nested HPO did not beat them on outer
confirmation). Ridge alpha is selected on a chrono holdout carved from the
expanding train partition (same log grid as 11.A).

Examples:
    python models/Strikeout-Model/research/walkforward_stack_backtest.py
    python models/Strikeout-Model/research/walkforward_stack_backtest.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Python import config
from Python.count_layer import (
    DEFAULT_K_LINES,
    attach_count_predictions,
    count_point_metrics,
    evaluate_count_layer,
    expected_strikeouts,
    fit_count_layer_kappa,
)
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.tbf import (
    TBF_DEFAULT_FEATURE_SET,
    TBF_TARGET,
    assert_tbf_label_not_in_features,
    tbf_feature_names,
)
from Python.training import (
    assert_pa_not_in_features,
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
    predict_nonnegative,
)

# Expanding test windows (future blocks). Train = all rows strictly before start.
DEFAULT_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("wf_2024_apr_may", "2024-04-01", "2024-06-01"),
    ("wf_2024_jun_jul", "2024-06-01", "2024-08-01"),
    ("wf_2024_aug_sep", "2024-08-01", "2025-01-01"),
)

RIDGE_ALPHA_GRID = tuple(float(x) for x in np.logspace(-2, 3, 12))
BASELINE_FREEZE = "lightgbm_krate_20260803_155401"
EXPECTED_K_BASELINE_MAE = 1.79  # count_layer chrono test reference


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_frame() -> pd.DataFrame:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.loc[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .dropna(subset=[TARGET, "K", "PA", "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )
    return frame


def _chrono_val_split(
    train: pd.DataFrame, *, val_fraction: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carve a date-disjoint validation slice from the end of train."""
    if len(train) < 50:
        raise ValueError("train partition too small for val split")
    cut = int(len(train) * (1.0 - val_fraction))
    cut = min(max(cut, 1), len(train) - 1)
    val_start = train.iloc[cut]["game_date"]
    fit = train[train["game_date"] < val_start]
    val = train[train["game_date"] >= val_start]
    if fit.empty or val.empty:
        # Fallback: last calendar month as val.
        last = train["game_date"].max()
        val_start = last - pd.Timedelta(days=30)
        fit = train[train["game_date"] < val_start]
        val = train[train["game_date"] >= val_start]
    if fit.empty or val.empty:
        raise ValueError("could not form chrono train/val split")
    return fit, val


def _fit_krate(
    fit: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
) -> object:
    model = build_model("lightgbm", lightgbm_verbosity=-1)
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(fit, features),
        fit[TARGET],
        validation_features=lightgbm_matrix(val, features),
        validation_target=val[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model


def _select_ridge_alpha(
    fit: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
) -> float:
    best_alpha = RIDGE_ALPHA_GRID[0]
    best_mae = float("inf")
    for alpha in RIDGE_ALPHA_GRID:
        model = build_model("ridge", ridge_alpha=alpha)
        fit_regressor(model, "ridge", fit[features], fit[TBF_TARGET])
        upper = float(fit[TBF_TARGET].quantile(0.999))
        pred = predict_nonnegative(model, "ridge", val, features, upper=upper)
        mae = metrics(val[TBF_TARGET], pred, clip_to_unit_interval=False)["mae"]
        if mae < best_mae:
            best_mae = float(mae)
            best_alpha = float(alpha)
    return best_alpha


def _fit_tbf(
    train: pd.DataFrame,
    fit: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    tune_alpha: bool,
) -> tuple[object, float, float]:
    alpha = (
        _select_ridge_alpha(fit, val, features)
        if tune_alpha
        else 123.28467394420659  # 11.A chrono pick; refit on full train below
    )
    model = build_model("ridge", ridge_alpha=alpha)
    fit_regressor(model, "ridge", train[features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, alpha, upper


def _slice_metrics(
    frame: pd.DataFrame,
    expected_k: np.ndarray,
    k_hat: np.ndarray,
    tbf_hat: np.ndarray,
) -> dict[str, dict[str, float]]:
    """Residual / error slices required by Gate 11.B."""
    out: dict[str, dict[str, float]] = {}
    work = frame.copy()
    work["_expected_K"] = expected_k
    work["_k_err"] = np.abs(work["K"].to_numpy(dtype=float) - expected_k)
    work["_rate_err"] = np.abs(work[TARGET].to_numpy(dtype=float) - k_hat)
    work["_tbf_err"] = np.abs(work["PA"].to_numpy(dtype=float) - tbf_hat)
    work["month"] = work["game_date"].dt.strftime("%Y-%m")

    def _agg(mask: pd.Series, label: str) -> None:
        sub = work.loc[mask]
        if len(sub) < 20:
            return
        out[label] = {
            "n": int(len(sub)),
            "expected_K_mae": float(sub["_k_err"].mean()),
            "k_rate_mae": float(sub["_rate_err"].mean()),
            "tbf_mae": float(sub["_tbf_err"].mean()),
        }

    for month, grp in work.groupby("month"):
        _agg(work.index.isin(grp.index), f"month:{month}")

    if "is_home" in work.columns:
        _agg(work["is_home"] == 1, "home")
        _agg(work["is_home"] == 0, "away")

    if "rest_is_long_gap" in work.columns:
        _agg(work["rest_is_long_gap"] == 1, "rest_long_gap")
        _agg(work["rest_is_long_gap"] == 0, "rest_normal")

    # TBF prediction quintiles (exposure regime).
    try:
        q = pd.qcut(tbf_hat, 5, labels=False, duplicates="drop")
        for qi in sorted(pd.Series(q).dropna().unique()):
            _agg(pd.Series(q, index=work.index) == qi, f"tbf_quintile:{int(qi)}")
    except ValueError:
        pass

    return out


def _run_window(
    frame: pd.DataFrame,
    *,
    name: str,
    test_start: str,
    test_end: str,
    k_features: list[str],
    tbf_features: list[str],
    tune_alpha: bool,
) -> tuple[dict, pd.DataFrame]:
    start = pd.Timestamp(test_start)
    end = pd.Timestamp(test_end)
    train = frame[frame["game_date"] < start]
    test = frame[(frame["game_date"] >= start) & (frame["game_date"] < end)]
    if len(train) < 500 or len(test) < 50:
        raise ValueError(
            f"{name}: insufficient rows (train={len(train)}, test={len(test)})"
        )

    fit, val = _chrono_val_split(train)
    k_model = _fit_krate(fit, val, k_features)
    tbf_model, alpha, tbf_upper = _fit_tbf(
        train, fit, val, tbf_features, tune_alpha=tune_alpha
    )

    k_hat_train = predict_clipped(k_model, "lightgbm", train, k_features)
    kappa = fit_count_layer_kappa(
        k=train["K"], pa=train["PA"], k_rate=k_hat_train
    )

    k_hat = predict_clipped(k_model, "lightgbm", test, k_features)
    tbf_hat = predict_nonnegative(
        tbf_model, "ridge", test, tbf_features, upper=tbf_upper
    )
    expected = expected_strikeouts(k_hat, tbf_hat)

    count_report = evaluate_count_layer(
        test,
        k_rate=k_hat,
        projected_tbf=tbf_hat,
        lines=DEFAULT_K_LINES,
        kappa=kappa,
        families=("binomial", "poisson"),
    )
    mean_pa = float(train["PA"].mean())
    pa_p5 = test["PA_P5"].to_numpy(dtype=np.float64)
    pa_p5 = np.where(np.isfinite(pa_p5), pa_p5, mean_pa)

    row = {
        "window": name,
        "test_start": test_start,
        "test_end": test_end,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_end": str(train["game_date"].max().date()),
        "ridge_alpha": alpha,
        "kappa": kappa,
        "k_rate_mae": metrics(test[TARGET], k_hat)["mae"],
        "k_rate_rmse": metrics(test[TARGET], k_hat)["rmse"],
        "tbf_mae": metrics(
            test["PA"], tbf_hat, clip_to_unit_interval=False
        )["mae"],
        "tbf_rmse": metrics(
            test["PA"], tbf_hat, clip_to_unit_interval=False
        )["rmse"],
        "expected_K_mae": count_report["expected_k"]["mae"],
        "expected_K_rmse": count_report["expected_k"]["rmse"],
        "expected_K_r2": count_report["expected_k"]["r2"],
        "expected_K_mae_pa_p5": count_point_metrics(
            test["K"], expected_strikeouts(k_hat, pa_p5)
        )["mae"],
        "expected_K_mae_mean_pa": count_point_metrics(
            test["K"],
            expected_strikeouts(k_hat, np.full_like(k_hat, mean_pa)),
        )["mae"],
    }
    for line in DEFAULT_K_LINES:
        key = str(line)
        row[f"brier_bin_{key}"] = count_report["lines"]["binomial"][key]["brier"]
        row[f"brier_poi_{key}"] = count_report["lines"]["poisson"][key]["brier"]
        row[f"logloss_bin_{key}"] = count_report["lines"]["binomial"][key][
            "log_loss"
        ]

    row["slices"] = _slice_metrics(test, expected, k_hat, tbf_hat)
    scored = attach_count_predictions(
        test.assign(window=name),
        k_rate=k_hat,
        projected_tbf=tbf_hat,
        lines=DEFAULT_K_LINES,
        kappa=kappa,
    )
    return row, scored


def main(
    *,
    dry_run: bool,
    tune_alpha: bool,
    feature_set: str = "production",
    output_dir: Path | None = None,
) -> None:
    frame = _load_frame()
    k_features = list(resolve_feature_names(frame, feature_set))
    assert_pa_not_in_features(k_features)
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    assert_tbf_label_not_in_features(tbf_features)

    if output_dir is None:
        suffix = "" if feature_set == "production" else f"_{feature_set}"
        output_dir = (
            config.OUTPUT_DIR / "model_quality" / f"phase11b_walkforward{suffix}"
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    window_plan = []
    for name, start, end in DEFAULT_WINDOWS:
        train_n = int((frame["game_date"] < pd.Timestamp(start)).sum())
        test_n = int(
            (
                (frame["game_date"] >= pd.Timestamp(start))
                & (frame["game_date"] < pd.Timestamp(end))
            ).sum()
        )
        window_plan.append(
            {"window": name, "start": start, "end": end, "train_n": train_n, "test_n": test_n}
        )

    if dry_run:
        print(
            json.dumps(
                {
                    "n_rows": len(frame),
                    "n_k_features": len(k_features),
                    "n_tbf_features": len(tbf_features),
                    "windows": window_plan,
                    "output_dir": str(output_dir),
                },
                indent=2,
            )
        )
        return

    rows: list[dict] = []
    scored_parts: list[pd.DataFrame] = []
    for name, start, end in DEFAULT_WINDOWS:
        print(f"Running {name} ({start} -> {end})...", flush=True)
        row, scored = _run_window(
            frame,
            name=name,
            test_start=start,
            test_end=end,
            k_features=k_features,
            tbf_features=tbf_features,
            tune_alpha=tune_alpha,
        )
        # Flatten slices out of the CSV row.
        slices = row.pop("slices")
        rows.append(row)
        (output_dir / f"slices_{name}.json").write_text(
            json.dumps(slices, indent=2), encoding="utf-8"
        )
        scored_parts.append(scored)
        print(
            f"  expected_K MAE={row['expected_K_mae']:.3f}  "
            f"k_rate MAE={row['k_rate_mae']:.4f}  "
            f"tbf MAE={row['tbf_mae']:.3f}",
            flush=True,
        )

    outer = pd.DataFrame(rows)
    outer_path = output_dir / "outer_results.csv"
    outer.to_csv(outer_path, index=False)

    pooled = pd.concat(scored_parts, ignore_index=True)
    pred_path = output_dir / "walkforward_predictions.parquet"
    pooled.to_parquet(pred_path)

    # Aggregate with fold variance (do not claim one number without it).
    ek = outer["expected_K_mae"]
    brier_cols = [c for c in outer.columns if c.startswith("brier_bin_")]
    summary = {
        "phase": "11.B",
        "k_rate_feature_set": feature_set,
        "k_rate_estimator": "lightgbm_baseline_defaults",
        "compare_freeze_artifact": BASELINE_FREEZE,
        "tbf_estimator": "ridge_workload_context_bullpen",
        "tune_alpha_per_window": tune_alpha,
        "n_windows": len(outer),
        "n_features_k_rate": len(k_features),
        "n_features_tbf": len(tbf_features),
        "expected_K_mae_mean": float(ek.mean()),
        "expected_K_mae_std": float(ek.std(ddof=0)),
        "expected_K_mae_min": float(ek.min()),
        "expected_K_mae_max": float(ek.max()),
        "expected_K_baseline_reference": EXPECTED_K_BASELINE_MAE,
        "pass_expected_K_vs_baseline": bool(
            float(ek.mean()) <= EXPECTED_K_BASELINE_MAE + 0.05
        ),
        "line_brier_binomial_mean": {
            col.replace("brier_bin_", ""): float(outer[col].mean())
            for col in brier_cols
        },
        "line_brier_binomial_std": {
            col.replace("brier_bin_", ""): float(outer[col].std(ddof=0))
            for col in brier_cols
        },
        "windows": rows,
        "training_artifact": str(config.PITCHER_TRAINING_PATH),
        "training_artifact_sha256": _sha256(config.PITCHER_TRAINING_PATH),
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in summary if k != "windows"}, indent=2))
    print(f"Wrote {outer_path}")
    print(f"Wrote {pred_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--feature-set",
        default="production",
        help="k-rate feature registry (default: production).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override.",
    )
    parser.add_argument(
        "--tune-alpha",
        action="store_true",
        default=True,
        help="Select Ridge alpha on each window's chrono val (default: on).",
    )
    parser.add_argument(
        "--fixed-alpha",
        action="store_true",
        help="Use 11.A alpha ≈ 123 instead of per-window search.",
    )
    args = parser.parse_args()
    main(
        dry_run=args.dry_run,
        tune_alpha=not args.fixed_alpha,
        feature_set=args.feature_set,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
