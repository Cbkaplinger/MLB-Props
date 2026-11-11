"""Market-benchmark seam (research-side; no live-path change).

Smallest glue that lets the EXISTING market-evaluation lane
(``market_eval_k.py``) benchmark TODAY's registered harness outputs:
(1) model-only probabilities, (2) each individual sportsbook,
(3) market consensus. Two seams only - all scoring, de-vig, consensus,
timestamp, and bootstrap math stays in the registered modules.

Seam A - harness model frame: converts the harness keyed 24-bucket
K-PMF contract (``k_pmf_per_start`` layout, one PMF column per arm)
plus assessment-derived observed K, the DECLARED eligible cohort
(hash-checked), and declared start dates into the frame
``run_market_eval_k`` consumes: (game_pk, side, pitcher, game_date,
block, realized_k, pmf_baseline). Block assignment reuses the
registered ``ad.add_block`` rule; protected/unknown blocks refuse.

Seam B - per-book and leave-target-book-out (LTBO) consensus
construction: from the existing near-close quote frame, per
(game_pk, pitcher, book, line) two-sided de-vigged over probability
(existing ``devig_over``), the LTBO consensus (median of the OTHER
books' de-vigged over probabilities at the SAME line; >= 2 other
books required, else recorded unavailable), and the all-book
consensus (delegates to ``market_eval_k.consensus_over_probs``).

Exact comparison contract (declared):
- forecast decision time / input availability: model inputs are
  strictly-prior pregame states; market inputs are NEAR-CLOSE quotes
  under the registered tier A/B timestamp rules (existing
  ``select_near_close``). Closing quotes are BENCHMARK-ONLY - never
  earlier decision inputs;
- identity: complete start key (game_pk, side, pitcher); the quoted
  pitcher's vendor key is bridged to the MLBAM id by the tested
  ``starts_out`` table inside the existing runner;
- settlement: realized over = 1{K > line} with K = complete
  full-start realized strikeouts from the pinned assessment (registered
  derivation: class_label == 0 counts);
- matching: per (start, book, line) TWO-SIDED near-close quotes only;
  one-sided ladders are never converted into full PMFs and no model
  PMF is inferred from a single line;
- LTBO consensus: median over OTHER books at the same line
  (>= 2 other books; fewer -> recorded unavailable, never filled);
- paired cohort: the declared eligible cohort (hash-checked); the
  model arm is scored against the realized over indicator at the
  consensus line (existing runner); book arms at their own quoted
  line against the LTBO consensus at that same line; coverage,
  exclusions (including ltbo-unavailable counts), weighting (equal
  weight per (start, line)) and uncertainty (the registered paired
  slate-date bootstrap) are recorded with the results;
- model-only and market-only results are kept separate (separate
  artifacts; no blending).

This module performs no fitting, no calibration, no live-path edit,
and no private-data access. Real-data use requires the registered
market-eval gate plus delegated owner order (the existing
``run_market_eval_k`` gate).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
sys.path.insert(0, str(_HERE.parents[3] / "src"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402

START_KEYS = ("game_pk", "side", "pitcher")
BUCKET_COL = "bucket"
K_MAX = ad.K_MAX


def _validate_bucket_labels(k_pmf: pl.DataFrame,
                            bucket_col: str = BUCKET_COL) -> None:
    """Strict bucket-label validation BEFORE integer conversion: null,
    nonfinite, fractional, and non-numeric labels refuse; valid
    integer-typed producer output passes unchanged (same contract as
    the market bridge and the K-PMF diagnostic)."""
    col = k_pmf[bucket_col]
    if col.null_count() > 0:
        raise ValueError("null bucket label(s) present")
    dtype = k_pmf.schema[bucket_col]
    integer_dtypes = (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                      pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64)
    float_dtypes = (pl.Float32, pl.Float64)
    if dtype in integer_dtypes:
        return
    if dtype not in float_dtypes:
        raise ValueError(
            f"bucket column dtype {dtype} is neither integer nor "
            "float; refusing non-numeric bucket labels")
    for v in col.to_list():
        if not np.isfinite(v):
            raise ValueError(f"nonfinite bucket label: {v!r}")
        if float(v) != int(v):
            raise ValueError(
                f"fractional bucket label: {v!r}; buckets must be "
                "integers 0..23")


def _reject_null(frame: pl.DataFrame, cols, ctx: str) -> None:
    null_mask = pl.any_horizontal([pl.col(c).is_null() for c in cols])
    if frame.filter(null_mask).height > 0:
        raise ValueError(f"{ctx}: null value(s) present")


def _reject_duplicates(frame: pl.DataFrame, cols, ctx: str) -> None:
    dups = frame.group_by(cols).agg(n=pl.len()).filter(pl.col("n") > 1)
    if dups.height > 0:
        sample = frame.select(cols).head(3).rows()
        raise ValueError(
            f"{ctx}: {dups.height} duplicate identity key(s) "
            f"(sample: {sample})")


def _pmfs_for_arm(k_pmf: pl.DataFrame, arm: str,
                  keys: set) -> dict:
    by_start: dict[tuple, dict[int, float]] = {}
    for r in k_pmf.sort([*START_KEYS, BUCKET_COL]).iter_rows(
            named=True):
        key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        by_start.setdefault(key, {})[int(r[BUCKET_COL])] = \
            float(r[arm])
    out = {}
    for key in keys:
        pmf = np.asarray([by_start[key][b] for b in range(K_MAX)],
                         dtype=np.float64)
        ad.check_pmf(pmf, ctx=f"start {key} arm {arm}")
        out[key] = pmf
    return out


def harness_model_frame(k_pmf: pl.DataFrame, observed: pl.DataFrame,
                        start_dates: pl.DataFrame, cohort: pl.DataFrame,
                        expected_cohort_hash: str,
                        arm: str) -> pl.DataFrame:
    """Seam A: harness keyed PMF + observed K + declared cohort +
    declared start dates -> the registered market-eval model frame
    (game_pk, side, pitcher, game_date, block, realized_k,
    pmf_baseline). Cohort identity hash-checked; forecast keys must
    equal the cohort exactly; observations restricted to the cohort
    must cover it exactly; declared dates must cover the cohort
    exactly (no date invention)."""
    from pregame_pa_ext import count_pmf_diagnostic as cpd
    if arm not in k_pmf.columns:
        raise ValueError(f"k_pmf missing requested arm column {arm!r}")
    cohort_unique = cpd.validate_cohort(cohort, expected_cohort_hash)
    cohort_keys = {tuple(r) for r in cohort_unique.iter_rows()}
    missing = [c for c in START_KEYS if c not in observed.columns]
    if missing or "realized_k" not in observed.columns:
        raise ValueError(
            "observed frame missing required column(s): "
            f"{sorted(set(missing) | ({'realized_k'} - set(observed.columns)))}")
    _reject_null(observed, START_KEYS, "observed start identity")
    _reject_duplicates(observed, START_KEYS, "observed start")
    for v in observed["realized_k"].to_list():
        if v is None or not np.isfinite(v) or v < 0 \
                or float(v) != int(v):
            raise ValueError(
                f"observed K must be a nonnegative integer: {v!r}")
    _validate_bucket_labels(k_pmf)
    _reject_null(k_pmf, START_KEYS, "forecast start identity")
    _reject_duplicates(k_pmf, (*START_KEYS, BUCKET_COL),
                       "forecast (start, bucket)")
    present = set(int(b) for b in k_pmf[BUCKET_COL].unique().to_list())
    if present != set(range(K_MAX)):
        raise ValueError(
            f"bucket set != declared 0..{K_MAX - 1}")
    per_start = k_pmf.group_by(START_KEYS).agg(n=pl.len())
    if per_start.filter(pl.col("n") != K_MAX).height > 0:
        raise ValueError(
            "start(s) without exactly 24 buckets")

    forecast_keys = {tuple(r) for r in
                     k_pmf.select(START_KEYS).unique().iter_rows()}
    if forecast_keys != cohort_keys:
        raise ValueError(
            "forecast/declared-cohort key mismatch "
            f"(missing_from_cohort={len(forecast_keys - cohort_keys)}, "
            f"missing_from_forecast={len(cohort_keys - forecast_keys)}); "
            "refusing")
    observed_keys = {tuple(r) for r in
                     observed.select(START_KEYS).unique().iter_rows()}
    outside = sorted(observed_keys - cohort_keys)
    observed_restricted = observed.join(cohort_unique, on=START_KEYS,
                                        how="semi")
    restricted_keys = {tuple(r) for r in
                       observed_restricted.select(START_KEYS)
                       .iter_rows()}
    if restricted_keys != cohort_keys:
        raise ValueError(
            "restricted observations do not cover the cohort "
            f"({len(cohort_keys - restricted_keys)} cohort start(s) "
            "without observations); refusing")
    observed_by_key = {
        (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])):
            int(r["realized_k"])
        for r in observed_restricted.iter_rows(named=True)}

    d_missing = [c for c in [*START_KEYS, "game_date"]
                 if c not in start_dates.columns]
    if d_missing:
        raise ValueError(
            f"start_dates frame missing required column(s): "
            f"{d_missing}")
    _reject_null(start_dates, (*START_KEYS, "game_date"),
                 "declared start date")
    _reject_duplicates(start_dates, START_KEYS, "declared start date")
    date_keys = {tuple(r) for r in
                 start_dates.select(START_KEYS).unique().iter_rows()}
    if date_keys != cohort_keys:
        raise ValueError(
            "declared dates do not cover the cohort exactly "
            f"(missing={sorted(cohort_keys - date_keys)[:5]}, "
            f"extra={sorted(date_keys - cohort_keys)[:5]}); refusing")
    dates_by_key = {
        (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])):
            r["game_date"]
        for r in start_dates.iter_rows(named=True)}

    pmfs = _pmfs_for_arm(k_pmf, arm, cohort_keys)
    out_rows = []
    for key in sorted(cohort_keys):
        game_date = dates_by_key[key]
        block = ad.add_block(pl.DataFrame(
            [key[0:2] + (game_date,)], schema={
                "game_pk": pl.Int64, "side": pl.Utf8,
                "game_date": pl.Date}, orient="row"))["block"][0]
        if block == "confirm_2025H2" or block not in (
                "block_2024H2", "block_2025H1"):
            raise ValueError(
                f"start {key} maps to protected/unknown block "
                f"{block!r}; refusing")
        out_rows.append({
            "game_pk": key[0], "side": key[1], "pitcher": key[2],
            "game_date": game_date, "block": block,
            "realized_k": observed_by_key[key],
            "pmf_baseline": pmfs[key].tolist()})
    return pl.DataFrame(out_rows)


def book_over_probabilities(near_close: pl.DataFrame) -> pl.DataFrame:
    """Per (game_pk, pitcher, book, line): the two-sided de-vigged over
    probability (existing ``market_eval_k.devig_over``). Requires both
    bet sides at the quote; one-sided ladders never produce a book
    probability."""
    required = {"game_pk", "pitcher", "book", "line", "side", "price"}
    missing = required - set(near_close.columns)
    if missing:
        raise ValueError(
            f"near_close frame missing column(s): {sorted(missing)}")
    wide = near_close.pivot(
        values="price", index=["game_pk", "pitcher", "book", "line"],
        on="side", aggregate_function="first")
    if "over" not in wide.columns or "under" not in wide.columns:
        raise ValueError("near-close quotes missing over/under bet sides")
    wide = wide.filter(pl.col("over").is_not_null()
                       & pl.col("under").is_not_null())
    if wide.height == 0:
        raise ValueError("no two-sided near-close quotes")
    return wide.with_columns(
        pl.struct(["over", "under"]).map_elements(
            lambda s: mk.devig_over(s["over"], s["under"]),
            return_dtype=pl.Float64).alias("p_over_book"))


def ltbo_consensus(book_probs: pl.DataFrame,
                   min_other_books: int = 2) -> tuple:
    """Leave-target-book-out consensus per (game_pk, pitcher, book,
    line): the median of the OTHER books' de-vigged over probabilities
    at the SAME line. Requires >= min_other_books other books;
    (start, book, line) rows with fewer are recorded unavailable
    (never filled from other lines). Returns (available frame,
    unavailable count)."""
    per_line_all = book_probs.select(
        "game_pk", "pitcher", "line", "book", "p_over_book")
    ltbo_rows = []
    n_unavailable = 0
    for r in book_probs.sort(["game_pk", "pitcher", "line", "book"]
                             ).iter_rows(named=True):
        others = per_line_all.filter(
            (pl.col("game_pk") == r["game_pk"])
            & (pl.col("pitcher") == r["pitcher"])
            & (pl.col("line") == r["line"])
            & (pl.col("book") != r["book"]))
        n_other = others.height
        if n_other < min_other_books:
            n_unavailable += 1
            continue
        ltbo_rows.append({
            "game_pk": r["game_pk"], "pitcher": r["pitcher"],
            "book": r["book"], "line": r["line"],
            "p_over_book": r["p_over_book"],
            "p_over_ltbo": float(
                np.median(others["p_over_book"].to_list())),
            "n_other_books": int(n_other)})
    return pl.DataFrame(ltbo_rows), n_unavailable


def all_book_consensus(near_close: pl.DataFrame) -> pl.DataFrame:
    """Existing all-book consensus (registered construction, reused
    unchanged)."""
    return mk.consensus_over_probs(near_close)
