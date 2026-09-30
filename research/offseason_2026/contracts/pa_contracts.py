"""Research-only PA prediction/aggregation contracts (Phase 7.5).

No production imports, no board/odds/ledger side effects, no writes.
Key-based alignment everywhere; row order is never trusted.
"""
from __future__ import annotations
import numpy as np
import polars as pl

PA_KEYS = ["game_pk", "at_bat_number", "pitcher"]
START_KEYS = ["game_pk", "pitcher"]
EPS = 1e-6


def assert_single_season(df: pl.DataFrame, season: int) -> None:
    """G1: a requested frame must contain only the declared season."""
    if "season" in df.columns:
        vals = df["season"].unique().to_list()
    else:
        vals = sorted({int(str(d)[:4]) for d in df["game_date"].to_list()})
    if vals != [season]:
        raise ValueError(
            f"SEASON_ISOLATION_VIOLATION: expected season {season}, found {vals}. "
            "Historical failure: Phase 7 mixed 2023 rows into the 2024 evaluation frame.")


def assert_unique_keys(df: pl.DataFrame, keys: list[str]) -> None:
    """G8: reject duplicate keys before prediction or aggregation."""
    n = df.height
    nu = df.select(keys).unique().height
    if nu != n:
        dups = df.group_by(keys).len().filter(pl.col("len") > 1).head(3)
        raise ValueError(
            f"DUPLICATE_KEY_VIOLATION on {keys}: {n - nu} duplicated rows. Sample:\n{dups}")


def align_predictions(pa_frame: pl.DataFrame, predictions: pl.DataFrame,
                      pred_cols: list[str], keys: list[str] = None) -> pl.DataFrame:
    """G2: key-based left alignment of predictions onto the canonical PA frame.

    Raises on duplicate prediction keys, missing prediction keys, or extra
    prediction keys. Never relies on row order.
    """
    keys = keys or PA_KEYS
    assert_unique_keys(pa_frame, keys)
    assert_unique_predictions_keys(predictions, keys)
    pa_keys = pa_frame.select(keys)
    pr_keys = predictions.select(keys)
    missing = pa_keys.join(pr_keys, on=keys, how="anti")
    if missing.height > 0:
        raise ValueError(f"MISSING_PREDICTION_KEYS: {missing.height} PA rows lack predictions. "
                         f"Sample: {missing.head(3).to_dicts()}")
    extra = pr_keys.join(pa_keys, on=keys, how="anti")
    if extra.height > 0:
        raise ValueError(f"EXTRA_PREDICTION_KEYS: {extra.height} predictions match no PA row. "
                         f"Sample: {extra.head(3).to_dicts()}")
    idx = pa_frame.with_row_index("__row")
    out = idx.join(predictions.select(keys + pred_cols), on=keys, how="left").sort("__row").drop("__row")
    if out.height != pa_frame.height:
        raise ValueError("JOIN_CARDINALITY_VIOLATION: join changed row count "
                         "(row multiplication). Historical failure: Phase 7 join reordering.")
    return out


def assert_unique_predictions_keys(predictions: pl.DataFrame, keys: list[str]) -> None:
    n = predictions.height
    nu = predictions.select(keys).unique().height
    if nu != n:
        raise ValueError(f"DUPLICATE_KEY_VIOLATION in predictions on {keys}: {n - nu} dupes")


def validate_feature_frame(df: pl.DataFrame, feature_manifest: dict) -> None:
    """Enforce exact feature order and completeness against the manifest."""
    required = feature_manifest["feature_order"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"FEATURE_SCHEMA_VIOLATION: missing features {missing}")
    extra_ok = feature_manifest.get("allow_extra_columns", True)
    if not extra_ok:
        unexpected = [c for c in df.columns if c not in required and c not in
                      feature_manifest.get("permitted_aux_columns", [])]
        if unexpected:
            raise ValueError(f"FEATURE_SCHEMA_VIOLATION: unexpected columns {unexpected}")


def predict_pa_probabilities(pa_frame: pl.DataFrame, bundle: dict,
                             as_of_policy: str = "ACTUAL_BATTER_PREGAME_FEATURES") -> pl.DataFrame:
    """Apply a stored logistic bundle (coefficients + preprocessing) to a feature frame.

    bundle keys: model_id, model_version, intercept, coefficients (dict name->float,
    ordered), feature_order, preprocessing {mean, std} per feature, clip bounds,
    baseline_column (logit offset) optional, prediction_context.
    No model fitting happens here.
    """
    if as_of_policy not in ("ACTUAL_BATTER_PREGAME_FEATURES",):
        raise NotImplementedError(f"as_of_policy {as_of_policy!r} not supported")
    fm = bundle["feature_manifest"]
    validate_feature_frame(pa_frame, fm)
    order = fm["feature_order"]
    prep = bundle["preprocessing"]
    X = np.column_stack([
        (pa_frame[c].fill_null(prep[c]["fill"]).to_numpy() - prep[c]["mean"]) / prep[c]["std"]
        for c in order])
    eta = np.full(pa_frame.height, float(bundle["intercept"]))
    for name, coef in bundle["coefficients"].items():
        if name == "__BASELINE_LOGIT__":
            eta = eta + coef * pa_frame[bundle["baseline_column"]].to_numpy()
        else:
            eta = eta + coef * X[:, order.index(name)]
    p = np.clip(1.0 / (1.0 + np.exp(-eta)), EPS, 1 - EPS)
    if not np.isfinite(p).all():
        raise ValueError("NONFINITE_PROBABILITY")
    out = pa_frame.select(PA_KEYS + ["game_date", "batter"]).with_columns(
        pl.Series("p_k", p),
        pl.lit(bundle["model_id"]).alias("model_name"),
        pl.lit(bundle["model_version"]).alias("model_version"),
        pl.lit(bundle["feature_manifest_hash"]).alias("feature_manifest_hash"),
        pl.lit(as_of_policy).alias("prediction_context"))
    return out


def aggregate_oracle_xk(pa_predictions: pl.DataFrame, start_manifest: dict,
                        mode: str = "ACTUAL_TBF_ORACLE") -> pl.DataFrame:
    """Sum PA probabilities into start-level xK. ACTUAL_TBF_ORACLE only.

    start_manifest: {"pa_counts": {(game_pk, pitcher): official_BF}, "starts": ...}
    Enforces: official-starter rows only (per manifest), no split PAs (manifest),
    exact PA-count == official BF reconciliation, keyed joins.
    """
    if mode != "ACTUAL_TBF_ORACLE":
        raise NotImplementedError(
            f"mode {mode!r} is not implemented. Only ACTUAL_TBF_ORACLE is authorized. "
            "FROZEN_POINT_TBF / TBF_SURVIVAL_WEIGHTS / TBF_MIXTURE / POISSON_BINOMIAL are "
            "declared but unapproved branches.")
    assert_unique_keys(pa_predictions, PA_KEYS)
    bf = start_manifest["official_bf"]
    g = pa_predictions.group_by(START_KEYS).agg(
        pl.len().alias("n_modeled"),
        pl.col("p_k").sum().alias("oracle_xK"),
        pl.col("game_date").first())
    rows = []
    for r in g.iter_rows(named=True):
        key = (r["game_pk"], r["pitcher"])
        if key not in bf:
            raise ValueError(f"POPULATION_VIOLATION: start {key} not in reconciled manifest")
        if r["n_modeled"] != bf[key]:
            raise ValueError(
                f"BF_RECONCILIATION_FAILURE: {key} modeled {r['n_modeled']} vs official {bf[key]}")
        rows.append({**r, "opportunity_mode": mode})
    return pl.DataFrame(rows)


def assert_temporal_boundary(feature_ts, cutoff_ts, label: str) -> None:
    """G7: every feature timestamp must precede its prediction cutoff."""
    import datetime as dt
    bad = [t for t in feature_ts if t is not None and t >= cutoff_ts]
    if bad:
        raise ValueError(
            f"TEMPORAL_BOUNDARY_VIOLATION ({label}): {len(bad)} feature timestamps >= cutoff "
            f"{cutoff_ts}. Historical failure class: same-game information entering features.")


def population_reconcile(counts: dict, manifest: dict) -> None:
    """G4: exact manifest reconciliation."""
    for k, expected in manifest.items():
        got = counts.get(k)
        if got != expected:
            raise ValueError(f"POPULATION_MISMATCH: {k} = {got}, manifest expects {expected}")
