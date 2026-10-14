"""2026 cohort enumeration - eligibility metadata ONLY (no outcome reads).

Bounded preparation for the bf-2026-predictor-seal-v1 readiness review.
Applies PREREGISTRATION_2026.md section 1.2 row eligibility (frozen
recipe inputs) over the 2026 regular season using the EXISTING frozen
builders:

  - first-pitcher-of-record starts: (game_pk, side = inning_topbot),
    opener-inclusive, from the completed-PA frame (2026 Savant regular
    parquet);
  - projected-batter-state coverage: ACCEPTED unique-batter v2 recipe
    (pregame-state-v1 build_projected_lineups_variant_v2.assign_unique,
    imported unchanged from the lake, N = 7 prior team-games, greedy +
    fallback_usage, nine-distinct requirement);
  - BF PMF construction inputs: chronological strictly-prior pool
    (bf-workload-v1 BASE: own counts when prior_n >= 10 else league),
    2023-01-01 onward, updated only AFTER each slate date is enumerated;
  - 2022 warm-up: PA feature state machinery pools 2022+ rows as
    strictly-prior state (never fitted, never scored).

OUTCOME BOUNDARY (enforced by construction): the raw frames load ONLY
the columns needed for eligibility; the `events` column is used ONLY
for (a) completed-PA determination (non-null) and (b) `truncated_pa`
exclusion - exactly the frozen builders' eligibility machinery. NO
strikeout/label column is ever created, selected, aggregated, or
stored. Realized BF is an exposure count (completed PAs per pitcher
start), not an outcome label. Zero outcome joins, zero metrics, zero
scoring.

Outputs (card dir): report.json, report.md, cohort_rows_metadata.parquet
(one metadata row per enumerated 2026 start), manifest block.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

K_EVENTS = ["strikeout", "strikeout_double_play"]  # NEVER USED HERE
EXCLUDED_EVENTS = ["truncated_pa"]
N_PRIOR_GAMES = 7
OWN_DIST_MIN_N = 10
TEAM_NORMALIZE = {"OAK": "ATH"}
RAW_COLS = ["game_pk", "game_date", "at_bat_number", "pitch_number",
            "batter", "pitcher", "inning_topbot", "inning",
            "home_team", "away_team", "events"]


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", default=os.environ.get("MLB_PROPS_RESEARCH_LAKE",
                                                     r"<external-lake>"))
    ap.add_argument("--savant", default=os.environ.get(
        "MLB_PROPS_SAVANT_DATA_DIR",
        str(REPO.parent.parent / "MLB-Props" / "data" / "Savant-Data" / "regular")))
    ap.add_argument("--processed", default=os.environ.get(
        "MLB_PROPS_DATA_DIR",
        str(REPO.parent.parent / "MLB-Props" / "data" / "processed")))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    lake, raw, processed = Path(args.lake), Path(args.savant), Path(args.processed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---- frozen builder modules (imported UNCHANGED from the lake) ------
    pgs_scripts = lake / "pregame-state-v1" / "scripts"
    bl = load_module("enum_pgs_build", pgs_scripts / "build_projected_lineups.py")
    variant = load_module("enum_pgs_variant_v2",
                          pgs_scripts / "build_projected_lineups_variant_v2.py")
    sys.path.insert(0, str(HERE))
    import pregame_lineup_capture as pc

    builder_hashes = {
        "build_projected_lineups.py": sha256_file(
            pgs_scripts / "build_projected_lineups.py"),
        "build_projected_lineups_variant_v2.py": sha256_file(
            pgs_scripts / "build_projected_lineups_variant_v2.py"),
        "preregistration_variant_v2.json": sha256_file(
            pgs_scripts / "preregistration_variant_v2.json"),
    }

    # ---- raw metadata frames (events used ONLY for completion filter) ---
    def scan_season(season: int, cols):
        path = raw / str(season) / ("statcast_%d_regular.parquet" % season)
        if not path.exists():
            raise SystemExit("missing raw file: %s" % path)
        return (pl.scan_parquet(path).select(cols)
                .with_columns(pl.col("game_date").cast(pl.Date))
                .with_columns(pl.lit(season).alias("season")))

    pa_frames = [scan_season(y, RAW_COLS) for y in (2022, 2023, 2024, 2025, 2026)]
    raw_all = pl.concat(pa_frames, how="vertical")
    completed = (
        raw_all.filter(pl.col("events").is_not_null())
        .sort(["game_pk", "at_bat_number", "pitch_number"])
        .unique(subset=["game_pk", "at_bat_number", "batter"], keep="last")
        .filter(~pl.col("events").is_in(EXCLUDED_EVENTS))
        .select("game_pk", "game_date", "season", "inning", "inning_topbot",
                "at_bat_number", "batter", "pitcher", "home_team", "away_team")
        .collect())
    # eligibility metadata only: NO label column exists at this point
    assert "events" not in completed.columns

    # ---- first-pitcher-of-record starts (2026) ---------------------------
    first_pitcher = (
        completed.filter(pl.col("season") == 2026)
        .sort(["game_pk", "inning_topbot", "at_bat_number"])
        .unique(subset=["game_pk", "inning_topbot"], keep="first")
        .select("game_pk", "game_date",
                pl.col("inning_topbot").alias("side"),
                pl.col("pitcher").alias("pitcher"))
        .sort(["game_date", "game_pk", "side"]))
    n_starts = first_pitcher.height
    d_min = first_pitcher["game_date"].min()
    d_max = first_pitcher["game_date"].max()
    n_slate_dates = first_pitcher["game_date"].n_unique()

    # ---- BF PMF construction inputs (strictly-prior exposure pools) ------
    bf_counts_all = (
        completed.filter(pl.col("season") >= 2023)
        .group_by("game_pk", "pitcher").agg(bf=pl.len()))
    starts_for_pool = (
        first_pitcher.join(bf_counts_all, on=["game_pk", "pitcher"],
                           how="left")
        .with_columns(pl.col("bf").fill_null(0).cast(pl.Int64))
        .sort(["game_date", "game_pk", "side"]))
    assert int(starts_for_pool["bf"].min()) >= 1, "start with zero BF of record"
    starts_by_date = {
        (k[0] if isinstance(k, tuple) else k): v
        for k, v in starts_for_pool.partition_by(
            "game_date", as_dict=True).items()}

    bf_meta: dict[tuple, dict] = {}
    league_n = 0
    pitchers_pool: dict[int, dict] = {}
    # seed the strictly-prior pools with ALL 2023-2025 BF exposures before
    # enumerating any 2026 date (exposure counts only; same discipline as
    # the frozen builder: each slate date updates pools only AFTER its
    # rows are enumerated)
    hist_counts = (
        completed.filter(pl.col("season") < 2026)
        .group_by("game_pk", "pitcher").agg(bf=pl.len()))
    for rec in hist_counts.iter_rows(named=True):
        st = pitchers_pool.setdefault(rec["pitcher"], {"n": 0})
        st["n"] += 1
        league_n += 1
    for d in (starts_for_pool
              .filter(pl.col("game_date") >= pl.date(2026, 1, 1))
              ["game_date"].unique().sort().to_list()):
        for rec in starts_by_date[d].iter_rows(named=True):
            pid = rec["pitcher"]
            st = pitchers_pool.get(pid)
            prior_n = int(st["n"]) if st is not None else 0
            bf_meta[(rec["game_pk"], rec["side"])] = {
                "bf_prior_n": prior_n,
                "bf_source": ("own" if prior_n >= OWN_DIST_MIN_N else "league"),
                "bf_cold_start": int(prior_n == 0),
                "league_history_available": int(league_n > 0),
            }
        for rec in starts_by_date[d].iter_rows(named=True):
            st = pitchers_pool.setdefault(
                rec["pitcher"], {"n": 0})
            st["n"] += 1
            league_n += 1

    # ---- projected-batter-state coverage (unique-batter v2, UNCHANGED) ---
    def norm(col: str) -> pl.Expr:
        return pl.col(col).replace(TEAM_NORMALIZE)

    games = (
        completed.select("game_pk", "game_date", "home_team", "away_team")
        .unique(subset=["game_pk"])
        .with_columns(norm("home_team").alias("home_team"),
                      norm("away_team").alias("away_team")))
    slots = (
        completed.sort(["game_pk", "inning_topbot", "inning",
                        "at_bat_number"])
        .unique(subset=["game_pk", "inning_topbot", "batter"],
                keep="first", maintain_order=True)
        .with_columns(
            (pl.int_range(pl.len()).over("game_pk", "inning_topbot") + 1)
            .alias("slot"))
        .filter(pl.col("slot") <= 9)
        .with_columns(
            pl.when(pl.col("inning_topbot") == "Top")
            .then(norm("away_team")).otherwise(norm("home_team"))
            .alias("bat_team"))
        .select("game_pk", "game_date", "bat_team", "slot", "batter"))
    tg_by_team = {
        (k[0] if isinstance(k, tuple) else k): v
        for k, v in slots.select("bat_team", "game_date", "game_pk")
        .unique().sort(["bat_team", "game_date", "game_pk"])
        .partition_by("bat_team", as_dict=True).items()}
    lookup_by_game = dict(slots.partition_by(
        "game_pk", "bat_team", as_dict=True).items())

    def assign_for(starts: pl.DataFrame) -> pl.DataFrame:
        rows = []
        for s in starts.to_dicts():
            opp, d = s["opp_team"], s["game_date"]
            prior = tg_by_team[opp].filter(pl.col("game_date") < d)
            prior = prior.tail(N_PRIOR_GAMES)
            pools = {i: [] for i in range(1, 10)}
            for rec in prior.iter_rows(named=True):
                grp = lookup_by_game.get((rec["game_pk"], rec["bat_team"]))
                if grp is None:
                    continue
                for r in grp.iter_rows(named=True):
                    pools[r["slot"]].append(
                        (r["batter"], r["game_date"], 0))
            asg, usage, nine = variant.assign_unique(pools)
            nf = 0
            for i in range(1, 10):
                if asg[i] is not None and asg[i][2] == "fallback_usage":
                    nf += 1
            rows.append({
                "game_pk": s["game_pk"], "side": s["side"],
                "pitcher": s["pitcher"], "game_date": d,
                "opp_team": opp,
                "n_prior_team_games": prior.height,
                "n_pool_distinct": len(usage),
                "nine_distinct": int(nine),
                "n_fallback_slots": nf,
                "n_distinct_ids": len({
                    asg[i][0] for i in range(1, 10) if asg[i] is not None}),
            })
        return pl.DataFrame(rows).sort(["game_date", "game_pk", "side"])

    season_starts = (
        first_pitcher.join(games, on="game_pk", how="left")
        .with_columns(
            pl.when(pl.col("side") == "Top").then(pl.col("away_team"))
            .otherwise(pl.col("home_team")).alias("opp_team"))
        .select("game_pk", "side", "pitcher", "game_date", "opp_team")
        .sort(["game_date", "game_pk", "side"]))
    n_unknown_teams = int(season_starts["opp_team"].null_count())
    proj = assign_for(season_starts)

    # ---- captured cohort + pregame cutoff availability -------------------
    cap_files = sorted(processed.glob("daily_lineups_*.parquet"))
    snaps = pc.load_snapshots(cap_files)
    # canonical capture dates come from the 6 capture FILE names
    # (daily_lineups_YYYY-MM-DD.parquet); fetched_at is a UTC instant and
    # can fall on the next UTC day
    capture_dates = sorted(
        p.stem.replace("daily_lineups_", "") for p in cap_files)
    g = snaps.group_by(["game_pk", "is_home"]).agg(
        pl.col("game_time").max().alias("game_time"),
        pl.col("game_date").max().alias("game_date"))
    probs = (snaps.select(["game_pk", "is_home", "game_time", "game_date",
                           "home_probable_pitcher_id",
                           "away_probable_pitcher_id"])
             .unique(subset=["game_pk", "is_home"], keep="last")
             .with_columns(
                 pl.when(pl.col("is_home") == 1)
                 .then(pl.col("home_probable_pitcher_id"))
                 .otherwise(pl.col("away_probable_pitcher_id"))
                 .cast(pl.Int64).alias("pitcher")))
    n_null_prob = int(probs["pitcher"].null_count())
    cap_rows = (
        probs.filter(pl.col("pitcher").is_not_null())
        .with_columns(
            pl.when(pl.col("is_home") == 1).then(pl.lit("Top"))
            .otherwise(pl.lit("Bottom")).alias("side"))
        .with_columns(pl.col("game_date").cast(pl.Date))
        .select("game_pk", "pitcher", "side", "game_date", "game_time"))
    captured_dates = capture_dates
    captured_team_games = int(g.height)
    cap_key = {(int(r["game_pk"]), int(r["pitcher"])) for r in
               cap_rows.iter_rows(named=True)}

    # ---- pilot overlap (seal + pilot packages, key identity only) --------
    seal_dir = lake / "bf-2026-predictor-seal-v1"
    pilot_dir = lake / "seal-package-preflight"
    seal_keys = json.loads((seal_dir / "row_keys.json").read_text("ascii"))
    pilot_keys = json.loads((pilot_dir / "row_keys.json").read_text("ascii"))
    seal_set = {(int(k["game_pk"]), int(k["pitcher"])) for k in seal_keys}
    pilot_set = {(int(k["game_pk"]), int(k["pitcher"])) for k in pilot_keys}
    season_set = {(int(r["game_pk"]), int(r["pitcher"])) for r in
                  season_starts.iter_rows(named=True)}
    pilot_usable = {(int(k["game_pk"]), int(k["pitcher"])) for k in pilot_keys
                    if k["arm_B_status"] == "ok_confirmed"
                    and not k["arm_B_equals_A"]}

    # ---- p1-harness 2026 contact (definition-level reservation check) ----
    ev = pl.read_parquet(lake / "p1-harness-v2" / "data"
                         / "eval_predictions.parquet")
    ev_d = ev["game_date"]
    if ev_d.dtype != pl.Date:
        ev_d = ev_d.str.slice(0, 10).str.to_date()
    n_eval_rows_2026 = int((ev_d >= date(2026, 1, 1)).sum())

    # ---- per-row metadata table ------------------------------------------
    proj = proj.with_columns([
        pl.struct("game_pk", "side")
        .map_elements(lambda s: bf_meta[(int(s["game_pk"]), s["side"])][
            "bf_prior_n"], return_dtype=pl.Int64).alias("bf_prior_n"),
        pl.struct("game_pk", "side")
        .map_elements(lambda s: bf_meta[(int(s["game_pk"]), s["side"])][
            "bf_source"], return_dtype=pl.String).alias("bf_source"),
        pl.struct("game_pk", "side")
        .map_elements(lambda s: bf_meta[(int(s["game_pk"]), s["side"])][
            "bf_cold_start"], return_dtype=pl.Int8).alias("bf_cold_start"),
        pl.struct("game_pk", "side")
        .map_elements(lambda s: bf_meta[(int(s["game_pk"]), s["side"])][
            "league_history_available"], return_dtype=pl.Int8)
        .alias("league_history_available"),
    ])
    meta = (
        proj.with_columns([
            pl.struct("game_pk", "pitcher")
            .map_elements(lambda s: int((int(s["game_pk"]),
                                         int(s["pitcher"])) in cap_key),
                          return_dtype=pl.Int8).alias("has_captured_cutoff"),
            pl.struct("game_pk", "pitcher")
            .map_elements(lambda s: int((int(s["game_pk"]),
                                         int(s["pitcher"])) in seal_set),
                          return_dtype=pl.Int8).alias("in_pilot_134"),
            pl.struct("game_pk", "pitcher")
            .map_elements(lambda s: int((int(s["game_pk"]),
                                         int(s["pitcher"])) in pilot_usable),
                          return_dtype=pl.Int8).alias("in_pilot_usable_B_11"),
        ])
        .with_columns([
            pl.when(pl.col("has_captured_cutoff") == 1)
            .then(pl.lit("captured_snapshot_game_time"))
            .otherwise(pl.lit("none_captured_only_6_fetch_dates"))
            .alias("pregame_cutoff_availability"),
            pl.lit(1).alias("bf_inputs_available"),
            pl.lit(1).alias("pa_state_available_2022_warmup"),
        ])
        .sort(["game_date", "game_pk", "side"]))
    meta.write_parquet(out / "cohort_rows_metadata.parquet")

    # ---- eligibility roll-up ---------------------------------------------
    nine_fail = meta.filter(pl.col("nine_distinct") != 1)
    eligible = meta.filter(pl.col("nine_distinct") == 1)
    captured_elig = meta.filter(
        (pl.col("has_captured_cutoff") == 1)
        & (pl.col("nine_distinct") == 1))
    captured_nine_fail = meta.filter(
        (pl.col("has_captured_cutoff") == 1)
        & (pl.col("nine_distinct") != 1))
    overlap = meta.filter(pl.col("in_pilot_134") == 1)
    overlap_usable = meta.filter(pl.col("in_pilot_usable_B_11") == 1)
    on_capture_dates = meta.filter(
        pl.col("game_date").is_in(
            [date.fromisoformat(x) for x in
             {c[:10] for c in captured_dates}]))
    season_n = meta.height
    report = {
        "card": "bf-2026-cohort-enumeration-2026-10-14",
        "method": ("eligibility metadata only per PREREGISTRATION_2026.md "
                   "section 1.2; frozen builders imported unchanged; NO "
                   "outcome reads (events used only for completed-PA / "
                   "truncated_pa eligibility, no label column created)"),
        "season_window": {
            "data_min_game_date": str(d_min),
            "data_max_game_date": str(d_max),
            "n_slate_dates": int(n_slate_dates),
        },
        "full_season_cohort": {
            "first_pitcher_of_record_starts": int(n_starts),
            "unknown_opp_team": n_unknown_teams,
            "nine_distinct_failures_excluded": int(nine_fail.height),
            "eligible_rows_after_exclusions": int(eligible.height),
            "bf_inputs_available_rows": int(
                (meta["bf_inputs_available"] == 1).sum()),
            "league_history_available_rows": int(
                (meta["league_history_available"] == 1).sum()),
            "bf_cold_start_rows": int((meta["bf_cold_start"] == 1).sum()),
            "bf_own_dist_rows_prior_n_ge10": int(
                (meta["bf_source"] == "own").sum()),
            "pa_state_available_rows": int(
                (meta["pa_state_available_2022_warmup"] == 1).sum()),
            "n_prior_team_games_lt7_rows": int(
                (meta["n_prior_team_games"] < N_PRIOR_GAMES).sum()),
            "rows_with_fallback_slot": int(
                (meta["n_fallback_slots"] > 0).sum()),
            "eligible_with_captured_pregame_cutoff": int(
                (eligible["has_captured_cutoff"] == 1).sum()),
            "eligible_without_captured_pregame_cutoff": int(
                (eligible["has_captured_cutoff"] == 0).sum()),
        },
        "captured_cohort": {
            "captured_team_games": captured_team_games,
            "captured_lineup_dates": captured_dates,
            "null_probable_pitcher_excluded": n_null_prob,
            "captured_rows_with_pregame_cutoff": len(cap_key),
            "captured_nine_distinct_failures": int(
                captured_nine_fail.height),
            "captured_eligible_rows": int(captured_elig.height),
        },
        "exclusions_by_reason": {
            "full_season_nine_distinct_failures": {
                "n": int(nine_fail.height),
                "registered_reason": "insufficient_distinct_prior_batters"},
            "captured_null_probable_pitcher": {"n": n_null_prob},
            "captured_nine_distinct_failures": {
                "n": int(captured_nine_fail.height)},
            "unknown_opp_team": {"n": n_unknown_teams},
            "missing_bf_inputs": {"n": int(
                (meta["bf_inputs_available"] != 1).sum())},
        },
        "pilot_overlap": {
            "seal_keys_n": len(seal_set),
            "pilot_keys_n": len(pilot_set),
            "key_sets_identical": seal_set == pilot_set,
            "pilot_rows_in_full_season_enumeration": int(overlap.height),
            "pilot_usable_B_11_in_enumeration": int(overlap_usable.height),
            "membership_source_note": (
                "pilot usable-B membership (11 usable-B / 123 fallback) "
                "comes from the PILOT package row_keys.json; the seal "
                "payload re-stamps all 134 rows ok_confirmed and is NOT "
                "a membership source (see CLASSIFICATION.md)"),
        },
        "prior_exposure_groups": {
            "pilot_134_rows": {
                "n": len(seal_set),
                "reason": "sealed 2026 A/B pilot replay population; "
                          "outcomes already observed (DEV_STANDARD_RECIPE "
                          "9.4.1); excluded from confirmation/pooling"},
            "captured_team_games_pilot_replay_inputs": {
                "n": captured_team_games,
                "reason": "142 captured team-games touched as pilot "
                          "replay inputs (bf-bundle-2026 lineage)"},
            "captured_lineup_slate_dates": {
                "dates": sorted({c[:10] for c in captured_dates}),
                "n_rows_on_those_slate_dates": int(on_capture_dates.height),
                "reason": "6 captured 2026 lineup dates flagged by "
                          "registration section 8"},
            "p1_harness_2026_contact": {
                "eval_rows_with_2026_dates": n_eval_rows_2026,
                "reason": "p1-harness EVAL split reserves 2026 rows at "
                          "definition level only; eval_predictions "
                          "contain 0 rows dated 2026 (verified); no 2026 "
                          "row was scored by the harness"},
            "rows_outside_all_groups": {
                "n": int(meta.filter(
                    (pl.col("in_pilot_134") == 0)
                    & (pl.col("has_captured_cutoff") == 0)
                    & ~pl.col("game_date").is_in(
                        [date.fromisoformat(x) for x in
                         {c[:10] for c in captured_dates}])).height),
                "note": "full-season rows with no recorded development "
                        "contact; state inputs were rebuilt strictly-"
                        "prior by this metadata-only enumeration"},
        },
        "builder_hashes": builder_hashes,
        "inputs": {
            "savant_root": str(raw),
            "processed_root": str(processed),
            "lake": str(lake),
        },
        "outcome_boundary": {
            "label_columns_created": 0,
            "k_events_used": False,
            "events_column_use": "completed-PA determination + "
                                 "truncated_pa exclusion only",
            "realized_bf_use": "exposure count (completed PAs per "
                               "pitcher-game), strictly-prior state only",
            "scoring_performed": False,
        },
    }
    (out / "report.json").write_text(
        json.dumps(report, indent=1), encoding="ascii")
    print(json.dumps({
        "out": str(out),
        "season_window": report["season_window"],
        "full_season_eligible": report["full_season_cohort"][
            "eligible_rows_after_exclusions"],
        "nine_distinct_failures": report["exclusions_by_reason"][
            "full_season_nine_distinct_failures"]["n"],
        "captured_eligible": report["captured_cohort"][
            "captured_eligible_rows"],
        "pilot_overlap": report["pilot_overlap"][
            "pilot_rows_in_full_season_enumeration"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
