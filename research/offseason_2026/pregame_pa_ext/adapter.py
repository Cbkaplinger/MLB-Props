"""pregame-pa-ext-v2 projected per-PA probability adapter.

Scores the frozen projected unique-batter-v2 lineups
(pregame-state-v1\\data\\projected_lineups_variant_v2.parquet) with the
frozen H3-raw 8-feature per-PA K-probability checkpoint, strictly before
each start's forecast cutoff (its game_date).

Lineage (read-only; this module reimplements nothing new and tunes nothing):

- Feature construction: FEAT_H3 as registered in
  ``research/offseason_2026/specs/count-eval-v2-spec/harness/comparison.py``
  (branch research/market-eval-v2; identical list in pregame-state-v1
  ``run_pregame_state_comparison.py``):
  6 B features (w150-shrunk pitcher/batter cumulative priors, league rate,
  prior counts, cold_start) + ew_pitcher + ew_batter (EW-90d).
- Cumulative/EW state: ``entity_daily_state`` / ``league_daily_state``
  mirror run_pregame_state_comparison.py (strictly-prior shift; EW weights
  2^(dnum/90) with half-life 90d); G1-verified machinery from pregame-pa-ext-v1.
- Frozen checkpoint coefficients: no serialized model artifact exists in any
  lineage directory; the coefficients are obtained by deterministic refit of
  the frozen recipe (StandardScaler + LogisticRegression(C=1.0, max_iter=1000)
  per block on the 8 FEAT_H3 features) and verified against the stored
  overnight-p2 preds checkpoints at <=1e-8 (the paext-v1
  ``fit_models_verified`` mechanism). A serialized-model injection hook is
  provided for future artifacts.
- Count PMFs: both registered RAW arms over the shared BF workload PMF
  (bf-workload-v1 BASE empirical build, extended by
  ``kcount_combiner.bf_pmf_from_37``): H3-raw cycled-prefix-mean arm and
  LOG5 corrected arm, mixed over binomial conditionals (24 buckets, 0..23).

Design rules:
- Every core function is pure over injected frames (no file I/O), so
  synthetic tests run the identical code path as the real lineage.
- Real-data paths live behind env-overridable constants and are lazily
  evaluated; missing real inputs fail loud (never silently skip).
- Research-only: no live scorer, policy JSON, schedule, or ledger is touched.
- No realized outcomes enter the projected path: no y join, no same-date or
  future rows can influence any feature (strictly-prior construction with a
  hard cutoff gate).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import polars as pl

from kcount_combiner import KCOUNT_CAP, bf_pmf_from_37  # noqa: F401

# ------------------------------------------------------- frozen constants
FEAT_B = [
    "p_pitcher_prior_w150", "p_batter_prior_w150", "lg_rate",
    "n_prior_pitcher", "n_prior_batter", "cold_start",
]
FEAT_H3 = FEAT_B + ["ew_pitcher", "ew_batter"]

W_PRIOR = 150
HALF_LIFE_DAYS = 90.0
P_CLIP = 1e-9
EPS = 1e-15
K_MAX = 24  # last PMF bucket absorbs >= 23

KS = np.arange(K_MAX)
N_ARR = np.arange(1, KCOUNT_CAP + 1)[:, None]
LOG_BINOM = np.full((KCOUNT_CAP + 1, K_MAX), -np.inf)
for _n in range(KCOUNT_CAP + 1):
    for _k in range(K_MAX):
        if _k <= _n:
            from math import lgamma
            LOG_BINOM[_n, _k] = (
                lgamma(_n + 1) - lgamma(_k + 1) - lgamma(_n - _k + 1)
            )

SOURCE_TYPE_ENTITY = "entity_history"
SOURCE_TYPE_COLD = "league_prior_no_entity_history"
SOURCE_TYPE_FALLBACK = "league_rate_fill_uncovered_slot"

SRC_DATE_COLS = [
    "src_date_pitcher", "src_date_batter",
    "src_date_ew_pitcher", "src_date_ew_batter",
]
OUTPUT_KEY = ["game_pk", "pitcher", "batter", "slot", "game_date"]


class AdapterError(RuntimeError):
    """Every adapter guard fails loud."""


# ------------------------------------------------------------ state builders
def entity_daily_state(pa: pl.DataFrame, ent: str) -> pl.DataFrame:
    """One row per (entity, game_date) with STRICTLY-PRIOR cumulative and
    90d-EW state (weights 2^(dnum/90); same-date rows excluded via the
    shift). Mirrors pregame-state-v1 entity_daily_state exactly."""
    return (
        pa.group_by(ent, "game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort(ent, "game_date")
        .with_columns(
            (pl.col("game_date") - pl.date(1970, 1, 1))
            .dt.total_days().cast(pl.Float64).alias("dnum"),
        )
        .with_columns(
            pl.col("k").cum_sum().over(ent).alias("cum_k"),
            pl.col("n").cum_sum().over(ent).alias("cum_n"),
            ((2.0 ** (pl.col("dnum") / HALF_LIFE_DAYS))
             * pl.col("k").cast(pl.Float64))
            .cum_sum().over(ent).alias("ew_k_cum"),
            ((2.0 ** (pl.col("dnum") / HALF_LIFE_DAYS))
             * pl.col("n").cast(pl.Float64))
            .cum_sum().over(ent).alias("ew_den_cum"),
        )
        .with_columns(
            pl.col("cum_k").shift(1).over(ent).fill_null(0).alias("prior_k"),
            pl.col("cum_n").shift(1).over(ent).fill_null(0).alias("prior_n"),
            pl.col("game_date").shift(1).over(ent).alias("src_date"),
            pl.col("ew_k_cum").shift(1).over(ent).fill_null(0.0)
            .alias("ew_k"),
            pl.col("ew_den_cum").shift(1).over(ent).fill_null(0.0)
            .alias("ew_den"),
            pl.col("game_date").shift(1).over(ent).alias("ew_src"),
        )
        .select(ent, "game_date", "prior_k", "prior_n", "src_date",
                "ew_k", "ew_den", "ew_src")
        .sort("game_date")
    )


def league_daily_state(pa: pl.DataFrame) -> pl.DataFrame:
    """League cumulative K rate, strictly-prior (shift(1))."""
    return (
        pa.group_by("game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort("game_date")
        .with_columns(
            pl.col("k").cum_sum().alias("cum_k"),
            pl.col("n").cum_sum().alias("cum_n"),
        )
        .with_columns(
            pl.col("cum_k").shift(1).fill_null(0).alias("lg_k_prior"),
            pl.col("cum_n").shift(1).fill_null(0).alias("lg_n_prior"),
        )
        .with_columns(
            pl.col("game_date").shift(1).alias("lg_src_date"),
        )
        .with_columns(
            (pl.col("lg_k_prior").cast(pl.Float64)
             / pl.col("lg_n_prior")).alias("lg_rate"),
        )
        .select("game_date", "lg_rate", "lg_src_date")
        .sort("game_date")
    )


def attach_league_asof(df: pl.DataFrame, lg: pl.DataFrame) -> pl.DataFrame:
    return df.sort("game_date").join_asof(
        lg, left_on="game_date", right_on="game_date", strategy="backward"
    )


# --------------------------------------------------------------- projection
def projected_long(proj_slots: pl.DataFrame, prefix: str = "u") -> pl.DataFrame:
    """Projected unique-batter-v2 lineups -> one row per (start, slot).

    Uncovered slots (null batter) are DROPPED and reported via the
    ``slot_uncovered`` column being absent: callers that need the fallback
    path must handle it upstream (per-slot source_type below only carries
    entity_history / cold states). Asserts start keys unique and
    (start, slot) keys unique."""
    slot_cols = [f"{prefix}_slot_{i}" for i in range(1, 10)]
    for col in ["game_pk", "side", "pitcher", "game_date", "nine_distinct"]:
        if col not in proj_slots.columns:
            raise AdapterError(f"projected lineups missing column: {col}")
    missing_slots = [c for c in slot_cols if c not in proj_slots.columns]
    if missing_slots:
        raise AdapterError(
            f"projected lineups missing slot columns: {missing_slots}")
    dup_starts = proj_slots.group_by("game_pk", "side", "pitcher").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    if dup_starts:
        raise AdapterError("projected start keys not unique")
    long = proj_slots.select(
        "game_pk", "side", "pitcher", "game_date", "nine_distinct",
        *slot_cols,
    ).unpivot(
        index=["game_pk", "side", "pitcher", "game_date", "nine_distinct"],
        on=slot_cols,
        variable_name="slot_name", value_name="batter",
    ).with_columns(
        pl.col("slot_name").str.extract(r"(\d+)").cast(pl.Int32).alias("slot")
    ).drop("slot_name")
    n_uncovered = long.filter(pl.col("batter").is_null()).height
    long = long.filter(pl.col("batter").is_not_null())
    dup = long.group_by("game_pk", "side", "pitcher", "slot").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    if dup:
        raise AdapterError("projected (start, slot) keys not unique")
    return long.sort("game_date", "game_pk", "side", "slot"), n_uncovered


def attach_prior_features(
    long: pl.DataFrame,
    p_daily: pl.DataFrame,
    b_daily: pl.DataFrame,
    lg: pl.DataFrame,
) -> pl.DataFrame:
    """Frozen prior-only features per projected (start, slot, batter) PA,
    with full provenance. Joins are asof at the start's game_date by
    pitcher / batter (backward), league asof; w150 shrinkage; EW fallback
    to league rate when the entity has no EW history (cold start)."""
    pstate = p_daily.select(
        "pitcher", "game_date",
        pl.col("prior_k").alias("prior_k_pitcher"),
        pl.col("prior_n").alias("prior_n_pitcher"),
        pl.col("src_date").alias("src_date_pitcher"),
        pl.col("ew_k").alias("ew_k_pitcher"),
        pl.col("ew_den").alias("ew_den_pitcher"),
        pl.col("ew_src").alias("src_date_ew_pitcher"),
    ).sort("game_date")
    bstate = b_daily.select(
        "batter", "game_date",
        pl.col("prior_k").alias("prior_k_batter"),
        pl.col("prior_n").alias("prior_n_batter"),
        pl.col("src_date").alias("src_date_batter"),
        pl.col("ew_k").alias("ew_k_batter"),
        pl.col("ew_den").alias("ew_den_batter"),
        pl.col("ew_src").alias("src_date_ew_batter"),
    ).sort("game_date")
    pf = (
        long.join_asof(
            pstate, left_on="game_date", right_on="game_date",
            by="pitcher", strategy="backward",
        )
        .sort("game_date")
        .join_asof(
            bstate, left_on="game_date", right_on="game_date",
            by="batter", strategy="backward",
        )
    )
    pf = attach_league_asof(pf, lg)
    pf = pf.with_columns(
        pl.col("prior_n_pitcher").fill_null(0),
        pl.col("prior_n_batter").fill_null(0),
        pl.col("prior_k_pitcher").fill_null(0),
        pl.col("prior_k_batter").fill_null(0),
        pl.col("ew_den_pitcher").fill_null(0.0),
        pl.col("ew_den_batter").fill_null(0.0),
    ).with_columns(
        ((pl.col("prior_k_pitcher").cast(pl.Float64)
          + W_PRIOR * pl.col("lg_rate"))
         / (pl.col("prior_n_pitcher") + W_PRIOR)
         ).alias("p_pitcher_prior_w150"),
        ((pl.col("prior_k_batter").cast(pl.Float64)
          + W_PRIOR * pl.col("lg_rate"))
         / (pl.col("prior_n_batter") + W_PRIOR)
         ).alias("p_batter_prior_w150"),
        (pl.when(pl.col("ew_den_pitcher") > 0)
         .then(pl.col("ew_k_pitcher") / pl.col("ew_den_pitcher"))
         .otherwise(pl.col("lg_rate"))).alias("ew_pitcher"),
        (pl.when(pl.col("ew_den_batter") > 0)
         .then(pl.col("ew_k_batter") / pl.col("ew_den_batter"))
         .otherwise(pl.col("lg_rate"))).alias("ew_batter"),
    ).with_columns(
        ((pl.col("prior_n_pitcher") == 0)
         | (pl.col("prior_n_batter") == 0)).cast(pl.Int8)
        .alias("cold_start"),
        pl.col("prior_n_pitcher").alias("n_prior_pitcher"),
        pl.col("prior_n_batter").alias("n_prior_batter"),
    ).with_columns(
        pl.when(pl.col("prior_n_pitcher") == 0)
        .then(pl.lit(SOURCE_TYPE_COLD)).otherwise(pl.lit(SOURCE_TYPE_ENTITY))
        .alias("src_type_pitcher"),
        pl.when(pl.col("prior_n_batter") == 0)
        .then(pl.lit(SOURCE_TYPE_COLD)).otherwise(pl.lit(SOURCE_TYPE_ENTITY))
        .alias("src_type_batter"),
    ).with_columns(
        *[pl.col(c).fill_null(pl.col("lg_src_date")) for c in SRC_DATE_COLS]
    )
    return pf


# -------------------------------------------------------------------- gates
def add_block(pf: pl.DataFrame) -> pl.DataFrame:
    """Block assignment identical to pregame-state-v1 (fixed date bounds;
    the projection window starts 2024-07-01, so block_2024H1 is out of
    scope by construction)."""
    return pf.with_columns(
        pl.when(pl.col("game_date") <= pl.date(2024, 12, 31))
        .then(pl.lit("block_2024H2"))
        .when(pl.col("game_date") <= pl.date(2025, 6, 30))
        .then(pl.lit("block_2025H1"))
        .otherwise(pl.lit("confirm_2025H2"))
        .alias("block")
    )


def assert_cutoff(pf: pl.DataFrame) -> dict:
    """Hard cutoff gate: every feature source date non-null and STRICTLY
    BEFORE the start's forecast cutoff (game_date)."""
    for col in SRC_DATE_COLS + ["lg_src_date"]:
        if col not in pf.columns:
            raise AdapterError(f"cutoff gate: missing source-date column {col}")
        n_null = pf.filter(pl.col(col).is_null()).height
        if n_null:
            raise AdapterError(f"cutoff gate: {col} null on {n_null} rows")
        bad = pf.filter(pl.col(col) >= pl.col("game_date")).height
        if bad:
            raise AdapterError(
                f"cutoff gate: {col} >= game_date on {bad} rows")
    max_src = pf.select(pl.max_horizontal(SRC_DATE_COLS)).to_series()
    lag = (pf["game_date"] - max_src).dt.total_days()
    return {
        "n_rows": pf.height,
        "all_source_dates_strictly_before_cutoff": True,
        "min_source_lag_days": int(lag.min()),
    }


def assert_identity(pf: pl.DataFrame) -> None:
    """Identity gate: output keys unique, non-null, no duplicate keys."""
    for col in OUTPUT_KEY:
        if col not in pf.columns:
            raise AdapterError(f"identity gate: missing key column {col}")
        n_null = pf.filter(pl.col(col).is_null()).height
        if n_null:
            raise AdapterError(f"identity gate: {col} null on {n_null} rows")
    dup = pf.group_by(OUTPUT_KEY).agg(n=pl.len()).filter(
        pl.col("n") > 1).height
    if dup:
        raise AdapterError(
            f"identity gate: {dup} duplicate (game_pk, pitcher, batter, "
            "slot, game_date) keys")


def require_feature_columns(df: pl.DataFrame) -> None:
    """Fail loud when any of the 8 FEAT_H3 columns is missing -- in
    particular the EW-90d columns (canonical features_v3 lacks them; the
    adapter builds them from the PA table, so a caller passing a features
    frame without EW columns is a lineage error, never a silent fallback)."""
    missing = [c for c in FEAT_H3 if c not in df.columns]
    if missing:
        raise AdapterError(
            f"missing required feature columns (fail-loud on EW): {missing}")


def assert_no_feature_nulls(pf: pl.DataFrame) -> None:
    require_feature_columns(pf)
    for col in FEAT_H3:
        n_null = pf.filter(pl.col(col).is_null()).height
        if n_null:
            raise AdapterError(
                f"feature gate: {col} null on {n_null} rows")


# -------------------------------------------------------------- checkpoint
def fit_models_from_frames(train: pl.DataFrame, cal: pl.DataFrame) -> dict:
    """Frozen H3-raw arm fit for one block: StandardScaler +
    LogisticRegression(C=1.0, max_iter=1000) on FEAT_H3. Pure over injected
    frames; used by the verified real-lineage checkpoint and synthetic
    tests alike. Returns the serializable coefficient dict."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(train.select(FEAT_H3).to_numpy())
    lr = LogisticRegression(C=1.0, max_iter=1000)
    lr.fit(scaler.transform(train.select(FEAT_H3).to_numpy()),
           train["y"].to_numpy().astype(int))
    return {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coef": lr.coef_[0].tolist(),
        "intercept": float(lr.intercept_[0]),
        "features": list(FEAT_H3),
    }


def apply_h3_raw(features: pl.DataFrame, model: dict) -> np.ndarray:
    """Apply one block's frozen H3-raw coefficients to feature rows."""
    assert_no_feature_nulls(features)
    X = features.select(FEAT_H3).to_numpy()
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    z = (X - mean) / scale
    eta = z @ coef + model["intercept"]
    p = 1.0 / (1.0 + np.exp(-eta))
    if not np.all(np.isfinite(p)):
        raise AdapterError("non-finite H3-raw probability")
    return np.clip(p, P_CLIP, 1.0 - P_CLIP)


def verify_checkpoint(models: dict, feat: pl.DataFrame,
                      preds_dir: Path) -> dict:
    """Real-lineage verification gate (run only with the private lake
    present): refit coefficients must reproduce the stored overnight-p2
    preds checkpoints (pred_H3_raw) at <=1e-8 for the three registered
    blocks, else STOP. PREDS and BLOCK_TRAIN_END mirror
    run_pregame_state_comparison.py exactly."""
    preds_files = {
        "block_2024H2": ("preds_block_2024H2.parquet", (2024, 6, 30)),
        "block_2025H1": ("preds_block_2025H1.parquet", (2024, 12, 31)),
        "confirm_2025H2": ("preds_confirm_2025H2.parquet", (2025, 6, 30)),
    }
    report = {}
    for block, (fname, _train_end) in preds_files.items():
        preds = pl.read_parquet(Path(preds_dir) / fname)
        joined = preds.join(
            feat.select("game_pk", "at_bat_number", "batter", *FEAT_H3),
            on=["game_pk", "at_bat_number", "batter"], how="left",
        )
        if joined.height != preds.height:
            raise AdapterError(f"checkpoint join expanded for {block}")
        if joined["ew_pitcher"].null_count():
            raise AdapterError(f"checkpoint join missing EW features {block}")
        p = apply_h3_raw(joined, models[block])
        d = float(np.abs(p - joined["pred_H3_raw"].to_numpy()).max())
        if d > 1e-8:
            raise AdapterError(
                f"STOP: frozen checkpoint verification FAILED for {block}: "
                f"max_abs_diff={d:.3e}")
        report[block] = {"n_rows": preds.height, "max_abs_diff": d}
    return report


def maybe_load_serialized_models(directory: Path) -> dict | None:
    """Load a serialized checkpoint (one .joblib/.pkl mapping block name ->
    coefficient dict) if one exists; None otherwise. No serialized model
    artifact exists in any current lineage directory, so the canonical path
    is the deterministic refit + verify gate."""
    import pickle
    for name in ("h3_raw_checkpoint.pkl", "h3_raw_checkpoint.joblib"):
        p = Path(directory) / name
        if p.exists():
            if p.suffix == ".joblib":
                import joblib
                return joblib.load(p)
            with open(p, "rb") as fh:
                return pickle.load(fh)
    return None


# --------------------------------------------------------------- LOG5 arm
def log5(p_p, p_b, l, eps=P_CLIP):
    p = np.clip(np.asarray(p_p, dtype=np.float64), eps, 1.0 - eps)
    b = np.clip(np.asarray(p_b, dtype=np.float64), eps, 1.0 - eps)
    lg = np.clip(np.asarray(l, dtype=np.float64), eps, 1.0 - eps)
    num = p * b * (1.0 - lg)
    den = num + (1.0 - p) * (1.0 - b) * lg
    return num / den


def arm_probs(pf: pl.DataFrame, models: dict | None) -> pl.DataFrame:
    """Per-PA K probabilities for both RAW arms:
    - p_h3_raw: frozen H3-raw checkpoint coefficients on the 8 features
      (feature-based scoring: player IDs never enter the model).
    - p_l5_raw: LOG5 corrected from the w150 priors and league rate."""
    p_l5 = np.clip(log5(
        pf["p_pitcher_prior_w150"].to_numpy(),
        pf["p_batter_prior_w150"].to_numpy(),
        pf["lg_rate"].to_numpy()), P_CLIP, 1.0 - P_CLIP)
    if models is None:
        raise AdapterError("no frozen checkpoint provided (fail loud)")
    n = pf.height
    p_h3 = np.full(n, np.nan)
    blocks = pf.get_column("block") if "block" in pf.columns else None
    if blocks is None:
        if len(models) != 1:
            raise AdapterError(
                "no block column and multi-block checkpoint provided")
        (model,) = models.values()
        p_h3[:] = apply_h3_raw(pf, model)
    else:
        for block, model in models.items():
            m = (blocks == block).to_numpy()
            if not m.any():
                continue
            p_h3[m] = apply_h3_raw(pf.filter(pl.Series(m)), model)
        if np.isnan(p_h3).any():
            raise AdapterError("projected row outside known checkpoint blocks")
    return pf.with_columns(
        pl.Series("p_h3_raw", p_h3),
        pl.Series("p_l5_raw", p_l5),
    )


# -------------------------------------------------------- count-PMF arms
def cycled_cond_mean(p9: np.ndarray) -> np.ndarray:
    """pbar_n = mean of the projected nine per-PA probabilities cycled to
    n, n = 1..KCOUNT_CAP (identical to pregame-state-v1)."""
    p9 = np.asarray(p9, dtype=np.float64)
    if p9.shape != (9,):
        raise AdapterError(f"cycled_cond_mean expects 9 probs, got {p9.shape}")
    if not np.all(np.isfinite(p9)) or p9.min() < 0 or p9.max() > 1:
        raise AdapterError("invalid per-PA probabilities")
    cycled = np.tile(p9, KCOUNT_CAP // 9 + 1)[:KCOUNT_CAP]
    return np.clip(
        np.cumsum(cycled) / np.arange(1, KCOUNT_CAP + 1), P_CLIP, 1 - P_CLIP
    )


def count_pmf_from_mixture(bf_ext: np.ndarray, pbar_n: np.ndarray) -> np.ndarray:
    """P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n); 24 buckets, tail
    absorbed into k=23."""
    with np.errstate(divide="ignore"):
        logp = np.log(pbar_n)
        log1mp = np.log1p(-pbar_n)
    lp = LOG_BINOM[1:KCOUNT_CAP + 1] + logp[:, None] * KS[None, :] \
        + log1mp[:, None] * (N_ARR - KS[None, :])
    binom = np.exp(lp)
    binom[N_ARR - KS < 0] = 0.0
    out = (bf_ext[:, None] * binom).sum(axis=0)
    tail = max(0.0, 1.0 - out.sum())
    out = out.copy()
    out[K_MAX - 1] += tail
    return out


def check_pmf(p_k: np.ndarray, ctx: str) -> None:
    p_k = np.asarray(p_k, dtype=np.float64)
    if not np.all(np.isfinite(p_k)):
        raise AdapterError(f"non-finite PMF: {ctx}")
    if p_k.min() < 0.0 or p_k.max() > 1.0:
        raise AdapterError(f"PMF out of [0,1]: {ctx}")
    if abs(float(p_k.sum()) - 1.0) > 1e-9:
        raise AdapterError(f"PMF sum != 1: {ctx}")


def start_count_pmfs(p9_h3: np.ndarray, p9_l5: np.ndarray,
                     bf37: np.ndarray) -> dict:
    """Both registered RAW arms from the shared BF PMF: H3-raw
    cycled-prefix-mean and LOG5 corrected. Returns 24-bucket PMFs plus
    mean-K for each arm."""
    bf_ext = bf_pmf_from_37(np.asarray(bf37, dtype=np.float64))
    out = {}
    for tag, p9 in (("h3_raw", p9_h3), ("l5_raw", p9_l5)):
        pbar = cycled_cond_mean(p9)
        pk = count_pmf_from_mixture(bf_ext, pbar)
        check_pmf(pk, tag)
        mean_k = float((bf_ext * N_ARR[:, 0] * pbar).sum())
        out[f"pmf_{tag}"] = pk
        out[f"mean_k_{tag}"] = mean_k
    return out


# ----------------------------------------------------------- unseen pairs
def unseen_pairs_report(pf: pl.DataFrame, pa: pl.DataFrame) -> dict:
    """Document projected (pitcher, batter) pairs that never occur in the
    PA table, and verify the frozen checkpoint still scores them.

    The H3-raw model consumes the 8 features only -- never a pitcher or
    batter ID -- and the features are built from per-entity histories
    (pitcher asof + batter asof + league asof), not from pair history. So
    an unseen pair is scored through its entities' priors exactly like a
    seen pair. Verified here: every unseen-pair row carries finite features
    and finite probabilities."""
    seen_p = set(pa["pitcher"].unique().to_list())
    seen_b = set(pa["batter"].unique().to_list())
    seen_pairs = set(zip(pa["pitcher"].to_list(), pa["batter"].to_list()))
    proj_pairs = list(zip(pf["pitcher"].to_list(), pf["batter"].to_list()))
    unseen_rows = [
        i for i, pair in enumerate(proj_pairs) if pair not in seen_pairs]
    unseen_pair_set = sorted({proj_pairs[i] for i in unseen_rows})
    never_seen_entities = sorted({
        e for pair in unseen_pair_set for e in pair
        if (e not in seen_p) or (e not in seen_b)
    })
    if unseen_rows:
        sub = pf[unseen_rows]
        assert_no_feature_nulls(sub)
        for col in ("p_h3_raw", "p_l5_raw"):
            if col in sub.columns:
                v = sub[col].to_numpy()
                if not np.all(np.isfinite(v)):
                    raise AdapterError(
                        f"unseen-pair rows have non-finite {col}")
    return {
        "n_rows": pf.height,
        "n_rows_unseen_pair": len(unseen_rows),
        "n_unseen_pairs": len(unseen_pair_set),
        "unseen_pairs_sample": [list(p) for p in unseen_pair_set[:20]],
        "n_entities_never_seen_in_pa_table": len(never_seen_entities),
        "handled_by": (
            "feature-based scoring: the H3-raw checkpoint consumes the 8 "
            "FEAT_H3 features only (no player IDs); unseen pairs are scored "
            "via per-entity cumulative priors + EW-90d + league rate"),
    }


# --------------------------------------------------------------- write-once
def write_once(df: pl.DataFrame, out_path: Path) -> Path:
    """Write-once output: refuses to overwrite an existing parquet."""
    out_path = Path(out_path)
    if out_path.exists():
        raise AdapterError(f"write-once violation: {out_path} exists")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)
    return out_path


# ----------------------------------------------------------------- driver
def build_projected_pa_probs(
    proj: pl.DataFrame,
    pa: pl.DataFrame,
    models: dict,
    bf37_by_start: pl.DataFrame | None = None,
    out_path: Path | None = None,
) -> tuple[pl.DataFrame, dict]:
    """End-to-end projected per-PA probability build over injected frames.

    proj: projected unique-batter-v2 lineups (one row per start).
    pa: PA table with (game_pk, at_bat_number, batter, pitcher, game_date,
        y) -- the training-side lineage only; no same-date or future row can
        reach a feature (strictly-prior shift + hard cutoff gate).
    models: {block_name -> coefficient dict} from the verified frozen
        checkpoint (or a single 'default' entry when scoring one block).
    bf37_by_start: optional (game_pk, side, pitcher, pmf37_0..pmf37_36)
        frame; when given, both RAW count-PMF arms are attached per start.
    out_path: when given, results are written write-once.

    Returns (per-PA probabilities frame, provenance summary dict)."""
    long, n_uncovered = projected_long(proj)
    p_daily = entity_daily_state(pa, "pitcher")
    b_daily = entity_daily_state(pa, "batter")
    lg = league_daily_state(pa)
    pf = attach_prior_features(long, p_daily, b_daily, lg)
    pf = add_block(pf)
    cutoff = assert_cutoff(pf)
    require_feature_columns(pf)
    pf = arm_probs(pf, models)
    assert_identity(pf)
    unseen = unseen_pairs_report(pf, pa)
    summary = {
        "n_projected_starts": proj.height,
        "n_uncovered_slots_dropped": n_uncovered,
        "n_pa_rows_scored": pf.height,
        "cutoff": cutoff,
        "unseen_pairs": unseen,
    }
    if bf37_by_start is not None:
        pmf37_cols = [f"pmf37_{j}" for j in range(37)]
        missing = [c for c in ["game_pk", "side", "pitcher", *pmf37_cols]
                   if c not in bf37_by_start.columns]
        if missing:
            raise AdapterError(f"BF PMF frame missing columns: {missing}")
        bf = bf37_by_start.select("game_pk", "side", "pitcher", *pmf37_cols)
        starts = pf.sort("slot").group_by(
            "game_pk", "side", "pitcher").agg(
            pl.col("p_h3_raw").sort_by("slot").alias("p9_h3"),
            pl.col("p_l5_raw").sort_by("slot").alias("p9_l5"),
        ).join(bf, on=["game_pk", "side", "pitcher"], how="left")
        if starts.filter(pl.col("pmf37_0").is_null()).height:
            raise AdapterError("BF PMF missing for projected starts")
        pmf_h3, pmf_l5, mk_h3, mk_l5 = [], [], [], []
        for row in starts.iter_rows(named=True):
            p9_h3 = np.asarray(row["p9_h3"], dtype=np.float64)
            p9_l5 = np.asarray(row["p9_l5"], dtype=np.float64)
            if p9_h3.shape != (9,) or p9_l5.shape != (9,):
                raise AdapterError(
                    "start does not carry exactly 9 covered slots "
                    f"(game_pk={row['game_pk']}, side={row['side']}, "
                    f"pitcher={row['pitcher']})")
            arms = start_count_pmfs(
                p9_h3, p9_l5,
                np.asarray([row[f"pmf37_{j}"] for j in range(37)]))
            pmf_h3.append(arms["pmf_h3_raw"])
            pmf_l5.append(arms["pmf_l5_raw"])
            mk_h3.append(arms["mean_k_h3_raw"])
            mk_l5.append(arms["mean_k_l5_raw"])
        starts = starts.with_columns(
            pl.Series("pmf_h3_raw", pmf_h3),
            pl.Series("pmf_l5_raw", pmf_l5),
            pl.Series("mean_k_h3_raw", mk_h3),
            pl.Series("mean_k_l5_raw", mk_l5),
        ).drop("p9_h3", "p9_l5", *pmf37_cols)
        pf = pf.join(
            starts.select("game_pk", "side", "pitcher", "pmf_h3_raw",
                          "pmf_l5_raw", "mean_k_h3_raw", "mean_k_l5_raw"),
            on=["game_pk", "side", "pitcher"], how="left",
        )
        if pf["pmf_h3_raw"].null_count():
            raise AdapterError("count-PMF join left unmatched per-PA rows")
    if out_path is not None:
        write_once(pf, out_path)
    return pf, summary


# ----------------------------------------------------------- real lineage
PREGAME_STATE_DIR = Path(os.environ.get(
    "PREGAME_STATE_V1_DIR",
    r"C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1"))
OVERNIGHT_P2_DIR = Path(os.environ.get(
    "OVERNIGHT_P2_DIR",
    r"C:\Users\ckaplinger\MLB-Props-Research\overnight-p2"))
PAEXT_OUT_DIR = Path(os.environ.get(
    "PAEXT_V2_OUT_DIR",
    r"C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2"))


def load_projected_lineups(directory: Path | None = None) -> pl.DataFrame:
    d = Path(directory) if directory else PREGAME_STATE_DIR
    p = d / "data" / "projected_lineups_variant_v2.parquet"
    if not p.exists():
        raise AdapterError(f"projected lineups not found: {p}")
    return pl.read_parquet(p)


def load_pa_table(directory: Path | None = None) -> pl.DataFrame:
    d = Path(directory) if directory else OVERNIGHT_P2_DIR
    p = d / "data" / "pa_table.parquet"
    if not p.exists():
        raise AdapterError(f"PA table not found: {p}")
    return pl.read_parquet(p)


def run_real(out_name: str = "projected_pa_probs_v1.parquet") -> dict:
    """Real-lineage driver (private lake required; never runs in CI).
    Deterministic refit of the frozen H3-raw checkpoint recipe per block
    (train on 2023-01-01..cal_first, sigmoid-free RAW principal, cal window
    = last 60 days before each BLOCK_TRAIN_END, identical to
    paext-v1 fit_models_verified), verified against the stored overnight-p2
    preds checkpoints (<=1e-8) BEFORE any projected-row inference; output
    is write-once."""
    from datetime import timedelta
    proj = load_projected_lineups()
    pa = load_pa_table()
    p_daily = entity_daily_state(pa, "pitcher")
    b_daily = entity_daily_state(pa, "batter")
    lg = league_daily_state(pa)
    realized = pa.select(
        "game_pk", "at_bat_number", "batter", "pitcher", "game_date",
    ).sort("game_date")
    feat = attach_prior_features(realized, p_daily, b_daily, lg)
    feat = feat.join(pa.select("game_pk", "at_bat_number", "batter", "y"),
                     on=["game_pk", "at_bat_number", "batter"], how="inner")
    # day-1 league state is 0/0 (NaN) in any PA table; the frozen fits
    # start 2023-01-01, long after league history exists, so drop the
    # non-finite league rows from fit frames only (never silently in the
    # projected path, where the cutoff gate already guarantees a finite
    # asof league rate).
    feat = feat.filter(pl.col("lg_rate").is_finite())
    blocks = {
        "block_2024H2": (2024, 6, 30),
        "block_2025H1": (2024, 12, 31),
        "confirm_2025H2": (2025, 6, 30),
    }
    models = {}
    for block, (te_y, te_m, te_d) in blocks.items():
        cal_last = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") <= pl.date(te_y, te_m, te_d))
        )["game_date"].max()
        cal_first = cal_last - timedelta(days=59)
        train = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") < cal_first))
        cal = feat.filter(
            (pl.col("game_date") >= cal_first)
            & (pl.col("game_date") <= cal_last))
        models[block] = fit_models_from_frames(train, cal)
    verify = verify_checkpoint(models, feat, OVERNIGHT_P2_DIR / "data")
    pf, summary = build_projected_pa_probs(proj, pa, models)
    out = write_once(pf, PAEXT_OUT_DIR / "outputs" / out_name)
    summary["checkpoint_verification"] = verify
    summary["output"] = str(out)
    return summary
