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


def bridge_market_key(market_frame: pl.DataFrame,
                      starts_bridge: pl.DataFrame) -> pl.DataFrame:
    """Map the REDUCED market key (game_pk, pitcher_key) to the
    complete start identity via the tested bridge; the team side is
    inherited from the model frame downstream. Ambiguous mappings
    refuse: one (game_pk, pitcher_key) must map to exactly one MLBAM
    pitcher."""
    required = {"game_pk", "pitcher_key", "pitcher"}
    missing = required - set(starts_bridge.columns)
    if missing:
        raise ValueError(
            f"starts_bridge missing column(s): {sorted(missing)}")
    bridge = starts_bridge.select(
        "game_pk", "pitcher_key",
        pl.col("pitcher").alias("pitcher_id")).unique()
    dup = bridge.group_by("game_pk", "pitcher_key").agg(
        n=pl.len()).filter(pl.col("n") > 1)
    if dup.height > 0:
        sample = dup.select("game_pk", "pitcher_key").head(3).rows()
        raise ValueError(
            f"ambiguous market/start identity mapping: {dup.height} "
            "(game_pk, pitcher_key) pair(s) map to multiple MLBAM ids "
            f"(sample: {sample}); refusing")
    out = market_frame.join(
        bridge, left_on=["game_pk", "pitcher"],
        right_on=["game_pk", "pitcher_key"], how="inner")
    return out.drop("pitcher").rename({"pitcher_id": "pitcher"})


def validate_selected_quotes(quotes: pl.DataFrame) -> None:
    """Selector precondition: the registered near-close selector keeps
    the LAST duplicate quote-side row (pivot 'first'), so this seam
    refuses duplicate (start, book, line, side) rows before any pivot
    or book counting - duplicate rows can never silently pass through
    or inflate the count of OTHER books."""
    _reject_duplicates(quotes, ["game_pk", "pitcher", "book", "line",
                                "side"], "selected near-close quote")


def benchmark_contract_rows(
        k_pmf: pl.DataFrame, observed: pl.DataFrame,
        start_dates: pl.DataFrame, cohort: pl.DataFrame,
        expected_cohort_hash: str, arm: str, quotes: pl.DataFrame,
        starts_bridge: pl.DataFrame, *, min_other_books: int = 2,
        n_boot: int = 2000, seed: int = 20261001,
        consensus_policy: str = "refuse") -> dict:
    """Narrow end-to-end benchmark contract assembly. Every stage
    reuses the registered machinery; this function adds only the
    ordered glue and observable coverage accounting.

    ``consensus_policy``: "refuse" (default) keeps the exact-cohort
    coverage gate; "shared_population" scores model-vs-consensus on
    the declared intersection, keeps the ORIGINAL cohort as the
    coverage denominator, and derives matched/unmatched start keys
    with reason codes BEFORE scoring. Book/LTBO populations stay
    separate with their own denominators in either mode.

    Stages: harness PMF + full-start observed K + declared cohort/dates
    -> selected two-sided quotes (registered near-close rules; the
    DECISION TIMESTAMP is each start's first_pitch_ts - the registered
    tier-A cutoff - so every selected quote is available at or before
    it; a closing-tier benchmark would be labeled separately)
    -> book, LTBO, and all-book consensus probabilities
    -> identical paired contract rows: every source is evaluated
    against the SAME realized event (the start's full-start observed K)
    at that source's own quoted line
    -> the existing outcome scorer (``market_eval_k.score_starts`` for
    model-vs-consensus with the registered slate-date bootstrap; the
    extracted paired line-score definitions ``market_eval_k.paired_line_
    scores`` for book-vs-LTBO, same bootstrap).

    Probability disagreement (book vs LTBO) and outcome scoring are
    reported separately. Coverage accounting is observable throughout.
    """
    from pregame_pa_ext import count_pmf_diagnostic as cpd

    cohort_unique = cpd.validate_cohort(cohort, expected_cohort_hash)
    cohort_keys = {tuple(r) for r in cohort_unique.iter_rows()}
    observed_keys_full = {
        (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        for r in observed.select(START_KEYS).unique().iter_rows(
            named=True)}
    observed_outside_cohort = sorted(observed_keys_full - cohort_keys)

    model_frame = harness_model_frame(
        k_pmf, observed, start_dates, cohort, expected_cohort_hash,
        arm)

    # ---- quotes: registered timing + own-player + near-close rules
    required_bridge = {"game_pk", "pitcher_key", "pitcher",
                       "first_pitch_ts", "has_commence"}
    missing = required_bridge - set(starts_bridge.columns)
    if missing:
        raise ValueError(
            f"starts_bridge missing column(s): {sorted(missing)}")
    _reject_null(quotes, ["game_pk", "pitcher", "book", "line",
                          "side", "price"], "quote identity")
    n_quotes_total = quotes.height
    odds = quotes.join(
        starts_bridge.select("game_pk", "pitcher_key", "first_pitch_ts",
                             "has_commence"),
        on="game_pk", how="inner")
    odds_own = mk.verified_odds_for_start(odds)
    near = mk.select_near_close(odds_own)
    funnel = {
        "quotes_total": n_quotes_total,
        "quotes_attached_to_starts": odds.height,
        "quotes_other_player_dropped": odds.height - odds_own.height,
        "quotes_near_close_selected": near.height,
        "decision_timestamp": ("each start's first_pitch_ts (the "
                               "registered tier-A cutoff); every "
                               "selected quote is available at or "
                               "before it; a closing-tier benchmark "
                               "would be labeled separately")}

    # ---- probabilities per source (bridged to MLBAM start identity;
    # the SELECTED quotes must be unique per (start, book, line, side)
    # at this boundary - duplicate rows would silently pass pivot
    # ('first') and inflate the count of OTHER books
    validate_selected_quotes(near)
    book_probs = bridge_market_key(book_over_probabilities(near),
                                   starts_bridge)
    ltbo, n_ltbo_unavailable = ltbo_consensus(
        book_probs, min_other_books=min_other_books)
    consensus = bridge_market_key(all_book_consensus(near),
                                  starts_bridge)
    _reject_duplicates(consensus, ["game_pk", "pitcher"],
                       "bridged consensus")

    # ---- identical paired contract rows (same realized event)
    cons_sel = consensus.select("game_pk", "pitcher", "line", "p_over",
                                "n_books")
    model_rows = model_frame.join(cons_sel, on=["game_pk", "pitcher"],
                                  how="inner")
    consensus_shared = None
    consensus_unmatched_rows: list[dict] = []
    consensus_matched_rows: list[dict] = []
    if model_rows.height != model_frame.height:
        if consensus_policy == "refuse":
            raise ValueError(
                "model rows lost in the consensus join "
                f"({model_frame.height} -> {model_rows.height}); refusing")
        # ---- declared shared-population policy: score model-vs-
        # consensus ONLY on their intersection; the ORIGINAL cohort
        # stays the coverage denominator; matched/unmatched start keys
        # and reason codes are derived BEFORE any scoring, and the
        # book/LTBO populations keep their own separate denominators.
        unmatched = model_frame.join(cons_sel, on=["game_pk", "pitcher"],
                                     how="anti")
        # bridge the near-close frame (vendor keys) to MLBAM start keys
        near_bridged = near.join(
            starts_bridge.select("game_pk", "pitcher_key",
                                 pl.col("pitcher").alias("pitcher_id")),
            left_on=["game_pk", "pitcher"],
            right_on=["game_pk", "pitcher_key"], how="left")
        has_quotes = {(int(r["game_pk"]), int(r["pitcher_id"]))
                      for r in near_bridged.select("game_pk", "pitcher_id")
                      .unique().iter_rows(named=True)
                      if r["pitcher_id"] is not None}
        # a start has a two-sided quote when SOME (book, line) carries
        # both sides for its quoted pitcher
        two_sided = (near_bridged
                     .group_by(["game_pk", "pitcher_id", "book", "line"])
                     .agg(n_sides=pl.col("side").n_unique())
                     .filter(pl.col("n_sides") == 2)
                     .select(["game_pk", "pitcher_id"]).unique())
        has_two_sided = {(int(r["game_pk"]), int(r["pitcher_id"]))
                         for r in two_sided.iter_rows(named=True)}
        for r in unmatched.iter_rows(named=True):
            k = (int(r["game_pk"]), int(r["pitcher"]))
            reason = ("no_near_close_quotes"
                      if k not in has_quotes else
                      "no_two_sided_quote_at_any_line"
                      if k not in has_two_sided else
                      "consensus_unavailable_other")
            consensus_unmatched_rows.append({
                "game_pk": r["game_pk"], "side": r["side"],
                "pitcher": r["pitcher"], "game_date": str(r["game_date"]),
                "block": r["block"], "reason": reason})
        by_reason: dict = {}
        for u in consensus_unmatched_rows:
            by_reason[u["reason"]] = by_reason.get(u["reason"], 0) + 1
        for r in model_rows.select([*START_KEYS, "game_date", "block"]
                                   ).sort(START_KEYS).iter_rows(
                                        named=True):
            consensus_matched_rows.append({
                "game_pk": r["game_pk"], "side": r["side"],
                "pitcher": r["pitcher"], "game_date": str(r["game_date"]),
                "block": r["block"]})
        consensus_shared = {
            "policy": "shared_population",
            "cohort_denominator": len(cohort_keys),
            "matched": model_rows.height,
            "unmatched": unmatched.height,
            "unmatched_by_reason": by_reason,
            "note": ("model-vs-consensus scored on the declared shared "
                     "population only; the original cohort remains the "
                     "coverage denominator; book/LTBO populations are "
                     "separate and disclose their own denominators"),
        }
    n_consensus_unmatched = consensus.height - model_rows.height

    # ---- model-vs-consensus: EXISTING outcome scorer + uncertainty
    sc = mk.score_starts(model_rows)
    per = sc.pop("_per_start")
    sc["slate_date_bootstrap"] = mk.cmp_bootstrap(
        per, model_rows, n_boot=n_boot, seed=seed)

    # ---- book-vs-LTBO: the same extracted paired line-score
    # definitions (mk.paired_line_scores) + the same bootstrap. The
    # market frames carry the REDUCED key (game_pk, pitcher); the team
    # side is inherited from the model frame, whose (game_pk, pitcher)
    # mapping is asserted unique (ambiguous mapping would refuse).
    market_key_unique = (
        model_frame.group_by(["game_pk", "pitcher"]).agg(n=pl.len())
        .filter(pl.col("n") > 1).height == 0)
    if not market_key_unique:
        raise ValueError(
            "model frame (game_pk, pitcher) pairs are not unique; the "
            "reduced market key would map ambiguously; refusing")
    book_rows = ltbo.join(
        model_frame.select(["game_pk", "side", "pitcher", "game_date",
                            "block", "realized_k"]),
        on=["game_pk", "pitcher"], how="inner")
    n_book_rows_unmatched = ltbo.height - book_rows.height
    book_scores = {}
    for book in sorted(book_rows["book"].unique().to_list()):
        grp = book_rows.filter(pl.col("book") == book).sort(START_KEYS)
        o = np.asarray(
            [1.0 if int(k) > float(l) else 0.0
             for k, l in zip(grp["realized_k"].to_list(),
                             grp["line"].to_list())], dtype=float)
        p_book = np.asarray(grp["p_over_book"].to_list(), dtype=float)
        p_ltbo = np.asarray(grp["p_over_ltbo"].to_list(), dtype=float)
        scores = mk.paired_line_scores(o, p_book, p_ltbo)
        boot = mk.cmp_bootstrap(
            {"o": o, "p_m": p_book, "p_c": p_ltbo},
            grp.select("game_date", "block"), n_boot=n_boot, seed=seed)
        book_scores[book] = {"n_starts": len(grp), **scores,
                             "slate_date_bootstrap": boot}

    coverage = {
        "cohort": {"n_keys": len(cohort_keys),
                   "content_hash": expected_cohort_hash,
                   "match": True},
        "n_forecast_starts": len(forecast_keys_in(k_pmf)),
        "observed_only_outside_cohort": {
            "n": len(observed_outside_cohort),
            "keys": [list(k) for k in observed_outside_cohort]},
        "n_matched_model_starts": model_frame.height,
        "consensus_starts_total": consensus.height,
        "n_consensus_unmatched_to_model": n_consensus_unmatched,
        "consensus_shared_population": consensus_shared,
        "consensus_matched_starts": consensus_matched_rows,
        "consensus_unmatched_starts": consensus_unmatched_rows,
        "ltbo_unavailable_rows": n_ltbo_unavailable,
        "book_rows": book_probs.height,
        "book_vs_ltbo_denominators": {
            str(book): s["n_starts"]
            for book, s in sorted(book_scores.items())},
        "quotes_funnel": funnel,
    }
    return {
        "model_rows": model_rows,
        "consensus": consensus,
        "book_probs": book_probs,
        "ltbo": ltbo,
        "model_vs_consensus": sc,
        "book_scores": book_scores,
        "coverage": coverage,
    }


def forecast_keys_in(k_pmf: pl.DataFrame) -> set:
    """Complete forecast start identity set (keyed PMF contract)."""
    return {(int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            for r in k_pmf.select(START_KEYS).unique().iter_rows(
                named=True)}
