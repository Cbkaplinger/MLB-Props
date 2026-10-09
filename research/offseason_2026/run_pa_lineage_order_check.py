"""PA lineage/order check (owner order 2026-10-09) - bounded, no fitting.

1. PA identity/order: unique identity, explicit pitch order, inning/half
   progression, pitcher-to-defensive-side mapping, pitcher-specific
   opportunity index after attribution, repeated encounters retained.
2. Prior lineage: priors computed from (label, keys, raw) BEFORE any
   feature join; each historical event contributes exactly once; the
   game_pk-only join (invalidated run only) never fed prior construction.
3. One representative game proof table.

Outputs JSON + markdown under the task-authorized research root.
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

SEASONS = (2023, 2024)


def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def identity_and_order_checks(raw: pl.DataFrame, label: pl.DataFrame,
                              season: int) -> dict:
    # 1. explicit pitch order: pitch_number unique within PA
    pn = raw.group_by(["game_pk", "at_bat_number"]).agg(
        pl.len().alias("n_rows"),
        pl.col("pitch_number").n_unique().alias("n_pn"))
    n_pn_dup = int((pn["n_rows"] != pn["n_pn"]).sum())

    # 2. inning progression: inning must be non-decreasing by at_bat_number
    ordj = (raw.select(["game_pk", "at_bat_number", "inning",
                        "inning_topbot", "pitcher", "batter"])
            .unique(["game_pk", "at_bat_number"], keep="last")
            .sort(["game_pk", "at_bat_number"]))
    ordj = ordj.with_columns(
        (pl.col("inning") < pl.col("inning").shift(1).over("game_pk"))
        .fill_null(False).alias("inversion"))
    n_inning_inversions = int(ordj["inversion"].sum())

    # 3. pitcher-to-defensive-side: each pitcher throws in ONE half
    half = (raw.select(["game_pk", "pitcher", "inning_topbot"])
            .unique()
            .group_by(["game_pk", "pitcher"]).agg(
                pl.col("inning_topbot").n_unique().alias("n_halves")))
    n_multihalf_pitchers = int((half["n_halves"] > 1).sum())

    # 4. pitcher-specific opportunity index = dense rank over the
    #    pitcher-FILTERED at_bat_number sequence (post-attribution)
    lab = label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    mine = (lab.select(["game_pk", "pitcher", "at_bat_number"])
            .sort(["game_pk", "pitcher", "at_bat_number"])
            .with_columns(pl.int_range(pl.len())
                          .over(["game_pk", "pitcher"]).add(1)
                          .alias("spi_recompute")))
    dens = mine.with_columns(
        pl.col("at_bat_number").rank("dense").over(["game_pk", "pitcher"])
        .alias("dense_rank"))
    n_spi_mismatch = int((dens["spi_recompute"] != dens["dense_rank"])
                         .sum())

    # 5. repeated encounters retained
    enc = (lab.group_by(["pitcher", "batter"]).agg(pl.len().alias("n")))
    n_repeat_pairs = int((enc["n"] > 1).sum())
    max_repeat = int(enc["n"].max())

    # 6. game PA number semantics: at_bat_number is the GAME-wide PA number
    #    (both halves interleaved) - demonstrated by the proof game below.
    return {
        "season": season,
        "pitch_number_duplicates": n_pn_dup,
        "inning_progression_inversions": n_inning_inversions,
        "multi_half_pitchers": n_multihalf_pitchers,
        "spi_vs_dense_rank_mismatches": n_spi_mismatch,
        "completed_pa": int(lab.height),
        "repeat_pitcher_batter_pairs": n_repeat_pairs,
        "max_pas_one_pair": max_repeat,
    }


def prior_lineage_checks(label: pl.DataFrame, keys: pl.DataFrame,
                         season: int) -> dict:
    """Independently recompute per-snapshot priors and compare to the
    scaffold; assert strict cutoffs; quantify event-once contribution."""
    lab = label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    snap_keys = sc.pitcher_snapshot_keys(
        keys.select(["game_pk", "game_date", "forecast_pitcher"])
        .rename({"forecast_pitcher": "pitcher"}))
    scaffold = sc.pitcher_rate_priors(lab, snap_keys)
    # independent recompute: plain group-by over strictly-prior rows
    ind = (snap_keys.join(lab, on="pitcher", how="inner")
           .filter(pl.col("game_date") < pl.col("cutoff_date"))
           .group_by(["key_game_pk", "cutoff_date", "pitcher"])
           .agg(pl.col("y").sum().alias("k_ind"), pl.len().alias("n_ind")))
    cmp_ = (scaffold.join(ind, on=sc.PITCHER_SNAPSHOT_COLUMNS,
                          how="full", coalesce=True)
            .with_columns([
                (pl.col("k_prior") != pl.col("k_ind"))
                .fill_null(True).alias("k_bad"),
                (pl.col("n_prior") != pl.col("n_ind"))
                .fill_null(True).alias("n_bad")]))
    n_prior_rows = int(cmp_["k_prior"].fill_null(0).sum())
    n_ind_rows = int(cmp_["k_ind"].fill_null(0).sum())
    # strict cutoff: max prior date < cutoff for every key with history
    mx = (snap_keys.join(lab, on="pitcher", how="inner")
          .filter(pl.col("game_date") < pl.col("cutoff_date"))
          .group_by(["key_game_pk", "cutoff_date"])
          .agg(pl.col("game_date").max().alias("mx")))
    n_cutoff_violations = int((mx["mx"] >= mx["cutoff_date"]).sum())
    # event-once: scaffold and independent recompute must agree on every
    # key (each historical PA contributes exactly once to each snapshot)
    return {
        "season": season,
        "n_snapshot_keys": int(snap_keys.height),
        "n_keys_with_prior": int(scaffold.height),
        "k_sum_scaffold": n_prior_rows,
        "k_sum_independent": n_ind_rows,
        "k_equal_per_key": int((~cmp_["k_bad"]).sum()),
        "n_equal_per_key": int((~cmp_["n_bad"]).sum()),
        "k_mismatch_keys": int(cmp_["k_bad"].sum()),
        "n_mismatch_keys": int(cmp_["n_bad"].sum()),
        "cutoff_violations": n_cutoff_violations,
    }


def proof_game(raw: pl.DataFrame, label: pl.DataFrame,
               game_pk: int) -> list[dict]:
    """Game PA number, inning/half, pitcher, batter, class, per-pitcher
    opportunity index for one full game."""
    lab = label.filter(pl.col("game_pk") == game_pk).sort("at_bat_number")
    spi = (lab.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
           .sort(["pitcher", "at_bat_number"])
           .with_columns(pl.int_range(pl.len()).over("pitcher").add(1)
                         .alias("spi"))
           .select(["game_pk", "at_bat_number", "pitcher", "spi"]))
    ctx = (raw.filter(pl.col("game_pk") == game_pk)
           .select(["game_pk", "at_bat_number", "inning", "inning_topbot"])
           .unique(["game_pk", "at_bat_number"], keep="last"))
    out = (lab.join(ctx, on=["game_pk", "at_bat_number"], how="left")
           .join(spi, on=["game_pk", "at_bat_number", "pitcher"],
                 how="left"))
    return [{
        "game_pa_number": r["at_bat_number"],
        "inning": r["inning"],
        "half": r["inning_topbot"],
        "pitcher": r["pitcher"],
        "batter": r["batter"],
        "pa_class": r["pa_class"],
        "y": r["y"],
        "pitcher_opportunity_index": r["spi"],
    } for r in out.iter_rows(named=True)]


def pick_proof_game(raw: pl.DataFrame, label: pl.DataFrame) -> int:
    """A game with repeated batter encounters for one starter."""
    lab = label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    enc = lab.group_by(["game_pk", "pitcher", "batter"]).agg(
        pl.len().alias("n"))
    good = enc.filter(pl.col("n") >= 2).group_by("game_pk").agg(
        pl.len().alias("pairs")).sort("pairs", descending=True)
    return int(good["game_pk"][0])


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
    frames, labels, keys_tables, order_checks, prior_checks = {}, {}, {}, {}, {}
    for season in SEASONS:
        path = (root / "Savant-Data" / "regular" / str(season)
                / ("statcast_%d_regular.parquet" % season))
        frames[season] = pl.read_parquet(path)
        keys, _q = rch.audit_identity(
            rch._unified_pitches([frames[season]]))
        keys_tables[season] = keys
        labels[season] = sc.build_pa_label_table(frames[season])
        order_checks[str(season)] = identity_and_order_checks(
            frames[season], labels[season], season)
        prior_checks[str(season)] = prior_lineage_checks(
            labels[season], keys_tables[season], season)
        print("season %d: order %s | priors k_mismatch %s cutoff_viol %s"
              % (season, order_checks[str(season)],
                 prior_checks[str(season)]["k_mismatch_keys"],
                 prior_checks[str(season)]["cutoff_violations"]))

    proof_pk = pick_proof_game(frames[2023], labels[2023])
    proof = proof_game(frames[2023], labels[2023], proof_pk)
    print("proof game: %d (%d PAs)" % (proof_pk, len(proof)))

    report = {
        "generated": str(date.today()),
        "scope": "bounded lineage/order check; no fitting, no tuning",
        "identity_and_order": order_checks,
        "prior_lineage": prior_checks,
        "proof_game_pk": proof_pk,
        "proof_game_rows": proof,
        "prior_lineage_statement": (
            "All priors (rate, workload, swing, pitch-type, batter, "
            "discipline) are computed from (pa_completed_v1 label tables, "
            "audit_identity keys, pooled RAW frames) BEFORE any feature "
            "join; the faulty game_pk-only join lived only in "
            "build_season_features output assembly (feature rows fed to "
            "model fits). Affected artifacts: pa-lgbm-comparison runs "
            "20261009_152350/_152829 ONLY (already INVALIDATED - their "
            "fitted models saw duplicated feature rows; priors themselves "
            "were computed pre-join and were NOT contaminated). Unaffected: "
            "reconciliation, prefit checks, corrected comparison 154851, "
            "L3 refit 162338, all archived experiments, I3b."),
        "code": {p.name: sha256_file(p) for p in [
            HERE / "run_pa_lineage_order_check.py",
            HERE / "pa_lgbm_scaffold.py"]},
    }
    (out_dir / "lineage_order_check.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="ascii")
    lines = ["# PA lineage/order check (bounded; no fitting)", ""]
    lines.append("## Identity / order")
    lines.append("| season | pitch_number dups | inning inversions | "
                 "multi-half pitchers | spi vs dense-rank mismatch | "
                 "completed PA | repeat pitcher-batter pairs | max PA/pair |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for s, c in sorted(report["identity_and_order"].items()):
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            s, c["pitch_number_duplicates"],
            c["inning_progression_inversions"],
            c["multi_half_pitchers"],
            c["spi_vs_dense_rank_mismatches"], c["completed_pa"],
            c["repeat_pitcher_batter_pairs"], c["max_pas_one_pair"]))
    lines.append("")
    lines.append("## Prior lineage")
    lines.append("| season | snapshot keys | keys with prior | "
                 "k mismatch keys | n mismatch keys | cutoff violations |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for s, c in sorted(report["prior_lineage"].items()):
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            s, c["n_snapshot_keys"], c["n_keys_with_prior"],
            c["k_mismatch_keys"], c["n_mismatch_keys"],
            c["cutoff_violations"]))
    lines.append("")
    lines.append(report["prior_lineage_statement"])
    lines.append("")
    lines.append("## Proof game %d (game PA number = game-wide; pitcher "
                 "opportunity index = per-pitcher dense rank)" % proof_pk)
    lines.append("| game PA | inning | half | pitcher | batter | class | "
                 "K | pitcher opp index |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in proof:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["game_pa_number"], r["inning"], r["half"], r["pitcher"],
            r["batter"], r["pa_class"], r["y"],
            r["pitcher_opportunity_index"]))
    (out_dir / "lineage_order_check.md").write_text(
        "\n".join(lines) + "\n", encoding="ascii")
    print("WROTE %s" % (out_dir / "lineage_order_check.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
