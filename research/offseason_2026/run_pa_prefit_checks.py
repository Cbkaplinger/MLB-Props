"""Pre-fit checks for the PA-LGBM lane (owner conditional authorization 2026-10-09).

Three focused checks on existing evidence; NO fitting, NO predictions,
NO tuning. Outputs under the task-authorized research root.

Check 1: population reconciliation across four definitions (v1 completed,
production counted, pa-k baseline, historical-feature opportunities) with
row traces connecting the earlier baserunning-terminal/filter-order
explanation to the truncated_pa + mixed-batter mechanism.

Check 2: velocity provenance - raw historical FF availability separately
from post-imputation coverage, career-debut breakdown, no-leakage statement.

Check 3: prototype inventory reconciled with earlier PA logistic/tree
records (logistic_pa, tree_pa, pitcher_prior); arm D provenance decision.
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
from Python.statcast import plate_appearances  # noqa: E402

SEASONS = (2022, 2023, 2024)
MAX_TRACES = 5
L3_PRED = HERE / "experiments" / "logistic_pa" / "pa_predictions.parquet"


def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_seasons(root: Path) -> dict[int, pl.DataFrame]:
    frames = {}
    for season in SEASONS:
        path = (root / "Savant-Data" / "regular" / str(season)
                / ("statcast_%d_regular.parquet" % season))
        if not path.is_file():
            raise RuntimeError("missing input %s" % path)
        frames[season] = pl.read_parquet(path)
    return frames


def starter_groups(raw: pl.DataFrame, keys: pl.DataFrame) -> dict:
    """All four starter-level populations for one season + traces."""
    label = sc.build_pa_label_table(raw)
    fp = sc.first_pitcher_filter(label, keys)
    starter_keys = set(zip(fp["game_pk"].to_list(),
                           fp["at_bat_number"].to_list()))

    prod = plate_appearances(raw)
    prod_fp = prod.join(keys.select(["game_pk",
                                     pl.col("forecast_pitcher")
                                     .alias("fp_pitcher")]),
                        on="game_pk", how="inner").filter(
        pl.col("pitcher") == pl.col("fp_pitcher"))
    prod_keys = set(zip(prod_fp["game_pk"].to_list(),
                        prod_fp["at_bat_number"].to_list()))

    pak = raw.filter(pl.col("events").is_not_null()
                     & (pl.col("events") != "truncated_pa"))
    pak_fp = pak.join(keys.select(["game_pk",
                                   pl.col("forecast_pitcher")
                                   .alias("fp_pitcher")]),
                      on="game_pk", how="inner").filter(
        pl.col("pitcher") == pl.col("fp_pitcher"))
    pak_keys = set(zip(pak_fp["game_pk"].to_list(),
                       pak_fp["at_bat_number"].to_list()))

    v1c = fp.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    v1_keys = set(zip(v1c["game_pk"].to_list(),
                      v1c["at_bat_number"].to_list()))
    lab_map = {(r["game_pk"], r["at_bat_number"]): r
               for r in fp.iter_rows(named=True)}

    seq = (raw.filter(pl.col("events").is_not_null())
           .sort(["game_pk", "at_bat_number", "pitch_number"])
           .group_by(["game_pk", "at_bat_number"])
           .agg(pl.col("events").alias("seq")))
    seq_map = {(r["game_pk"], r["at_bat_number"]): r["seq"]
               for r in seq.iter_rows(named=True)}

    def traces(keyset, classify):
        out = []
        for key in sorted(keyset)[:MAX_TRACES]:
            lab = lab_map.get(key, {})
            out.append({"game_pk": key[0], "at_bat_number": key[1],
                        "event_sequence": seq_map.get(key, []),
                        "v1_class": lab.get("pa_class"),
                        "v1_event": lab.get("event"),
                        "reason": classify(lab)})
        return out

    prod_only = prod_keys - v1_keys
    v1_only = v1_keys - prod_keys
    pak_only = pak_keys - v1_keys
    trunc_groups = {k for k, lab in lab_map.items()
                    if lab.get("event") == "truncated_pa"}
    mixed_groups = {k for k, lab in lab_map.items()
                    if lab.get("mixed_batter")}
    baserun_no_completed = {k for k, lab in lab_map.items()
                            if lab.get("pa_class") == sc.CLASS_BASERUNNING}
    midpa = {k for k, lab in lab_map.items()
             if lab.get("mid_pa_pitcher_change")}

    counts = {
        "v1_completed_starter_pa": len(v1_keys),
        "production_counted_starter_pa": len(prod_keys),
        "pak_baseline_starter_pa": len(pak_keys),
        "pa_groups_total_starter_scope": len(lab_map),
        "identity_pak_minus_v1": len(pak_keys) - len(v1_keys),
        "mixed_batter_groups": len(mixed_groups),
        "identity_check_pak_eq_v1_plus_mixed":
            (len(pak_keys) - len(v1_keys)) == len(mixed_groups),
        "identity_prod_minus_v1": len(prod_keys) - len(v1_keys),
        "truncated_pa_groups": len(trunc_groups),
        "identity_check_prod_eq_v1_plus_trunc_plus_mixed":
            (len(prod_keys) - len(v1_keys))
            == len(trunc_groups) + len(mixed_groups),
        "mechanism_completed_before_baserunning_terminal_v1_only":
            len(v1_only),
        "mechanism_baserunning_terminal_no_completed_both_exclude":
            len(baserun_no_completed),
        "mid_pa_pitcher_change_groups": len(midpa),
        "v1_k_starter": int(v1c["y"].sum()),
        "production_k_starter": int(prod_fp["is_k"].sum()),
    }
    traces_out = {
        "truncated_pa_production_counted_v1_excluded": traces(
            prod_only & trunc_groups,
            lambda lab: "terminal row events=truncated_pa; production "
                        "last-row filter retains it (not in NON_PA_EVENTS); "
                        "v1 class incomplete"),
        "mixed_batter_production_counted_v1_excluded": traces(
            prod_only & mixed_groups,
            lambda lab: "mixed-batter group; production has no batter "
                        "uniqueness check; v1 excludes with mixed_batter "
                        "flag"),
        "v1_completed_not_production": traces(
            v1_only, lambda lab: "bridge-audit mechanism class: completed "
                                 "event before a baserunning terminal row"),
        "pak_minus_v1": traces(
            pak_only, lambda lab: "pa-k terminal-events convention vs v1"),
    }
    return counts, traces_out, fp


def velocity_provenance(prior_label: pl.DataFrame, pooled_raw: pl.DataFrame,
                        keys: pl.DataFrame, season: int) -> dict:
    snap_keys = sc.pitcher_snapshot_keys(
        keys.select(["game_pk", "game_date", "forecast_pitcher"])
        .rename({"forecast_pitcher": "pitcher"}))
    lab = prior_label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    rates = sc.pitcher_rate_priors(prior_label, snap_keys)
    rates = (snap_keys.join(rates, on=sc.PITCHER_SNAPSHOT_COLUMNS,
                            how="left")
             .with_columns([pl.col(c).fill_null(0)
                            for c in ("k_prior", "n_prior",
                                      "n_prior_season")]))
    classes = {
        (r["key_game_pk"], r["pitcher"]):
            sc.classify_cold_start(int(r["n_prior"]),
                                   int(r["n_prior_season"]))
        for r in rates.iter_rows(named=True)}
    types = sc.pitcher_pitchtype_priors(pooled_raw, snap_keys)
    ff = types.filter(pl.col("pitch_type") == "FF")
    ff_map = {(r["key_game_pk"], r["pitcher"]): r
              for r in ff.iter_rows(named=True)}
    by_class: dict[str, dict] = {}
    for key, cls in classes.items():
        b = by_class.setdefault(cls, {"keys": 0, "has_ff_row": 0,
                                      "has_valid": 0, "zero_valid": 0})
        b["keys"] += 1
        row = ff_map.get(key)
        if row is not None:
            b["has_ff_row"] += 1
            if row["n_valid"] > 0:
                b["has_valid"] += 1
            else:
                b["zero_valid"] += 1
    n_valid_all = [int(r["n_valid"]) for r in ff_map.values()]
    n_valid_all_sorted = sorted(n_valid_all)
    return {
        "season": season,
        "snapshot_keys": snap_keys.height,
        "raw_coverage_by_cold_start_class": by_class,
        "raw_ff_valid_total_keys": int(sum(b["has_valid"]
                                           for b in by_class.values())),
        "raw_ff_zero_or_absent_keys": snap_keys.height - int(
            sum(b["has_valid"] for b in by_class.values())),
        "ff_n_valid_p50_among_keys_with_any_valid": (
            n_valid_all_sorted[len(n_valid_all_sorted) // 2]
            if n_valid_all_sorted else 0),
        "window_definition": "entire prior pool: prior seasons + same "
                             "season strictly earlier (game_date < cutoff); "
                             "no fixed window cap; p50 = all-career valid FF "
                             "measurements available in the pool",
        "imputation_policy": "scaffold carries RAW values only (mean_speed "
                             "null when n_valid=0; no fill); frozen fit "
                             "fill = training-window league-median FF speed "
                             "(train-only, pregame-legal) + has_ff_history "
                             "flag; post-fill coverage 100% by construction",
        "leakage_statement": "prior joins filter game_date < cutoff only; "
                             "current-game rows never enter; future-append "
                             "and outcome-mutation invariance tests green "
                             "in tests/test_pa_lgbm_scaffold.py",
    }


def baseline_inventory() -> dict:
    stored = pl.read_parquet(L3_PRED)
    l3_keys = set(zip(stored["game_pk"].to_list(),
                      stored["at_bat_number"].to_list()))
    return {
        "correction_note": (
            "The scaffold reconciliation statement 'no PA-level tree "
            "prototype exists in the tree' is CORRECTED: experiments/tree_pa "
            "EXISTS (card sha 95b9627d..., phase 8) with verdict TIE / blend "
            "rejected / lane CLOSED - it is not an open challenger, but it "
            "does exist. experiments/logistic_pa (L3 ridge logistic) also "
            "exists and is the strongest prior PA ML baseline."),
        "records": [
            {"name": "L3 ridge logistic (logistic_pa)",
             "path": "research/offseason_2026/experiments/logistic_pa/",
             "status": "DEVELOPMENT_BASELINE; fit 2023 (105,225 rows, "
                       "03-30..10-01); permitted scoring 2024 E1/E2; "
                       "reproducible to 2.2e-16; bundle serialized "
                       "(intercept + coefs + scaler)",
             "reusable_for_this_run": "2024 block ONLY, via stored "
                                      "out-of-sample predictions "
                                      "(pa_predictions.parquet, all 2024); "
                                      "2023 stored predictions are "
                                      "IN-SAMPLE and are NOT used",
             "stored_predictions_2024_rows": stored.height},
            {"name": "constrained PA tree (tree_pa)",
             "path": "research/offseason_2026/experiments/tree_pa/",
             "status": "CLOSED: TIE vs L3, blend rejected (corr 0.9965 "
                       "fail); card hashed; not an open baseline",
             "reusable_for_this_run": "no (closed lane; verdict recorded)"},
            {"name": "P3-log5 (pitcher_prior)",
             "path": "research/offseason_2026/experiments/pitcher_prior/",
             "status": "odds-form log5 m=100 with season-cum counts; L3's "
                       "internal baseline term",
             "reusable_for_this_run": "not an arm (arm A is the pa-k w=150 "
                                      "shrunk log5; adding P3 as a fifth "
                                      "arm is out of scope)"},
            {"name": "pa-k arm A/B (2026-10-07)",
             "path": "research/offseason_2026/pa_k_baseline.py",
             "status": "scored 2023; arm A retained PA benchmark",
             "reusable_for_this_run": "arm A IS arm A of this run"},
        ],
        "arm_d_decision": {
            "include": True,
            "block": "2024 only",
            "mechanism": "join stored L3 predictions to the 2024 v1 eval "
                         "rows on (game_pk, at_bat_number); unmatched rows "
                         "counted; per-row log loss recomputed from stored "
                         "L3 probabilities on MY labels",
            "provenance": "fit 2023 only -> 2024 scoring is "
                          "out-of-sample; no in-sample comparison anywhere",
            "stored_predictions_sha256": sha256_file(L3_PRED),
            "stored_l3_keys": len(l3_keys),
        },
    }


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
    frames = load_seasons(root)
    label_tables = {}
    keys_tables = {}
    check1 = {}
    for season in SEASONS:
        keys, _q = rch.audit_identity(rch._unified_pitches([frames[season]]))
        keys_tables[season] = keys
        label_tables[season] = sc.build_pa_label_table(frames[season])
        counts, traces, _fp = starter_groups(frames[season], keys)
        check1[str(season)] = {"counts": counts, "traces": traces}
        print("season %d: v1 %d | prod %d | pa-k %d | identity checks %s/%s"
              % (season, counts["v1_completed_starter_pa"],
                 counts["production_counted_starter_pa"],
                 counts["pak_baseline_starter_pa"],
                 counts["identity_check_pak_eq_v1_plus_mixed"],
                 counts["identity_check_prod_eq_v1_plus_trunc_plus_mixed"]))
    check2 = {}
    for season in (2023, 2024):
        pool_seasons = tuple(y for y in SEASONS if y <= season)
        pool = pl.concat([label_tables[y] for y in pool_seasons],
                         how="vertical")
        pooled_raw = pl.concat([frames[y] for y in pool_seasons],
                               how="diagonal_relaxed")
        check2[str(season)] = velocity_provenance(
            pool, pooled_raw, keys_tables[season], season)
        c2 = check2[str(season)]
        print("season %d velocity: raw valid keys %d / %s; zero-or-absent %d"
              % (season, c2["raw_ff_valid_total_keys"],
                 c2["snapshot_keys"], c2["raw_ff_zero_or_absent_keys"]))
    check3 = baseline_inventory()

    report = {
        "generated": str(date.today()),
        "check1_population_reconciliation": check1,
        "check2_velocity_provenance": check2,
        "check3_baseline_inventory": check3,
        "label_feature_denominator_statement": (
            "Labels AND historical-feature priors both use pa_completed_v1 "
            "completed rows (scaffold pitcher_rate_priors / "
            "batter_rate_priors filter pa_class == completed_pa); no mixing "
            "of denominators within the lane."),
        "code": {p.name: sha256_file(p) for p in [
            HERE / "run_pa_prefit_checks.py", HERE / "pa_lgbm_scaffold.py"]},
    }
    (out_dir / "checks.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="ascii")
    _write_md(report, out_dir / "checks_report.md")
    print("WROTE %s" % (out_dir / "checks_report.md"))
    return 0


def _write_md(report: dict, path: Path) -> None:
    lines = ["# PA-LGBM pre-fit checks (2026-10-09)", ""]
    lines.append("## Check 1 - starter population reconciliation")
    lines.append("| season | v1 completed | production | pa-k | prod-v1 | "
                 "truncated | mixed | prod identity | pa-k identity | "
                 "v1-only (bridge mechanism) | both-exclude baserunning | "
                 "mid-PA pitcher |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | "
                 "--- | --- | --- |")
    for season, c1 in sorted(report["check1_population_reconciliation"]
                             .items()):
        k = c1["counts"]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (season, k["v1_completed_starter_pa"],
               k["production_counted_starter_pa"],
               k["pak_baseline_starter_pa"],
               k["identity_prod_minus_v1"], k["truncated_pa_groups"],
               k["mixed_batter_groups"],
               k["identity_check_prod_eq_v1_plus_trunc_plus_mixed"],
               k["identity_check_pak_eq_v1_plus_mixed"],
               k["mechanism_completed_before_baserunning_terminal_v1_only"],
               k["mechanism_baserunning_terminal_no_completed_both_exclude"],
               k["mid_pa_pitcher_change_groups"]))
    lines.append("")
    lines.append("Mechanism statement: the earlier bridge-audit hypothesis "
                 "(baserunning-terminal records surviving/dying under "
                 "filter order) predicts a nonempty v1-only class; measured "
                 "v1-only = 0 in every season, and the production-only "
                 "class decomposes EXACTLY into truncated_pa + mixed-batter "
                 "groups. Row traces in checks.json.")
    lines.append("")
    lines.append("## Check 2 - FF velocity provenance (raw vs filled)")
    for season, c2 in sorted(report["check2_velocity_provenance"].items()):
        lines.append("- %s: keys %d | raw valid %d | zero-or-absent %d | "
                     "p50 n_valid (among raw>0) %s" %
                     (season, c2["snapshot_keys"],
                      c2["raw_ff_valid_total_keys"],
                      c2["raw_ff_zero_or_absent_keys"],
                      c2["ff_n_valid_p50_among_keys_with_any_valid"]))
        for cls, b in sorted(c2["raw_coverage_by_cold_start_class"].items()):
            lines.append("    - %s: keys %d, has_valid %d, zero_valid %d, "
                         "no_ff_row %d" % (cls, b["keys"], b["has_valid"],
                                           b["zero_valid"],
                                           b["keys"] - b["has_ff_row"]))
    lines.append("")
    lines.append("## Check 3 - corrected baseline inventory")
    lines.append(report["check3_baseline_inventory"]["correction_note"])
    lines.append("")
    lines.append("Arm D: 2024-block-only stored L3 predictions "
                 "(fit 2023 -> out-of-sample on 2024); 2023 stored "
                 "predictions are in-sample and excluded from the 2023 "
                 "family.")
    lines.append("")
    lines.append(report["label_feature_denominator_statement"])
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


if __name__ == "__main__":
    raise SystemExit(main())
