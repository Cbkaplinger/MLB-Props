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
- Frozen checkpoint coefficients: no coefficients are ever fit at adapter
  execution time. A one-time reconstruction script
  (``pregame_pa_ext/build_checkpoint.py``) performs the deterministic refit
  of the frozen recipe (StandardScaler + LogisticRegression(C=1.0,
  max_iter=1000) per block on the 8 FEAT_H3 features), verifies it against
  the stored overnight-p2 preds checkpoints at <=1e-8 (the paext-v1
  ``fit_models_verified`` mechanism), and serializes the VERIFIED
  coefficients to a JSON artifact with a sha256 pin. The adapter loads ONLY
  that serialized artifact; if it is absent the adapter fails loud with the
  named error ``MISSING_CHECKPOINT_ARTIFACT`` -- no league-rate fallback
  and no reconstruction fallback at execution time.
- Count PMFs: both registered RAW arms over the shared BF workload PMF
  (bf-workload-v1 BASE empirical build, extended by
  ``kcount_combiner.bf_pmf_from_37``): H3-raw cycled-prefix-mean arm and
  LOG5 corrected arm, mixed over binomial conditionals (24 buckets, 0..23).
  ``run_real`` wires the registered bf-workload-v1 artifact
  (``data/bf_forecasts.parquet``, start grain (game_pk, side, pitcher),
  ``pmf37_0..36``) through ``load_bf_forecasts`` (sha256 provenance gate
  against the registered pin) and ``validate_bf37_by_start`` (unique start
  keys, coverage of every scored start, finite/nonnegative/normalized
  pmf37 rows, registered cap-60 geometric-tail conversion check). Missing
  or mismatched BF inputs fail loud -- no invented replacement
  distributions.

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

import hashlib
import json
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
SOURCE_TYPE_COLD_NO_PRIOR = "cold_start_no_prior"
EXCLUSION_REASON_COLD = (
    "cold_start_no_prior: no pitcher/batter history in the PA table and the "
    "frozen recipe declares no cold-start probability; PA excluded from "
    "scoring (owner rule: no silent league-rate fallback)"
)
CHECKPOINT_FORMAT = "pregame-pa-ext-v2/h3_raw-checkpoint-v1"

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


def checkpoint_payload(models: dict, verification: dict | None) -> dict:
    """Canonical JSON-serializable checkpoint payload (coefficient dict per
    block + the recorded <=1e-8 verification report)."""
    return {
        "features": list(FEAT_H3),
        "recipe": {"w_prior": W_PRIOR, "half_life_days": HALF_LIFE_DAYS},
        "blocks": models,
        "verification": verification,
    }


def checkpoint_sha256(payload: dict) -> str:
    """sha256 pin over the canonical JSON encoding of the payload."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def serialize_checkpoint(
    models: dict, verification: dict | None, out_path: Path,
) -> Path:
    """Serialize VERIFIED coefficients to the JSON artifact with a sha256
    pin (used only by build_checkpoint.py, never by the adapter path)."""
    payload = checkpoint_payload(models, verification)
    doc = {
        "format": CHECKPOINT_FORMAT,
        "sha256": checkpoint_sha256(payload),
        "payload": payload,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True),
                        encoding="utf-8")
    return out_path


FREEZE_CONFIG_RELPATH = "freeze_pregame_pa_ext_v2.json"
_FREEZE_CONFIG_CACHE: dict = {}


def load_freeze_config(path: Path | None = None) -> dict:
    """Load the freeze/registration config (freeze_pregame_pa_ext_v2.json)
    that carries the REGISTERED expected checkpoint sha256 pin. Cached per
    resolved path."""
    p = (Path(path) if path
         else Path(__file__).resolve().parent / FREEZE_CONFIG_RELPATH)
    p = p.resolve()
    if not p.exists():
        raise AdapterError(
            f"FREEZE_CONFIG_MISSING: registration config not found: {p}")
    key = str(p)
    if key not in _FREEZE_CONFIG_CACHE:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise AdapterError(
                f"FREEZE_CONFIG_INVALID: not a JSON object: {p}")
        _FREEZE_CONFIG_CACHE[key] = cfg
    return _FREEZE_CONFIG_CACHE[key]


def registered_checkpoint_pin(path: Path | None = None) -> str | None:
    """The registered expected checkpoint sha256
    (``checkpoint_sha256_expected`` in the freeze/registration config).
    ``None`` (the current registered value) = gate DISABLED: the artifact
    has not been produced by a real-data reconstruction yet, so no pin
    exists to enforce. A non-null value MUST be a 64-char hex sha256
    (anything else fails loud as CHECKPOINT_PIN_MALFORMED)."""
    cfg = load_freeze_config(path)
    pin = cfg.get("checkpoint_sha256_expected")
    if pin is None:
        return None
    if (not isinstance(pin, str) or len(pin) != 64
            or any(c not in "0123456789abcdef" for c in pin.lower())):
        raise AdapterError(
            "CHECKPOINT_PIN_MALFORMED: checkpoint_sha256_expected must be "
            f"null or a 64-char hex sha256; got {pin!r}")
    return pin.lower()


def load_serialized_checkpoint(path: Path | None = None) -> tuple[dict, dict]:
    """Load the SERIALIZED frozen checkpoint (the only coefficient source
    at adapter execution time). Fails loud:
    - MISSING_CHECKPOINT_ARTIFACT when the file does not exist (no
      league-rate fallback, no reconstruction fallback),
    - CHECKPOINT_HASH_MISMATCH when the sha256 pin over the payload does
      not match (corrupted or tampered artifact), and
    - CHECKPOINT_REGISTERED_PIN_MISMATCH when the artifact sha256 does
      not match the REGISTERED pin (checkpoint_sha256_expected in the
      freeze/registration config) while that pin is non-null. The
      registered pin is a PLACEHOLDER (null = gate disabled) until a
      real-data reconstruction registers the artifact hash."""
    p = Path(path) if path else CHECKPOINT_PATH
    if not p.exists():
        raise AdapterError(
            f"MISSING_CHECKPOINT_ARTIFACT: frozen checkpoint artifact not "
            f"found: {p}; run build_checkpoint.py once to reconstruct and "
            "verify it (the adapter never refits and never falls back)")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("format") != CHECKPOINT_FORMAT:
        raise AdapterError(
            f"CHECKPOINT_FORMAT_MISMATCH: {p} is not a "
            f"{CHECKPOINT_FORMAT} artifact")
    payload = doc["payload"]
    pin = doc.get("sha256")
    actual = checkpoint_sha256(payload)
    if pin != actual:
        raise AdapterError(
            f"CHECKPOINT_HASH_MISMATCH: sha256 pin mismatch for {p}: "
            f"declared {pin}, computed {actual}")
    expected = registered_checkpoint_pin()
    if expected is not None and expected != actual:
        raise AdapterError(
            "CHECKPOINT_REGISTERED_PIN_MISMATCH: checkpoint artifact sha256 "
            f"{actual} does not match the REGISTERED pin {expected} "
            f"(checkpoint_sha256_expected in the freeze/registration config) "
            f"for {p}; refusing to load")
    if payload.get("features") != list(FEAT_H3):
        raise AdapterError(
            f"CHECKPOINT_FEATURE_MISMATCH: artifact features "
            f"{payload.get('features')} != registered {list(FEAT_H3)}")
    models = payload["blocks"]
    if not isinstance(models, dict) or not models:
        raise AdapterError(f"CHECKPOINT_BLOCKS_INVALID: {p}")
    meta = {
        "path": str(p),
        "sha256": pin,
        "verification": payload.get("verification"),
        "registered_pin": expected,
        "registered_pin_enforced": expected is not None,
    }
    return models, meta


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


# ------------------------------------------------------------ BF37 wiring
BF37_TOL = 1e-9
PMF37_COLS = [f"pmf37_{j}" for j in range(37)]
START_KEYS = ["game_pk", "side", "pitcher"]


def validate_bf37_by_start(
    bf: pl.DataFrame, starts: pl.DataFrame
) -> tuple[pl.DataFrame, dict]:
    """Registered BF-PMF wiring validation (pure over injected frames).

    bf: bf-workload-v1 ``bf_forecasts.parquet`` frame -- start grain
        (game_pk, side, pitcher) with ``pmf37_0..36`` (the registered
        artifact is also unique on (game_pk, pitcher); both grains are
        enforced).
    starts: fully-scored projected starts (game_pk, side, pitcher[, 
        game_date]).

    Fail-loud guards (a missing or mismatched input NEVER produces an
    invented replacement distribution):
    - required columns present -> ``BF_PMF_COLUMNS_MISSING``;
    - duplicate start keys on either registered grain ->
      ``BF_PMF_DUPLICATE_START_KEYS``;
    - every scored start must have a complete BF PMF row ->
      ``BF_PMF_COVERAGE_MISSING``;
    - artifact ``game_date`` must match the projected start's when both
      frames carry it -> ``BF_PMF_DATE_MISMATCH``;
    - matched pmf37 rows finite, nonnegative, summing to 1 ->
      ``BF_PMF_DISTRIBUTION_INVALID``;
    - the registered bucket/tail conversion
      (``kcount_combiner.bf_pmf_from_37``, cap 60, geometric tail) must
      succeed per matched start -> ``BF_PMF_CONVERSION_FAILED``.

    Returns (starts frame with the 37 pmf37 columns attached, provenance
    meta dict)."""
    keys = list(START_KEYS)
    pmf37_cols = list(PMF37_COLS)
    for c in keys + pmf37_cols:
        if c not in bf.columns:
            raise AdapterError(
                f"BF_PMF_COLUMNS_MISSING: BF PMF frame lacks column {c!r}")
    for grain in (keys, ["game_pk", "pitcher"]):
        dups = bf.group_by(grain).agg(n=pl.len()).filter(pl.col("n") > 1)
        if dups.height:
            raise AdapterError(
                "BF_PMF_DUPLICATE_START_KEYS: %d duplicate %s key(s) in the "
                "BF PMF frame (sample: %s)"
                % (dups.height, "+".join(grain),
                   dups.select(*grain).head(3).rows()))
    bf_sel = bf.select(*keys, *pmf37_cols,
                       *(["game_date"] if "game_date" in bf.columns else []))
    if "game_date" in bf.columns:
        bf_sel = bf_sel.with_columns(
            pl.col("game_date").alias("bf_game_date"))
    j = starts.join(bf_sel, on=keys, how="left")
    missing = j.filter(
        pl.any_horizontal([pl.col(c).is_null() for c in pmf37_cols]))
    if missing.height:
        sample = missing.select(*keys).head(5).rows()
        raise AdapterError(
            "BF_PMF_COVERAGE_MISSING: %d scored start(s) have no complete "
            "BF PMF row in the registered bf-workload-v1 artifact "
            "(sample: %s); no replacement distribution may be invented"
            % (missing.height, sample))
    if "bf_game_date" in j.columns and "game_date" in j.columns:
        mm = j.filter(pl.col("bf_game_date") != pl.col("game_date"))
        if mm.height:
            raise AdapterError(
                "BF_PMF_DATE_MISMATCH: BF PMF game_date differs from the "
                "projected start game_date on %d start(s)" % mm.height)
    mat = j.select(*pmf37_cols).to_numpy().astype(np.float64)
    if mat.shape[0] == 0:
        # no fully-scored starts (all contain a cold-start slot): nothing
        # to validate or attach; PMFs stay absent with the explicit
        # cold-slot exclusion counts
        meta = {
            "n_scored_starts": int(starts.height),
            "n_starts_bf_matched": 0,
            "bf_extension": (
                "kcount_combiner.bf_pmf_from_37 (cap 60, geometric tail)"),
            "kcount_cap": KCOUNT_CAP,
            "k_max": K_MAX,
        }
        return j, meta
    if not np.isfinite(mat).all():
        raise AdapterError(
            "BF_PMF_DISTRIBUTION_INVALID: non-finite pmf37 entry on a "
            "matched start")
    if float(mat.min()) < 0.0:
        raise AdapterError(
            "BF_PMF_DISTRIBUTION_INVALID: negative pmf37 entry on a "
            "matched start")
    dev = np.abs(mat.sum(axis=1) - 1.0)
    if float(dev.max()) > BF37_TOL:
        raise AdapterError(
            "BF_PMF_DISTRIBUTION_INVALID: pmf37 row deviates from sum=1 "
            "(max abs dev %.3e)" % float(dev.max()))
    for i in range(mat.shape[0]):
        try:
            ext = bf_pmf_from_37(mat[i])
        except (ValueError, AssertionError) as exc:
            raise AdapterError(
                "BF_PMF_CONVERSION_FAILED: the registered bucket/tail "
                "conversion kcount_combiner.bf_pmf_from_37 (cap 60, "
                "geometric tail) rejected matched start %d: %s" % (i, exc))
        if ext.shape != (KCOUNT_CAP,) or abs(float(ext.sum()) - 1.0) > BF37_TOL:
            raise AdapterError(
                "BF_PMF_CONVERSION_FAILED: invalid cap-60 extension for "
                "matched start %d" % i)
    meta = {
        "n_scored_starts": int(starts.height),
        "n_starts_bf_matched": int(j.height),
        "bf_extension": (
            "kcount_combiner.bf_pmf_from_37 (cap 60, geometric tail)"),
        "kcount_cap": KCOUNT_CAP,
        "k_max": K_MAX,
    }
    return j, meta


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
        scored_sub = sub.filter(
            pl.col("source_type") != SOURCE_TYPE_COLD_NO_PRIOR)
        if scored_sub.height:
            assert_no_feature_nulls(scored_sub)
        for col in ("p_h3_raw", "p_l5_raw"):
            if col in scored_sub.columns:
                v = scored_sub[col].to_numpy()
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
            "FEAT_H3 features only (no player IDs); unseen pairs with full "
            "entity history are scored via per-entity cumulative priors + "
            "EW-90d + league rate; cold-start slots (no entity history) "
            f"carry source_type={SOURCE_TYPE_COLD_NO_PRIOR} and are "
            "EXCLUDED from scoring, never league-rate filled"),
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
    models: {block_name -> coefficient dict} loaded from the SERIALIZED
        sha256-pinned frozen checkpoint (load_serialized_checkpoint); the
        adapter never refits.
    bf37_by_start: optional (game_pk, side, pitcher, pmf37_0..pmf37_36)
        frame; when given, both RAW count-PMF arms are attached per start
        (fully scored starts only; starts containing a cold-start slot are
        excluded from the PMF arms with an explicit reason).
    out_path: when given, results are written write-once.

    Cold-start slots (pitcher or batter without PA-table history) are
    EXCLUDED from scoring: source_type = "cold_start_no_prior", PA
    probability null, explicit exclusion_reason. There is NO league-rate
    fallback (owner rule).

    Returns (per-PA probabilities frame, provenance summary dict)."""
    long, n_uncovered = projected_long(proj)
    p_daily = entity_daily_state(pa, "pitcher")
    b_daily = entity_daily_state(pa, "batter")
    lg = league_daily_state(pa)
    pf = attach_prior_features(long, p_daily, b_daily, lg)
    pf = add_block(pf)
    pf = pf.with_columns(
        pl.when(pl.col("cold_start") == 1)
        .then(pl.lit(SOURCE_TYPE_COLD_NO_PRIOR))
        .otherwise(pl.lit(SOURCE_TYPE_ENTITY))
        .alias("source_type")
    )
    cutoff = assert_cutoff(pf)
    # Cold-start slots are EXCLUDED from scoring (explicit, never a silent
    # league-rate fill): the frozen recipe declares no cold-start
    # probability, so their PA probability stays null with an explicit
    # exclusion_reason. Feature construction upstream keeps the registered
    # frozen w150/EW recipe (required for checkpoint verification); the
    # exclusion guarantees those league-derived features never reach a
    # scored probability.
    cold = pf.filter(pl.col("source_type") == SOURCE_TYPE_COLD_NO_PRIOR)
    scored = pf.filter(pl.col("source_type") != SOURCE_TYPE_COLD_NO_PRIOR)
    require_feature_columns(scored)
    scored = arm_probs(scored, models).with_columns(
        pl.lit(None, dtype=pl.Utf8).alias("exclusion_reason")
    )
    cold = cold.with_columns(
        pl.lit(None, dtype=pl.Float64).alias("p_h3_raw"),
        pl.lit(None, dtype=pl.Float64).alias("p_l5_raw"),
        pl.lit(EXCLUSION_REASON_COLD).alias("exclusion_reason"),
    )
    pf = pl.concat([scored, cold], how="vertical").sort(
        "game_date", "game_pk", "side", "slot"
    )
    assert_identity(pf)
    unseen = unseen_pairs_report(pf, pa)
    summary = {
        "n_projected_starts": proj.height,
        "n_uncovered_slots_dropped": n_uncovered,
        "n_pa_rows_scored": scored.height,
        "n_pa_rows_excluded_cold_start": cold.height,
        "cold_start_exclusion_reason": EXCLUSION_REASON_COLD,
        "cutoff": cutoff,
        "unseen_pairs": unseen,
    }
    if bf37_by_start is not None:
        pmf37_cols = list(PMF37_COLS)
        missing = [c for c in ["game_pk", "side", "pitcher", *pmf37_cols]
                   if c not in bf37_by_start.columns]
        if missing:
            raise AdapterError(f"BF PMF frame missing columns: {missing}")
        per_start = pf.group_by("game_pk", "side", "pitcher").agg(
            n_scored=(pl.col("exclusion_reason").is_null()).sum(),
            n_cold=(pl.col("source_type") == SOURCE_TYPE_COLD_NO_PRIOR).sum(),
        )
        bad_shape = per_start.filter(
            (pl.col("n_cold") == 0) & (pl.col("n_scored") != 9))
        if bad_shape.height:
            raise AdapterError(
                "start(s) without any cold slot do not carry exactly 9 "
                f"scored slots: {bad_shape.height} start(s)")
        # Starts containing a cold-start slot are excluded from the
        # count-PMF arms with an explicit reason (never league-rate
        # filled); only fully scored starts get PMFs.
        starts_ok = per_start.filter(
            (pl.col("n_cold") == 0) & (pl.col("n_scored") == 9)
        ).select("game_pk", "side", "pitcher")
        n_pmf_excluded_starts = per_start.filter(
            pl.col("n_cold") > 0).height
        scored_rows = pf.filter(
            pl.col("exclusion_reason").is_null()).join(
            starts_ok, on=["game_pk", "side", "pitcher"], how="semi")
        starts = scored_rows.sort("slot").group_by(
            "game_pk", "side", "pitcher").agg(
            pl.col("game_date").first().alias("game_date"),
            pl.col("p_h3_raw").sort_by("slot").alias("p9_h3"),
            pl.col("p_l5_raw").sort_by("slot").alias("p9_l5"),
        )
        # Registered BF wiring validation: unique start keys, complete
        # coverage of every scored start, valid pmf37 distributions, and
        # the registered cap-60 geometric-tail conversion. Fail-loud; no
        # invented replacement distributions.
        starts, bf_meta = validate_bf37_by_start(bf37_by_start, starts)
        pmf_h3, pmf_l5, mk_h3, mk_l5 = [], [], [], []
        for row in starts.iter_rows(named=True):
            p9_h3 = np.asarray(row["p9_h3"], dtype=np.float64)
            p9_l5 = np.asarray(row["p9_l5"], dtype=np.float64)
            if p9_h3.shape != (9,) or p9_l5.shape != (9,):
                raise AdapterError(
                    "start does not carry exactly 9 scored slots "
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
        # Null PMFs are allowed ONLY on cold-start rows and on rows of
        # starts that contain a cold-start slot (explicit exclusion);
        # anything else is a lineage error.
        cold_starts = per_start.filter(pl.col("n_cold") > 0).select(
            "game_pk", "side", "pitcher").with_columns(
            pl.lit(True).alias("start_has_cold_slot"))
        pf = pf.join(cold_starts, on=["game_pk", "side", "pitcher"],
                     how="left").with_columns(
            pl.col("start_has_cold_slot").fill_null(False))
        unexplained = pf.filter(
            pl.col("pmf_h3_raw").is_null()
            & (pl.col("source_type") != SOURCE_TYPE_COLD_NO_PRIOR)
            & ~pl.col("start_has_cold_slot")
        )
        if unexplained.height:
            raise AdapterError(
                "count-PMF join left null PMFs on non-excluded rows: "
                f"{unexplained.height} row(s)")
        pf = pf.drop("start_has_cold_slot")
        summary["n_starts_pmf_computed"] = starts.height
        summary["n_starts_pmf_excluded_cold_slot"] = n_pmf_excluded_starts
        summary["bf37"] = bf_meta
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
CHECKPOINT_PATH = Path(os.environ.get(
    "PAEXT_V2_CHECKPOINT_PATH",
    str(PAEXT_OUT_DIR / "checkpoints" / "h3_raw_checkpoint.json")))
BF_WORKLOAD_DIR = Path(os.environ.get(
    "BF_WORKLOAD_V1_DIR",
    r"C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1"))
BF_FORECASTS_RELPATH = Path("data") / "bf_forecasts.parquet"
# Registered pin (bf_lane/COUNT_REGISTRATION.md; bf-workload-v1 report.json
# inputs_sha256 -- identical value, independently registered).
REGISTERED_BF_FORECASTS_SHA256 = (
    "c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_bf_forecasts(directory: Path | None = None
                      ) -> tuple[pl.DataFrame, dict]:
    """Load the registered bf-workload-v1 BF PMF artifact
    (``data/bf_forecasts.parquet``) with provenance validation:
    - the artifact must exist -> ``BF_PMF_ARTIFACT_MISSING``;
    - its sha256 must equal the registered pin
      (``REGISTERED_BF_FORECASTS_SHA256``) -> ``BF_PMF_SHA_MISMATCH``.
    No fallback and no substitute distribution."""
    d = Path(directory) if directory else BF_WORKLOAD_DIR
    p = d / BF_FORECASTS_RELPATH
    if not p.exists():
        raise AdapterError(
            "BF_PMF_ARTIFACT_MISSING: registered BF PMF artifact not "
            f"found: {p}")
    sha = sha256_file(p)
    if sha != REGISTERED_BF_FORECASTS_SHA256:
        raise AdapterError(
            "BF_PMF_SHA_MISMATCH: BF PMF artifact sha256 %s does not match "
            "the registered pin %s for %s"
            % (sha, REGISTERED_BF_FORECASTS_SHA256, p))
    bf = pl.read_parquet(p)
    meta = {
        "artifact": "bf-workload-v1/data/bf_forecasts.parquet",
        "path": str(p),
        "sha256": sha,
        "registered_sha256": REGISTERED_BF_FORECASTS_SHA256,
        "n_rows": int(bf.height),
    }
    return bf, meta


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


def run_real(
    out_name: str = "projected_pa_probs_v1.parquet",
    *,
    tracking_uri: str | None = None,
    experiment: str = "pa-k-probability-v1",
    run_name: str = "pregame-pa-ext-v2-run_real",
    artifact_location: str | None = None,
    wrapper_path: Path | None = None,
    pipeline_id: str | None = None,
) -> dict:
    """Real-lineage driver (private lake required; never runs in CI).
    Loads the SERIALIZED frozen checkpoint artifact produced ONCE by
    ``build_checkpoint.py`` (deterministic refit + <=1e-8 verification
    gate at build time, sha256-pinned). The adapter NEVER refits and NEVER
    reconstructs at execution time: a missing artifact fails loud with
    MISSING_CHECKPOINT_ARTIFACT (no league-rate fallback, no
    reconstruction fallback). Output is write-once.

    BF37 wiring: loads the registered bf-workload-v1 BF PMF artifact
    (``load_bf_forecasts``: sha256 provenance gate against the registered
    pin) and passes it to ``build_projected_pa_probs``, whose
    ``validate_bf37_by_start`` enforces unique start keys, complete
    coverage of every scored start, finite/nonnegative/normalized pmf37
    rows, and the registered cap-60 geometric-tail conversion. Missing or
    mismatched BF inputs fail loud.

    Tracking (D-1 harness, count-eval-v1): when ``tracking_uri`` is given,
    the finalized run is logged through the SHARED count-eval-v1 tracking
    wrapper (``track_and_verify.log_run`` + ``verify_run`` -- the same
    module the frozen LightGBM command uses; no hand-replicated mlflow
    calls here). Logging happens strictly AFTER the canonical output is
    written write-once, so a tracking failure NEVER triggers a refit: the
    canonical outputs stay untouched on disk and ``TrackingFailure``
    surfaces to the caller. ``verify_run`` re-retrieves the run through a
    fresh MlflowClient (exact metric round-trip + output artifact
    byte-hash) and only a VERIFIED verdict is attached to the summary
    under ``summary["tracking"]``. The scoring run is tagged
    ``phase=scoring``; when ``pipeline_id`` is given it is also tagged
    ``pipeline_id=<id>`` so the scoring run and the matching
    ``phase=reconstruction`` run logged by ``build_checkpoint.py`` are
    retrievable as ONE pipeline (dual-phase linkage)."""
    proj = load_projected_lineups()
    pa = load_pa_table()
    models, ck = load_serialized_checkpoint()
    bf, bf_meta = load_bf_forecasts()
    pf, summary = build_projected_pa_probs(proj, pa, models,
                                           bf37_by_start=bf)
    out = write_once(pf, PAEXT_OUT_DIR / "outputs" / out_name)
    summary["checkpoint"] = ck
    summary["bf37_artifact"] = bf_meta
    summary["output"] = str(out)
    if tracking_uri is not None:
        tv = load_track_wrapper(wrapper_path)
        params, metrics, artifacts = describe_paext_run(summary, out)
        tags = {"phase": "scoring"}
        if pipeline_id is not None:
            tags["pipeline_id"] = str(pipeline_id)
        try:
            run_id = tv.log_run(tracking_uri, experiment, run_name,
                                params, metrics, artifacts,
                                artifact_location=artifact_location,
                                tags=tags)
            verdict = tv.verify_run(
                tracking_uri, run_id, metrics,
                "outputs/" + Path(out).name, tv.sha256_file(out),
                PAEXT_OUT_DIR / "outputs" / "retrieved")
        except Exception as exc:
            raise tv.TrackingFailure(
                "tracking failed after canonical outputs finalized "
                f"({out}); outputs preserved untouched, no refit"
            ) from exc
        if verdict["status"] != "VERIFIED":
            raise tv.TrackingFailure(
                "tracking verification MISMATCH: "
                + json.dumps(verdict, sort_keys=True))
        summary["tracking"] = verdict
    return summary


# -------------------------------------------------------- tracking (D-1)
TRACKING_WRAPPER_RELPATH = (Path("specs") / "count-eval-v2-spec" / "harness"
                            / "track_and_verify.py")
_TRACK_WRAPPER_CACHE: dict = {}


def load_track_wrapper(path: Path | None = None):
    """Import the SHARED count-eval-v1 tracking wrapper (D-1) by path --
    the identical module the frozen LightGBM command invokes; the adapter
    never re-implements logging, verification, or the failure contract.
    Cached per resolved path so exception classes keep a stable identity
    across call sites."""
    p = (Path(path) if path
         else Path(__file__).resolve().parents[1] / TRACKING_WRAPPER_RELPATH)
    p = p.resolve()
    if not p.exists():
        raise AdapterError(f"TRACKING_WRAPPER_MISSING: {p}")
    mod = _TRACK_WRAPPER_CACHE.get(str(p))
    if mod is not None:
        return mod
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pregame_pa_ext_track_and_verify", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _TRACK_WRAPPER_CACHE[str(p)] = mod
    return mod


def describe_paext_run(summary: dict, out_path: Path) -> tuple[dict, dict,
                                                               list]:
    """Map a run_real summary + finalized output to
    (params, metrics, artifacts) for the shared wrapper's log_run."""
    ck = summary.get("checkpoint", {}) or {}
    bf = summary.get("bf37_artifact", {}) or {}
    params = {
        "adapter": "pregame-pa-ext-v2",
        "output": Path(out_path).name,
        "checkpoint_sha256": str(ck.get("sha256", "")),
        "bf_pmf_sha256": str(bf.get("sha256", "")),
    }
    metrics = {
        "n_projected_starts": float(summary["n_projected_starts"]),
        "n_pa_rows_scored": float(summary["n_pa_rows_scored"]),
        "n_pa_rows_excluded_cold_start": float(
            summary["n_pa_rows_excluded_cold_start"]),
    }
    if "n_starts_pmf_computed" in summary:
        metrics["n_starts_pmf_computed"] = float(
            summary["n_starts_pmf_computed"])
    if "n_starts_pmf_excluded_cold_slot" in summary:
        metrics["n_starts_pmf_excluded_cold_slot"] = float(
            summary["n_starts_pmf_excluded_cold_slot"])
    artifacts = [(str(out_path), "outputs")]
    return params, metrics, artifacts
