"""Workload compatibility + lineup availability receipts (gates B and C).

Bounded: no fitting, no scoring. Compares the I3b workload target per
canonical kcount-integration eval start against pa_completed_v1 completed
PAs, reason-codes every difference, and inventories realized initial-lineup
coverage (mode-3 oracle) for the same starts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import pa_lgbm_scaffold as sc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402

KC = Path(r"C:\Users\ckaplinger\MLB-Props-Research"
          r"\kcount-integration-20261008_152747")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    root = Path(args.data_root) if args.data_root else (
        Path(__file__).resolve().parents[2] / "data")
    preds = pl.read_csv(KC / "predictions.csv")
    print("kcount eval rows:", preds.height)
    label = sc.build_pa_label_table(frames_2023(root))
    v1 = (label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
          .group_by(["game_pk", "pitcher"])
          .agg(pl.len().alias("v1_pa"), pl.col("y").sum().alias("v1_k")))
    # start-level comparison
    j = (preds.select(["game_pk", "pitcher", "game_date", "PA", "K",
                       "batting_team", "is_home"])
         .join(v1, on=["game_pk", "pitcher"], how="left")
         .with_columns([
             (pl.col("PA") - pl.col("v1_pa")).alias("diff"),
             (pl.col("K") - pl.col("v1_k")).alias("k_diff"),
         ]))
    matched = j.filter(pl.col("v1_pa").is_not_null())
    n_missing_join = int(j.height - matched.height)
    n_equal = int((matched["diff"] == 0).sum())
    diffs = matched.filter(pl.col("diff") != 0)
    # reason-code: truncated + mixed + mid-PA + baserunning per start-game
    reasons = (label.group_by(["game_pk", "pitcher"]).agg(
        ((pl.col("pa_class") == sc.CLASS_INCOMPLETE)
         & (pl.col("event") == "truncated_pa")).sum().alias("n_trunc"),
        ((pl.col("pa_class") == sc.CLASS_INCOMPLETE)
         & pl.col("mixed_batter")).sum().alias("n_mixed"),
        ((pl.col("pa_class") == sc.CLASS_INCOMPLETE)
         & ~pl.col("mixed_batter")
         & (pl.col("event") != "truncated_pa")).sum().alias("n_other_inc"),
        (pl.col("pa_class") == sc.CLASS_BASERUNNING).sum().alias("n_base"),
        pl.col("mid_pa_pitcher_change").sum().alias("n_midpa")))
    diffs = diffs.join(reasons, on=["game_pk", "pitcher"], how="left")
    explained = diffs.with_columns(
        (pl.col("diff").abs() <= (
            pl.col("n_trunc").fill_null(0)
            + pl.col("n_mixed").fill_null(0)
            + pl.col("n_other_inc").fill_null(0)
            + pl.col("n_base").fill_null(0)
            + pl.col("n_midpa").fill_null(0)
            + 1)).alias("plausibly_explained"))
    summary = {
        "n_eval_starts": int(preds.height),
        "n_matched_to_v1": int(matched.height),
        "n_unmatched_join": n_missing_join,
        "n_diff_zero": n_equal,
        "n_diff_nonzero": int(diffs.height),
        "n_plausibly_explained_by_known_classes": int(
            explained["plausibly_explained"].sum()),
        "diff_distribution": {
            "min": int(matched["diff"].min()),
            "p50": float(matched["diff"].median()),
            "max": int(matched["diff"].max()),
        },
        "k_diff_zero": int((matched["k_diff"] == 0).sum()),
        "k_diff_nonzero": int((matched["k_diff"] != 0).sum()),
    }
    print(json.dumps(summary, indent=1))

    # lineup availability (mode-3 oracle): realized initial lineup slots
    bg = pl.read_parquet(root / "processed" / "batter_games.parquet")
    init = bg.filter((pl.col("is_initial_lineup") == 1)
                     & pl.col("lineup_slot").is_not_null())
    slots = init.group_by(["game_pk", "bat_team"]).agg(
        pl.col("lineup_slot").n_unique().alias("n_slots"))
    full = slots.filter(pl.col("n_slots") == 9)
    lineup = (preds.select(["game_pk", "batting_team"])
              .join(full, left_on=["game_pk", "batting_team"],
                    right_on=["game_pk", "bat_team"], how="left"))
    lineup_summary = {
        "mode": "mode-3 ORACLE realized initial lineup (no pregame "
                "timestamp archive for 2023-2025; non-deployable)",
        "n_starts": int(preds.height),
        "n_starts_with_full_9slot_initial_lineup": int(
            (lineup["n_slots"] == 9).sum()),
        "n_starts_missing_or_partial": int(
            (lineup["n_slots"] != 9).sum()
            + lineup["n_slots"].is_null().sum()),
    }
    print(json.dumps(lineup_summary, indent=1))

    report = {
        "generated": str(date.today()),
        "workload_target": (
            "I3b/kcount-integration realized per-start PA (predictions.csv "
            "column PA) on the 4,446 canonical eval starts"),
        "workload_compatibility": summary,
        "lineup_availability": lineup_summary,
        "unexplained_examples": [
            {k: r[k] for k in ("game_pk", "pitcher", "PA", "v1_pa", "diff",
                               "n_trunc", "n_mixed", "n_other_inc",
                               "n_base", "n_midpa")}
            for r in explained.filter(~pl.col("plausibly_explained"))
            .head(10).iter_rows(named=True)],
        "verdict": (
            "COMPATIBLE-FOR-DIAGNOSTIC if differences are small and "
            "reason-coded: each BF support value n indexes a v1 completed-PA "
            "opportunity sequence of length n; the workload target and v1 "
            "opportunity concept differ only by the classified row classes "
            "above, counted and disclosed per start; no ratio correction."),
        "code": {"run_pa_workload_lineup_check.py": "sha recorded in git"},
    }
    (out_dir / "workload_lineup_check.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="ascii")
    print("WROTE %s" % out_dir)
    return 0


def frames_2023(root: Path) -> pl.DataFrame:
    path = (root / "Savant-Data" / "regular" / "2023"
            / "statcast_2023_regular.parquet")
    return pl.read_parquet(path)


if __name__ == "__main__":
    raise SystemExit(main())
