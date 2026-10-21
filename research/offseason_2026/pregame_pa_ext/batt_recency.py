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
from datetime import date, timedelta
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

HARNESS_RELPATH = Path("specs") / "count-eval-v2-spec" / "harness"
DEV_BLOCKS = ["block_2024H2", "block_2025H1"]
DEV_BLOCK_TRAIN_END = {"block_2024H2": (2024, 6, 30),
                       "block_2025H1": (2024, 12, 31)}
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
    # carry the required identity columns PLUS any extra slot columns
    # (e.g., the baseline probability) through to every observed PA row
    carry = [c for c in eligible_slots.columns if c not in need]
    j = eligible_slots.select(
        sorted(need) + carry
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


# ------------------------------------------- frozen abstention record
# Classification evidence (FROZEN, existing):
# report_debut_pitcher_reconciliation_2026-10-20.md - Chat 2 authoritative
# check, independently confirmed from raw statcast 2015-2021 files. No
# debut-date re-query happens at diagnostic time: this classification is
# used verbatim.
ABSTENTION_VETERANS = [
    {"pitcher": 608650, "name": "Dietrich Enns", "game_pk": 777351,
     "side": "Top", "mlb_debut": "2017-08-10"},
    {"pitcher": 606996, "name": "Kyle Hart", "game_pk": 778499,
     "side": "Top", "mlb_debut": "2020-08-13"},
]
# Expected counts against the preserved ledger's exclusions (existing
# exclusion evidence; asserted only on real-data runs where
# verify_published=True).
ABSTENTION_EXPECTED = {"total": 59, "newcomers": 57, "veterans": 2,
                       "development": 43, "confirmation": 16}


def build_abstention_record(ledger: pl.DataFrame,
                            expected: dict | None = None) -> dict:
    """Machine-readable abstention record from the preserved run ledger's
    excluded rows (exclusion_reason non-null): all excluded start keys,
    their frozen classification, and block membership. Development and
    confirmation-block abstentions are counted SEPARATELY - the full-run
    total is never a development count."""
    out = ledger.with_columns(
        pl.when(pl.col("game_date") <= pl.date(2024, 12, 31))
        .then(pl.lit("block_2024H2"))
        .when(pl.col("game_date") <= pl.date(2025, 6, 30))
        .then(pl.lit("block_2025H1"))
        .otherwise(pl.lit("confirm_2025H2"))
        .alias("block")
    )
    exc = (out.filter(pl.col("exclusion_reason").is_not_null())
           .select("game_pk", "side", "pitcher", "game_date", "block",
                   "exclusion_reason")
           .unique(subset=["game_pk", "side", "pitcher", "game_date"],
                   keep="first")
           .sort("game_date", "game_pk", "side"))
    vet_by_key = {(v["game_pk"], v["side"]): v for v in ABSTENTION_VETERANS}
    entries = []
    for r in exc.iter_rows(named=True):
        key = (r["game_pk"], r["side"])
        vet = vet_by_key.get(key)
        entries.append({
            "game_pk": r["game_pk"], "side": r["side"],
            "pitcher": r["pitcher"], "game_date": str(r["game_date"]),
            "block": r["block"], "development": r["block"] in DEV_BLOCKS,
            "classification": ("window_limited_veteran" if vet
                               else "debut_date_newcomer"),
            "veteran": ({"name": vet["name"],
                         "mlb_debut": vet["mlb_debut"]} if vet else None),
            "exclusion_reason": r["exclusion_reason"],
        })
    dev = [e for e in entries if e["development"]]
    n_vet = sum(1 for e in entries
                if e["classification"] == "window_limited_veteran")
    record = {
        "source": ("report_debut_pitcher_reconciliation_2026-10-20.md "
                   "(Chat 2 authoritative check; raw-statcast confirmation)"),
        "full_run_total": len(entries),
        "development_total": len(dev),
        "confirmation_total": len(entries) - len(dev),
        "classification_totals": {
            "debut_date_newcomer": len(entries) - n_vet,
            "window_limited_veteran": n_vet,
        },
        "starts": entries,
    }
    if expected:
        for k, want in expected.items():
            got = (record["full_run_total"] if k == "total" else
                   record["classification_totals"]["debut_date_newcomer"]
                   if k == "newcomers" else
                   record["classification_totals"]["window_limited_veteran"]
                   if k == "veterans" else
                   record["development_total"] if k == "development" else
                   record["confirmation_total"])
            if got != want:
                raise ValueError(
                    f"abstention record INCONSISTENT with the frozen "
                    f"exclusion evidence: {k} = {got}, expected {want}")
        missing = [v["pitcher"] for v in ABSTENTION_VETERANS
                   if (v["game_pk"], v["side"])
                   not in {(e["game_pk"], e["side"]) for e in entries}]
        if missing:
            raise ValueError(
                "abstention record INCONSISTENT: window-limited-veteran "
                f"keys missing from the ledger exclusions: {missing}")
    return record


def validate_abstention_record(record: dict) -> None:
    """Structural validation of the abstention record (an omitted or
    malformed record prevents acceptance)."""
    for s in ("source", "full_run_total", "development_total",
              "confirmation_total", "classification_totals", "starts"):
        if s not in record or record[s] in (None, "", [], {}):
            raise ValueError(
                f"incomplete abstention record: missing/empty '{s}'")
    if record["full_run_total"] != len(record["starts"]):
        raise ValueError(
            "inconsistent abstention record: full_run_total != len(starts)")
    if (record["development_total"]
            + record["confirmation_total"]) != record["full_run_total"]:
        raise ValueError(
            "inconsistent abstention record: development + confirmation "
            "!= full_run_total")


# --------------------------------------------------------------- gated runner
def challenger_training_frame(pa: pl.DataFrame, train_end) -> pl.DataFrame:
    """ONE dev block's training frame: the FROZEN recipe's realized-PA fit
    lineage (build_checkpoint.build_feature_frame: realized rows from
    2023-01-01, original PA identity (game_pk, at_bat_number, batter, y)
    retained, lg-finite filter, same train/cal split) with the challenger
    batter features rebuilt AS OF each row's own date. NOT assembled from
    the outcome-observable evaluation subset: the row set is derived from
    the frozen pa_table lineage alone and is independent of the preserved
    run ledger."""
    from pregame_pa_ext import build_checkpoint as bc

    feat = bc.build_feature_frame(pa)
    te_y, te_m, te_d = train_end
    end = date(te_y, te_m, te_d)
    cal_last = feat.filter(
        (pl.col("game_date") >= pl.date(2023, 1, 1))
        & (pl.col("game_date") <= pl.date(te_y, te_m, te_d))
    )["game_date"].max()
    cal_first = cal_last - timedelta(days=59)
    train = feat.filter(
        (pl.col("game_date") >= pl.date(2023, 1, 1))
        & (pl.col("game_date") < cal_first))
    if train.height == 0:
        raise ValueError("empty training frame for train_end " + str(train_end))
    if train["game_date"].max() > end:
        raise ValueError("training rows leak past the block train_end")
    if train["game_date"].max() >= cal_first:
        raise ValueError("training rows overlap the calibration window")
    rows = train.select("game_pk", "at_bat_number", "batter", "pitcher",
                        "game_date", "y")
    f = challenger_feature_frame(rows, pa)
    if f.height != train.height:
        raise ValueError("training frame row count changed in feature build")
    ident_nulls = f.select(["game_pk", "at_bat_number", "batter"]
                           ).null_count().row(0)
    if f["y"].null_count() or any(ident_nulls):
        raise ValueError("training frame lost PA identity or label")
    return f


def challenger_training_frames(pa: pl.DataFrame) -> dict:
    """Both DEV blocks' training frames (block_2024H2, block_2025H1).
    confirm_2025H2 is PROTECTED: never a training block."""
    return {b: challenger_training_frame(pa, te)
            for b, te in DEV_BLOCK_TRAIN_END.items()}


def _log_loss(y, p):
    pc = np.clip(p, ad.P_CLIP, 1.0 - ad.P_CLIP)
    return -(y * np.log(pc) + (1 - y) * np.log1p(-pc))


def _brier(y, p):
    return (p - y) ** 2


def load_registered_comparison():
    """Established import path to the REGISTERED count-eval-v1 harness
    module: comparison.py owns the slate-date block-stratified bootstrap
    (slate_date_draws), the (B+1) finite-resample null-centering
    (null_centered_p_value), null_centered_contrast_test, and Holm. The
    frozen harness is IMPORTED AND CALLED - never modified, never
    re-implemented (Chat 2 blocker resolution)."""
    h = Path(__file__).resolve().parents[1] / HARNESS_RELPATH
    if str(h) not in sys.path:
        sys.path.insert(0, str(h))
    import comparison

    return comparison


def evaluation_metrics(ev: pl.DataFrame, *, n_boot: int = 2000,
                       seed: int = 20261001) -> dict:
    """Registered machinery, paired by evaluation row: LOG LOSS primary
    evaluated with the REGISTERED harness primitive
    (comparison.slate_date_draws + null_centered_contrast_test: the
    registered per-block multinomial date-draw construction, the (B+1)
    finite-resample null-centering, Holm m=1 = family of one), plus the
    unadjusted percentile interval on the replicate deltas. Brier +
    calibration are SUPPORTING point summaries (never selectable, never
    gated)."""
    y = ev["y"].to_numpy().astype(int)
    p_b = ev["p_baseline"].to_numpy().astype(float)
    p_c = ev["p_challenger"].to_numpy().astype(float)
    ll_b = _log_loss(y, p_b)
    ll_c = _log_loss(y, p_c)
    d_row = ll_c - ll_b
    out = {
        "n_evaluation_rows": int(ev.height),
        "log_loss_baseline": float(ll_b.mean()),
        "log_loss_challenger": float(ll_c.mean()),
        "log_loss_delta": float(d_row.mean()),
        "brier_baseline": float(_brier(y, p_b).mean()),
        "brier_challenger": float(_brier(y, p_c).mean()),
        "brier_delta": float((_brier(y, p_c) - _brier(y, p_b)).mean()),
    }
    # REGISTERED hypothesis test through the established import path: the
    # two arms enter as candidates (per-row log loss), the single
    # pre-declared contrast is signed challenger - baseline, the date
    # draws are the harness's own per-block multinomial construction, and
    # the null-centering uses the harness's (B + 1) finite-resample
    # correction. Holm m=1: the family is exactly the one pre-declared
    # contrast.
    cmp = load_registered_comparison()
    values = {"baseline": ll_b, "challenger": ll_c}
    dates = ev["game_date"].to_list()
    blocks = ev["block"].to_list()
    res = cmp.slate_date_draws(values, dates, blocks, n_boot=n_boot,
                               seed=seed)
    idx = {n: i for i, n in enumerate(values)}
    delta_rep = res[:, idx["challenger"]] - res[:, idx["baseline"]]
    test = cmp.null_centered_contrast_test(
        values, [("C_batt_recency_vs_baseline", "challenger", "baseline")],
        dates, blocks, n_boot=n_boot, seed=seed, res=res)
    primary = test["contrasts"]["C_batt_recency_vs_baseline"]
    out["bootstrap"] = {
        "primitive": ("registered harness comparison.py: "
                      "slate_date_draws + null_centered_contrast_test"),
        "contrast": "C_batt_recency_vs_baseline",
        "delta": primary["delta"],
        "ci95": [float(np.percentile(delta_rep, 2.5)),
                 float(np.percentile(delta_rep, 97.5))],
        "p_null_centered": primary["p_value"],
        "p_holm": primary["p_holm"],
        "n_boot": n_boot, "seed": seed, "holm_m": 1,
    }
    cal = {"baseline_mean_pred": float(p_b.mean()),
           "baseline_observed": float(y.mean()),
           "challenger_mean_pred": float(p_c.mean()),
           "challenger_observed": float(y.mean())}
    q = np.quantile(p_c, np.linspace(0, 1, 11))
    bins = np.clip(np.searchsorted(q, p_c, side="right") - 1, 0, 9)
    gaps = []
    for k in range(10):
        m = bins == k
        if m.any():
            gaps.append(abs(p_c[m].mean() - y[m].mean()))
    cal["challenger_max_decile_gap"] = float(max(gaps)) if gaps else None
    out["calibration"] = cal
    # coverage note: the development/full-run abstention distinction is
    # explicit; metric tables never imply all abstentions are development
    out["coverage"] = {
        "abstention_record": "abstentions.json",
        "development_abstaining_starts": None,
        "full_run_abstaining_starts": None,
        "note": ("development metrics cover the eligible development "
                 "starts only; abstentions.json itemizes development and "
                 "confirmation-block abstentions separately - the "
                 "full-run total is not a development count"),
    }
    return out


REQUIRED_RECEIPT_SECTIONS = ("inputs", "code_config", "dev_keys", "fits",
                             "metrics", "outputs", "abstentions",
                             "acceptance")


def validate_receipt(receipt: dict) -> None:
    """A run without a COMPLETE receipt is unaccepted by definition."""
    if not isinstance(receipt, dict):
        raise ValueError("provenance receipt is not a JSON object")
    for s in REQUIRED_RECEIPT_SECTIONS:
        if s not in receipt:
            raise ValueError(f"incomplete provenance receipt: missing '{s}'")
        v = receipt[s]
        if v is None or (isinstance(v, (dict, list)) and not v):
            raise ValueError(f"incomplete provenance receipt: empty '{s}'")


def _sha_or_missing(p) -> str:
    p = Path(p)
    if p.exists():
        return ad.sha256_file(p)
    return "NOT_AVAILABLE"


def br_lf_bytes() -> bytes:
    raw = Path(__file__).read_bytes()
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def run_diagnostic(pa: pl.DataFrame, ledger: pl.DataFrame, out_dir,
                   *, verify_published: bool = True,
                   artifact_paths: dict | None = None,
                   n_boot: int = 2000, seed: int = 20261001) -> dict:
    """GATED diagnostic runner (synthetic-tested only; real-data execution
    requires --i-accept-fitting-execution via the CLI AND owner
    authorization). Write-once: refuses an existing output directory.
    Produces: evaluation parquet (paired baseline/challenger on the frozen
    dev keys), metrics.json, and the MANDATORY provenance receipt
    (validated before the run is accepted; MLflow transport optional,
    receipt mandatory)."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(
            f"write-once violation: diagnostics output dir exists: {out_dir}")
    out_dir.mkdir(parents=True)
    out_table = out_dir / "batt_recency_eval_v1.parquet"
    if out_table.exists():
        raise ValueError(f"write-once violation: {out_table} exists")

    # frozen abstention record (machine-readable; referenced by the receipt
    # and the human-readable outputs - never duplicated into them)

    # 1. eligibility (unchanged policy) + frozen dev keys
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
    dev_keys = {
        "slot_keys_n": len(slot_keys),
        "slot_keys_sha256": sha256_stream(serialize_slot_keys(slot_keys)),
    }
    if verify_published:
        if dev_keys["slot_keys_sha256"] != PUBLISHED_DEV_SLOT_KEYS_SHA256 \
                or dev_keys["slot_keys_n"] != PUBLISHED_DEV_SLOT_KEYS_N:
            raise ValueError("frozen dev slot keys do not match the "
                             "published pins; refusing")

    # abstention record: verified against the frozen exclusion evidence on
    # real-data runs; an omission or inconsistency prevents acceptance
    abst = build_abstention_record(
        out, expected=(ABSTENTION_EXPECTED if verify_published else None))
    validate_abstention_record(abst)
    abst_path = out_dir / "abstentions.json"
    abst_path.write_text(json.dumps(abst, indent=1, sort_keys=True),
                         encoding="utf-8")
    abst_hash = ad.sha256_file(abst_path)

    # 2. per-block training frames (frozen lineage, original PA identity)
    trains = challenger_training_frames(pa)
    fits = {}
    models = {}
    for b in DEV_BLOCKS:
        f = trains[b]
        if (f["block"] == PROTECTED_BLOCK).any():
            raise ValueError(f"protected block rows in training frame {b}")
        models[b] = fit_challenger_models(f)
        coef_blob = json.dumps(models[b], sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
        fits[b] = {"n_train_rows": int(f.height),
                   "max_train_date": str(f["game_date"].max()),
                   "coefficients_sha256": hashlib.sha256(coef_blob)
                   .hexdigest()}

    # 3. evaluation table: baseline + challenger on the SAME rows
    slots = elig.join(
        ledger.select("game_pk", "side", "pitcher", "batter", "slot",
                      "game_date", "p_h3_raw"),
        on=["game_pk", "side", "pitcher", "batter", "slot", "game_date"],
        how="left").with_columns(
        pl.col("p_h3_raw").alias("p_baseline"))
    if slots["p_h3_raw"].null_count():
        raise ValueError("eligible slot without a baseline probability")
    slot_feats = challenger_feature_frame(slots, pa)
    p_c = np.full(slot_feats.height, np.nan)
    for b in DEV_BLOCKS:
        m = (slot_feats["block"] == b).to_numpy()
        if m.any():
            p_c[m] = apply_challenger(slot_feats.filter(pl.Series(m)),
                                      models[b])
    if np.isnan(p_c).any():
        raise ValueError("evaluation slot outside the dev block models")
    slot_feats = slot_feats.with_columns(pl.Series("p_challenger", p_c))
    ev = observed_pa_join(slots, pa).join(
        slot_feats.select("game_pk", "side", "pitcher", "batter", "slot",
                          "game_date", "p_challenger"),
        on=["game_pk", "side", "pitcher", "batter", "slot", "game_date"],
        how="inner")
    if ev["p_baseline"].null_count() or ev["p_challenger"].null_count():
        raise ValueError("paired evaluation rows missing an arm")
    eval_keys = sorted(set(zip(ev["game_pk"].to_list(),
                               ev["at_bat_number"].to_list())))
    dev_keys["eval_keys_n"] = len(eval_keys)
    dev_keys["eval_keys_sha256"] = sha256_stream(
        serialize_eval_keys(eval_keys))
    if verify_published and (
            dev_keys["eval_keys_sha256"] != PUBLISHED_DEV_EVAL_KEYS_SHA256
            or dev_keys["eval_keys_n"] != PUBLISHED_DEV_EVAL_KEYS_N):
        raise ValueError("frozen dev evaluation keys do not match the "
                         "published pins; refusing")
    if (ev["block"] == PROTECTED_BLOCK).any():
        raise ValueError("protected confirm block in the evaluation table")

    # 4. metrics (registered machinery)
    metrics = evaluation_metrics(ev, n_boot=n_boot, seed=seed)
    metrics["coverage"]["development_abstaining_starts"] = \
        abst["development_total"]
    metrics["coverage"]["full_run_abstaining_starts"] = \
        abst["full_run_total"]

    # 5. write-once outputs
    ev.write_parquet(out_table)
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=1, sort_keys=True),
                            encoding="utf-8")

    # 6. MANDATORY provenance receipt (validated; MLflow transport optional
    # and NOT exercised here)
    ap = artifact_paths or {}
    inputs = {k: _sha_or_missing(v) for k, v in ap.items()}
    if not inputs:
        inputs = {"note": "no artifact paths supplied (synthetic run)"}
    code_config = {
        "batt_recency_py_lf_sha256": sha256_stream(br_lf_bytes()),
        "adapter_py_lf_sha256": sha256_stream(
            Path(ad.__file__).read_bytes()
            .replace(b"\r\n", b"\n").replace(b"\r", b"\n")),
        "challenger_config": {"R_days": RECENT_DAYS, "m_pseudo": M_PSEUDO,
                              "anchor_w": ANCHOR_W,
                              "features": list(CHALLENGER_FEATURES)},
    }
    receipt = {
        "abstentions": {
            "file": "abstentions.json",
            "sha256": abst_hash,
            "full_run_total": abst["full_run_total"],
            "development_total": abst["development_total"],
            "confirmation_total": abst["confirmation_total"],
            "classification_totals": abst["classification_totals"],
        },
        "inputs": inputs,
        "code_config": code_config,
        "dev_keys": dev_keys,
        "fits": fits,
        "metrics": metrics,
        "outputs": {
            "batt_recency_eval_v1.parquet": ad.sha256_file(out_table),
            "metrics.json": ad.sha256_file(metrics_path),
        },
        "acceptance": {
            "verify_published": bool(verify_published),
            "paired_keys_exact": True,
            "block_isolation": True,
            "exclusion_policy_unchanged": True,
        },
    }
    validate_receipt(receipt)
    receipt_path = out_dir / "provenance_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=1, sort_keys=True),
                            encoding="utf-8")
    reread = json.loads(receipt_path.read_text(encoding="utf-8"))
    validate_receipt(reread)
    if ad.sha256_file(abst_path) != reread["abstentions"]["sha256"]:
        raise ValueError(
            "abstention record hash mismatch after write; run rejected")
    return {"out_dir": str(out_dir), "receipt": receipt,
            "receipt_complete": True}


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
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--bf", default=None)
    ap.add_argument("--lineup", default=None)
    ap.add_argument("--freeze", default=None)
    ap.add_argument("--out-dir", default=None,
                    help="diagnostics output directory override (defaults "
                         "to PAEXT_OUT_DIR/diagnostics/batt_recency_v1)")
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

    out_dir = (Path(args.out_dir) if args.out_dir else
               ad.PAEXT_OUT_DIR / "diagnostics" / "batt_recency_v1")
    pa = pl.read_parquet(args.pa_table) if args.pa_table else ad.load_pa_table()
    ledger_path = (Path(args.ledger) if args.ledger else
                   ad.PAEXT_OUT_DIR / "outputs"
                   / "projected_pa_probs_v1.parquet")
    ledger = pl.read_parquet(ledger_path)
    # REAL artifact identities for the MANDATORY provenance receipt
    # (inputs section): the frozen files this diagnostic actually reads.
    artifact_paths = {
        "pa_table": (Path(args.pa_table) if args.pa_table
                     else ad.OVERNIGHT_P2_DIR / "data" / "pa_table.parquet"),
        "preserved_run_ledger": ledger_path,
        "checkpoint": (Path(args.checkpoint) if args.checkpoint
                       else ad.CHECKPOINT_PATH),
        "bf_pmf": (Path(args.bf) if args.bf else
                   ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet"),
        "lineups": (Path(args.lineup) if args.lineup else
                    ad.PREGAME_STATE_DIR / "data"
                    / "projected_lineups_variant_v2.parquet"),
        "freeze_config": (Path(args.freeze) if args.freeze else
                          Path(ad.__file__).resolve().parent
                          / "freeze_pregame_pa_ext_v2.json"),
    }
    result = run_diagnostic(pa, ledger, out_dir, verify_published=True,
                            artifact_paths=artifact_paths)
    print(json.dumps({"out_dir": result["out_dir"],
                      "receipt_complete": result["receipt_complete"],
                      "log_loss_delta": result["receipt"]["metrics"]
                      ["log_loss_delta"]}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
