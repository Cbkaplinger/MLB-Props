"""Final feature dataset search focused on LGBM MAE minimization.

This script does NOT compare architectures. It searches feature datasets:
1) starts from broad shortlisted pool
2) sweeps candidate set sizes
3) re-optimizes windows inside each candidate
4) evaluates monotone modes
5) reports best expected_K MAE and k_rate MAE on nested folds
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.count_layer import expected_strikeouts
from Python.features import TARGET
from Python.training import build_model, fit_regressor, lightgbm_matrix, metrics, predict_clipped, predict_nonnegative
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from nested_cv import nested_research_folds

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "final_feature_dataset_search"
_WINDOW_RE = re.compile(r"^(.*)_P(\d+)$")
_STD_RE = re.compile(r"^(.*)_std(?:_shrunk)?$")
_MONO_POS = (
    "k_rate_",
    "opp_lineup_k",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
    "park_k_factor",
)
_MONO_NEG = ("opp_lineup_zcontact", "opp_lineup_bb")


@dataclass(frozen=True)
class LgbmCfg:
    learning_rate: float
    num_leaves: int
    min_child_samples: int
    subsample: float
    colsample_bytree: float
    reg_alpha: float
    reg_lambda: float


def _load_frame() -> pd.DataFrame:
    seasons = list(config.FEATURE_RESEARCH_SEASONS)
    plf = (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
        .filter(pl.col("game_date").is_not_null() & pl.col(TARGET).is_not_null())
        .filter(pl.col("season").is_in(seasons))
        .sort(["game_date", "player_name"])
    )
    return plf.to_pandas().reset_index(drop=True)


def _load_ranked_candidates(ranked_csv: str = "") -> pd.DataFrame:
    if ranked_csv:
        m = pd.read_csv(ranked_csv).copy()
        if "feature" not in m.columns:
            raise ValueError(f"ranked csv missing 'feature' column: {ranked_csv}")
        if "score" in m.columns:
            m["score"] = pd.to_numeric(m["score"], errors="coerce").fillna(0.0)
        elif "global_score" in m.columns:
            m["score"] = pd.to_numeric(m["global_score"], errors="coerce").fillna(0.0)
        else:
            mean_col = "mean_delta_mae" if "mean_delta_mae" in m.columns else None
            pos_col = "positive_share" if "positive_share" in m.columns else None
            stab_col = "selection_probability" if "selection_probability" in m.columns else None
            base = pd.to_numeric(m[mean_col], errors="coerce").fillna(0.0) if mean_col else 0.0
            pos = pd.to_numeric(m[pos_col], errors="coerce").fillna(0.0) if pos_col else 0.0
            stab = pd.to_numeric(m[stab_col], errors="coerce").fillna(0.0) if stab_col else 0.0
            m["score"] = base + 2e-5 * pos + 1e-5 * stab
        return m.sort_values("score", ascending=False).reset_index(drop=True)

    p = (
        config.OUTPUT_DIR
        / "model_quality"
        / "full_feature_importance_screen"
        / "refine_top220"
        / "feature_scores.csv"
    )
    s = (
        config.OUTPUT_DIR
        / "model_quality"
        / "full_feature_importance_screen"
        / "refine_top220"
        / "stability_selection.csv"
    )
    f = pd.read_csv(p)
    st = pd.read_csv(s)
    m = f.merge(st, on="feature", how="left")
    m["selection_probability"] = m["selection_probability"].fillna(0.0)
    m["score"] = (
        m["mean_delta_mae"].astype(float)
        + 2e-5 * m["positive_share"].astype(float)
        + 1e-5 * m["selection_probability"].astype(float)
    )
    return m.sort_values("score", ascending=False).reset_index(drop=True)


def _stem(feature: str) -> str:
    m = _WINDOW_RE.match(feature)
    if m:
        return m.group(1)
    m2 = _STD_RE.match(feature)
    if m2:
        return m2.group(1)
    return feature


def _window_optimize(frame: pd.DataFrame, features: list[str], cfg: LgbmCfg) -> list[str]:
    folds = nested_research_folds(frame)
    stems: dict[str, list[str]] = {}
    for f in features:
        key = _stem(f)
        stems.setdefault(key, []).append(f)
    selected = list(features)
    for key, members in stems.items():
        if len(members) < 2:
            continue
        non = [f for f in selected if f not in set(members)]
        options: list[list[str]] = [[]] + [[m] for m in members]
        p_cols = [m for m in members if _WINDOW_RE.match(m)]
        s_cols = [m for m in members if _STD_RE.match(m)]
        for p in p_cols:
            for s in s_cols:
                options.append([p, s])
        best = []
        best_mae = float("inf")
        for opt in options:
            use = [*non, *opt]
            maes = []
            for nested in folds.values():
                for inner in nested.inner.values():
                    model = _fit_lgbm(inner.train, inner.validation, use, cfg, monotone="none")
                    pred = predict_clipped(model, "lightgbm", inner.validation, use)
                    maes.append(float(metrics(inner.validation[TARGET], pred)["mae"]))
            m = float(np.mean(maes))
            if m < best_mae:
                best_mae = m
                best = opt
        selected = [*non, *best]
    return list(dict.fromkeys(selected))


def _constraints(features: list[str], mode: str) -> list[int]:
    if mode == "none":
        return [0] * len(features)
    out: list[int] = []
    for f in features:
        if any(f == s or f.startswith(s) for s in _MONO_POS):
            out.append(1)
        elif mode == "refined_signed" and any(f == s or f.startswith(s) for s in _MONO_NEG):
            out.append(-1)
        else:
            out.append(0)
    return out


def _fit_lgbm(train: pd.DataFrame, val: pd.DataFrame, features: list[str], cfg: LgbmCfg, *, monotone: str):
    params = {
        "learning_rate": cfg.learning_rate,
        "num_leaves": cfg.num_leaves,
        "min_child_samples": cfg.min_child_samples,
        "subsample": cfg.subsample,
        "colsample_bytree": cfg.colsample_bytree,
        "reg_alpha": cfg.reg_alpha,
        "reg_lambda": cfg.reg_lambda,
        "objective": "regression",
        "seed": 42,
        "feature_fraction_seed": 42,
        "bagging_seed": 42,
        "data_random_seed": 42,
    }
    if cfg.subsample < 1.0:
        params["bagging_freq"] = 1
    cons = _constraints(features, monotone)
    if any(v != 0 for v in cons):
        params["monotone_constraints"] = cons
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
    fit_regressor(model, "ridge", train[tbf_features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, upper


def _eval_candidate(frame: pd.DataFrame, features: list[str], cfg: LgbmCfg, monotone: str) -> dict[str, float]:
    folds = nested_research_folds(frame)
    tbf_feats = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    k_mae = []
    ek_mae = []
    for nested in folds.values():
        train = nested.outer.train
        test = nested.outer.validation
        cut = max(200, int(len(train) * 0.85))
        fit = train.iloc[:cut]
        val = train.iloc[cut:]
        model = _fit_lgbm(fit, val, features, cfg, monotone=monotone)
        k_hat = predict_clipped(model, "lightgbm", test, features)
        tbf_model, tbf_upper = _fit_tbf(train, tbf_feats)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", test, tbf_feats, upper=tbf_upper)
        ek = expected_strikeouts(k_hat, tbf_hat)
        k_mae.append(float(metrics(test[TARGET], k_hat)["mae"]))
        ek_mae.append(float(metrics(test["K"], ek, clip_to_unit_interval=False)["mae"]))
    return {
        "k_rate_mae_mean": float(np.mean(k_mae)),
        "k_rate_mae_std": float(np.std(k_mae)),
        "expected_k_mae_mean": float(np.mean(ek_mae)),
        "expected_k_mae_std": float(np.std(ek_mae)),
    }


def _parse_sizes(raw: str, max_n: int) -> list[int]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            vals.append(int(part))
        except ValueError:
            continue
    vals = sorted(set(v for v in vals if v > 0 and v <= max_n))
    return vals


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        default="16,20,24,27,30,36,42,50,60,72,90,120,160,200",
        help="Comma-separated candidate seed sizes.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use compact LGBM grid for faster search.",
    )
    parser.add_argument(
        "--output-tag",
        default="",
        help="Optional subfolder tag under final_feature_dataset_search.",
    )
    parser.add_argument(
        "--ranked-csv",
        default="",
        help="Optional CSV with candidate features (must include 'feature').",
    )
    parser.add_argument(
        "--candidate-cap",
        type=int,
        default=0,
        help="Optional cap on ranked pool size before size sweep (0 disables).",
    )
    args = parser.parse_args()

    out_dir = OUT_DIR / args.output_tag if args.output_tag else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_frame()
    ranked = _load_ranked_candidates(args.ranked_csv)
    ranked = ranked[ranked["feature"].isin(set(frame.columns))].copy()
    if args.candidate_cap and args.candidate_cap > 0:
        ranked = ranked.head(int(args.candidate_cap)).copy()

    size_grid = _parse_sizes(args.sizes, len(ranked))
    if not size_grid:
        raise ValueError("no valid candidate sizes")
    cfg_grid = (
        [
            LgbmCfg(0.03, 31, 50, 0.8, 0.7, 0.1, 2.0),
            LgbmCfg(0.05, 63, 30, 0.8, 0.7, 0.05, 1.0),
        ]
        if args.fast
        else [
            LgbmCfg(0.02, 31, 50, 0.8, 0.7, 0.1, 2.0),
            LgbmCfg(0.03, 31, 50, 0.8, 0.7, 0.1, 2.0),
            LgbmCfg(0.05, 63, 30, 0.8, 0.7, 0.05, 1.0),
            LgbmCfg(0.03, 63, 50, 1.0, 0.9, 0.0, 2.0),
        ]
    )
    modes = ("none", "coarse_positive", "refined_signed")

    rows: list[dict[str, object]] = []
    best_features: list[str] = []
    best_row: dict[str, object] | None = None

    for k in size_grid:
        seed = ranked.head(k)["feature"].astype(str).tolist()
        # window optimize with default-mid cfg for stability
        win = _window_optimize(frame, seed, cfg_grid[1])
        for cfg in cfg_grid:
            for mode in modes:
                ev = _eval_candidate(frame, win, cfg, mode)
                row = {
                    "k_seed": k,
                    "n_features_after_window": len(win),
                    "monotone_mode": mode,
                    "learning_rate": cfg.learning_rate,
                    "num_leaves": cfg.num_leaves,
                    "min_child_samples": cfg.min_child_samples,
                    "subsample": cfg.subsample,
                    "colsample_bytree": cfg.colsample_bytree,
                    "reg_alpha": cfg.reg_alpha,
                    "reg_lambda": cfg.reg_lambda,
                    **ev,
                }
                rows.append(row)
                if best_row is None or float(row["expected_k_mae_mean"]) < float(best_row["expected_k_mae_mean"]):
                    best_row = dict(row)
                    best_features = list(win)
        print(f"done k={k}", flush=True)

    results = pd.DataFrame(rows).sort_values(
        ["expected_k_mae_mean", "k_rate_mae_mean", "expected_k_mae_std"]
    )
    results.to_csv(out_dir / "candidate_results.csv", index=False)
    pd.DataFrame({"feature": best_features}).to_csv(out_dir / "best_features.csv", index=False)
    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_ranked_pool": int(len(ranked)),
        "size_grid": size_grid,
        "fast_mode": bool(args.fast),
        "output_tag": args.output_tag,
        "best": best_row,
        "files": {
            "candidate_results_csv": str(out_dir / "candidate_results.csv"),
            "best_features_csv": str(out_dir / "best_features.csv"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(results.head(20).to_string(index=False))
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
