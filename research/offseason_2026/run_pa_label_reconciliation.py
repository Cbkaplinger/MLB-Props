"""pa_completed_v1 reconciliation runner (pa-lgbm contract 2026-10-09).

BOUNDED: label/population reconciliation + feature-source coverage +
baseline inventory ONLY. No model fitting, no predictions, no tuning,
no production changes. Outputs under the task-authorized research root
or system temp (enforced by rch._require_temp_out).

Inputs: verified 2022/2023 Savant parquets (known SHAs via
run_corrected_history_2023.default_sources); 2024 parquet is FIRST-HASHED
here as identity registration (not independently verified) when no
--season-sha 2024:<hex> is supplied, mirroring the 2024 transfer-run
convention.
"""

from __future__ import annotations

import argparse
import hashlib
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
HISTORY_FOR = {2023: (2022,), 2024: (2022, 2023)}
MAX_EXAMPLES = 20


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_season_label(raw: pl.DataFrame, season: int) -> dict:
    """Label table + production/pa-k convention counts for one season."""
    unmapped = sorted(set(
        raw.filter(pl.col("events").is_not_null())["events"].unique()
        .to_list()) - set(sc.EVENT_MAP))
    if unmapped:
        raise RunFailure("season %d unmapped events: %s" % (season, unmapped))
    label = sc.build_pa_label_table(raw)
    prod = plate_appearances(raw)
    pak_conv = raw.filter(pl.col("events").is_not_null()
                          & (pl.col("events") != "truncated_pa"))
    counts = {
        "season": season,
        "raw_pitch_rows": raw.height,
        "pa_groups": label.height,
        "v1_completed": int((label["pa_class"] == sc.CLASS_COMPLETED).sum()),
        "v1_k": int(label["y"].sum() or 0),
        "v1_incomplete": int((label["pa_class"] == sc.CLASS_INCOMPLETE)
                             .sum()),
        "v1_baserunning_only": int((label["pa_class"]
                                    == sc.CLASS_BASERUNNING).sum()),
        "v1_incomplete_null_terminal": int(
            ((label["pa_class"] == sc.CLASS_INCOMPLETE)
             & (label["event"].is_null())).sum()),
        "v1_incomplete_truncated": int(
            ((label["pa_class"] == sc.CLASS_INCOMPLETE)
             & (label["event"] == "truncated_pa")).sum()),
        "v1_mid_pa_pitcher_change": int(
            label["mid_pa_pitcher_change"].sum()),
        "production_pa_rows": prod.height,
        "production_k": int(prod["is_k"].sum()),
        "pak_convention_rows": pak_conv.height,
        "pak_convention_k": int(
            pak_conv["events"].is_in(list(sc.K_EVENTS)).sum()),
        "distinct_events": sorted(
            raw.filter(pl.col("events").is_not_null())["events"]
            .unique().to_list()),
    }
    return {"label": label, "counts": counts}


def disagreement_examples(raw: pl.DataFrame, v1_completed: pl.DataFrame,
                          prod: pl.DataFrame, v1_label: pl.DataFrame) -> dict:
    """Concrete examples for each v1-vs-production disagreement class."""
    v1_keys = set(zip(v1_completed["game_pk"].to_list(),
                      v1_completed["at_bat_number"].to_list()))
    prod_keys = set(zip(prod["game_pk"].to_list(),
                        prod["at_bat_number"].to_list()))
    seq = (raw.filter(pl.col("events").is_not_null())
           .sort(["game_pk", "at_bat_number", "pitch_number"])
           .group_by(["game_pk", "at_bat_number"])
           .agg(pl.col("events").alias("seq")))
    seq_map = {(r["game_pk"], r["at_bat_number"]): r["seq"]
               for r in seq.iter_rows(named=True)}
    label_map = {(r["game_pk"], r["at_bat_number"]): r
                 for r in v1_label.iter_rows(named=True)}

    def examples(keys, classify):
        out = []
        for key in sorted(keys)[:MAX_EXAMPLES]:
            lab = label_map.get(key, {})
            out.append({
                "game_pk": key[0], "at_bat_number": key[1],
                "event_sequence": seq_map.get(key, []),
                "v1_class": lab.get("pa_class"),
                "v1_event": lab.get("event"),
                "classification_reason": classify(lab),
            })
        return out

    prod_only = prod_keys - v1_keys
    v1_only = v1_keys - prod_keys

    def prod_only_reason(lab):
        if lab.get("pa_class") == sc.CLASS_INCOMPLETE:
            if lab.get("event") == "truncated_pa":
                return ("truncated_pa: production's last-row filter keeps it "
                        "(not in NON_PA_EVENTS); pa_completed_v1 excludes it")
            if lab.get("mixed_batter"):
                return ("mixed-batter group: production has no batter "
                        "uniqueness check; pa_completed_v1 excludes it")
            return ("incomplete under pa_completed_v1 (terminal row "
                    "null/unmapped event); production retains it")
        if lab.get("pa_class") == sc.CLASS_BASERUNNING:
            return ("terminal row is a baserunning-only event with no "
                    "completed event in the group; production's last-row "
                    "filter retains it only if its terminal event is not "
                    "in NON_PA_EVENTS")
        return "unclassified production-only group (inspect)"

    return {
        "n_production_pa_not_v1_completed": len(prod_only),
        "n_v1_completed_not_production_pa": len(v1_only),
        "examples_production_not_v1": examples(prod_only, prod_only_reason),
        "examples_v1_not_production": examples(
            v1_only, lambda lab: (
                "group contains a completed event before its terminal row; "
                "production last-row filter dropped it")),
    }


def feature_coverage(prior_label: pl.DataFrame, raw: pl.DataFrame,
                     season: int, keys: pl.DataFrame) -> dict:
    """FF velocity availability, usage null rate, cold-start classes."""
    snap_keys = sc.pitcher_snapshot_keys(
        keys.select(["game_pk", "game_date", "forecast_pitcher"])
        .rename({"forecast_pitcher": "pitcher"}))
    types = sc.pitcher_pitchtype_priors(raw, snap_keys)
    ff = types.filter(pl.col("pitch_type") == "FF")
    n_keys = snap_keys.height
    ff_zero = int((ff["n_valid"] == 0).sum()) if ff.height else n_keys
    n_valid = ff["n_valid"].to_list() if ff.height else []
    elig = raw.filter(pl.col("pitch_type").is_not_null())
    n_elig = elig.height
    n_vel_missing = int(elig["release_speed"].is_null().sum())
    rates = sc.pitcher_rate_priors(prior_label, snap_keys)
    rate_cols = [c for c in ("k_prior", "n_prior", "n_prior_season")
                 if c in rates.columns]
    rates = (snap_keys.join(rates, on=sc.PITCHER_SNAPSHOT_COLUMNS,
                            how="left")
             .with_columns([pl.col(c).fill_null(0).cast(pl.Int64)
                            for c in rate_cols]))
    classes = {}
    if rates.height:
        for r in rates.select(
                pl.struct("n_prior", "n_prior_season")
                .map_elements(lambda s: sc.classify_cold_start(
                    int(s["n_prior"]), int(s["n_prior_season"])),
                    return_dtype=pl.String).alias("cls")
        ).group_by("cls").agg(pl.len().alias("n")).iter_rows(named=True):
            classes[r["cls"]] = int(r["n"])
    return {
        "season": season,
        "snapshot_keys": n_keys,
        "ff_type_rows": int(ff.height) if ff.height else 0,
        "ff_keys_with_zero_valid_velocity": ff_zero,
        "ff_n_valid_p50": (sorted(n_valid)[len(n_valid) // 2]
                           if n_valid else 0),
        "ff_n_valid_min": min(n_valid) if n_valid else 0,
        "eligible_pitch_rows": n_elig,
        "velocity_missing_among_eligible": n_vel_missing,
        "velocity_missing_rate": (n_vel_missing / n_elig) if n_elig else None,
        "cold_start_classes": classes,
    }


def baseline_inventory() -> list[dict]:
    return [
        {"name": "pa-k arm A (shrunk log5, w=150)",
         "code": "research/offseason_2026/pa_k_baseline.py",
         "provenance": "scored 2026-10-07 on 2023 first-pitcher PAs "
                       "(n=96,615); GATE 1 FAIL -> retained PA benchmark",
         "reusable": True,
         "population": "first-pitcher terminal PAs, pa-k convention"},
        {"name": "pa-k arm B (L2 logistic C=1.0)",
         "code": "research/offseason_2026/pa_k_baseline.py",
         "provenance": "scored 2026-10-07; paired B-A -0.0000841 "
                       "[-0.000507, +0.000335], CI includes 0",
         "reusable": True,
         "population": "identical rows to arm A"},
        {"name": "production L3 LightGBM ensemble (mono72 x0.6 + final58 "
                 "x0.4)",
         "code": "artifacts/models/lightgbm_krate_*",
         "provenance": "game-rate K/PA models on the production PA "
                       "denominator; booster test window never early-stop; "
                       "ensemble weights selected with outcomes through "
                       "~2026-08-21 -> NOT untouched; NOT PA-usable",
         "reusable": False,
         "population": "pitcher-game K rate (not PA)"},
        {"name": "phase11b walkforward OOF (180-set)",
         "provenance": "4,607 rows 2024-04-01..09-30, genuinely "
                       "chronological, but game-rate lineage and feature "
                       "sets mismatch the active ensemble -> lineage-"
                       "mismatched, NOT promotion-usable",
         "reusable": False,
         "population": "pitcher-game K rate (not PA)"},
        {"name": "PA-level tree prototype",
         "provenance": "none exists in the tree (kcount prereg lists the "
                       "LightGBM PA lane as FUTURE/parked)",
         "reusable": False,
         "population": "n/a"},
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        season_shas: dict[int, str] = {}
        for item in args.season_sha:
            y, d = item.split(":", 1)
            season_shas[int(y)] = d.lower()

        frames: dict[int, pl.DataFrame] = {}
        input_records: dict[str, dict] = {}
        for season in SEASONS:
            path = (root / "Savant-Data" / "regular" / str(season)
                    / ("statcast_%d_regular.parquet" % season))
            if not path.is_file():
                raise RunFailure("missing input %s" % path)
            digest = season_shas.get(season, rch.SEASON_SHA_KNOWN.get(season))
            if digest is None:
                digest = sha256_file(path)  # identity registration only
                mode = "registered_first_hash"
            else:
                actual = sha256_file(path)
                if actual != digest:
                    raise RunFailure(
                        "source hash mismatch for %d: %s" % (season, actual))
                mode = "verified"
            frames[season] = pl.read_parquet(path)
            input_records["savant_%d" % season] = {
                "path": str(path.resolve()), "sha256": digest,
                "mode": mode}

        seasons_out: dict[str, dict] = {}
        label_tables: dict[int, pl.DataFrame] = {}
        for season in SEASONS:
            built = build_season_label(frames[season], season)
            label_tables[season] = built["label"]
            seasons_out[str(season)] = built["counts"]
            print("season %d: v1 completed %d / K %d | production %d / K %d"
                  % (season, built["counts"]["v1_completed"],
                     built["counts"]["v1_k"],
                     built["counts"]["production_pa_rows"],
                     built["counts"]["production_k"]))

        # v1-vs-production disagreement examples (all-pitcher level)
        for season in SEASONS:
            raw = frames[season]
            label = label_tables[season]
            v1c = label.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
            prod = plate_appearances(raw)
            dis = disagreement_examples(raw, v1c, prod, label)
            seasons_out[str(season)]["v1_vs_production"] = dis
            print("season %d: prod-only %d | v1-only %d"
                  % (season, dis["n_production_pa_not_v1_completed"],
                     dis["n_v1_completed_not_production_pa"]))

        # first-pitcher populations + coverage (2023/2024 need priors)
        first_pitcher: dict[str, int] = {}
        coverage: dict[str, dict] = {}
        for season in (2023, 2024):
            raw = frames[season]
            keys, quarantine = rch.audit_identity(rch._unified_pitches([raw]))
            if quarantine:
                print("season %d: %d quarantined identity games (reported, "
                      "not dropped silently)" % (season, len(quarantine)))
            fp = sc.first_pitcher_filter(label_tables[season], keys)
            first_pitcher[str(season)] = int(
                (fp["pa_class"] == sc.CLASS_COMPLETED).sum())
            # Prior pool = all seasons <= snapshot season; the scaffold's
            # strict game_date < cutoff filter enforces chronology (pa-k
            # convention: prior-season aggregates + same-season earlier
            # rows).
            pool_seasons = tuple(y for y in SEASONS if y <= season)
            prior_label = pl.concat(
                [label_tables[y] for y in pool_seasons], how="vertical")
            coverage[str(season)] = feature_coverage(
                prior_label, raw, season, keys)
        coverage["2022"] = {"season": 2022,
                            "note": "no prior seasons in scope; coverage "
                                    "reported for 2023/2024 only"}

        report = {
            "lane": "pa_lgbm_reconciliation",
            "status": "COMPLETE",
            "contract": "research/offseason_2026/pa-lgbm-contract-2026-10-09.md",
            "generated": str(date.today()),
            "input_provenance": input_records,
            "season_counts": seasons_out,
            "first_pitcher_completed_pa": first_pitcher,
            "feature_coverage": coverage,
            "baseline_inventory": baseline_inventory(),
            "workload_interface_findings": (
                "pa_completed_v1 counts differ from the production PA "
                "denominator used by the legacy models and from the pa-k "
                "convention; the BF workload lane is UNCHANGED. Any "
                "workload-denominator adjustment is a separate owner "
                "decision; the classifier lane uses pa_completed_v1 "
                "consistently across arms and seasons."),
            "code": {p.name: sha256_file(p) for p in [
                HERE / "run_pa_label_reconciliation.py",
                HERE / "pa_lgbm_scaffold.py",
                REPO / "src" / "Python" / "statcast.py"]},
        }
        (out_dir / "reconciliation.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="ascii")
        _write_markdown(report, out_dir / "reconciliation_report.md")
        print("WROTE %s" % (out_dir / "reconciliation_report.md"))
        return 0
    except (RunFailure, rch.MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


def _write_markdown(report: dict, path: Path) -> None:
    lines = ["# pa_completed_v1 reconciliation (2023-2024 scope)",
             "", "Contract: pa-lgbm-contract-2026-10-09.md. Bounded: no "
             "fitting, no predictions.", ""]
    lines.append("## Season counts")
    lines.append("| season | PA groups | v1 completed | v1 K | incomplete | "
                 "baserunning | mid-PA change | production PA | production "
                 "K | pa-k rows |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | "
                 "--- |")
    for season, c in sorted(report["season_counts"].items()):
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (season, c["pa_groups"], c["v1_completed"], c["v1_k"],
                        c["v1_incomplete"], c["v1_baserunning_only"],
                        c["v1_mid_pa_pitcher_change"],
                        c["production_pa_rows"], c["production_k"],
                        c["pak_convention_rows"]))
    lines.append("")
    lines.append("## v1 vs production disagreements")
    for season, c in sorted(report["season_counts"].items()):
        d = c.get("v1_vs_production", {})
        if not d:
            continue
        lines.append("- %s: production-PA-not-v1 %d; v1-completed-not-"
                     "production %d" % (season,
                                        d["n_production_pa_not_v1_completed"],
                                        d["n_v1_completed_not_production_pa"]))
    lines.append("")
    lines.append("## First-pitcher completed PAs")
    for season, n in sorted(report["first_pitcher_completed_pa"].items()):
        lines.append("- %s: %d" % (season, n))
    lines.append("")
    lines.append("## Feature-source coverage")
    for season, cov in sorted(report["feature_coverage"].items()):
        if "snapshot_keys" not in cov:
            lines.append("- %s: %s" % (season, cov.get("note", "")))
            continue
        lines.append("- %s: keys %d | FF zero-valid-velocity keys %d | "
                     "FF n_valid p50 %s | velocity missing among eligible "
                     "%.4f | cold starts %s"
                     % (season, cov["snapshot_keys"],
                        cov["ff_keys_with_zero_valid_velocity"],
                        cov["ff_n_valid_p50"],
                        cov["velocity_missing_rate"] or 0.0,
                        cov["cold_start_classes"]))
    lines.append("")
    lines.append("## Baseline inventory")
    for b in report["baseline_inventory"]:
        lines.append("- **%s** (reusable=%s): %s" % (b["name"],
                                                     b["reusable"],
                                                     b["provenance"]))
    lines.append("")
    lines.append("## Workload interface findings")
    lines.append(report["workload_interface_findings"])
    lines.append("")
    lines.append("## Disagreement examples")
    for season, c in sorted(report["season_counts"].items()):
        d = c.get("v1_vs_production", {})
        for key, title in (("examples_production_not_v1",
                            "production PA, not v1 completed"),
                           ("examples_v1_not_production",
                            "v1 completed, not production PA")):
            for ex in d.get(key, [])[:10]:
                lines.append("- %s %s game_pk=%s ab=%d seq=%s -> v1=%s"
                             % (season, title, ex["game_pk"],
                                ex["at_bat_number"], ex["event_sequence"],
                                ex["v1_class"]))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


if __name__ == "__main__":
    raise SystemExit(main())
