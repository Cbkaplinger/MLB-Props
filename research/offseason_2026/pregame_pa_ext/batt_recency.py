"""Batter-history challenger (pregame-pa-ext-v2 diagnostic) - SPECIFICATION
IMPLEMENTATION ONLY. Implements card
proposal_batt_recency_diagnostic_2026-10-20.md v3 (published 3e7030f, design
passed by Chat 2). NO real-data fitting or evaluation has been authorized or
performed: the fitting/evaluation stage is gated behind
--i-accept-fitting-execution and remains unexecuted on real data.

Design (v3, unchanged):
- ONE batter-only challenger. Pitcher features, lg_rate, counts, cold_start,
  ew_pitcher, lineup construction, BF inputs, and eligibility are UNCHANGED
  from the frozen recipe. Batter features p_batter_prior_w150 + ew_batter are
  REPLACED by p_batt_recent + p_batt_anchor (8 features total).
- History split at forecast date t: RECENT = rows with d_i in (t-60d, t);
  ANCHOR = rows with d_i <= t-60d. Strictly prior (rows at t enter nothing).
  Disjoint by construction - no appearance enters both components.
- Anchor (age-aware confidence): forecast-date-anchored weights
  w_i(t) = 2^(-(t - d_i)/90) (frozen half-life 90d). Weighted K mass
  WK(t) = sum w_i k_i; DECAYED PA MASS M(t) = sum w_i n_i - the declared
  confidence measure (NOT statistical effective sample size). Anchor rate
  shrunk to the as-of league rate:
      p_anchor = (WK + 150 * lg_rate) / (M + 150)
  (same w150 weight and target as the frozen recipe). Empty anchor pool:
  p_anchor = lg_rate - an INTERNAL FEATURE DEFAULT, never permission to
  score; the registered cold_start_no_prior exclusion is untouched.
- Update rule (m = 30 pseudo-PA): p_batt_recent = (k_win + 30 * p_anchor)
  / (n_win + 30). Newcomer-adjacent batters approach the league rate as
  their evidence shrinks, by construction of the weighted denominators.
- Training/inference consistency: the SAME feature builder constructs both
  the historical training rows (as of each row's own date) and the
  evaluation rows; the same model family (StandardScaler +
  LogisticRegression(C=1.0, max_iter=1000)) is REFIT per development block
  on the rebuilt features. Frozen checkpoint coefficients are never fed
  challenger features.
- Exclusion policy: UNCHANGED. Zero-history entities keep the registered
  cold_start_no_prior exclusion; this module never grants scoring
  permission and never writes exclusion or cold-start columns.

Deterministic development-key serialization (v3.1, resolves the review
finding): both frozen development key sets are canonicalized as
- encoding UTF-8; separator "|" (U+007C); line separator LF (0x0A);
- NO trailing newline after the final line; NO header; no padding;
- ordering: ascending by (game_pk numeric, side ASCII, slot numeric) for
  slot keys, ascending by (game_pk numeric, at_bat_number numeric) for
  evaluation keys; each set MUST be duplicate-free (asserted);
- slot key line = f"{game_pk}|{side}|{slot}" with side exactly the frozen
  artifact literal ("Bot" / "Top"); evaluation key line =
  f"{game_pk}|{at_bat_number}";
- NO dates in the key stream: (game_pk, side, slot) uniquely determines
  game_date inside the frozen lineup artifact (asserted at verification),
  so a date column would be redundant, not identity-bearing;
- hash = sha256 over the exact byte stream.
The earlier provisional pins (82592f18..., c6568151...) were computed with
this exact byte format; what was missing was the declaration above. The
recomputation under this declared format reproduces them byte-for-byte
(verified in PUBLISHED_* constants + tests/test_batt_recency_diagnostic.py);
no serialization was chosen to force a match - the format stands on being
the minimal identifying tuple with a total order and a canonical encoding.

Run stages:
  python research/offseason_2026/pregame_pa_ext/batt_recency.py --verify-keys-only
      read-only: recompute the frozen development key sets from the
      preserved run ledger + frozen artifacts and assert the published
      hashes (no fitting).
  python research/offseason_2026/pregame_pa_ext/batt_recency.py \
      --i-accept-fitting-execution ...
      GATED fitting/evaluation stage - NOT AUTHORIZED; has never been run
      on real data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pregame_pa_ext import adapter as ad  # noqa: E402

# ------------------------------------------------------------- frozen config
RECENT_DAYS = 60
M_PSEUDO = 30.0
ANCHOR_W = 150.0  # same w150 weight/target as the frozen recipe

CHALLENGER_FEATURES = [
    "p_pitcher_prior_w150", "p_batt_recent", "p_batt_anchor", "lg_rate",
    "n_prior_pitcher", "n_prior_batter", "cold_start", "ew_pitcher",
]
DROPPED_BATTER_FEATURES = ["p_batter_prior_w150", "ew_batter"]

DEV_BLOCKS = ["block_2024H2", "block_2025H1"]
PROTECTED_BLOCK = "confirm_2025H2"

# Published deterministic hashes (sha256 over the canonical byte streams
# defined in the module docstring; recomputed from the frozen artifacts +
# preserved run ledger on 2026-10-20 and re-verified by --verify-keys-only).
PUBLISHED_DEV_SLOT_KEYS_SHA256 = (
    "82592f18f824359e9a48848acf7662c040edc5e3284ed6f4a1741137606318ef")
PUBLISHED_DEV_EVAL_KEYS_SHA256 = (
    "c65681512d5de924e842e80d7c7f27369889590f1c46111eec11e25acb50f902")
PUBLISHED_DEV_SLOT_KEYS_N = 43407
PUBLISHED_DEV_EVAL_KEYS_N = 82817

# ------------------------------------------------- canonical key serialization
def _canon_bytes(lines: list[str]) -> bytes:
    """Encode a canonical key stream: the caller passes UNIQUE lines in the
    declared (numeric/ASCII tuple) order; this function validates
    duplicate-freeness and joins with LF, UTF-8, no trailing newline. It
    must NOT re-sort (numeric tuple order != lexicographic line order)."""
    dup = len(lines) - len(set(lines))
    if dup:
        raise ValueError(f"canonical key stream not duplicate-free: {dup}")
    return "\n".join(lines).encode("utf-8")


def serialize_slot_keys(keys) -> bytes:
    """Canonical byte stream for dev eligible projected-slot keys.
    keys: iterable of (game_pk:int, side:str, slot:int). Ordering:
    ascending by the NUMERIC/ASCII tuple (game_pk, side, slot); the line
    stream is then the sorted tuples joined with LF (no trailing newline).
    A duplicate key is a construction defect and fails loud."""
    tuples = [(int(g), str(s), int(k)) for g, s, k in keys]
    if len(tuples) != len(set(tuples)):
        raise ValueError("duplicate key in slot key set")
    return _canon_bytes(["%d|%s|%d" % t for t in sorted(set(tuples))])


def serialize_eval_keys(keys) -> bytes:
    """Canonical byte stream for dev evaluation observed-PA keys.
    keys: iterable of (game_pk:int, at_bat_number:int). Ordering:
    ascending by the NUMERIC tuple (game_pk, at_bat_number) - numeric, not
    lexicographic (at_bat_number is variable-width). A duplicate key is a
    construction defect and fails loud."""
    tuples = [(int(g), int(a)) for g, a in keys]
    if len(tuples) != len(set(tuples)):
        raise ValueError("duplicate key in evaluation key set")
    return _canon_bytes(["%d|%d" % t for t in sorted(set(tuples))])


def sha256_stream(stream: bytes) -> str:
    return hashlib.sha256(stream).hexdigest()


# --------------------------------------------------------- state machinery
def batt_daily_cums(pa: pl.DataFrame) -> pl.DataFrame:
    """Per (batter, game_date) INCLUSIVE cumulative + forecast-anchored-EW
    building blocks. Same weight convention as adapter.entity_daily_state
    (2^(dnum/90), dnum = days since epoch) but returns the UNSHIFTED cums:
    callers form disjoint recent/anchor components from the two as-of
    boundaries. Reuses the shared battery of conventions; nothing here is
    a new rolling framework."""
    return (
        pa.group_by("batter", "game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort("batter", "game_date")
        .with_columns(
            (pl.col("game_date") - pl.date(1970, 1, 1))
            .dt.total_days().cast(pl.Float64).alias("dnum"),
        )
        .with_columns(
            pl.col("k").cum_sum().over("batter").alias("cum_k"),
            pl.col("n").cum_sum().over("batter").alias("cum_n"),
            ((2.0 ** (pl.col("dnum") / ad.HALF_LIFE_DAYS))
             * pl.col("k").cast(pl.Float64))
            .cum_sum().over("batter").alias("ew_k_cum"),
            ((2.0 ** (pl.col("dnum") / ad.HALF_LIFE_DAYS))
             * pl.col("n").cast(pl.Float64))
            .cum_sum().over("batter").alias("ew_den_cum"),
        )
        .select("batter", "game_date", "cum_k", "cum_n",
                "ew_k_cum", "ew_den_cum")
        .sort("game_date")
    )


def _drop_cols(df: pl.DataFrame, *names: str) -> pl.DataFrame:
    return df.drop([n for n in names if n in df.columns])


def attach_batt_recency(rows: pl.DataFrame, daily: pl.DataFrame,
                        lg: pl.DataFrame) -> pl.DataFrame:
    """Attach the challenger batter features to `rows` (each row carries
    batter + game_date; t = game_date). Same builder for training rows and
    evaluation rows (identical construction guarantee).

    Prior-state convention: IDENTICAL to the frozen recipe - the adapter's
    asof(t) on the SHIFTED daily table takes the state strictly before the
    entity's last game date L <= t (prior_n = rows < L; a same-day row at t
    enters nothing). The challenger splits THAT SAME set at the 60-day
    boundary:
      RECENT = rows with t-60d < d_i < L        -> raw counts (k_win, n_win)
      ANCHOR = rows with d_i <= t-60d and d_i < L -> forecast-date-anchored
               EW: WK(t) = sum 2^(-(t-d_i)/90) k_i, and DECAYED PA MASS
               M(t) = sum 2^(-(t-d_i)/90) n_i (the declared confidence,
               not statistical effective sample size)
    so n_win + n_anchor_raw == prior_n exactly (no double counting, no
    gaps) and the anchor decays toward the league rate as its mass ages.
    """
    need = {"batter", "game_date"}
    if not need.issubset(rows.columns):
        raise ValueError(
            f"rows missing columns: {sorted(need - set(rows.columns))}")
    r = rows.with_columns(
        (pl.col("game_date") - timedelta(days=RECENT_DAYS)).alias("_t_m60"),
        ((pl.col("game_date") - pl.date(1970, 1, 1))
         .dt.total_days().cast(pl.Float64).alias("_t_dnum")),
    )
    # SHIFTED daily view (frozen convention): row d carries the state
    # strictly before d. L_date (data) + L_asof (key) both hold the row's
    # own date so L survives the join under any key-name handling.
    S = daily.with_columns(
        pl.col("cum_k").shift(1).over("batter").fill_null(0).alias("s_k"),
        pl.col("cum_n").shift(1).over("batter").fill_null(0).alias("s_n"),
        pl.col("ew_k_cum").shift(1).over("batter").fill_null(0.0)
        .alias("s_ewk"),
        pl.col("ew_den_cum").shift(1).over("batter").fill_null(0.0)
        .alias("s_ewn"),
        pl.col("game_date").shift(1).over("batter").alias("s_prev_date"),
        pl.col("game_date").alias("L_date"),
        pl.col("game_date").alias("L_asof"),
    ).drop("cum_k", "cum_n", "ew_k_cum", "ew_den_cum", "game_date")
    # asof(t): the L row (last game date <= t) with the shifted state.
    r = r.sort("game_date").join_asof(
        S, left_on="game_date", right_on="L_asof", by="batter",
        strategy="backward")
    r = _drop_cols(r, "L_asof")
    # asof(t-60d) on the UNSHIFTED daily: the anchor boundary row a (last
    # date <= t-60d) with INCLUSIVE cums (rows <= a).
    A = daily.rename({
        "cum_k": "cum_k_a", "cum_n": "cum_n_a",
        "ew_k_cum": "ew_k_a", "ew_den_cum": "ew_den_a",
        "game_date": "anchor_date_data",
    }).with_columns(
        pl.col("anchor_date_data").alias("anchor_asof"),
    )
    r = r.sort("_t_m60").join_asof(
        A, left_on="_t_m60", right_on="anchor_asof", by="batter",
        strategy="backward")
    r = _drop_cols(r, "anchor_asof").sort("game_date")
    r = r.with_columns(
        pl.col("s_k").fill_null(0), pl.col("s_n").fill_null(0),
        pl.col("s_ewk").fill_null(0.0), pl.col("s_ewn").fill_null(0.0),
        pl.col("cum_k_a").fill_null(0), pl.col("cum_n_a").fill_null(0),
        pl.col("ew_k_a").fill_null(0.0), pl.col("ew_den_a").fill_null(0.0),
        pl.col("_t_dnum").fill_null(0.0),
    )
    # Boundary cases under the frozen row convention:
    # - no prior game (L null): empty prior state.
    # - L <= t-60d: the ENTIRE prior set (rows < L) is the anchor; the
    #   recent window is empty.
    # - L > t-60d: anchor = rows <= t-60d; recent = rows in (t-60d, L).
    # Decay uses forecast-date-anchored factors: a mass stored with epoch
    # weights 2^(d/90) is scaled by 2^(-t_dnum/90) to yield
    # sum 2^(-(t-d_i)/90) n_i (the decayed PA mass at t).
    scale = (2.0 ** (-pl.col("_t_dnum") / ad.HALF_LIFE_DAYS))
    r = r.with_columns(
        pl.when(pl.col("L_date").is_null())
        .then(0)
        .when(pl.col("L_date") <= pl.col("_t_m60"))
        .then(pl.col("s_n"))
        .otherwise(pl.col("cum_n_a"))
        .alias("n_batt_anchor_raw"),
        pl.when(pl.col("L_date").is_null())
        .then(0)
        .when(pl.col("L_date") <= pl.col("_t_m60"))
        .then(0)
        .otherwise(pl.col("s_n") - pl.col("cum_n_a"))
        .alias("n_batt_win"),
        pl.when(pl.col("L_date").is_null())
        .then(0)
        .when(pl.col("L_date") <= pl.col("_t_m60"))
        .then(0)
        .otherwise(pl.col("s_k") - pl.col("cum_k_a"))
        .alias("k_batt_win"),
        pl.when(pl.col("L_date").is_null())
        .then(pl.lit(None, dtype=pl.Date))
        .when(pl.col("L_date") <= pl.col("_t_m60"))
        .then(pl.col("s_prev_date"))
        .otherwise(pl.col("anchor_date_data"))
        .alias("src_date_batt_anchor"),
        pl.col("s_prev_date").alias("src_date_batt_recent"),
    ).with_columns(
        (pl.when(pl.col("L_date") <= pl.col("_t_m60"))
         .then(pl.col("s_ewn"))
         .otherwise(pl.col("ew_den_a")) * scale).alias("mass_anchor"),
        (pl.when(pl.col("L_date") <= pl.col("_t_m60"))
         .then(pl.col("s_ewk"))
         .otherwise(pl.col("ew_k_a")) * scale).alias("wk_anchor"),
    )
    if "lg_rate" not in r.columns:
        r = ad.attach_league_asof(r, lg)
    r = r.with_columns(
        pl.when(pl.col("mass_anchor") > 0)
        .then((pl.col("wk_anchor") + ANCHOR_W * pl.col("lg_rate"))
              / (pl.col("mass_anchor") + ANCHOR_W))
        .otherwise(pl.col("lg_rate"))
        .alias("p_batt_anchor"),
    ).with_columns(
        ((pl.col("k_batt_win") + M_PSEUDO * pl.col("p_batt_anchor"))
         / (pl.col("n_batt_win") + M_PSEUDO)).alias("p_batt_recent"),
    )
    # cutoff-gate provenance: fill missing source dates with the league
    # source date (same convention as the frozen recipe's SRC_DATE_COLS).
    if "lg_src_date" in r.columns:
        r = r.with_columns(
            pl.col("src_date_batt_recent").fill_null(pl.col("lg_src_date")),
            pl.col("src_date_batt_anchor").fill_null(pl.col("lg_src_date")),
        )
    return r


def challenger_feature_frame(rows: pl.DataFrame, pa: pl.DataFrame) -> pl.DataFrame:
    """Full challenger feature frame: frozen pitcher-side/league features
    (adapter machinery, unchanged) + the challenger batter features. The
    replaced frozen batter columns are dropped; the final feature list is
    asserted."""
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    feat = ad.attach_prior_features(rows, p_daily, b_daily, lg)
    feat = feat.filter(pl.col("lg_rate").is_finite())
    feat = ad.add_block(feat)
    feat = attach_batt_recency(feat, batt_daily_cums(pa), lg)
    for c in DROPPED_BATTER_FEATURES:
        if c in feat.columns:
            feat = feat.drop(c)
    missing = [c for c in CHALLENGER_FEATURES if c not in feat.columns]
    if missing:
        raise ValueError(f"challenger feature frame missing: {missing}")
    return feat


# ------------------------------------------------------------- model family
def fit_challenger_models(train: pl.DataFrame) -> dict:
    """Same model family as the frozen recipe (StandardScaler +
    LogisticRegression(C=1.0, max_iter=1000)) on CHALLENGER_FEATURES.
    GATED: callable only from the --i-accept-fitting-execution stage or
    synthetic tests."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(train.select(CHALLENGER_FEATURES).to_numpy())
    lr = LogisticRegression(C=1.0, max_iter=1000)
    lr.fit(scaler.transform(train.select(CHALLENGER_FEATURES).to_numpy()),
           train["y"].to_numpy().astype(int))
    return {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coef": lr.coef_[0].tolist(),
        "intercept": float(lr.intercept_[0]),
        "features": list(CHALLENGER_FEATURES),
    }


def apply_challenger(features: pl.DataFrame, model: dict) -> np.ndarray:
    if list(model["features"]) != CHALLENGER_FEATURES:
        raise ValueError("challenger model feature list mismatch")
    X = features.select(CHALLENGER_FEATURES).to_numpy()
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    z = (X - mean) / scale
    eta = z @ coef + model["intercept"]
    p = 1.0 / (1.0 + np.exp(-eta))
    if not np.all(np.isfinite(p)):
        raise ValueError("non-finite challenger probability")
    return np.clip(p, ad.P_CLIP, 1.0 - ad.P_CLIP)


# ------------------------------------------------- observed-PA evaluation join
def observed_pa_join(eligible_slots: pl.DataFrame,
                     pa: pl.DataFrame) -> pl.DataFrame:
    """IDENTITY join (game_pk, pitcher, batter, game_date) of eligible
    projected slots to the frozen pa_table - the observed instances of the
    projected matchup. Grain: (game_pk, at_bat_number), verified unique
    (each observed PA contributes exactly once; a PA's recorded pitcher
    selects at most one projected slot). PAs against other pitchers are
    structurally excluded (they test a different matchup). Unobserved
    projected matchups contribute zero rows - never an invented outcome."""
    need = {"game_pk", "side", "pitcher", "batter", "slot", "game_date"}
    if not need.issubset(eligible_slots.columns):
        raise ValueError(
            f"eligible slots missing columns: {sorted(need - set(eligible_slots.columns))}")
    j = eligible_slots.select(
        "game_pk", "side", "pitcher", "batter", "slot", "game_date"
    ).join(
        pa.select("game_pk", "at_bat_number", "pitcher", "batter",
                  "game_date", "y"),
        on=["game_pk", "pitcher", "batter", "game_date"], how="inner",
    )
    dup = j.group_by("game_pk", "at_bat_number").agg(n=pl.len())
    dup = dup.filter(pl.col("n") > 1)
    if dup.height:
        raise ValueError(
            "observed-PA join not unique on (game_pk, at_bat_number): "
            f"{dup.height} duplicated key(s)")
    return j


def eligible_slots_from_ledger(ledger: pl.DataFrame,
                               blocks) -> pl.DataFrame:
    """Eligible projected slots from the preserved run ledger (read-only):
    scored rows only (exclusion_reason null) in the given blocks. The
    registered cold_start_no_prior exclusion is applied upstream by the
    frozen adapter; this filter never re-admits an excluded row."""
    e = ledger.filter(
        pl.col("exclusion_reason").is_null()
        & pl.col("block").is_in(list(blocks))
    )
    return e.select("game_pk", "side", "pitcher", "batter", "slot",
                    "game_date", "block")


# ------------------------------------------------------ frozen-key verification
def verify_published_keys(ledger: pl.DataFrame, pa: pl.DataFrame) -> dict:
    """Recompute both frozen development key sets from the preserved run
    ledger + frozen pa_table and assert the published hashes/counts.
    Read-only; used by --verify-keys-only and by synthetic tests (on
    synthetic fixtures with matching published constants supplied by the
    caller via the returned dict comparison)."""
    out = ledger.with_columns(
        pl.when(pl.col("game_date") <= pl.date(2024, 12, 31))
        .then(pl.lit("block_2024H2"))
        .when(pl.col("game_date") <= pl.date(2025, 6, 30))
        .then(pl.lit("block_2025H1"))
        .otherwise(pl.lit("confirm_2025H2"))
        .alias("block")
    )
    elig = eligible_slots_from_ledger(out, DEV_BLOCKS)
    slot_keys = [(int(r["game_pk"]), str(r["side"]), int(r["slot"]))
                 for r in elig.iter_rows(named=True)]
    h1 = sha256_stream(serialize_slot_keys(slot_keys))
    ev = observed_pa_join(elig, pa)
    eval_keys = [(int(r["game_pk"]), int(r["at_bat_number"]))
                 for r in ev.iter_rows(named=True)]
    h2 = sha256_stream(serialize_eval_keys(eval_keys))
    report = {
        "dev_slot_keys_n": len(slot_keys),
        "dev_eval_keys_n": len(eval_keys),
        "dev_slot_keys_sha256": h1,
        "dev_eval_keys_sha256": h2,
        "slot_keys_match": h1 == PUBLISHED_DEV_SLOT_KEYS_SHA256,
        "eval_keys_match": h2 == PUBLISHED_DEV_EVAL_KEYS_SHA256,
        "slot_count_match": len(slot_keys) == PUBLISHED_DEV_SLOT_KEYS_N,
        "eval_count_match": len(eval_keys) == PUBLISHED_DEV_EVAL_KEYS_N,
    }
    if not (report["slot_keys_match"] and report["eval_keys_match"]
            and report["slot_count_match"] and report["eval_count_match"]):
        raise ValueError("published development key verification FAILED: "
                         + json.dumps(report, sort_keys=True))
    return report


# ------------------------------------------------------------------- CLI
CONTRACT_TEXT = (
    "REFUSING to fit: the batter-history challenger's fitting/evaluation "
    "stage is NOT AUTHORIZED. Bounded execution contract (owner approval "
    "required): (1) verify frozen dev keys (this tool --verify-keys-only); "
    "(2) build challenger features over the 4,823 dev-eligible starts / "
    "43,407 slots from the preserved run ledger; (3) fit ONE primary "
    "challenger (R=60d, m=30) per dev block (block_2024H2, block_2025H1) "
    "on rebuilt historical training rows (2023-01-01..block cal_first, "
    "same rows as the frozen recipe); (4) evaluate LOG LOSS primary + "
    "Brier/calibration supporting on the 82,817 frozen dev evaluation PAs "
    "(identity join, pitcher-matched); (5) write-once outputs to a NEW "
    "diagnostics directory - the preserved run parquet is never read for "
    "writing and never modified; (6) confirm_2025H2 untouched; (7) the 59 "
    "abstaining starts (57 debut-date newcomers + Enns 608650 / Hart "
    "606996) prominently reported; (8) any acceptance-check failure stops "
    "all downstream use. No refit of the frozen recipe, no population-"
    "policy change, no confirmation access.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify-keys-only", action="store_true",
                    help="read-only: recompute the frozen development key "
                         "sets and assert the published hashes")
    ap.add_argument("--i-accept-fitting-execution", action="store_true",
                    help="gate for the fitting/evaluation stage (owner "
                         "authorization required; never run on real data "
                         "to date)")
    ap.add_argument("--pa-table", default=None,
                    help="override pa_table path (synthetic tests only)")
    ap.add_argument("--ledger", default=None,
                    help="override preserved-run ledger path (synthetic "
                         "tests only)")
    args = ap.parse_args(argv)

    if args.verify_keys_only:
        pa = (pl.read_parquet(args.pa_table) if args.pa_table
              else ad.load_pa_table())
        ledger_path = (Path(args.ledger) if args.ledger else
                       ad.PAEXT_OUT_DIR / "outputs"
                       / "projected_pa_probs_v1.parquet")
        ledger = pl.read_parquet(ledger_path)
        report = verify_published_keys(ledger, pa)
        print(json.dumps(report, indent=1, sort_keys=True))
        return 0

    if not args.i_accept_fitting_execution:
        print(CONTRACT_TEXT)
        return 2

    print("fitting/execution stage reached but NOT IMPLEMENTED for real "
          "data: this turn delivers specification implementation + "
          "synthetic tests only. Synthetic callers use the module functions "
          "directly.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
