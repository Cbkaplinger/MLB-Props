"""Full feature-universe screening with grouped/conditional permutation + stability.

Outputs:
- artifacts/model_quality/full_feature_importance_screen/feature_scores.csv
- artifacts/model_quality/full_feature_importance_screen/group_scores.csv
- artifacts/model_quality/full_feature_importance_screen/stability_selection.csv
- artifacts/model_quality/full_feature_importance_screen/sage_scores.csv (optional)
- artifacts/model_quality/full_feature_importance_screen/summary.json
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

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.features import TARGET, model_feature_names
from Python.registries import FEATURE_SETS, resolve_feature_names
from Python.training import build_model, fit_regressor, lightgbm_matrix, metrics, predict_clipped
from nested_cv import nested_research_folds

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "full_feature_importance_screen"
SEED = 19
_WINDOW_SUFFIX_RE = re.compile(r"(.+)_(P3|P5|P7|P10|P14|P20|std)$")
_EXCLUDE_SETS = {"production_plus_discipline"}  # alias of production

BASE_PARAMS = {
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 2.0,
    "seed": SEED,
    "feature_fraction_seed": SEED,
    "bagging_seed": SEED,
    "data_random_seed": SEED,
    "objective": "regression",
}


@dataclass(frozen=True)
class ScreenConfig:
    correlation_threshold: float
    quantile_bins: int
    stability_runs: int
    stability_top_k: int
    enable_sage: bool
    sage_max_features: int
    max_features: int
    max_inner_folds: int
    derive_base_features: bool
    derive_include_three_way: bool
    feature_offset: int
    chunk_size: int
    anchor_feature_set: str
    derived_corr_quantile: float
    output_tag: str
    feature_list_csv: str


def _fit_lgbm(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    params = dict(BASE_PARAMS)
    if float(params.get("subsample", 1.0)) < 1.0:
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


def _eligible_feature_sets() -> tuple[str, ...]:
    out: list[str] = []
    for name in FEATURE_SETS:
        if name in _EXCLUDE_SETS:
            continue
        if name.startswith("step") or name in {"pre_freeze_248", "ridge_vif"}:
            continue
        out.append(name)
    return tuple(out)


def _build_feature_universe(frame: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    rows: list[dict[str, object]] = []
    members: dict[str, set[str]] = {}
    for feature_set in _eligible_feature_sets():
        try:
            names = list(resolve_feature_names(frame, feature_set))
        except Exception:
            continue
        for feature in names:
            if feature not in frame.columns:
                continue
            members.setdefault(feature, set()).add(feature_set)
    for feature, sets in members.items():
        m = _WINDOW_SUFFIX_RE.match(feature)
        rows.append(
            {
                "feature": feature,
                "n_source_sets": len(sets),
                "source_sets": "|".join(sorted(sets)),
                "window_stem": m.group(1) if m else "",
                "window_suffix": m.group(2) if m else "",
            }
        )
    catalog = pd.DataFrame(rows).sort_values(["n_source_sets", "feature"], ascending=[False, True])
    return catalog["feature"].tolist(), catalog


def _feature_family(name: str) -> str:
    if name.startswith("opp_lineup_"):
        return "lineup"
    if name.startswith(("ff_", "si_", "ch_", "cu_", "sl_", "fc_", "kc_", "sv_", "st_")):
        return "pitch_shape"
    if name in {"is_home", "park_k_factor", "days_rest", "days_rest_capped", "rest_gap_severity", "rest_is_long_gap"}:
        return "context"
    if "interaction" in name or "_minus_" in name or "_over_" in name:
        return "interaction_base"
    if name.startswith(("k_rate_", "swstr_rate_", "whiff_rate_", "zone_rate_", "chase_rate_", "xwOBA_", "xBA_")):
        return "pitch_results"
    return "other"


def _derive_candidate_pairs(
    frame: pd.DataFrame,
    features: list[str],
    *,
    min_abs_corr: float = 0.02,
    max_abs_corr: float = 0.98,
) -> list[tuple[str, str]]:
    fam = {f: _feature_family(f) for f in features}
    corr = frame[features].corr(numeric_only=True).abs().fillna(0.0)
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(features):
        fa = fam[a]
        vals = corr.iloc[i].to_numpy(dtype=float)
        for j, b in enumerate(features[i + 1 :], start=i + 1):
            fb = fam[b]
            c = vals[j]
            if not np.isfinite(c) or c < min_abs_corr or c > max_abs_corr:
                continue
            if fa == "context" and fb == "context":
                continue
            if fa == "other" and fb == "other":
                continue
            if {fa, fb} & {"lineup", "pitch_shape", "pitch_results", "interaction_base"}:
                pairs.append((a, b))
    return pairs


def _safe_ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    denom = b.to_numpy(dtype=float)
    out = np.full_like(denom, np.nan, dtype=float)
    num = a.to_numpy(dtype=float)
    ok = np.isfinite(denom) & (np.abs(denom) > 1e-9) & np.isfinite(num)
    out[ok] = num[ok] / denom[ok]
    return pd.Series(out, index=a.index)


def _screen_derived_series(
    frame: pd.DataFrame,
    *,
    name: str,
    values: pd.Series,
    parent_a: str,
    parent_b: str,
    parent_c: str = "",
) -> dict[str, object] | None:
    arr = pd.to_numeric(values, errors="coerce")
    finite_share = float(np.isfinite(arr.to_numpy(dtype=float)).mean())
    if finite_share < 0.995:
        return None
    std = float(np.nanstd(arr.to_numpy(dtype=float)))
    if not np.isfinite(std) or std <= 1e-6:
        return None
    y = frame[TARGET].to_numpy(dtype=float)
    x = arr.to_numpy(dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 100:
        return None
    corr_target = float(np.corrcoef(x[ok], y[ok])[0, 1]) if ok.sum() > 1 else 0.0
    if not np.isfinite(corr_target) or abs(corr_target) < 0.005:
        return None
    pa = frame[parent_a].to_numpy(dtype=float)
    pb = frame[parent_b].to_numpy(dtype=float)
    ok_a = np.isfinite(x) & np.isfinite(pa)
    ok_b = np.isfinite(x) & np.isfinite(pb)
    corr_a = float(np.corrcoef(x[ok_a], pa[ok_a])[0, 1]) if ok_a.sum() > 1 else 0.0
    corr_b = float(np.corrcoef(x[ok_b], pb[ok_b])[0, 1]) if ok_b.sum() > 1 else 0.0
    if any(np.isfinite(c) and abs(c) >= 0.995 for c in (corr_a, corr_b)):
        return None
    return {
        "feature": name,
        "n_source_sets": 0,
        "source_sets": "derived_base",
        "window_stem": "",
        "window_suffix": "",
        "derived": True,
        "derived_family": "base_exhaustive",
        "parent_a": parent_a,
        "parent_b": parent_b,
        "parent_c": parent_c,
        "corr_target": corr_target,
        "finite_share": finite_share,
    }


def _augment_with_derived_base_features(
    frame: pd.DataFrame,
    *,
    include_three_way: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pool = list(model_feature_names(frame, include_experimental=True))
    pool = [f for f in pool if f in frame.columns]
    numeric_pool = []
    for f in pool:
        col = frame[f]
        if pd.api.types.is_numeric_dtype(col) or pd.api.types.is_bool_dtype(col):
            numeric_pool.append(f)
    pairs = _derive_candidate_pairs(frame, numeric_pool)
    added_rows: list[dict[str, object]] = []
    added_names: set[str] = set()
    new_cols: dict[str, pd.Series] = {}
    contexts = [c for c in ("is_home", "park_k_factor", "days_rest_capped", "rest_gap_severity") if c in frame.columns]

    for a, b in pairs:
        a_s = pd.to_numeric(frame[a], errors="coerce")
        b_s = pd.to_numeric(frame[b], errors="coerce")
        forms: list[tuple[str, pd.Series]] = [
            (f"drv_mul__{a}__{b}", a_s * b_s),
            (f"drv_sub__{a}__{b}", a_s - b_s),
            (f"drv_sub__{b}__{a}", b_s - a_s),
            (f"drv_rat__{a}__{b}", _safe_ratio(a_s, b_s)),
            (f"drv_rat__{b}__{a}", _safe_ratio(b_s, a_s)),
        ]
        for name, series in forms:
            if name in added_names or name in frame.columns:
                continue
            row = _screen_derived_series(frame, name=name, values=series, parent_a=a, parent_b=b)
            if row is None:
                continue
            new_cols[name] = pd.to_numeric(series, errors="coerce")
            added_names.add(name)
            added_rows.append(row)

            if include_three_way and contexts and (_feature_family(a) != "context" and _feature_family(b) != "context"):
                for ctx in contexts:
                    ctx_s = pd.to_numeric(frame[ctx], errors="coerce")
                    n3 = f"drv_tri__{a}__{b}__{ctx}"
                    if n3 in added_names or n3 in frame.columns:
                        continue
                    tri = series * ctx_s
                    row3 = _screen_derived_series(
                        frame,
                        name=n3,
                        values=tri,
                        parent_a=a,
                        parent_b=b,
                        parent_c=ctx,
                    )
                    if row3 is None:
                        continue
                    new_cols[n3] = pd.to_numeric(tri, errors="coerce")
                    added_names.add(n3)
                    added_rows.append(row3)

    out = pd.DataFrame(added_rows)
    if new_cols:
        frame = pd.concat([frame, pd.DataFrame(new_cols, index=frame.index)], axis=1)
    if out.empty:
        return frame, out
    out = out.sort_values(["corr_target", "finite_share", "feature"], ascending=[False, False, True])
    return frame, out


def _window_groups(features: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for feature in features:
        m = _WINDOW_SUFFIX_RE.match(feature)
        if m:
            groups.setdefault(f"stem::{m.group(1)}", []).append(feature)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def _corr_groups(
    train: pd.DataFrame,
    features: list[str],
    *,
    threshold: float,
) -> dict[str, list[str]]:
    corr = train[features].corr(numeric_only=True).abs().fillna(0.0)
    parent = {f: f for f in features}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(features):
        vals = corr.iloc[i].to_numpy(dtype=float)
        for j in range(i + 1, len(features)):
            if vals[j] >= threshold:
                union(a, features[j])

    clusters: dict[str, list[str]] = {}
    for f in features:
        clusters.setdefault(find(f), []).append(f)
    out: dict[str, list[str]] = {}
    idx = 0
    for cols in clusters.values():
        if len(cols) >= 2:
            out[f"corr::{idx:04d}"] = sorted(cols)
            idx += 1
    return out


def _conditional_permute_series(
    values: pd.Series,
    conditioner: pd.Series,
    *,
    bins: int,
    rng: np.random.Generator,
) -> pd.Series:
    out = values.copy()
    if conditioner.nunique(dropna=True) < 3:
        vals = out.to_numpy(copy=True)
        rng.shuffle(vals)
        return pd.Series(vals, index=out.index)
    codes = pd.qcut(conditioner, q=max(2, bins), labels=False, duplicates="drop")
    for code in pd.Series(codes).dropna().unique():
        idx = out.index[codes == code]
        if len(idx) <= 1:
            continue
        vals = out.loc[idx].to_numpy(copy=True)
        rng.shuffle(vals)
        out.loc[idx] = vals
    return out


def _best_conditioner(
    train: pd.DataFrame,
    *,
    feature: str,
    features: list[str],
) -> str | None:
    others = [f for f in features if f != feature]
    if not others:
        return None
    corr = (
        train[others + [feature]]
        .corr(numeric_only=True)[feature]
        .drop(labels=[feature])
        .abs()
        .dropna()
    )
    if corr.empty:
        return None
    return str(corr.idxmax())


def _stability_selection(
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    runs: int,
    top_k: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    counts = {f: 0 for f in features}
    n = len(train)
    take = max(200, int(0.5 * n))
    for _ in range(runs):
        idx = rng.choice(n, size=take, replace=False)
        sub = train.iloc[np.sort(idx)].copy()
        cut = max(100, int(0.85 * len(sub)))
        fit = sub.iloc[:cut]
        hold = sub.iloc[cut:]
        if fit.empty or hold.empty:
            continue
        model = _fit_lgbm(fit, hold, features)
        gain = model.booster_.feature_importance(importance_type="gain")
        order = np.argsort(-gain)
        for j in order[: min(top_k, len(features))]:
            counts[features[int(j)]] += 1
    denom = max(1, runs)
    return {f: counts[f] / denom for f in features}


def _run_fold(
    *,
    outer_name: str,
    inner_name: str,
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    cfg: ScreenConfig,
    seed_offset: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    model = _fit_lgbm(train, val, features)
    y = val[TARGET].to_numpy(dtype=float)
    base_pred = predict_clipped(model, "lightgbm", val, features)
    base_mae = float(metrics(y, base_pred)["mae"])
    rng = np.random.default_rng(SEED + seed_offset)

    corr_groups = _corr_groups(train, features, threshold=cfg.correlation_threshold)
    grouped = _window_groups(features)
    for g, cols in corr_groups.items():
        grouped.setdefault(g, cols)

    feature_rows: list[dict[str, object]] = []
    for feature in features:
        permuted = val.copy()
        mate = _best_conditioner(train, feature=feature, features=features)
        if mate is None or mate not in permuted.columns:
            vals = permuted[feature].to_numpy(copy=True)
            rng.shuffle(vals)
            permuted[feature] = vals
        else:
            permuted[feature] = _conditional_permute_series(
                permuted[feature],
                permuted[mate],
                bins=cfg.quantile_bins,
                rng=rng,
            )
        pred = predict_clipped(model, "lightgbm", permuted, features)
        mae = float(metrics(y, pred)["mae"])
        feature_rows.append(
            {
                "outer_fold": outer_name,
                "inner_fold": inner_name,
                "feature": feature,
                "base_mae": base_mae,
                "conditional_perm_mae": mae,
                "delta_mae": mae - base_mae,
                "conditioner_feature": mate if mate is not None else "",
            }
        )

    group_rows: list[dict[str, object]] = []
    for group_name, cols in grouped.items():
        perm = val.copy()
        order = perm.index.to_numpy(copy=True)
        rng.shuffle(order)
        perm.loc[:, cols] = perm.loc[order, cols].to_numpy()
        pred = predict_clipped(model, "lightgbm", perm, features)
        mae = float(metrics(y, pred)["mae"])
        group_rows.append(
            {
                "outer_fold": outer_name,
                "inner_fold": inner_name,
                "group": group_name,
                "n_features": len(cols),
                "group_features": "|".join(cols),
                "base_mae": base_mae,
                "group_perm_mae": mae,
                "delta_mae": mae - base_mae,
            }
        )

    stability = _stability_selection(
        train,
        val,
        features,
        runs=cfg.stability_runs,
        top_k=cfg.stability_top_k,
        rng=rng,
    )
    stability_rows = [
        {
            "outer_fold": outer_name,
            "inner_fold": inner_name,
            "feature": f,
            "selection_probability": p,
        }
        for f, p in stability.items()
    ]
    return feature_rows, group_rows, stability_rows


def _optional_sage(
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    max_features: int,
) -> pd.DataFrame:
    try:
        import sage  # type: ignore
    except Exception:
        return pd.DataFrame()
    subset = features[: max_features]
    model = _fit_lgbm(train, val, subset)
    X_bg = train[subset].to_numpy(dtype=float)
    X_val = val[subset].to_numpy(dtype=float)
    y_val = val[TARGET].to_numpy(dtype=float)
    estimator = sage.MarginalImputer(model.predict, X_bg)
    explainer = sage.PermutationEstimator(estimator, "mse")
    values = explainer(X_val, y_val)
    return pd.DataFrame(
        {
            "feature": subset,
            "sage_value": np.asarray(values.values, dtype=float),
            "sage_std": np.asarray(values.std, dtype=float),
        }
    ).sort_values("sage_value", ascending=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correlation-threshold", type=float, default=0.85)
    parser.add_argument("--quantile-bins", type=int, default=10)
    parser.add_argument("--stability-runs", type=int, default=20)
    parser.add_argument("--stability-top-k", type=int, default=72)
    parser.add_argument("--enable-sage", action="store_true")
    parser.add_argument("--sage-max-features", type=int, default=120)
    parser.add_argument("--max-features", type=int, default=0)
    parser.add_argument("--max-inner-folds", type=int, default=0)
    parser.add_argument("--derive-base-features", action="store_true")
    parser.add_argument("--derive-include-three-way", action="store_true")
    parser.add_argument("--feature-offset", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=0)
    parser.add_argument("--anchor-feature-set", default="production")
    parser.add_argument("--derived-corr-quantile", type=float, default=0.99)
    parser.add_argument("--output-tag", default="")
    parser.add_argument("--feature-list-csv", default="")
    args = parser.parse_args()
    cfg = ScreenConfig(
        correlation_threshold=float(args.correlation_threshold),
        quantile_bins=int(args.quantile_bins),
        stability_runs=int(args.stability_runs),
        stability_top_k=int(args.stability_top_k),
        enable_sage=bool(args.enable_sage),
        sage_max_features=int(args.sage_max_features),
        max_features=int(args.max_features),
        max_inner_folds=int(args.max_inner_folds),
        derive_base_features=bool(args.derive_base_features),
        derive_include_three_way=bool(args.derive_include_three_way),
        feature_offset=max(0, int(args.feature_offset)),
        chunk_size=max(0, int(args.chunk_size)),
        anchor_feature_set=str(args.anchor_feature_set),
        derived_corr_quantile=float(args.derived_corr_quantile),
        output_tag=str(args.output_tag or "").strip(),
        feature_list_csv=str(args.feature_list_csv or "").strip(),
    )

    out_dir = OUT_DIR / cfg.output_tag if cfg.output_tag else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # Use Polars for heavy data manipulation, then convert at model boundary.
    seasons = list(config.FEATURE_RESEARCH_SEASONS)
    pl_frame = (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
        .filter(pl.col(TARGET).is_not_null() & pl.col("game_date").is_not_null())
        .filter(pl.col("season").is_in(seasons))
        .sort(["game_date", "player_name"])
    )
    frame = pl_frame.to_pandas()
    frame = frame.reset_index(drop=True)

    if cfg.feature_list_csv:
        fl = pd.read_csv(cfg.feature_list_csv)
        if "feature" not in fl.columns:
            raise ValueError(f"{cfg.feature_list_csv} must contain 'feature' column")
        features = [f for f in fl["feature"].astype(str).tolist() if f in frame.columns]
        catalog = pd.DataFrame(
            {
                "feature": features,
                "n_source_sets": 0,
                "source_sets": "feature_list",
                "window_stem": "",
                "window_suffix": "",
            }
        )
    else:
        features, catalog = _build_feature_universe(frame)
    derived_catalog = pd.DataFrame()
    if cfg.derive_base_features:
        frame, derived_catalog = _augment_with_derived_base_features(
            frame,
            include_three_way=cfg.derive_include_three_way,
        )
        if not derived_catalog.empty:
            q = float(min(max(cfg.derived_corr_quantile, 0.0), 1.0))
            thresh = float(derived_catalog["corr_target"].abs().quantile(q))
            derived_catalog = derived_catalog[
                derived_catalog["corr_target"].abs() >= thresh
            ].copy()
            catalog = pd.concat([catalog, derived_catalog], ignore_index=True)
            features = [*features, *derived_catalog["feature"].astype(str).tolist()]
    if cfg.max_features > 0:
        features = features[: cfg.max_features]
        catalog = catalog[catalog["feature"].isin(features)].copy()
    features = list(dict.fromkeys(features))
    # Chunking support: evaluate a manageable slice while anchoring to a stable base set.
    anchored: list[str] = []
    try:
        anchored = list(resolve_feature_names(frame, cfg.anchor_feature_set))
    except Exception:
        anchored = []
    pool = [f for f in features if f not in set(anchored)]
    if cfg.chunk_size > 0:
        pool = pool[cfg.feature_offset : cfg.feature_offset + cfg.chunk_size]
    selected = list(dict.fromkeys([*anchored, *pool]))
    selected = [f for f in selected if f in frame.columns]
    features = selected
    # Keep only required columns to avoid fold slicing OOM.
    keep_cols = list(
        dict.fromkeys(
            ["game_date", "season", "player_name", TARGET, *features]
        )
    )
    frame = frame[[c for c in keep_cols if c in frame.columns]].copy()
    catalog.to_csv(out_dir / "feature_catalog.csv", index=False)
    folds = nested_research_folds(frame)
    feature_rows: list[dict[str, object]] = []
    group_rows: list[dict[str, object]] = []
    stability_rows: list[dict[str, object]] = []
    fold_idx = 0
    fold_cap = cfg.max_inner_folds if cfg.max_inner_folds > 0 else 10**9
    for outer_name, nested in folds.items():
        for inner_name, inner in nested.inner.items():
            if fold_idx >= fold_cap:
                break
            fr, gr, sr = _run_fold(
                outer_name=outer_name,
                inner_name=inner_name,
                train=inner.train,
                val=inner.validation,
                features=features,
                cfg=cfg,
                seed_offset=fold_idx,
            )
            feature_rows.extend(fr)
            group_rows.extend(gr)
            stability_rows.extend(sr)
            fold_idx += 1
        if fold_idx >= fold_cap:
            break

    feature_df = pd.DataFrame(feature_rows)
    group_df = pd.DataFrame(group_rows)
    stability_df = pd.DataFrame(stability_rows)

    feature_summary = (
        feature_df.groupby("feature", as_index=False)
        .agg(
            mean_delta_mae=("delta_mae", "mean"),
            std_delta_mae=("delta_mae", "std"),
            positive_share=("delta_mae", lambda s: float(np.mean(np.asarray(s) > 0.0))),
            folds=("delta_mae", "count"),
        )
        .sort_values(["mean_delta_mae", "positive_share"], ascending=[False, False])
    )
    group_summary = (
        group_df.groupby("group", as_index=False)
        .agg(
            mean_delta_mae=("delta_mae", "mean"),
            std_delta_mae=("delta_mae", "std"),
            positive_share=("delta_mae", lambda s: float(np.mean(np.asarray(s) > 0.0))),
            folds=("delta_mae", "count"),
            n_features=("n_features", "max"),
            group_features=("group_features", "first"),
        )
        .sort_values("mean_delta_mae", ascending=False)
    )
    stability_summary = (
        stability_df.groupby("feature", as_index=False)["selection_probability"]
        .mean()
        .sort_values("selection_probability", ascending=False)
    )

    feature_df.to_csv(out_dir / "feature_scores_raw.csv", index=False)
    group_df.to_csv(out_dir / "group_scores_raw.csv", index=False)
    stability_df.to_csv(out_dir / "stability_selection_raw.csv", index=False)
    feature_summary.to_csv(out_dir / "feature_scores.csv", index=False)
    group_summary.to_csv(out_dir / "group_scores.csv", index=False)
    stability_summary.to_csv(out_dir / "stability_selection.csv", index=False)
    if not derived_catalog.empty:
        derived_catalog.to_csv(out_dir / "derived_feature_catalog.csv", index=False)

    sage_path = out_dir / "sage_scores.csv"
    sage_status = "disabled"
    if cfg.enable_sage:
        outer = next(iter(folds.values())).outer
        top = feature_summary["feature"].astype(str).tolist()
        sage_df = _optional_sage(
            outer.train,
            outer.validation,
            top,
            max_features=cfg.sage_max_features,
        )
        if not sage_df.empty:
            sage_df.to_csv(sage_path, index=False)
            sage_status = "completed"
        else:
            sage_status = "unavailable"

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "n_features_universe": len(features),
        "n_feature_sets_considered": len(_eligible_feature_sets()),
        "config": {
            "correlation_threshold": cfg.correlation_threshold,
            "quantile_bins": cfg.quantile_bins,
            "stability_runs": cfg.stability_runs,
            "stability_top_k": cfg.stability_top_k,
            "enable_sage": cfg.enable_sage,
            "sage_max_features": cfg.sage_max_features,
            "max_features": cfg.max_features,
            "max_inner_folds": cfg.max_inner_folds,
            "derive_base_features": cfg.derive_base_features,
            "derive_include_three_way": cfg.derive_include_three_way,
            "feature_offset": cfg.feature_offset,
            "chunk_size": cfg.chunk_size,
            "anchor_feature_set": cfg.anchor_feature_set,
            "derived_corr_quantile": cfg.derived_corr_quantile,
            "output_tag": cfg.output_tag,
        },
        "sage_status": sage_status,
        "files": {
            "feature_catalog_csv": str(out_dir / "feature_catalog.csv"),
            "derived_feature_catalog_csv": str(out_dir / "derived_feature_catalog.csv"),
            "feature_scores_csv": str(out_dir / "feature_scores.csv"),
            "group_scores_csv": str(out_dir / "group_scores.csv"),
            "stability_selection_csv": str(out_dir / "stability_selection.csv"),
            "sage_scores_csv": str(sage_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(feature_summary.head(25).to_string(index=False))
    print("\nTop grouped deltas:")
    print(group_summary.head(25).to_string(index=False))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
