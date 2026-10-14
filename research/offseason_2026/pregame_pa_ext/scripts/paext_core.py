"""pregame-pa-ext-v1 shared machinery.

Read-only reimplementation surface for the registered per-PA projected
probability payload (see scripts/preregistration.json, frozen before build).

Design rules:
- The pregame-state-v1 (v1) module is imported and its state builders,
  gates, log5/sigmoid helpers, count-PMF machinery, and bootstrap are used
  VERBATIM so this card inherits the accepted, G1/G2-verified machinery
  unchanged.
- Every function here is pure over injected frames (no file I/O except the
  explicit module-path constants), so tests can run synthetic + real
  lineage through the identical code path.
- The payload path NEVER touches realized outcomes: no y join, no
  realized_bf selection. The overnight-p2 preds files are read only by
  fit_models_verified() as a coefficient-verification oracle.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import polars as pl

# ------------------------------------------------------------------ paths
WORK = Path(__file__).resolve().parent.parent
PREGAME_STATE = Path(r"C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1")
P2_DATA = Path(r"C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data")
BFW = Path(r"C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data")
HELPERS = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\main-active\research\offseason_2026"
)
PAYLOAD = WORK / "data" / "predictor_payload.parquet"
MANIFEST = WORK / "manifest.json"
REPORT = WORK / "report.json"

_spec = importlib.util.spec_from_file_location(
    "pgs_v1", str(PREGAME_STATE / "scripts" / "run_pregame_state_comparison.py")
)
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)
sys.path.insert(0, str(HELPERS))
from kcount_combiner import (  # noqa: E402
    KCOUNT_CAP, bf_pmf_from_37, count_logscore, count_rps, exceedance,
)

# ------------------------------------------------------- frozen constants
K_MAX = v1.K_MAX                    # 24; last PMF bucket absorbs >= 23
MILESTONES = v1.MILESTONES          # (6, 8, 10, 12)
BOOT_N = v1.BOOT_N                  # 2000
BOOT_SEED = v1.BOOT_SEED            # 20261001
P_CLIP = v1.P_CLIP                  # 1e-9
EPS = v1.EPS
W_PRIOR = v1.W_PRIOR                # 150
HALF_LIFE_DAYS = v1.HALF_LIFE_DAYS  # 90.0
FEAT_H3 = list(v1.FEAT_H3)
N_ARR = v1.N_ARR                    # (60, 1) arange(1..60)
WINDOW = (pl.date(2024, 7, 1), pl.date(2025, 12, 31))
EXPECTED_N_STARTS = 7194

SOURCE_TYPE_ENTITY = "entity_history"
SOURCE_TYPE_COLD = "league_prior_no_entity_history"
SOURCE_TYPE_FALLBACK = "league_rate_fill_uncovered_slot"

SRC_DATE_COLS = [
    "src_date_pitcher", "src_date_batter",
    "src_date_ew_pitcher", "src_date_ew_batter",
]
PREDS = dict(v1.PREDS)
BLOCK_TRAIN_END = dict(v1.BLOCK_TRAIN_END)
BLOCKS = ["block_2024H2", "block_2025H1", "confirm_2025H2"]
PMF37_COLS = [f"pmf37_{j}" for j in range(37)]
PMF_COLS = {
    "h3_raw": [f"pmf_h3_raw_{k}" for k in range(K_MAX)],
    "l5_raw": [f"pmf_l5_raw_{k}" for k in range(K_MAX)],
}
ARM_TAGS = {"h3_raw": "p_h3_raw", "l5_raw": "p_l5_raw"}


def sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------- runtime checks
def check_prob_vec(p: np.ndarray, ctx: str) -> None:
    assert np.all(np.isfinite(p)), f"non-finite prob: {ctx}"
    assert float(p.min()) >= 0.0 and float(p.max()) <= 1.0, \
        f"prob out of [0,1]: {ctx}"


def check_pmf(p_k: np.ndarray, ctx: str) -> None:
    assert np.all(np.isfinite(p_k)), f"non-finite PMF: {ctx}"
    assert float(p_k.min()) >= 0.0, f"PMF < 0: {ctx}"
    assert float(p_k.max()) <= 1.0, f"PMF > 1: {ctx}"
    assert abs(float(p_k.sum()) - 1.0) <= 1e-9, f"PMF sum != 1: {ctx}"
    cdf = np.cumsum(p_k)
    assert bool((np.diff(cdf) >= -1e-12).all()), f"CDF not monotone: {ctx}"


# ------------------------------------------------------------- projection
def projected_long(proj_slots: pl.DataFrame, prefix: str = "u") -> pl.DataFrame:
    """Accepted unique-batter v2 lineups -> one row per (start, slot).
    Uncovered slots (null batter) are KEPT (fallback path); covered slots
    must carry a batter id. Asserts the start keys are unique."""
    slot_cols = [f"{prefix}_slot_{i}" for i in range(1, 10)]
    dup_starts = proj_slots.group_by("game_pk", "side", "pitcher").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    assert dup_starts == 0, "projected start keys not unique"
    long = proj_slots.select(
        "game_pk", "side", "pitcher", "game_date", "nine_distinct",
        *slot_cols,
    ).unpivot(
        index=["game_pk", "side", "pitcher", "game_date", "nine_distinct"],
        on=slot_cols,
        variable_name="slot_name", value_name="batter",
    ).with_columns(
        pl.col("slot_name").str.extract(r"(\d+)").cast(pl.Int32).alias("slot")
    ).drop("slot_name").sort("game_date", "game_pk", "side", "slot")
    dup = long.group_by("game_pk", "side", "pitcher", "slot").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    assert dup == 0, "projected (start, slot) keys not unique"
    return long


def attach_prior_features(
    long: pl.DataFrame,
    p_daily: pl.DataFrame,
    b_daily: pl.DataFrame,
    lg: pl.DataFrame,
) -> pl.DataFrame:
    """Frozen prior-only features per projected (start, slot, batter) PA,
    with full provenance. Mirrors pregame-state-v1 build_slot_probabilities
    joins exactly (asof at the start's game_date by pitcher / batter,
    league asof), plus per-row source dates and source types. Uncovered
    slots (null batter) fall through the joins to the league-rate fill."""
    long = long.with_columns(
        pl.col("batter").is_null().alias("slot_uncovered")
    ).sort("game_date")
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
    pf = v1.attach_league_asof(pf, lg)
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
        pl.when(pl.col("slot_uncovered"))
        .then(pl.lit(SOURCE_TYPE_FALLBACK))
        .when(pl.col("prior_n_batter") == 0)
        .then(pl.lit(SOURCE_TYPE_COLD)).otherwise(pl.lit(SOURCE_TYPE_ENTITY))
        .alias("src_type_batter"),
    ).with_columns(
        *[pl.col(c).fill_null(pl.col("lg_src_date")) for c in SRC_DATE_COLS]
    )
    return pf


def add_block(pf: pl.DataFrame) -> pl.DataFrame:
    """Block assignment identical to pregame-state-v1 (fixed date bounds)."""
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
    BEFORE the start's forecast cutoff (game_date). Returns summary stats."""
    n_rows = pf.height
    for col in SRC_DATE_COLS + ["lg_src_date"]:
        n_null = pf.filter(pl.col(col).is_null()).height
        assert n_null == 0, f"cutoff gate: {col} null on {n_null} rows"
        bad = pf.filter(pl.col(col) >= pl.col("game_date")).height
        assert bad == 0, f"cutoff gate: {col} >= game_date on {bad} rows"
    max_src = pf.select(pl.max_horizontal(SRC_DATE_COLS)).to_series()
    lag = (pf["game_date"] - max_src).dt.total_days()
    return {
        "n_rows": n_rows,
        "all_source_dates_strictly_before_cutoff": True,
        "mean_source_lag_days": float(lag.mean()),
        "min_source_lag_days": int(lag.min()),
    }


def assert_no_current_or_future_state(pf: pl.DataFrame) -> None:
    """Alias of the cutoff gate kept for readability at call sites."""
    return assert_cutoff(pf)


# ------------------------------------------------------------------ arms
def fit_models_from_frames(train: pl.DataFrame, cal: pl.DataFrame) -> tuple:
    """One block's frozen arm fit: StandardScaler + LogisticRegression(C=1.0)
    on FEAT_H3, sigmoid calibrators for H3 and log5 on `cal`. Used directly
    by fit_models_verified (real lineage) and by synthetic tests."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(train.select(FEAT_H3).to_numpy())
    lr = LogisticRegression(C=1.0, max_iter=1000)
    lr.fit(scaler.transform(train.select(FEAT_H3).to_numpy()),
           train["y"].to_numpy().astype(int))
    y_ca = cal["y"].to_numpy().astype(int)
    a_h3, b_h3 = v1.sigmoid_fit(
        y_ca, lr.predict_proba(
            scaler.transform(cal.select(FEAT_H3).to_numpy()))[:, 1])
    a_l5, b_l5 = v1.sigmoid_fit(
        y_ca, v1.log5(cal["p_pitcher_prior_w150"].to_numpy(),
                      cal["p_batter_prior_w150"].to_numpy(),
                      cal["lg_rate"].to_numpy()))
    return (scaler, lr, (a_h3, b_h3), (a_l5, b_l5))


def fit_models_verified(feat: pl.DataFrame, pa: pl.DataFrame) -> tuple:
    """Deterministic reconstruction of the FROZEN overnight-p2 checkpoint
    coefficients (run_ladder.py recipe, unchanged), verified bit-compatibly
    against the stored preds checkpoints BEFORE any projected-row inference
    (pregame-state-v1 G2 mechanism, extended to pred_LOG5_raw). Raises
    AssertionError (STOP) on any mismatch. Also verifies pred_LOG5_raw."""
    models, verify = {}, {}
    for block in BLOCKS:
        fname = PREDS[block]
        preds = pl.read_parquet(P2_DATA / fname)
        te_y, te_m, te_d = BLOCK_TRAIN_END[block]
        cal_last = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") <= pl.date(te_y, te_m, te_d))
        )["game_date"].max()
        cal_first = cal_last - timedelta(days=59)
        y_keyed = pa.select("game_pk", "at_bat_number", "batter", "y")
        train = (
            feat.filter(
                (pl.col("game_date") >= pl.date(2023, 1, 1))
                & (pl.col("game_date") < cal_first)
            )
            .join(y_keyed, on=["game_pk", "at_bat_number", "batter"],
                  how="inner")
        )
        cal = (
            feat.filter(
                (pl.col("game_date") >= cal_first)
                & (pl.col("game_date") <= cal_last)
            )
            .join(y_keyed, on=["game_pk", "at_bat_number", "batter"],
                  how="inner")
        )
        scaler, lr, (a_h3, b_h3), (a_l5, b_l5) = \
            fit_models_from_frames(train, cal)

        joined = preds.join(
            feat.select("game_pk", "at_bat_number", "batter", *FEAT_H3),
            on=["game_pk", "at_bat_number", "batter"], how="left",
        )
        assert joined.height == preds.height
        assert joined["ew_pitcher"].null_count() == 0
        X = scaler.transform(joined.select(FEAT_H3).to_numpy())
        p_h3_raw = lr.predict_proba(X)[:, 1]
        p_h3_cal = v1.sigmoid_apply(p_h3_raw, a_h3, b_h3)
        p_l5_raw = v1.log5(joined["p_pitcher_prior_w150"].to_numpy(),
                           joined["p_batter_prior_w150"].to_numpy(),
                           joined["lg_rate"].to_numpy())
        p_l5_cal = v1.sigmoid_apply(p_l5_raw, a_l5, b_l5)
        d_h3r = float(np.abs(p_h3_raw - joined["pred_H3_raw"].to_numpy()).max())
        d_h3c = float(np.abs(p_h3_cal - joined["pred_H3_cal"].to_numpy()).max())
        d_l5r = float(np.abs(p_l5_raw - joined["pred_LOG5_raw"].to_numpy()).max())
        d_l5c = float(np.abs(p_l5_cal - joined["pred_LOG5_cal"].to_numpy()).max())
        assert d_h3r <= 1e-8 and d_h3c <= 1e-8 \
            and d_l5r <= 1e-8 and d_l5c <= 1e-8, (
            f"STOP: frozen checkpoint verification FAILED for {block}: "
            f"H3_raw={d_h3r:.3e} H3_cal={d_h3c:.3e} "
            f"LOG5_raw={d_l5r:.3e} LOG5_cal={d_l5c:.3e}")
        verify[block] = {"n_rows": preds.height,
                         "max_abs_diff": {"H3_raw": d_h3r, "H3_cal": d_h3c,
                                          "LOG5_raw": d_l5r,
                                          "LOG5_cal": d_l5c}}
        models[block] = (scaler, lr, (a_h3, b_h3), (a_l5, b_l5))
    return models, verify


def arm_probs(pf: pl.DataFrame, models: dict) -> pl.DataFrame:
    """Apply the verified frozen arms to projected-row features. Mirrors
    pregame-state-v1 build_slot_probabilities exactly; adds the RAW arm
    outputs. Every projected row must land in a known block."""
    h3_raw = np.full(pf.height, np.nan)
    h3_cal = np.full(pf.height, np.nan)
    l5_raw = np.full(pf.height, np.nan)
    l5_cal = np.full(pf.height, np.nan)
    block_arr = pf["block"].to_numpy()
    for block, (scaler, lr, (a_h3, b_h3), (a_l5, b_l5)) in models.items():
        m = block_arr == block
        if not m.any():
            continue  # block absent from this slice (e.g. single-start tests)
        sub = pf.filter(pl.Series(m))
        raw = lr.predict_proba(
            scaler.transform(sub.select(FEAT_H3).to_numpy()))[:, 1]
        raw5 = v1.log5(sub["p_pitcher_prior_w150"].to_numpy(),
                       sub["p_batter_prior_w150"].to_numpy(),
                       sub["lg_rate"].to_numpy())
        h3_raw[m] = raw
        h3_cal[m] = v1.sigmoid_apply(raw, a_h3, b_h3)
        l5_raw[m] = raw5
        l5_cal[m] = v1.sigmoid_apply(raw5, a_l5, b_l5)
    assert not np.isnan(h3_raw).any(), "projected row outside known blocks"
    return pf.with_columns(
        pl.Series("p_h3_raw", np.clip(h3_raw, P_CLIP, 1 - P_CLIP)),
        pl.Series("p_h3_cal", np.clip(h3_cal, P_CLIP, 1 - P_CLIP)),
        pl.Series("p_l5_raw", np.clip(l5_raw, P_CLIP, 1 - P_CLIP)),
        pl.Series("p_l5_cal", np.clip(l5_cal, P_CLIP, 1 - P_CLIP)),
    )


# ------------------------------------------------------- count aggregation
def cycled_cond_mean(p9: np.ndarray) -> np.ndarray:
    """pbar_n = mean of the projected nine per-PA probabilities cycled to
    n, n = 1..KCOUNT_CAP (identical to pregame-state-v1)."""
    assert p9.shape == (9,)
    cycled = np.tile(p9, KCOUNT_CAP // 9 + 1)[:KCOUNT_CAP]
    return np.clip(
        np.cumsum(cycled) / np.arange(1, KCOUNT_CAP + 1), P_CLIP, 1 - P_CLIP
    )


def start_count_pmf(p9: np.ndarray, bf37: np.ndarray) -> tuple:
    """P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n) with the shared BF PMF;
    returns (pmf 0..K_MAX-1, mean_k, bf_ext, pbar)."""
    check_prob_vec(p9, "p9")
    bf_ext = bf_pmf_from_37(np.asarray(bf37, dtype=np.float64))
    pbar = cycled_cond_mean(np.asarray(p9, dtype=np.float64))
    check_prob_vec(pbar, "pbar")
    pk = v1.count_pmf_from_mixture(bf_ext, pbar)
    check_pmf(pk, "count PMF")
    mean_k = float((bf_ext * N_ARR[:, 0] * pbar).sum())
    return pk, mean_k, bf_ext, pbar


def realized_row_features(
    pa: pl.DataFrame,
    p_daily: pl.DataFrame,
    b_daily: pl.DataFrame,
    lg: pl.DataFrame,
) -> pl.DataFrame:
    """Prior features for every realized PA row (gate1 'mine' semantics,
    G1-verified against features_v3) - used by synthetic tests to build a
    consistent training frame without reading any checkpoint."""
    rows = pa.select(
        "game_pk", "at_bat_number", "batter", "pitcher", "game_date",
    ).with_columns(pl.lit(False).alias("slot_uncovered")).sort("game_date")
    pf = attach_prior_features(rows, p_daily, b_daily, lg)
    return pf
