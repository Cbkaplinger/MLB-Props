"""market-eval F-2 OUTCOME-FREE reference-uniqueness audit (read-only).

Audits a frozen prep directory (default: outputs/prep_v2) for the F-2
defect class WITHOUT touching any outcome data:

  1. Input integrity: the four sha256_16 input hashes in the prep manifest
     re-hashed against the current files on disk.
  2. Duplicate reference keys in the frozen outputs at the contract grains:
     closing_refs (start, line, book); actionable_pairs (start, line, book);
     paper_bets (start, line, side); matched_contracts (start, line, side);
     eval observations (chosen_for_eval) (start, line).
  3. In-memory rebuild of the pipeline from the frozen inputs with the
      CURRENT market_eval.py helpers (outcome-free: no realized-K read),
      then key-set + count comparison against the frozen outputs.
   4. EXPANDED (C3): OLD vs NEW eval-pair selection (pre- vs post- book-name
      tiebreak) on prep_v2 data - tie-group analysis, selected
      keys/books/prices old-vs-new, frozen-vs-NEW comparison, and
      probability-fix consequences (integer lines, push mass, EV formula);
      paper bets rebuilt under both rules. No realized_k read.
   5. Scorer prep-hash gate (_prep_hash_check) against the frozen prep.

Reads: the prep parquets, the prep manifest, and the four frozen inputs.
Writes: nothing. Prints one JSON report to stdout.

ASCII only (cp1252 console).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_eval as me  # noqa: E402


def _dup_audit(df: pl.DataFrame, keys: list, name: str) -> dict:
    n = df.height
    n_keys = df.select(keys).n_unique() if n else 0
    dup_groups = 0
    dup_rows = 0
    affected = None
    if n != n_keys:
        g = df.group_by(keys).agg(pl.len().alias("_n")).filter(pl.col("_n") > 1)
        dup_groups = int(g.height)
        dup_rows = int(g["_n"].sum())
        affected = df.join(g.drop("_n"), on=keys, how="semi")
    return {
        "table": name,
        "key": keys,
        "rows": n,
        "distinct_keys": n_keys,
        "duplicate_key_groups": dup_groups,
        "surplus_rows_from_duplicates": dup_rows - dup_groups if dup_groups else 0,
        "affected_starts": int(affected.select("game_pk", "pitcher").n_unique())
        if affected is not None else 0,
    }


def _rebuild() -> dict:
    """Rebuild the prep pipeline in memory from the frozen inputs using the
    CURRENT helpers (outcome-free)."""
    quotes, _ = me.load_quotes(me.DEFAULT_BOOK_LINES)
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
    closing_refs = me.pair_sides(pre)
    return {
        "eligible": eligible,
        "actionable": act,
        "closing_side_refs": closing_side_refs,
        "paired_all": paired_all,
        "eval_pairs": eval_pairs,
        "closing_refs": closing_refs,
    }


def _eval_pairs_old(paired: pl.DataFrame) -> pl.DataFrame:
    """Pre-850aa38 (ORIGINAL registration) observation rule: ONE pair per
    (start, line) by max total decimal, then book priority, then latest ts.
    NO book-name tiebreak - two books both outside BOOK_PRIORITY tie on all
    three keys and the keep=first choice fell to row order (nondeterministic
    across processes). Emulated exactly as the frozen prep_v2 was built."""
    if paired.height == 0:
        return paired
    prio_map = {b: i for i, b in enumerate(me.BOOK_PRIORITY)}
    ranked = paired.with_columns(
        pl.col("book")
        .replace_strict(prio_map, default=len(me.BOOK_PRIORITY), return_dtype=pl.Int64)
        .alias("_prio")
    ).with_columns(
        (pl.col("d_over") + pl.col("d_under")).alias("_total_dec")
    ).sort(
        ["_total_dec", "_prio", "pair_ts"], descending=[True, False, True]
    )
    return ranked.unique(subset=["game_pk", "pitcher", "line"], keep="first",
                         maintain_order=True).drop("_prio", "_total_dec")


def _tie_analysis(paired: pl.DataFrame) -> dict:
    """Locate (start, line) groups where the OLD rule was ambiguous: >= 2
    candidate pairs tie EXACTLY on the three registered keys (total decimal
    within 1e-9, book-priority index, pair_ts). For every tie group the OLD
    selection could have been ANY tied candidate (nondeterministic); the NEW
    rule picks the lexicographically first book. Reports the tie-set book
    and price spreads, i.e. the worst-case selection/book/price consequence
    of the tiebreak repair."""
    EPS = 1e-9
    keys = ["game_pk", "pitcher", "line"]
    out = {
        "definition": "groups with >=2 candidate pairs tied on (total decimal "
                      "within 1e-9, book-priority index, pair_ts); OLD rule "
                      "was nondeterministic exactly there",
        "tie_groups": 0,
        "affected_starts": 0,
        "max_books_per_tie_set": 0,
        "max_price_spread_in_tie_set": 0.0,
        "max_p_market_spread_in_tie_set": 0.0,
    }
    if paired.height == 0:
        return out
    prio_map = {b: i for i, b in enumerate(me.BOOK_PRIORITY)}
    df = paired.with_columns(
        pl.col("book")
        .replace_strict(prio_map, default=len(me.BOOK_PRIORITY), return_dtype=pl.Int64)
        .alias("_prio")
    ).with_columns(
        (pl.col("d_over") + pl.col("d_under")).alias("_total_dec")
    )
    mx = df.group_by(keys).agg(pl.col("_total_dec").max().alias("_max"))
    t1 = df.join(mx, on=keys).filter(
        (pl.col("_total_dec") - pl.col("_max")).abs() < EPS)
    pm = t1.group_by(keys).agg(pl.col("_prio").min().alias("_pmin"))
    t2 = t1.join(pm, on=keys).filter(pl.col("_prio") == pl.col("_pmin"))
    tm = t2.group_by(keys).agg(pl.col("pair_ts").max().alias("_tmax"))
    t3 = t2.join(tm, on=keys).filter(pl.col("pair_ts") == pl.col("_tmax"))
    tied = t3.group_by(keys).agg(
        pl.len().alias("_n_tied"),
        pl.col("book").min().alias("_book_lo"),
        pl.col("book").max().alias("_book_hi"),
        pl.col("price_over").min().alias("_po_lo"),
        pl.col("price_over").max().alias("_po_hi"),
        pl.col("price_under").min().alias("_pu_lo"),
        pl.col("price_under").max().alias("_pu_hi"),
        pl.col("p_over_mkt").min().alias("_pm_lo"),
        pl.col("p_over_mkt").max().alias("_pm_hi"),
    ).filter(pl.col("_n_tied") > 1)
    out["tie_groups"] = int(tied.height)
    if tied.height:
        out["affected_starts"] = int(
            tied.select("game_pk", "pitcher").n_unique())
        out["max_books_per_tie_set"] = int(tied["_n_tied"].max())
        spread = tied.select(
            (pl.col("_po_hi") - pl.col("_po_lo")).abs().alias("_s1"),
            (pl.col("_pu_hi") - pl.col("_pu_lo")).abs().alias("_s2"),
            (pl.col("_pm_hi") - pl.col("_pm_lo")).abs().alias("_s3"),
        )
        out["max_price_spread_in_tie_set"] = float(
            max(spread["_s1"].max(), spread["_s2"].max()))
        out["max_p_market_spread_in_tie_set"] = float(spread["_s3"].max())
        out["book_pairs"] = sorted(set(zip(
            tied["_book_lo"].to_list(), tied["_book_hi"].to_list())))
    return out


def _selection_comparison(rb: dict, frozen: dict) -> dict:
    """OLD vs NEW selection on prep_v2 data + frozen-vs-NEW consequence
    check (outcome-free: never touches realized_k)."""
    paired_all = rb["paired_all"]
    new_ep = rb["eval_pairs"]
    old_ep = _eval_pairs_old(paired_all)
    sel_keys = ["game_pk", "pitcher", "line"]
    cmp_cols = sel_keys + ["book", "price_over", "price_under"]

    new_s = new_ep.select(cmp_cols).sort(sel_keys)
    old_s = old_ep.select(cmp_cols).sort(sel_keys)
    same_keys = bool(
        new_s.select(sel_keys).equals(old_s.select(sel_keys)))
    j = old_s.join(new_s, on=sel_keys, suffix="_new")
    book_diff = int(j.filter(pl.col("book") != pl.col("book_new")).height)
    price_diff = int(j.filter(
        (pl.col("price_over") != pl.col("price_over_new"))
        | (pl.col("price_under") != pl.col("price_under_new"))).height)

    report = {
        "rule_under_comparison": {
            "OLD": "max total decimal -> book priority -> latest ts (no "
                   "book-name tiebreak; pre-850aa38, the rule prep_v2 was "
                   "built with)",
            "NEW": "max total decimal -> book priority -> latest ts -> book "
                   "name ascending (C3/850aa38)",
        },
        "old_vs_new_rebuild": {
            "eval_pairs": new_ep.height,
            "selection_keys_identical": same_keys,
            "selections_with_book_change": book_diff,
            "selections_with_price_change": price_diff,
        },
        "tie_analysis": _tie_analysis(paired_all),
    }

    # frozen prep_v2 was built with the OLD rule; compare the FROZEN chosen
    # eval observations against the NEW-rule rebuild on every contract grain
    frz = frozen["actionable_pairs"].filter(pl.col("chosen_for_eval")).select(
        cmp_cols).sort(sel_keys)
    fj = frz.join(new_s, on=sel_keys, suffix="_new")
    report["frozen_prep_v2_vs_new_rule"] = {
        "frozen_eval_observations": frz.height,
        "new_eval_pairs": new_s.height,
        "keys_identical": bool(
            frz.select(sel_keys).equals(new_s.select(sel_keys))),
        "book_mismatches": int(
            fj.filter(pl.col("book") != pl.col("book_new")).height),
        "price_mismatches": int(fj.filter(
            (pl.col("price_over") != pl.col("price_over_new"))
            | (pl.col("price_under") != pl.col("price_under_new"))).height),
    }

    # probability-fix consequences on frozen data (outcome-free):
    # (a) integer lines (the build_prob_table 0.0-line push fix) - count them
    # (b) push mass anywhere (if 0, the EV p_h3_lose fix cannot change a
    #     persisted value because 1 - p_win == p_lose when push == 0)
    # (c) recompute ev_h3/ev_l5 with the FIXED formula from frozen columns
    mc = frozen["matched_contracts"]
    recomputed_ev = mc.with_columns(
        (pl.col("p_h3_win") * (pl.col("decimal_odds") - 1.0)
         - pl.col("p_h3_lose")).alias("_ev_h3_fixed"),
        (pl.col("p_l5_win") * (pl.col("decimal_odds") - 1.0)
         - pl.col("p_l5_lose")).alias("_ev_l5_fixed"),
    )
    report["probability_fix_consequences_frozen"] = {
        "integer_line_rows": int(mc.filter((pl.col("line") % 1.0) == 0.0).height),
        "max_p_h3_push_frozen": float(mc["p_h3_push"].max()),
        "max_p_l5_push_frozen": float(mc["p_l5_push"].max()),
        "max_abs_ev_h3_diff_fixed_formula_vs_frozen": float(
            (recomputed_ev["_ev_h3_fixed"] - recomputed_ev["ev_h3"]).abs().max()),
        "max_abs_ev_l5_diff_fixed_formula_vs_frozen": float(
            (recomputed_ev["_ev_l5_fixed"] - recomputed_ev["ev_l5"]).abs().max()),
        "note": "model probabilities join on (start, line) only and are "
                "invariant under the book tiebreak; with zero integer rows "
                "and zero push mass, the C3 probability/EV fixes cannot "
                "change any persisted prep value",
    }

    # paper bets rebuilt under OLD vs NEW selection (key/book/price level)
    if new_ep.height and rb["closing_side_refs"].height:
        payload = me.load_payload(me.DEFAULT_PAYLOAD)
        probs = me.build_prob_table(
            payload, new_ep["line"].unique().to_list())
        bets_new = me.build_paper_bets(new_ep, probs, rb["closing_side_refs"])
        bets_old = me.build_paper_bets(old_ep, probs, rb["closing_side_refs"])
        bet_cols = ["game_pk", "pitcher", "line", "side", "book", "price"]
        bn = bets_new.select(bet_cols).sort(bet_cols)
        bo = bets_old.select(bet_cols).sort(bet_cols)
        bj = bo.join(bn, on=["game_pk", "pitcher", "line", "side"],
                     suffix="_new")
        report["paper_bets_old_vs_new_rebuild"] = {
            "bets_new": bn.height,
            "bets_old": bo.height,
            "bet_keys_identical": bool(
                bn.select(["game_pk", "pitcher", "line", "side"])
                .equals(bo.select(["game_pk", "pitcher", "line", "side"]))),
            "bets_with_book_change": int(
                bj.filter(pl.col("book") != pl.col("book_new")).height),
            "bets_with_price_change": int(bj.filter(
                pl.col("price") != pl.col("price_new")).height),
        }
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="F-2 outcome-free reference-uniqueness audit (read-only)"
    )
    ap.add_argument("--prep-dir", type=Path, default=me.DEFAULT_OUT_DIR,
                    help="frozen prep directory to audit (read-only)")
    args = ap.parse_args(argv)
    prep = args.prep_dir

    report = {
        "spec": "market-eval F-2 reference-uniqueness audit (outcome-free, "
                "read-only; no realized-K join, no scoring)",
        "prep_dir": str(prep),
    }

    # ---- 1. input integrity vs prep manifest ------------------------------
    manifest = json.loads((prep / "manifest.json").read_text(encoding="utf-8"))
    report["input_hashes"] = {
        fname: {"manifest": want, "actual": me.sha256_16(
            Path(me.DEFAULT_BOOK_LINES).parent / fname)
            if (Path(me.DEFAULT_BOOK_LINES).parent / fname).exists() else None}
        for fname, want in manifest["inputs_sha256_16"].items()
    }
    # resolve each input through market_eval defaults by name
    default_inputs = {
        "book_lines_pitcher.parquet": me.DEFAULT_BOOK_LINES,
        "snapshot_envelope.parquet": me.DEFAULT_ENVELOPE,
        "predictor_payload.parquet": me.DEFAULT_PAYLOAD,
        "player_id_map.parquet": me.DEFAULT_ID_MAP,
    }
    hashes_ok = True
    for fname, want in manifest["inputs_sha256_16"].items():
        p = default_inputs[fname]
        got = me.sha256_16(p) if p.exists() else None
        report["input_hashes"][fname] = {"manifest": want, "actual": got,
                                         "match": got == want}
        hashes_ok &= got == want
    report["inputs_match_manifest"] = bool(hashes_ok)

    # ---- 2. duplicate reference keys in the FROZEN outputs ---------------
    frozen = {
        "closing_refs": pl.read_parquet(prep / "closing_refs.parquet"),
        "actionable_pairs": pl.read_parquet(prep / "actionable_pairs.parquet"),
        "paper_bets": pl.read_parquet(prep / "paper_bets.parquet"),
        "matched_contracts": pl.read_parquet(prep / "matched_contracts.parquet"),
    }
    report["frozen_output_uniqueness"] = [
        _dup_audit(frozen["closing_refs"],
                   ["game_pk", "pitcher", "line", "book"], "closing_refs"),
        _dup_audit(frozen["actionable_pairs"],
                   ["game_pk", "pitcher", "line", "book"], "actionable_pairs"),
        _dup_audit(frozen["paper_bets"],
                   ["game_pk", "pitcher", "line", "side"], "paper_bets"),
        _dup_audit(frozen["matched_contracts"],
                   ["game_pk", "pitcher", "line", "side"], "matched_contracts"),
    ]
    ev = frozen["actionable_pairs"].filter(pl.col("chosen_for_eval"))
    report["frozen_output_uniqueness"].append(
        _dup_audit(ev, ["game_pk", "pitcher", "line"], "eval_observations")
    )

    # ---- 3. in-memory rebuild with CURRENT helpers vs frozen -------------
    rb = _rebuild()
    bet_cols = ["game_pk", "pitcher", "line", "side", "book", "price"]
    probs = me.build_prob_table(
        payload := me.load_payload(me.DEFAULT_PAYLOAD),
        rb["eval_pairs"]["line"].unique().to_list(),
    ) if rb["eval_pairs"].height else pl.DataFrame()
    rebuilt_bets = (
        me.build_paper_bets(rb["eval_pairs"], probs, rb["closing_side_refs"])
        if rb["eval_pairs"].height else rb["eval_pairs"]
    )
    fb = frozen["paper_bets"].select(bet_cols).sort(bet_cols)
    nbb = rebuilt_bets.select(bet_cols).sort(bet_cols)
    report["rebuilt_vs_frozen"] = {
        "note": "in-memory rebuild from frozen inputs with CURRENT "
                "market_eval.py (outcome-free); key/price sets compared",
        "frozen_bets": frozen["paper_bets"].height,
        "rebuilt_bets": rebuilt_bets.height,
        "frozen_closing_refs": frozen["closing_refs"].height,
        "rebuilt_closing_refs": rb["closing_refs"].height,
        "frozen_eval_pairs": ev.height,
        "rebuilt_eval_pairs": rb["eval_pairs"].height,
        "frozen_paired_actionable": frozen["actionable_pairs"].height,
        "rebuilt_paired_actionable": rb["paired_all"].height,
        "bet_key_price_sets_identical": bool(fb.equals(nbb)),
    }
    if not fb.equals(nbb):
        fk = fb.select(["game_pk", "pitcher", "line", "side", "book"])
        nk = nbb.select(["game_pk", "pitcher", "line", "side", "book"])
        report["rebuilt_vs_frozen"]["bets_only_in_frozen"] = int(
            fk.join(nk, on=["game_pk", "pitcher", "line", "side", "book"],
                    how="anti").height)
        report["rebuilt_vs_frozen"]["bets_only_in_rebuilt"] = int(
            nk.join(fk, on=["game_pk", "pitcher", "line", "side", "book"],
                    how="anti").height)
        changed = (
            fb.join(nbb, on=["game_pk", "pitcher", "line", "side", "book"],
                    suffix="_new")
            .filter(pl.col("price") != pl.col("price_new"))
        )
        report["rebuilt_vs_frozen"]["bets_with_price_change"] = int(changed.height)
        report["rebuilt_vs_frozen"]["price_changed_starts"] = int(
            changed.select("game_pk", "pitcher").n_unique()) if changed.height else 0

    # ---- 4. EXPANDED: OLD vs NEW selection + probability-fix consequences --
    report["expanded_selection_audit"] = _selection_comparison(rb, frozen)

    # ---- 5. scorer prep-hash gate (compatibility with unchanged prep_v2) ---
    try:
        me._prep_hash_check(prep)
        report["scorer_prep_hash_gate"] = {
            "gate": "market_eval._prep_hash_check",
            "result": "PASS (all frozen prep_v2 output hashes match the "
                      "prep manifest; the scorer accepts unchanged prep_v2)",
        }
    except me.ScoreReadError as e:
        report["scorer_prep_hash_gate"] = {"gate": "market_eval._prep_hash_check",
                                           "result": "FAIL: %s" % e}

    # ---- 6. same-book closing-reference linkage for selected bets ---------
    # build_paper_bets joins closing_side_refs on (game_pk, pitcher, line,
    # book, side): the CLV reference is the BET BOOK's OWN closing side
    # price (same-book by construction). The F-2 _assert_unique guard on
    # (start, line, book, side) makes the left join 1:0..1; coverage is
    # computed here directly from the frozen table (outcome-free: no
    # realized_k read).
    pb = frozen["paper_bets"]
    linked = pb.filter(pl.col("close_price").is_not_null())
    report["same_book_closing_linkage"] = {
        "join_keys": ["game_pk", "pitcher", "line", "book", "side"],
        "semantics": "same-book by construction: the closing reference "
                     "shares the bet's own (book, side); guarded unique at "
                     "(start, line, book, side) so the join cannot fan out",
        "bets": pb.height,
        "bets_with_same_book_closing_ref": linked.height,
        "bets_without_closing_ref": pb.height - linked.height,
        "linkage_pct": round(100.0 * linked.height / pb.height, 2)
        if pb.height else 0.0,
        "outcome_free": True,
    }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
