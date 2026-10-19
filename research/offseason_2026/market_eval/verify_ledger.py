"""market-eval-v1 ADDITIVE verification + benchmark separation + ledger.

Executed 2026-10-14 under EXPERIMENT_CARD.md versioned correction C2.
Outcome-free: NO realized-K join, NO scoring, NO fitting.

What it does (read-only on all frozen inputs and prep outputs):
  1. Rebuilds the prep pipeline in memory from the frozen inputs using the
     SAME registered helpers in market_eval.py, and verifies key-set identity
     against the frozen prep parquets (eval pairs, paper bets).
  2. Exclusion ledger: sequential stages from the original 7,194-start cohort
     to paper-selected opportunities (start counts and contract counts
     separate), written to outputs/verification/exclusion_ledger.json.
  3. Clock / identity / cohort-date verification against the envelope
     (tier A commence_time clock; tier B snapshot-label proxy), including the
     per-snapshot T-minus distributions.
  4. Benchmark separation: opening-time, later-pregame, and closing reference
     pairs as SEPARATE fields per chosen (start, line) observation, written to
     outputs/verification/benchmark_refs.parquet.
  5. Quote-time verification: predictor-information time (payload
     forecast_cutoff, ET) <= selected quote time; quotes predating predictor
     availability are flagged reference-only (counted; Tier A primary /
     Tier B sensitivity split disclosed).
  6. Selection-rule delta: the ONE registered book-selection rule (per
     (start, line, side): latest snapshot per book -> BOOK_PRIORITY -> best
     decimal price) measured against the frozen prep selections.
  7. Coverage recalculation after exclusions; compared to prep_summary.json.

Writes: outputs/verification/{verification_report.json, exclusion_ledger.json,
benchmark_refs.parquet, prep_summary_original.json}; updates
outputs/prep/prep_summary.json ADDITIVELY (new "verification" key only;
original keys byte-preserved).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_eval as me  # noqa: E402

PREP_DIR = Path(__file__).resolve().parent / "outputs" / "prep_v2"
VER_DIR = Path(__file__).resolve().parent / "outputs" / "verification"

ET = ZoneInfo("America/New_York")


def predictor_available_ts(forecast_cutoff) -> datetime:
    """First instant (UTC) at which the frozen predictor payload for a start
    is available: 00:00 ET on the forecast_cutoff (scheduled game_date).
    Conservative: any quote at/after this instant postdates the model."""
    d = forecast_cutoff
    return datetime(d.year, d.month, d.day, tzinfo=ET).astimezone(ZoneInfo("UTC"))


def pair_sides_earliest(quotes: pl.DataFrame) -> pl.DataFrame:
    """Opening-time paired reference: per (start, line, book) the EARLIEST
    both-sides clock in the given set (mirror of me.pair_sides with min)."""
    if quotes.height == 0:
        return quotes
    keys = ["game_pk", "pitcher", "line", "book"]
    both = (
        quotes.group_by(keys + ["quote_ts"])
        .agg(pl.col("side").n_unique().alias("n_sides"))
        .filter(pl.col("n_sides") == 2)
    )
    if both.height == 0:
        return both
    pair_ts = both.group_by(keys).agg(pl.col("quote_ts").min().alias("pair_ts"))
    at_pair = (
        quotes.join(pair_ts, on=keys, how="inner")
        .filter(pl.col("quote_ts") == pl.col("pair_ts"))
    )
    ov = (
        at_pair.filter(pl.col("side") == "over")
        .drop("side", "snapshot", "quote_ts", "market")
        .rename({"price": "price_over"})
        .with_columns(me.decimal_expr("price_over").alias("d_over"))
    )
    un = (
        at_pair.filter(pl.col("side") == "under")
        .select(keys + ["price"])
        .rename({"price": "price_under"})
        .with_columns(me.decimal_expr("price_under").alias("d_under"))
    )
    paired = ov.join(un, on=keys, how="inner")
    if paired.height:
        paired = paired.unique(keep="first", maintain_order=True)
    if paired.height == 0:
        return paired
    inv_o = 1.0 / pl.col("d_over")
    inv_u = 1.0 / pl.col("d_under")
    return paired.with_columns(
        (inv_o / (inv_o + inv_u)).alias("p_over_mkt"),
        (inv_u / (inv_o + inv_u)).alias("p_under_mkt"),
    )


def main() -> int:
    VER_DIR.mkdir(parents=True, exist_ok=True)
    report = {"spec": "market-eval-v1 verification C2 (outcome-free)", "date": "2026-10-14"}

    # ---- rebuild pipeline from frozen inputs (market_eval helpers) --------
    quotes, qmeta = me.load_quotes(me.DEFAULT_BOOK_LINES)
    payload = me.load_payload(me.DEFAULT_PAYLOAD)
    event_map, dup_keys = me.build_event_map(quotes)
    resolved = me.match_starts(payload, event_map, dup_keys, me.DEFAULT_ID_MAP)
    eligible = resolved["eligible"]
    commence = me.load_commence(me.DEFAULT_ENVELOPE)
    eligible = eligible.join(commence, on="event_id", how="left").with_columns(
        pl.col("first_pitch_ts").is_not_null().alias("has_commence"),
    ).with_columns(
        pl.when(pl.col("has_commence")).then(pl.lit(me.TIER_A))
        .otherwise(pl.lit(me.TIER_B)).alias("tier")
    ).with_columns(
        pl.col("forecast_cutoff")
        .map_elements(me.predictor_available_ts, return_dtype=pl.Datetime("us", "UTC"))
        .alias("predictor_available_ts")
    )
    joined = me.attach_quotes(quotes, eligible, event_map)
    act, closing_side_refs, pre = me.split_actionable_closing(joined)
    paired_all = me.pair_sides(act)
    eval_pairs = me.choose_eval_pairs(paired_all)

    # ---- verify against frozen prep parquets ------------------------------
    frozen_pairs = pl.read_parquet(PREP_DIR / "actionable_pairs.parquet")
    frozen_eval = frozen_pairs.filter(pl.col("chosen_for_eval"))
    fp_keys = frozen_eval.select("game_pk", "pitcher", "line", "book").sort(
        ["game_pk", "pitcher", "line", "book"])
    rp_keys = eval_pairs.select("game_pk", "pitcher", "line", "book").sort(
        ["game_pk", "pitcher", "line", "book"])
    pairs_identical = fp_keys.equals(rp_keys)
    frozen_bets = pl.read_parquet(PREP_DIR / "paper_bets.parquet")
    rebuilt_bets = me.build_paper_bets(
        eval_pairs, me.build_prob_table(payload, eval_pairs["line"].unique().to_list()),
        closing_side_refs)
    bet_cols = ["game_pk", "pitcher", "line", "side", "book", "price"]
    bets_identical = (
        frozen_bets.select(bet_cols).sort(bet_cols).equals(
            rebuilt_bets.select(bet_cols).sort(bet_cols))
    )
    report["frozen_prep_reproduction"] = {
        "eval_pair_key_sets_identical": bool(pairs_identical),
        "paper_bet_key_price_sets_identical": bool(bets_identical),
        "frozen_eval_pairs": frozen_eval.height,
        "rebuilt_eval_pairs": eval_pairs.height,
        "frozen_bets": frozen_bets.height,
        "rebuilt_bets": rebuilt_bets.height,
    }
    if not (pairs_identical and bets_identical):
        print("FATAL: rebuilt pipeline does not reproduce frozen prep key sets")
        return 2

    # ---- 1. sequential exclusion ledger -----------------------------------
    matched = pl.read_parquet(PREP_DIR / "matched_contracts.parquet")
    starts_with_contract = matched.select("game_pk", "pitcher").n_unique()
    bet_starts = frozen_bets.select("game_pk", "pitcher").n_unique()
    # reconciliation stage the v1 card silently folded away: starts whose
    # pitcher is resolved but has NO archive event within +/-1 day
    id_map = pl.read_parquet(me.DEFAULT_ID_MAP).select(
        pl.col("mlb_id").alias("pitcher"),
        pl.col("player_name").map_elements(me.sorted_name, return_dtype=pl.String)
        .alias("pitcher_key"),
    )
    resolved_keys = pl.concat([
        resolved["eligible"].select("game_pk", "pitcher"),
        resolved["ambiguous_starts"].select("game_pk", "pitcher"),
    ]).unique()
    resolved_starts = payload.select("game_pk", "pitcher").unique().join(
        id_map, on="pitcher", how="inner")
    n_no_match = int(resolved_starts.join(
        resolved_keys, on=["game_pk", "pitcher"], how="anti").height)
    ledger = {
        "stages_starts": [
            {"stage": "original_cohort", "n": int(payload.select("game_pk", "pitcher").n_unique()),
             "note": "pregame-pa-ext-v1 payload starts (7,194)"},
            {"stage": "identity_resolved", "n": int(resolved_starts.height),
             "excluded_previous": int(resolved["unresolved_ids"].height),
             "note": "minus unresolved MLBAM ids (player_id_map)"},
            {"stage": "event_matched", "n": int(resolved_keys.height),
             "excluded_previous": n_no_match,
             "note": "minus resolved starts with NO archive event for the "
                     "pitcher within +/-1 day (v1 folded these away silently; "
                     "C2 discloses them)"},
            {"stage": "clock_qualified", "n": int(eligible.height),
             "excluded_previous": int(resolved["ambiguous_starts"].height),
             "note": "minus doubleheader-ambiguous (vendor_date, pitcher) keys; "
                     "tier A = envelope commence (verified clock), tier B = snapshot proxy"},
            {"stage": "with_actionable_quote", "n": int(act.select("game_pk", "pitcher").n_unique()),
             "excluded_previous": int(eligible.height - act.select("game_pk", "pitcher").n_unique()),
             "note": ">=1 pre-cutoff non-closing quote at/after predictor availability"},
            {"stage": "usable_paired_contracts", "n": int(starts_with_contract),
             "excluded_previous": int(act.select("game_pk", "pitcher").n_unique() - starts_with_contract),
             "note": ">=1 (line, book, clock) quoting BOTH sides in the actionable set"},
            {"stage": "paper_selected_starts", "n": int(bet_starts),
             "excluded_previous": int(starts_with_contract - bet_starts),
             "note": ">=1 registered paper bet (H3 edge > break_even + 0.02)"},
        ],
        "stages_contracts": [
            {"stage": "k_market_quote_rows", "n": int(qmeta["k_market_rows"])},
            {"stage": "price_valid_rows", "n": int(qmeta["k_market_rows"] - qmeta["price_dropped"]),
             "excluded_previous": int(qmeta["price_dropped"])},
            {"stage": "paired_actionable_book_lines", "n": int(paired_all.height)},
            {"stage": "eval_observations_start_line", "n": int(eval_pairs.height),
             "note": "one per (start, line) by the registered dedup rule"},
            {"stage": "contract_side_rows", "n": int(matched.height)},
            {"stage": "paper_bets", "n": int(frozen_bets.height),
             "note": "one per (start, line, side); complementary sides NOT independent"},
        ],
        "effective_counts": {
            "contract_side_rows": int(matched.height),
            "distinct_start_line_pairs": int(matched.select("game_pk", "pitcher", "line").n_unique()),
            "distinct_starts": int(starts_with_contract),
            "distinct_slate_dates": int(matched["game_date"].n_unique()),
            "both_sides_share": round(float(
                matched.select("game_pk", "pitcher", "line").n_unique()
                and matched.group_by("game_pk", "pitcher", "line").agg(pl.len())
                .filter(pl.col("len") == 2).height
            ) / matched.select("game_pk", "pitcher", "line").n_unique(), 4),
        },
    }
    (VER_DIR / "exclusion_ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    # ---- 2. clock / identity / cohort-date verification -------------------
    tier_a = joined.filter(pl.col("tier") == me.TIER_A)
    tier_b = joined.filter(pl.col("tier") == me.TIER_B)
    clocks = {}
    for label in tier_a["snapshot"].unique().to_list():
        d = (
            tier_a.filter(pl.col("snapshot") == label)
            .select(((pl.col("first_pitch_ts") - pl.col("quote_ts")).dt.total_minutes() / 60.0)
                    .alias("t_minus_h")).drop_nulls()
        )
        if d.height:
            clocks[label] = {
                "n": int(d.height),
                "t_minus_hours_p50": round(float(d["t_minus_h"].median()), 3),
                "t_minus_hours_min": round(float(d["t_minus_h"].min()), 3),
                "t_minus_hours_max": round(float(d["t_minus_h"].max()), 3),
            }
    post_cutoff_quotes_a = int(tier_a.filter(pl.col("quote_ts") >= pl.col("first_pitch_ts")).height)
    b_snaps = {r["snapshot"]: int(r["n"]) for r in
               tier_b.group_by("snapshot").agg(pl.len().alias("n")).sort("snapshot").iter_rows(named=True)}
    report["clock_verification"] = {
        "tier_A_snapshots": clocks,
        "tier_A_post_cutoff_quotes_present_but_excluded": post_cutoff_quotes_a,
        "tier_B_snapshot_counts": b_snaps,
        "tier_B_has_commence_rows": 0,
        "tier_A_starts": int(eligible.filter(pl.col("tier") == me.TIER_A).height),
        "tier_B_starts": int(eligible.filter(pl.col("tier") == me.TIER_B).height),
    }
    report["cohort_dates"] = {
        "min_game_date": str(eligible["game_date"].min()),
        "max_game_date": str(eligible["game_date"].max()),
        "by_tier": {
            t: {"min": str(g["game_date"].min()), "max": str(g["game_date"].max()),
                "n_slate_dates": int(g["game_date"].n_unique())}
            for t, g in ((t, eligible.filter(pl.col("tier") == t))
                         for t in (me.TIER_A, me.TIER_B))
        },
    }
    report["identity_verification"] = {
        "ambiguous_archive_keys": int(dup_keys.height),
        "doubleheader_ambiguous_starts_excluded": int(resolved["ambiguous_starts"].height),
        "unresolved_ids_excluded": int(resolved["unresolved_ids"].height),
        "event_id_unique_per_start": bool(
            eligible.select("game_pk", "pitcher").n_unique() == eligible.height),
        "envelope_commence_unique_per_event": bool(
            commence.select("event_id").n_unique() == commence.height),
    }

    # ---- 3. benchmark separation (opening / later-pregame / closing) ------
    open_pairs = pair_sides_earliest(act)
    keys = ["game_pk", "pitcher", "line"]
    ev = eval_pairs.select(keys + ["book"]).rename({"book": "eval_book"})
    select_cols = ["pair_ts", "price_over", "price_under", "d_over", "d_under", "p_over_mkt"]

    def _attach(bench: pl.DataFrame, src: pl.DataFrame, prefix: str) -> pl.DataFrame:
        ren = {c: prefix + c for c in select_cols}
        return bench.join(
            src.select(keys + ["book"] + select_cols).rename(ren),
            left_on=keys + ["eval_book"], right_on=keys + ["book"], how="left",
        )

    bench = ev.sort(keys)
    bench = _attach(bench, open_pairs, "open_")
    bench = _attach(bench, paired_all, "pregame_")
    bench = _attach(bench, pl.read_parquet(PREP_DIR / "closing_refs.parquet"), "closing_")
    n_sl = ev.height
    bench_cov = {
        "eval_observations": int(n_sl),
        "with_opening_ref": int(bench.filter(pl.col("open_pair_ts").is_not_null()).height),
        "with_later_pregame_ref": int(bench.filter(pl.col("pregame_pair_ts").is_not_null()).height),
        "with_closing_ref": int(bench.filter(pl.col("closing_pair_ts").is_not_null()).height),
        "opening_equals_pregame_single_clock": int(bench.filter(
            (pl.col("open_pair_ts").is_not_null())
            & (pl.col("open_pair_ts") == pl.col("pregame_pair_ts")).fill_null(False)).height),
    }
    bench.write_parquet(VER_DIR / "benchmark_refs.parquet")
    report["benchmark_separation"] = bench_cov

    # ---- 4. quote-time verification ---------------------------------------
    # Prep v2 ENFORCES the floor (actionable requires quote_ts >=
    # predictor_available_ts); here we verify the frozen outputs satisfy it.
    fc = pl.read_parquet(me.DEFAULT_PAYLOAD).select(
        "game_pk", "pitcher", "forecast_cutoff").unique()
    avail = fc.with_columns(
        pl.col("forecast_cutoff")
        .map_elements(predictor_available_ts, return_dtype=pl.Datetime("us", "UTC"))
        .alias("predictor_available_ts")
    ).drop("forecast_cutoff")
    start_keys = ["game_pk", "pitcher"]
    evq = eval_pairs.select(keys + ["book", "pair_ts"]).join(
        fc.select(start_keys + ["forecast_cutoff"]), on=start_keys, how="left")
    evq = evq.join(avail, on=start_keys, how="left")
    n_pre = int(evq.filter(pl.col("pair_ts") < pl.col("predictor_available_ts")).height)
    bq = frozen_bets.select(keys + ["side", "book", "quote_ts", "tier"]).join(
        avail, on=start_keys, how="left")
    n_pre_bets = int(bq.filter(pl.col("quote_ts") < pl.col("predictor_available_ts")).height)
    actq = act.select(keys + ["side", "quote_ts"]).unique().join(avail, on=start_keys, how="left")
    n_pre_quotes = int(actq.filter(pl.col("quote_ts") < pl.col("predictor_available_ts")).height)
    report["quote_time_verification"] = {
        "rule": "predictor_available_ts = forecast_cutoff 00:00 ET (UTC-converted); "
                "a selected quote must satisfy predictor_available_ts <= quote_ts; "
                "earlier quotes are reference-only, not actionable "
                "(ENFORCED in prep v2 actionable set)",
        "actionable_quotes_predating_predictor_in_frozen_prep": n_pre_quotes,
        "eval_pair_observations_predating": n_pre,
        "paper_bets_predating": n_pre_bets,
        "tier_split_of_predating_bets": {
            t: int(bq.filter((pl.col("quote_ts") < pl.col("predictor_available_ts"))
                             & (pl.col("tier") == t)).height)
            for t in (me.TIER_A, me.TIER_B)
        },
        "tier_A_primary": True,
        "tier_B_role": "separately labeled sensitivity",
        "verdict": "PASS (no selected quote predates predictor availability)"
        if (n_pre == 0 and n_pre_bets == 0 and n_pre_quotes == 0) else
        "FLAGGED (reference-only rows present in the frozen actionable set)",
    }

    # ---- 5. selection-rule delta (ONE registered rule) --------------------
    # per (start, line, side): latest actionable snapshot per book (no pairing
    # requirement), then BOOK_PRIORITY, then best decimal price, then name.
    side_quotes = (
        act.select(keys + ["side", "book", "quote_ts", "price"])
        .sort("quote_ts")
        .unique(subset=keys + ["side", "book"], keep="last")
        .with_columns(me.decimal_expr("price").alias("d"))
    )
    one_rule = (
        side_quotes.with_columns(
            pl.col("book").replace_strict(
                {b: i for i, b in enumerate(me.BOOK_PRIORITY)},
                default=len(me.BOOK_PRIORITY), return_dtype=pl.Int64).alias("_prio"))
        .sort(["game_pk", "pitcher", "line", "side", "_prio", "d", "book"],
              descending=[False, False, False, False, False, True, False])
        .unique(subset=keys + ["side"], keep="first")
        .select(keys + ["side", "book"])
        .rename({"book": "one_rule_book"})
    )
    delta = (
        matched.select(keys + ["side", "book"]).rename({"book": "frozen_book"})
        .join(one_rule, on=keys + ["side"], how="left")
    )
    n_diff = int(delta.filter(pl.col("frozen_book") != pl.col("one_rule_book")).height)
    # paper-bet rule delta: frozen (first QUALIFYING book by priority, ties by
    # name) vs registered ordering (ties by best price)
    probs = me.build_prob_table(payload, matched["line"].unique().to_list())
    cand = (
        side_quotes.join(
            probs.select(["game_pk", "pitcher", "line"] +
                         [f"p_h3_{s}" for s in ("over", "under", "push")]),
            on=keys, how="inner")
    )
    qual = cand.with_columns(
        pl.when(pl.col("side") == "over").then(pl.col("p_h3_over"))
        .otherwise(pl.col("p_h3_under")).alias("p_win")
    ).with_columns(
        (pl.col("p_win") > (1.0 / pl.col("d")) + me.MARGIN).alias("_qual"),
        pl.col("book").replace_strict(
            {b: i for i, b in enumerate(me.BOOK_PRIORITY)},
            default=len(me.BOOK_PRIORITY), return_dtype=pl.Int64).alias("_prio"),
    ).filter(pl.col("_qual"))
    frozen_sel = (
        qual.sort(["game_pk", "pitcher", "line", "side", "_prio", "book"])
        .unique(subset=keys + ["side"], keep="first", maintain_order=True)
        .select(keys + ["side", "book"]).rename({"book": "frozen_rule_book"})
    )
    reg_sel = (
        qual.sort(["game_pk", "pitcher", "line", "side", "_prio", "d", "book"],
                  descending=[False, False, False, False, False, True, False])
        .unique(subset=keys + ["side"], keep="first")
        .select(keys + ["side", "book"]).rename({"book": "registered_rule_book"})
    )
    bd = frozen_sel.join(reg_sel, on=keys + ["side"], how="full", coalesce=True)
    n_bet_diff = int(bd.filter(pl.col("frozen_rule_book") != pl.col("registered_rule_book")).height)
    multi = frozen_bets.group_by("game_pk", "pitcher").agg(pl.len().alias("n_bets"))
    report["selection_rule_delta"] = {
        "registered_rule": "per (start, line, side): latest pre-cutoff snapshot "
                           "per book, then BOOK_PRIORITY, then best decimal price, "
                           "then book name; paper-bet edge gate selects the "
                           "(start, line, side) cells",
        "eval_pair_book_diffs_frozen_vs_one_rule": n_diff,
        "paper_bet_book_diffs_frozen_vs_registered": n_bet_diff,
        "note": "frozen prep outputs stand (write-once); the registered rule "
                "governs interpretation + any future re-prep; deltas disclosed",
        "starts_with_multiple_bets": int(multi.filter(pl.col("n_bets") > 1).height),
        "max_bets_per_start": int(multi["n_bets"].max()),
        "ladder_correlation_warning": "multiple bets per start share the same "
                                      "realized K (ladder exposure); ROI/PnL are "
                                      "NOT independent across a start's bets",
    }

    # ---- 6. coverage recalculation ----------------------------------------
    cov = me.per_start_coverage(eligible, act, closing_side_refs, pre)
    cov_all = me.coverage_counts(cov)
    frozen_summary = json.loads((PREP_DIR / "prep_summary.json").read_text(encoding="utf-8"))
    cov_match = cov_all == frozen_summary["coverage"]["after_exclusions_all"]
    report["coverage_recalculation"] = {
        "recalculated": cov_all,
        "matches_frozen_prep_summary": bool(cov_match),
    }
    if not cov_match:
        print("FATAL: recalculated coverage differs from frozen prep_summary")
        print(json.dumps(cov_all, indent=2))
        return 2

    # ---- 7. update prep_summary.json ADDITIVELY ---------------------------
    backup = VER_DIR / "prep_summary_original.json"
    if not backup.exists():
        backup.write_text(
            (PREP_DIR / "prep_summary.json").read_text(encoding="utf-8"),
            encoding="utf-8")
    frozen_summary["verification"] = {
        "date": "2026-10-14",
        "correction": "C2 additive verification (verify_ledger.py); original keys unchanged",
        "coverage_recalculated_matches": bool(cov_match),
        "frozen_prep_reproduction": report["frozen_prep_reproduction"],
        "quote_time_verdict": report["quote_time_verification"]["verdict"],
        "benchmark_outputs": "outputs/verification/benchmark_refs.parquet",
        "exclusion_ledger": "outputs/verification/exclusion_ledger.json",
        "verification_report": "outputs/verification/verification_report.json",
    }
    (PREP_DIR / "prep_summary.json").write_text(
        json.dumps(frozen_summary, indent=2), encoding="utf-8")

    (VER_DIR / "verification_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "frozen_prep_reproduction", "coverage_recalculation",
        "quote_time_verification", "selection_rule_delta",
        "benchmark_separation")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
