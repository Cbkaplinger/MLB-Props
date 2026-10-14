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

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
