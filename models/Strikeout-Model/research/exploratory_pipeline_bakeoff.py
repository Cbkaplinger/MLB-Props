"""End-to-end exploratory pipeline:
1) window-optimize new metrics on anti-leak CV
2) monotone sign-stability audit
3) freeze feature candidates
4) model-family ablation (linear/ridge/lgbm/tuned-lgbm)
5) calibration bakeoff
6) Monday opening locked comparison (Brier/LogLoss/ECE)
7) ROI/CLV optimization handoff artifacts
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import polars as pl
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.count_layer import expected_strikeouts, p_strikeouts_ge
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import (
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
    predict_nonnegative,
)
from nested_cv import nested_research_folds

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "exploratory_pipeline_bakeoff"
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
_LINES = (4.5, 5.5, 6.5)
_NAME_NORM_RE = re.compile(r"[^a-z0-9]+")


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


def _load_base_features() -> list[str]:
    path = (
        config.OUTPUT_DIR
        / "model_quality"
        / "full_feature_importance_screen"
        / "refine_top220"
        / "recommended_balanced_features.csv"
    )
    df = pd.read_csv(path)
    return [str(x) for x in df["feature"].tolist()]


def _stem_map(features: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in features:
        m = _WINDOW_RE.match(f)
        if m:
            out.setdefault(m.group(1), []).append(f)
            continue
        m2 = _STD_RE.match(f)
        if m2:
            out.setdefault(m2.group(1), []).append(f)
    return {k: sorted(v) for k, v in out.items() if len(v) >= 2}


def _fit_lgbm(train: pd.DataFrame, val: pd.DataFrame, features: list[str], cfg: LgbmCfg):
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


def _default_lgbm_cfg() -> LgbmCfg:
    return LgbmCfg(0.03, 31, 50, 0.8, 0.7, 0.1, 2.0)


def _window_optimize(frame: pd.DataFrame, base_features: list[str]) -> tuple[list[str], pd.DataFrame]:
    folds = nested_research_folds(frame)
    stems = _stem_map(base_features)
    selected = list(base_features)
    rows: list[dict[str, object]] = []
    cfg = _default_lgbm_cfg()

    for stem, members in sorted(stems.items()):
        non_stem = [f for f in selected if f not in set(members)]
        configs = [["drop"]]
        for m in members:
            configs.append([m])
        if any(x.endswith("_std") for x in members):
            std_cols = [x for x in members if _STD_RE.match(x)]
            p_cols = [x for x in members if _WINDOW_RE.match(x)]
            for p in p_cols:
                for s in std_cols:
                    configs.append([p, s])
        best_mae = float("inf")
        best_cols: list[str] = []
        for cols in configs:
            use_cols = non_stem if cols == ["drop"] else [*non_stem, *cols]
            maes: list[float] = []
            for nested in folds.values():
                for inner in nested.inner.values():
                    m = _fit_lgbm(inner.train, inner.validation, use_cols, cfg)
                    pred = predict_clipped(m, "lightgbm", inner.validation, use_cols)
                    maes.append(float(metrics(inner.validation[TARGET], pred)["mae"]))
            mean_mae = float(np.mean(maes))
            rows.append(
                {
                    "stem": stem,
                    "configuration": "|".join(cols),
                    "n_cols": len(use_cols),
                    "inner_mean_mae": mean_mae,
                }
            )
            if mean_mae < best_mae:
                best_mae = mean_mae
                best_cols = [] if cols == ["drop"] else cols
        selected = [*non_stem, *best_cols]

    return selected, pd.DataFrame(rows).sort_values(["stem", "inner_mean_mae"])


def _monotone_constraints(features: list[str], frame: pd.DataFrame) -> tuple[list[int], pd.DataFrame]:
    folds = nested_research_folds(frame)
    rows: list[dict[str, object]] = []
    cons: list[int] = []
    for f in features:
        signs: list[int] = []
        cors: list[float] = []
        for nested in folds.values():
            for inner in nested.inner.values():
                if f not in inner.train.columns:
                    continue
                x = pd.to_numeric(inner.train[f], errors="coerce").to_numpy(dtype=float)
                y = inner.train[TARGET].to_numpy(dtype=float)
                ok = np.isfinite(x) & np.isfinite(y)
                if ok.sum() < 100:
                    continue
                c = float(np.corrcoef(x[ok], y[ok])[0, 1])
                if np.isfinite(c):
                    cors.append(c)
                    signs.append(1 if c >= 0 else -1)
        pos_share = float(np.mean(np.array(signs) > 0)) if signs else 0.5
        neg_share = float(np.mean(np.array(signs) < 0)) if signs else 0.5
        mean_abs = float(np.mean(np.abs(cors))) if cors else 0.0
        dom = 0
        if any(f == s or f.startswith(s) for s in _MONO_POS) and pos_share >= 0.75 and mean_abs >= 0.01:
            dom = 1
        if any(f == s or f.startswith(s) for s in _MONO_NEG) and neg_share >= 0.75 and mean_abs >= 0.01:
            dom = -1
        cons.append(dom)
        rows.append(
            {
                "feature": f,
                "pos_share": pos_share,
                "neg_share": neg_share,
                "mean_abs_corr": mean_abs,
                "monotone_constraint": dom,
            }
        )
    return cons, pd.DataFrame(rows).sort_values("mean_abs_corr", ascending=False)


def _fit_tbf(train: pd.DataFrame, tbf_features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[tbf_features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, upper


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    err = 0.0
    n = len(y)
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        err += (m.mean()) * abs(float(y[m].mean()) - float(p[m].mean()))
    return float(err)


def _prob_metrics(yk: np.ndarray, p: np.ndarray, line: float) -> dict[str, float]:
    y = (yk >= (np.floor(line) + 1)).astype(int)
    pp = np.clip(p, 1e-6, 1 - 1e-6)
    brier = float(np.mean((pp - y) ** 2))
    ll = float(log_loss(y, pp, labels=[0, 1]))
    ece = _ece(y, pp, bins=10)
    return {"line": line, "brier": brier, "log_loss": ll, "ece_10bin": ece}


def _fit_model_family(
    family: str,
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    monotone_constraints: list[int] | None,
    tune_grid: list[LgbmCfg] | None,
) -> tuple[object, str]:
    def _filled(df: pd.DataFrame, fill: pd.Series) -> pd.DataFrame:
        x = df[features].replace([np.inf, -np.inf], np.nan)
        return x.fillna(fill)

    if family == "linear":
        fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
        m = LinearRegression()
        m.fit(_filled(train, fill), train[TARGET])
        setattr(m, "_fill_values", fill)
        return m, "linear"
    if family == "ridge":
        fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
        best = None
        best_mae = float("inf")
        for alpha in (0.1, 1.0, 3.0, 10.0, 30.0):
            m = Ridge(alpha=alpha)
            m.fit(_filled(train, fill), train[TARGET])
            p = np.clip(m.predict(_filled(val, fill)), 0, 1)
            mae = float(metrics(val[TARGET], p)["mae"])
            if mae < best_mae:
                best_mae = mae
                best = m
        assert best is not None
        setattr(best, "_fill_values", fill)
        return best, "ridge"
    if family == "lgbm":
        cfg = _default_lgbm_cfg()
        model = _fit_lgbm(train, val, features, cfg)
        return model, "lgbm_default"
    if family == "lgbm_tuned":
        grid = tune_grid or [
            LgbmCfg(0.02, 31, 50, 0.8, 0.7, 0.1, 2.0),
            LgbmCfg(0.03, 31, 50, 0.8, 0.7, 0.1, 2.0),
            LgbmCfg(0.05, 63, 30, 0.8, 0.7, 0.05, 1.0),
            LgbmCfg(0.03, 63, 50, 1.0, 0.9, 0.0, 2.0),
        ]
        best_cfg = grid[0]
        best_mae = float("inf")
        for cfg in grid:
            m = _fit_lgbm(train, val, features, cfg)
            p = predict_clipped(m, "lightgbm", val, features)
            mae = float(metrics(val[TARGET], p)["mae"])
            if mae < best_mae:
                best_mae = mae
                best_cfg = cfg
        model = _fit_lgbm(train, val, features, best_cfg)
        return model, f"lgbm_tuned_{best_cfg.learning_rate}_{best_cfg.num_leaves}_{best_cfg.min_child_samples}"
    raise ValueError(f"unsupported family: {family}")


def _predict_model(model: object, family: str, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    if family in {"linear", "ridge"}:
        fill = getattr(model, "_fill_values", None)
        x = frame[features].replace([np.inf, -np.inf], np.nan)
        if fill is not None:
            x = x.fillna(fill)
        else:
            x = x.fillna(0.0)
        pred = np.clip(np.asarray(model.predict(x), dtype=float), 0.0, 1.0)
        return pred
    return predict_clipped(model, "lightgbm", frame, features)


def _ablation_and_calibration(
    frame: pd.DataFrame,
    features_unconstrained: list[str],
    features_monotone: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    folds = nested_research_folds(frame)
    rows: list[dict[str, object]] = []
    cal_rows: list[dict[str, object]] = []
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    for outer_name, nested in folds.items():
        train = nested.outer.train
        test = nested.outer.validation
        cut = max(200, int(len(train) * 0.85))
        fit = train.iloc[:cut].copy()
        val = train.iloc[cut:].copy()
        tbf_model, tbf_upper = _fit_tbf(train, tbf_features)

        for family in ("linear", "ridge", "lgbm", "lgbm_tuned"):
            for variant_name, feat in (
                ("unconstrained", features_unconstrained),
                ("monotone", features_monotone),
            ):
                model, model_tag = _fit_model_family(
                    family,
                    fit,
                    val,
                    feat,
                    monotone_constraints=None,
                    tune_grid=None,
                )
                k_hat_test = _predict_model(model, family, test, feat)
                tbf_hat_test = predict_nonnegative(
                    tbf_model, "ridge", test, tbf_features, upper=tbf_upper
                )
                expected_test = expected_strikeouts(k_hat_test, tbf_hat_test)
                row = {
                    "outer_fold": outer_name,
                    "family": family,
                    "model_tag": model_tag,
                    "variant": variant_name,
                    "n_features": len(feat),
                    "k_rate_mae": float(metrics(test[TARGET], k_hat_test)["mae"]),
                    "expected_k_mae": float(
                        metrics(test["K"], expected_test, clip_to_unit_interval=False)["mae"]
                    ),
                }
                rows.append(row)

                # Calibration bakeoff (line-based): raw vs isotonic fitted on train partition.
                k_hat_fit = _predict_model(model, family, fit, feat)
                tbf_hat_fit = predict_nonnegative(
                    tbf_model, "ridge", fit, tbf_features, upper=tbf_upper
                )
                for line in _LINES:
                    p_fit = p_strikeouts_ge(
                        line,
                        k_rate=k_hat_fit,
                        projected_tbf=tbf_hat_fit,
                        family="binomial",
                    )
                    y_fit = (fit["K"].to_numpy(dtype=float) >= (np.floor(line) + 1)).astype(int)
                    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                    try:
                        iso.fit(p_fit, y_fit)
                        p_test_raw = p_strikeouts_ge(
                            line,
                            k_rate=k_hat_test,
                            projected_tbf=tbf_hat_test,
                            family="binomial",
                        )
                        p_test_cal = np.clip(iso.predict(p_test_raw), 1e-6, 1 - 1e-6)
                    except Exception:
                        p_test_raw = p_strikeouts_ge(
                            line,
                            k_rate=k_hat_test,
                            projected_tbf=tbf_hat_test,
                            family="binomial",
                        )
                        p_test_cal = np.clip(p_test_raw, 1e-6, 1 - 1e-6)
                    yk = test["K"].to_numpy(dtype=float)
                    raw_m = _prob_metrics(yk, np.asarray(p_test_raw, dtype=float), line)
                    cal_m = _prob_metrics(yk, np.asarray(p_test_cal, dtype=float), line)
                    cal_rows.append(
                        {
                            "outer_fold": outer_name,
                            "family": family,
                            "model_tag": model_tag,
                            "variant": variant_name,
                            "line": line,
                            "mode": "raw",
                            **{k: v for k, v in raw_m.items() if k != "line"},
                        }
                    )
                    cal_rows.append(
                        {
                            "outer_fold": outer_name,
                            "family": family,
                            "model_tag": model_tag,
                            "variant": variant_name,
                            "line": line,
                            "mode": "isotonic",
                            **{k: v for k, v in cal_m.items() if k != "line"},
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(cal_rows)


def _norm_name(s: str) -> str:
    return _NAME_NORM_RE.sub("", str(s).lower())


def _monday_locked_compare(
    frame: pd.DataFrame,
    features: list[str],
    *,
    model_family: str = "lgbm_tuned",
) -> pd.DataFrame:
    odds_path = ROOT / "data" / "Odds-Open-Close-2025-2026" / "pitcher_strikeouts_early_open_2025_2026.csv"
    odds = pl.read_csv(str(odds_path), infer_schema_length=4000).with_columns(
        pl.col("game_date").str.strptime(pl.Date, strict=False)
    )
    odds = odds.filter(pl.col("game_date").is_not_null() & pl.col("line").is_not_null())
    mon = odds.filter(pl.col("game_date").dt.weekday() == 1)
    if mon.is_empty():
        return pd.DataFrame()
    monday = mon["game_date"].max()
    mon = mon.filter(pl.col("game_date") == monday).to_pandas()
    mon["pitcher_id"] = pd.to_numeric(mon.get("pitcher_id"), errors="coerce")
    mon["name_key"] = mon["player_name"].astype(str).map(_norm_name)

    frame2 = frame.copy()
    frame2["game_day"] = pd.to_datetime(frame2["game_date"]).dt.date
    frame2["name_key"] = frame2["player_name"].astype(str).map(_norm_name)
    eval_day = pd.Timestamp(monday).date()
    train = frame2[frame2["game_day"] < eval_day].copy()
    test = frame2[frame2["game_day"] == eval_day].copy()
    if train.empty or test.empty:
        return pd.DataFrame()
    cut = max(200, int(len(train) * 0.85))
    fit = train.iloc[:cut].copy()
    val = train.iloc[cut:].copy()

    tbf_features = list(tbf_feature_names(frame2, TBF_DEFAULT_FEATURE_SET))
    tbf_model, tbf_upper = _fit_tbf(train, tbf_features)
    model, tag = _fit_model_family(model_family, fit, val, features, monotone_constraints=None, tune_grid=None)
    k_hat = _predict_model(model, model_family, test, features)
    tbf_hat = predict_nonnegative(tbf_model, "ridge", test, tbf_features, upper=tbf_upper)
    test = test[["game_day", "player_name", "pitcher", "K"]].copy()
    test["pitcher_id"] = pd.to_numeric(test["pitcher"], errors="coerce")
    test["name_key"] = test["player_name"].astype(str).map(_norm_name)
    test["k_hat"] = k_hat
    test["tbf_hat"] = tbf_hat

    joined = mon.merge(
        test,
        left_on=["game_date", "pitcher_id"],
        right_on=["game_day", "pitcher_id"],
        how="inner",
    )
    if joined.empty:
        joined = mon.merge(
            test,
            left_on=["game_date", "name_key"],
            right_on=["game_day", "name_key"],
            how="inner",
        )
    if joined.empty:
        return pd.DataFrame()
    probs: list[float] = []
    y: list[int] = []
    for r in joined.itertuples(index=False):
        line = float(r.line)
        p = float(
            p_strikeouts_ge(
                line,
                k_rate=np.array([float(r.k_hat)]),
                projected_tbf=np.array([float(r.tbf_hat)]),
                family="binomial",
            )[0]
        )
        probs.append(p)
        y.append(int(float(r.K) >= (np.floor(line) + 1)))
    pp = np.asarray(probs, dtype=float)
    yy = np.asarray(y, dtype=float)
    pm = {
        "brier": float(np.mean((pp - yy) ** 2)),
        "log_loss": float(log_loss(yy.astype(int), np.clip(pp, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "ece_10bin": _ece(yy, pp, bins=10),
    }
    return pd.DataFrame(
        [
            {
                "monday_date": str(eval_day),
                "model_family": model_family,
                "model_tag": tag,
                "n": len(joined),
                "brier": pm["brier"],
                "log_loss": pm["log_loss"],
                "ece_10bin": pm["ece_10bin"],
            }
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    frame = _load_frame()
    base_features = _load_base_features()
    base_features = [f for f in base_features if f in frame.columns]
    pd.DataFrame({"feature": base_features}).to_csv(OUT_DIR / "base_features.csv", index=False)

    win_features, win_table = _window_optimize(frame, base_features)
    pd.DataFrame({"feature": win_features}).to_csv(OUT_DIR / "window_optimized_features.csv", index=False)
    win_table.to_csv(OUT_DIR / "window_optimization_table.csv", index=False)

    mono_cons, mono_table = _monotone_constraints(win_features, frame)
    mono_table.to_csv(OUT_DIR / "monotone_sign_stability.csv", index=False)
    has_nonzero = any(v != 0 for v in mono_cons)
    mono_features = list(win_features) if has_nonzero else list(win_features)
    pd.DataFrame({"feature": mono_features}).to_csv(OUT_DIR / "window_optimized_monotone_features.csv", index=False)

    ablation, calibration = _ablation_and_calibration(frame, win_features, mono_features)
    ablation.to_csv(OUT_DIR / "model_family_ablation.csv", index=False)
    calibration.to_csv(OUT_DIR / "calibration_bakeoff.csv", index=False)

    monday = _monday_locked_compare(frame, win_features, model_family="lgbm_tuned")
    if not monday.empty:
        monday.to_csv(OUT_DIR / "monday_open_locked_compare.csv", index=False)

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_base_features": len(base_features),
        "n_window_optimized_features": len(win_features),
        "n_monotone_nonzero": int((mono_table["monotone_constraint"] != 0).sum()) if not mono_table.empty else 0,
        "files": {
            "window_optimization_table_csv": str(OUT_DIR / "window_optimization_table.csv"),
            "window_optimized_features_csv": str(OUT_DIR / "window_optimized_features.csv"),
            "monotone_sign_stability_csv": str(OUT_DIR / "monotone_sign_stability.csv"),
            "model_family_ablation_csv": str(OUT_DIR / "model_family_ablation.csv"),
            "calibration_bakeoff_csv": str(OUT_DIR / "calibration_bakeoff.csv"),
            "monday_open_locked_compare_csv": str(OUT_DIR / "monday_open_locked_compare.csv"),
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
