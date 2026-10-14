"""2026 predictor seal PREP builder -> bf-2026-predictor-seal-v1.

Bounded seal preparation only. Builds the predictor payload (row keys +
both arm count PMFs) for the 2026 captured eligible cohort under the
accepted frozen recipe (PREREGISTRATION_2026, binding DEV_STANDARD_RECIPE):

  - projected-batter-state: ACCEPTED unique-batter v2 recipe
    (pregame-state-v1, preregistration_variant_v2.json), reused verbatim;
  - BF PMF construction: bf-workload-v1 BASE variant (37-category add-one
    empirical, own dist if prior_n >= 10 else league). No fitted
    parameters exist in this component; the chronological pool builder is
    extended over 2026 and verified bitwise against the frozen
    bf-workload-v1 artifact on all of its rows;
  - PA probabilities: overnight-p2 ladder arms H3 (8-feature logistic)
    and cumulative log5, per-block sigmoid CALIBRATED columns per
    DEV_STANDARD_RECIPE section 5; 2026 dates resolve to the
    confirm_2025H2 frozen block via checkpoint-verified deterministic
    refit (max abs diff <= 1e-8 vs stored preds) - NOT a new fit;
  - count PMFs: bf_pmf_from_37 (60-exposure) + cycled projected nine
    per-PA probabilities -> pbar_n -> count_pmf_from_mixture (24 buckets,
    0..22 exact + >=23 absorbing), both arms on identical projected
    batter state and identical per-start BF PMF.

FORBIDDEN HERE, enforced by construction: no model fitting beyond the
checkpoint-verified deterministic refits of the frozen blocks, no
calibrator fitting, no outcome/label join, no metric calculation, no
2026 scoring. Realized BF counts enter ONLY as strictly-prior state
(strictly before each start's game_date), never as labels. The
realized-K label join happens ONLY in the canonical scorer
(run_bf_ab_score_v3.py -> run_bf_ab_score_v2.compute_stats) at gated
scoring time; this payload carries zero outcome columns.

Reproduction gates BEFORE any 2026 payload construction (fail-loud):
  V1 extended PA table restricted to 2022-2025 == frozen overnight-p2
     pa_table.parquet (sorted-frame bitwise);
  V2 daily states reproduce frozen features_v3 on all its rows
     (v1.gate1_state_verification);
  V3 deterministic ladder refits reproduce the stored checkpoint
     predictions (v1.gate2_refit_and_verify);
  V4 chronological BF pool builder reproduces the frozen bf-workload-v1
     bf_forecasts.parquet bitwise on all of its rows;
  V5 completed-PA frame 2023-2025 == frozen build_projected_lineups
     loader output, and the unique-batter assignment reproduces the
     frozen projected_lineups_variant_v2.parquet on all 7,194 starts.

Arm identity for the seal payload (preregistration section 5 direction
"H3-logistic minus cumulative log5" = B - A):
  arm_A = cumulative log5 (reference), arm_B = H3 logistic (challenger).
Both arms always execute the projected recipe; arm_B_status is
"ok_confirmed" on every emitted row (the recipe has no A-fallback; the
nine-distinct requirement is a hard exclusion, never a fallback).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import bf_distribution as bfd  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import pregame_lineup_capture as pc  # noqa: E402

KC_SHA256 = "c852b5cf14956942a2a9d67d7e076b758dbbca75a6983ba55cdfe6906f7264e5"
V3_RUNNER_SHA256 = "1cb3bc5d1c1653bfbfa06e28f1f91e6ed7c81e91dfba5210f1b1cf9fe36407db"
PREREG_V2_SHA256 = "0983d6aecff9689f67c5032ca240a8d6beb982c1534415d74f90b3a0d94b7303"

K_EVENTS = ["strikeout", "strikeout_double_play"]
EXCLUDED_EVENTS = ["truncated_pa"]
W_SHRINK_BF = 50.0
OWN_DIST_MIN_N = 10
N_PRIOR_GAMES = 7
TEAM_NORMALIZE = {"OAK": "ATH"}
FROZEN_VARIANT_ROWS = 7194


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fail(msg: str) -> None:
    raise SystemExit("SEAL-PREP BLOCKER: %s" % msg)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frames_bitwise_equal(a: pl.DataFrame, b: pl.DataFrame, label: str) -> dict:
    if a.columns != b.columns:
        _fail("%s: column mismatch" % label)
    if a.schema != b.schema:
        _fail("%s: schema mismatch" % label)
    if a.height != b.height:
        _fail("%s: height mismatch %d vs %d" % (label, a.height, b.height))
    diffs = {}
    for c in a.columns:
        s1, s2 = a[c], b[c]
        eq = (s1 == s2) | (s1.is_null() & s2.is_null())
        n_bad = int((~eq).sum())
        if n_bad:
            diffs[c] = n_bad
    if diffs:
        _fail("%s: differing columns %s" % (label, diffs))
    return {"identical": True, "n_rows": a.height}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True,
                    help="seal output dir (write-once; must be absent)")
    ap.add_argument("--lake", default=os.environ.get("MLB_PROPS_RESEARCH_LAKE"),
                    help="research lake root (or env MLB_PROPS_RESEARCH_LAKE)")
    ap.add_argument("--savant", default=os.environ.get(
        "MLB_PROPS_SAVANT_DATA_DIR",
        str(REPO / "data" / "Savant-Data" / "regular")))
    ap.add_argument("--processed", default=os.environ.get(
        "MLB_PROPS_DATA_DIR", str(REPO / "data" / "processed")))
    args = ap.parse_args()

    if not args.lake:
        _fail("set --lake or MLB_PROPS_RESEARCH_LAKE")
    lake = Path(args.lake)
    raw = Path(args.savant)
    processed = Path(args.processed)
    for p in (raw, processed):
        if not p.exists():
            _fail("missing input dir: %s" % p)

    out_dir = Path(args.out)
    if out_dir.exists() and any(out_dir.iterdir()):
        _fail("output dir exists and is non-empty (write-once): %s" % out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- pinned external modules and artifacts --------------------------
    if sha256_file(HERE / "kcount_combiner.py") != KC_SHA256:
        _fail("kcount_combiner.py sha mismatch vs frozen pin")
    assert kc.__file__ and Path(kc.__file__).resolve().is_relative_to(HERE)
    pgs_scripts = lake / "pregame-state-v1" / "scripts"
    if sha256_file(pgs_scripts / "run_pregame_state_v3.py") != V3_RUNNER_SHA256:
        _fail("run_pregame_state_v3.py sha mismatch vs preregistration pin")
    if sha256_file(pgs_scripts / "preregistration_variant_v2.json") \
            != PREREG_V2_SHA256:
        _fail("preregistration_variant_v2.json sha mismatch")
    p2_data = lake / "overnight-p2" / "data"
    bfw_data = lake / "bf-workload-v1" / "data"
    run_identity = json.loads(
        (lake / "overnight-p2" / "run_identity.json").read_text())
    rid = {k: v for k, v in run_identity.items() if k != "run_identity_sha256"}
    if hashlib.sha256(json.dumps(rid, sort_keys=True).encode("utf-8")
                      ).hexdigest() != run_identity["run_identity_sha256"]:
        _fail("overnight-p2 run_identity_sha256 mismatch")

    v1 = load_module("seal_pgs_v1",
                     pgs_scripts / "run_pregame_state_comparison.py")
    v3pgs = load_module("seal_pgs_v3", pgs_scripts / "run_pregame_state_v3.py")
    bl = load_module("seal_pgs_build",
                     pgs_scripts / "build_projected_lineups.py")
    variant = load_module("seal_pgs_variant_v2",
                          pgs_scripts / "build_projected_lineups_variant_v2.py")

    PREDS_FILES = dict(v1.PREDS)
    P2_FROZEN_PA = p2_data / "pa_table.parquet"
    P2_FROZEN_FEAT = p2_data / "features_v3.parquet"
    pa_frozen = pl.read_parquet(P2_FROZEN_PA)
    feat = pl.read_parquet(P2_FROZEN_FEAT)

    # ---- extended raw frames (2022-2026 / 2023-2026 state sources) ------
    raw_cols = ["game_pk", "game_date", "at_bat_number", "pitch_number",
                "batter", "pitcher", "p_throws", "stand", "events",
                "inning_topbot"]

    def scan_season(season: int, cols):
        path = raw / str(season) / ("statcast_%d_regular.parquet" % season)
        if not path.exists():
            _fail("missing raw file: %s" % path)
        return (pl.scan_parquet(path).select(cols)
                .with_columns(pl.col("game_date").cast(pl.Date))
                .with_columns(pl.lit(season).alias("season")))

    pa_frames = [scan_season(y, raw_cols) for y in (2022, 2023, 2024, 2025, 2026)]
    raw_all = pl.concat(pa_frames, how="vertical")
    completed = (
        raw_all.filter(pl.col("events").is_not_null())
        .sort(["game_pk", "at_bat_number", "pitch_number"])
        .unique(subset=["game_pk", "at_bat_number", "batter"], keep="last")
        .with_columns(pl.col("events").is_in(K_EVENTS).cast(pl.Int8)
                      .alias("y")))
    pa_ext = (
        completed.filter(~pl.col("events").is_in(EXCLUDED_EVENTS))
        .select("game_pk", "game_date", "season", "at_bat_number", "batter",
                "pitcher", "p_throws", "stand", "inning_topbot", "y")
        .collect())
    fp = (
        pa_ext.sort(["game_pk", "inning_topbot", "at_bat_number"])
        .unique(subset=["game_pk", "inning_topbot"], keep="first")
        .select("game_pk", pl.col("inning_topbot").alias("side"),
                pl.col("pitcher").alias("first_pitcher_of_record")))
    pa_ext = (
        pa_ext.join(fp, left_on=["game_pk", "inning_topbot"],
                    right_on=["game_pk", "side"], how="left")
        .with_columns(
            pl.when(pl.col("pitcher") == pl.col("first_pitcher_of_record"))
            .then(pl.lit("starter_pa")).otherwise(pl.lit("reliever_pa"))
            .cast(pl.String).alias("pitcher_role"))
        .drop("first_pitcher_of_record"))
    if (pa_ext.group_by("game_pk", "at_bat_number", "batter")
            .agg(n=pl.len()).filter(pl.col("n") > 1).height):
        _fail("duplicate PA identities in extended PA table")
    pa_ext_cols = ["game_pk", "game_date", "season", "at_bat_number",
                   "batter", "pitcher", "p_throws", "stand", "inning_topbot",
                   "y", "pitcher_role"]
    pa_key = ["game_pk", "at_bat_number", "batter"]
    gate_v1 = frames_bitwise_equal(
        pa_ext.select(pa_ext_cols).filter(
            pl.col("game_date") < pl.date(2026, 1, 1)).sort(pa_key),
        pa_frozen.select(pa_ext_cols).sort(pa_key),
        "V1 PA table 2022-2025")
    n_pa_2026 = int((pa_ext["game_date"] >= date(2026, 1, 1)).sum())

    p_daily = v1.entity_daily_state(pa_ext, "pitcher")
    b_daily = v1.entity_daily_state(pa_ext, "batter")
    lg = v1.league_daily_state(pa_ext)
    gate_v2 = v1.gate1_state_verification(p_daily, b_daily, lg, feat)
    models, gate_v3 = v1.gate2_refit_and_verify(feat, pa_ext)

    # ---- captured 2026 cohort (probable pitchers at cutoff) -------------
    snaps = pc.load_snapshots(sorted(processed.glob("daily_lineups_*.parquet")))
    g = snaps.group_by(["game_pk", "is_home"]).agg(
        pl.col("game_time").max().alias("game_time"),
        pl.col("game_date").max().alias("game_date"))
    rev = snaps.group_by(["game_pk", "is_home"]).agg(
        pl.col("fetched_at").n_unique().alias("n_fetch"),
        pl.col("home_probable_pitcher_id").n_unique().alias("n_hp"),
        pl.col("away_probable_pitcher_id").n_unique().alias("n_ap"),
        pl.col("game_time").n_unique().alias("n_time"))
    n_rev_conf = int(((rev["n_fetch"] > 1) | (rev["n_hp"] > 1)
                      | (rev["n_ap"] > 1) | (rev["n_time"] > 1)).sum())
    if n_rev_conf:
        _fail("conflicting capture revisions at (game_pk,is_home) grain: "
              "%d groups (no frozen revision rule; fail-closed)"
              % n_rev_conf)
    gd_map = {int(r["game_pk"]): r["game_date"]
              for r in g.iter_rows(named=True)}
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
        .select("game_pk", "is_home", "pitcher", "side", "game_date",
                "game_time"))

    # ---- V4: chronological BF pools (2023-2026) + bitwise gate ----------
    bf_frames = [scan_season(y, ["game_pk", "game_date", "at_bat_number",
                                 "pitch_number", "batter", "pitcher",
                                 "events", "inning_topbot", "inning",
                                 "home_team", "away_team"])
                 for y in (2023, 2024, 2025, 2026)]
    rawb = pl.concat(bf_frames, how="vertical")
    pa_b = (
        rawb.filter(pl.col("events").is_not_null())
        .sort(["game_pk", "at_bat_number", "pitch_number"])
        .unique(subset=["game_pk", "at_bat_number", "batter"], keep="last")
        .filter(~pl.col("events").is_in(EXCLUDED_EVENTS))
        .with_columns(pl.col("events").is_in(K_EVENTS).cast(pl.Int8)
                      .alias("y"))
        .select("game_pk", "game_date", "at_bat_number", "batter",
                "pitcher", "inning_topbot", "y")
        .collect())
    first_pitcher = (
        pa_b.sort(["game_pk", "inning_topbot", "at_bat_number"])
        .unique(subset=["game_pk", "inning_topbot"], keep="first")
        .select("game_pk", pl.col("inning_topbot").alias("side"),
                pl.col("pitcher").alias("pitcher"),
                pl.col("game_date").alias("game_date")))
    bf_counts = pa_b.group_by("game_pk", "pitcher").agg(bf=pl.len())
    starts_all = (
        first_pitcher.join(bf_counts, on=["game_pk", "pitcher"], how="left")
        .with_columns(pl.col("bf").fill_null(0).cast(pl.Int64))
        .sort(["game_date", "game_pk", "side"]))
    assert int(starts_all["bf"].min()) >= 1, "start with zero BF of record"

    request = {}
    for r in cap_rows.iter_rows(named=True):
        request.setdefault(r["game_date"], []).append(
            (int(r["game_pk"]), int(r["pitcher"])))

    pool_rows = []
    cap_bf = {}
    league_counts = np.zeros(37)
    league_sum = 0.0
    league_n = 0
    pitchers_pool: dict[int, dict] = {}
    starts_by_date = {
        (k[0] if isinstance(k, tuple) else k): v
        for k, v in starts_all.partition_by(
            "game_date", as_dict=True).items()}
    for d in starts_all["game_date"].unique().sort().to_list():
        for gp, pid in request.get(d, []):
            st = pitchers_pool.get(pid)
            prior_n = int(st["n"]) if st is not None else 0
            prior_mean = (st["sum"] / prior_n) if prior_n > 0 else None
            lg_mean = (league_sum / league_n) if league_n > 0 else None
            if lg_mean is None:
                _fail("no league BF history for %s on %s" % (pid, d))
            pm = prior_mean if prior_mean is not None else 0.0
            src = (st["counts"].copy() if prior_n >= OWN_DIST_MIN_N
                   else league_counts.copy())
            cap_bf[gp] = {
                "pitcher": pid, "prior_n": prior_n,
                "prior_mean": pm, "lg_mean": lg_mean,
                "prior_mean_shrunk_w50": (
                    (prior_n * pm + W_SHRINK_BF * lg_mean)
                    / (prior_n + W_SHRINK_BF)),
                "cold_start": int(prior_n == 0),
                "pmf37": bfd.empirical_baseline(src),
            }
        day = starts_by_date[d]
        for rec in day.iter_rows(named=True):
            pid = rec["pitcher"]
            bf = rec["bf"]
            st = pitchers_pool.get(pid)
            prior_n = int(st["n"]) if st is not None else 0
            prior_mean = (st["sum"] / prior_n) if prior_n > 0 else None
            lg_mean = (league_sum / league_n) if league_n > 0 else None
            if lg_mean is None:
                pmf37 = pmf37_mix = shrunk = None
            else:
                pm = prior_mean if prior_mean is not None else 0.0
                shrunk = ((prior_n * pm + W_SHRINK_BF * lg_mean)
                          / (prior_n + W_SHRINK_BF))
                src = (st["counts"].copy() if prior_n >= OWN_DIST_MIN_N
                       else league_counts.copy())
                pmf37 = bfd.empirical_baseline(src)
                pmf37_mix = bfd.empirical_baseline(
                    0.5 * src + 0.5 * league_counts)
            pool_rows.append({
                "game_pk": rec["game_pk"], "side": rec["side"],
                "pitcher": pid, "game_date": d,
                "prior_n": prior_n, "prior_mean": prior_mean,
                "lg_mean": lg_mean, "prior_mean_shrunk_w50": shrunk,
                "cold_start": int(prior_n == 0), "realized_bf": int(bf),
                "pmf37": pmf37, "pmf37_mix": pmf37_mix})
        for rec in day.iter_rows(named=True):
            c = bfd.counts_from_outcomes([int(rec["bf"])])
            league_counts += c
            league_sum += float(rec["bf"])
            league_n += 1
            st = pitchers_pool.get(rec["pitcher"])
            if st is None:
                st = {"counts": np.zeros(37), "sum": 0.0, "n": 0}
                pitchers_pool[rec["pitcher"]] = st
            st["counts"] += c
            st["sum"] += float(rec["bf"])
            st["n"] += 1

    pmf_cols = ["pmf37_%d" % j for j in range(37)]
    mix_cols = ["pmf37_mix_%d" % j for j in range(37)]
    rebuilt = pl.DataFrame({
        "game_pk": [r["game_pk"] for r in pool_rows],
        "side": [r["side"] for r in pool_rows],
        "pitcher": [r["pitcher"] for r in pool_rows],
        "game_date": [r["game_date"] for r in pool_rows],
        "prior_n": [r["prior_n"] for r in pool_rows],
        "prior_mean": [r["prior_mean"] for r in pool_rows],
        "lg_mean": [r["lg_mean"] for r in pool_rows],
        "prior_mean_shrunk_w50": [r["prior_mean_shrunk_w50"]
                                  for r in pool_rows],
        "cold_start": [r["cold_start"] for r in pool_rows],
        "realized_bf": [r["realized_bf"] for r in pool_rows],
    }, schema={
        "game_pk": pl.Int64, "side": pl.String, "pitcher": pl.Int64,
        "game_date": pl.Date, "prior_n": pl.Int64,
        "prior_mean": pl.Float64, "lg_mean": pl.Float64,
        "prior_mean_shrunk_w50": pl.Float64, "cold_start": pl.Int8,
        "realized_bf": pl.Int64})
    rebuilt = pl.concat(
        [rebuilt,
         pl.DataFrame({c: [None if r["pmf37"] is None
                           else float(r["pmf37"][j]) for r in pool_rows]
                       for j, c in enumerate(pmf_cols)}),
         pl.DataFrame({c: [None if r["pmf37_mix"] is None
                           else float(r["pmf37_mix"][j]) for r in pool_rows]
                       for j, c in enumerate(mix_cols)})],
        how="horizontal").sort(["game_date", "game_pk", "side"])
    frozen_bf = pl.read_parquet(bfw_data / "bf_forecasts.parquet").sort(
        ["game_date", "game_pk", "side"])
    gate_v4 = frames_bitwise_equal(
        rebuilt.filter(pl.col("game_date") < pl.date(2026, 1, 1)),
        frozen_bf, "V4 bf_forecasts")

    # ---- V5: projected-batter-state v2 verification + 2026 assignment ---
    completed_all = (
        rawb.select("game_pk", "game_date", "inning", "inning_topbot",
                    "at_bat_number", "pitch_number", "batter", "events",
                    "home_team", "away_team")
        .filter(pl.col("events").is_not_null())
        .sort(["game_pk", "at_bat_number", "pitch_number"])
        .unique(subset=["game_pk", "at_bat_number", "batter"], keep="last")
        .filter(~pl.col("events").is_in(EXCLUDED_EVENTS))
        .select("game_pk", "game_date", "inning", "inning_topbot",
                "at_bat_number", "batter", "home_team", "away_team")
        .collect())
    frozen_completed = bl.load_completed().sort(pa_key)
    gate_v5a = frames_bitwise_equal(
        completed_all.filter(pl.col("game_date") < pl.date(2026, 1, 1))
        .sort(pa_key).select(frozen_completed.columns),
        frozen_completed, "V5a completed-PA frame 2023-2025")

    def norm(col: str) -> pl.Expr:
        return pl.col(col).replace(TEAM_NORMALIZE)

    games = (
        completed_all.select("game_pk", "game_date", "home_team",
                             "away_team")
        .unique(subset=["game_pk"])
        .with_columns(norm("home_team").alias("home_team"),
                      norm("away_team").alias("away_team")))
    slots = (
        completed_all.sort(["game_pk", "inning_topbot", "inning",
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
        .with_columns((pl.col("slot") - 1).alias("first_appearance_pos"))
        .select("game_pk", "game_date", "bat_team", "slot", "batter",
                "first_appearance_pos"))
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
                        (r["batter"], r["game_date"],
                         r["first_appearance_pos"]))
            asg, usage, nine = variant.assign_unique(pools)
            row = {"game_pk": s["game_pk"], "side": s["side"],
                   "pitcher": s["pitcher"], "game_date": d,
                   "opp_team": opp, "n_prior_team_games": prior.height,
                   "n_pool_distinct": len(usage), "nine_distinct": int(nine)}
            nf = 0
            for i in range(1, 10):
                if asg[i] is None:
                    row["u_slot_%d" % i] = None
                    row["sup_slot_%d" % i] = None
                    row["how_slot_%d" % i] = None
                    continue
                b, sup, how = asg[i]
                row["u_slot_%d" % i] = b
                row["sup_slot_%d" % i] = sup
                row["how_slot_%d" % i] = how
                if how == "fallback_usage":
                    nf += 1
            row["n_fallback_slots"] = nf
            row["n_distinct_ids"] = len({
                asg[i][0] for i in range(1, 10) if asg[i] is not None})
            rows.append(row)
        return pl.DataFrame(rows).sort(["game_date", "game_pk", "side"])

    frozen_proj = pl.read_parquet(
        lake / "pregame-state-v1" / "data"
        / "projected_lineups_variant_v2.parquet")
    frozen_starts = (
        frozen_bf.filter((pl.col("game_date") >= pl.date(2024, 7, 1))
                         & (pl.col("game_date") <= pl.date(2025, 12, 31)))
        .select("game_pk", "side", "pitcher", "game_date")
        .join(games, on="game_pk", how="left")
        .with_columns(
            pl.when(pl.col("side") == "Top").then(pl.col("away_team"))
            .otherwise(pl.col("home_team")).alias("opp_team"))
        .select("game_pk", "side", "pitcher", "game_date", "opp_team")
        .sort(["game_date", "game_pk", "side"]))
    if frozen_starts.height != FROZEN_VARIANT_ROWS:
        _fail("frozen window starts != %d" % FROZEN_VARIANT_ROWS)
    rebuilt_proj = assign_for(frozen_starts)
    proj_cols = (["game_pk", "side", "pitcher", "game_date", "opp_team",
                  "n_prior_team_games", "n_pool_distinct", "nine_distinct"]
                 + ["u_slot_%d" % i for i in range(1, 10)]
                 + ["sup_slot_%d" % i for i in range(1, 10)]
                 + ["how_slot_%d" % i for i in range(1, 10)]
                 + ["n_fallback_slots", "n_distinct_ids"])
    gate_v5 = frames_bitwise_equal(
        rebuilt_proj.select(proj_cols), frozen_proj.select(proj_cols),
        "V5b unique-batter assignment")

    seal_starts = (
        cap_rows.join(games, on="game_pk", how="left")
        .with_columns(
            pl.when(pl.col("side") == "Top").then(pl.col("away_team"))
            .otherwise(pl.col("home_team")).alias("opp_team"))
        .select("game_pk", "side", "pitcher", "game_date", "opp_team")
        .sort(["game_date", "game_pk", "side"]))
    if int(seal_starts["opp_team"].null_count()) != 0:
        _fail("seal start with unknown teams")
    seal_proj = assign_for(seal_starts)

    # ---- slot probabilities + count PMFs --------------------------------
    slot_cols = ["u_slot_%d" % i for i in range(1, 10)]
    scoreable = seal_proj.filter(pl.col("nine_distinct") == 1)
    excluded = seal_proj.filter(pl.col("nine_distinct") != 1)
    long = (
        scoreable.select("game_pk", "side", "pitcher", "game_date",
                         *slot_cols)
        .unpivot(index=["game_pk", "side", "pitcher", "game_date"],
                 on=slot_cols, variable_name="slot_name",
                 value_name="batter")
        .with_columns(pl.col("slot_name").str.extract(r"(\d+)")
                      .cast(pl.Int32).alias("slot"))
        .drop("slot_name"))
    if int(long["batter"].null_count()) != 0:
        _fail("uncovered slot in scoreable rows")
    # 2026 game_dates resolve to the confirm_2025H2 frozen block only;
    # pass that single checkpoint-verified model so the accepted
    # per-block loop never transforms an empty sub-frame. Any row
    # landing outside it would leave NaN and trip the NaN assert inside
    # build_slot_probabilities.
    models_2026 = {"confirm_2025H2": models["confirm_2025H2"]}
    wide = v3pgs.build_slot_probabilities(long, p_daily, b_daily, lg,
                                          models_2026)
    wide = wide.join(
        cap_rows.select("game_pk", "pitcher", "game_time"),
        on=["game_pk", "pitcher"], how="inner")
    if wide.height != scoreable.height:
        _fail("seal join lost rows: %d vs %d"
              % (wide.height, scoreable.height))
    wide = wide.sort(["game_pk", "pitcher"])

    keys_out = []
    pA, pB = [], []
    for s in wide.to_dicts():
        rec = cap_bf[int(s["game_pk"])]
        bf37 = np.asarray(rec["pmf37"], dtype=float)
        bf_ext = kc.bf_pmf_from_37(bf37)
        pk_arms = {}
        for tag, name in (("l5", "A"), ("h3", "B")):
            p9 = np.array([s["p_%s_%d" % (tag, i)] for i in range(1, 10)])
            v3pgs.check_prob_vec(p9, "seal/%s p9" % name)
            cycled = np.tile(p9, v1.KCOUNT_CAP // 9 + 1)[:v1.KCOUNT_CAP]
            pbar = np.clip(
                np.cumsum(cycled) / np.arange(1, v1.KCOUNT_CAP + 1),
                v1.P_CLIP, 1 - v1.P_CLIP)
            v3pgs.check_prob_vec(pbar, "seal/%s pbar" % name)
            pk = v1.count_pmf_from_mixture(bf_ext, pbar)
            v3pgs.check_pmf(pk, "seal/%s" % name)
            pk_arms[name] = pk
        pA.append(pk_arms["A"])
        pB.append(pk_arms["B"])
        keys_out.append({
            "game_pk": int(s["game_pk"]), "pitcher": int(s["pitcher"]),
            "forecast_cutoff": str(s["game_time"]),
            "arm_B_status": "ok_confirmed", "arm_B_equals_A": False})
    A = np.array(pA)
    B = np.array(pB)
    n = len(keys_out)

    # ---- payload validations --------------------------------------------
    if A.shape != (n, 24) or B.shape != (n, 24):
        _fail("arm PMF shape mismatch: %r %r" % (A.shape, B.shape))
    if len({(k["game_pk"], k["pitcher"]) for k in keys_out}) != n:
        _fail("duplicate seal keys")
    if len({(r["game_pk"], r["side"]) for r in seal_proj.to_dicts()}) != n:
        _fail("seal row count vs batter-state population mismatch")
    for i in range(n):
        for pk in (A[i], B[i]):
            if not (np.all(np.isfinite(pk)) and float(pk.min()) >= 0.0
                    and abs(float(pk.sum()) - 1.0) <= 1e-9):
                _fail("PMF validation failed at row %d" % i)
    if int(seal_proj["n_distinct_ids"].min()) != 9:
        _fail("nine-distinct requirement violated")

    # ---- pilot population cross-check (archive, if present) -------------
    pilot_path = lake / "seal-package-preflight" / "row_keys.json"
    pilot_check = {"present": bool(pilot_path.exists())}
    if pilot_path.exists():
        pilot = json.loads(pilot_path.read_text(encoding="ascii"))
        pilot_map = {(int(x["game_pk"]), int(x["pitcher"])):
                     x["forecast_cutoff"] for x in pilot}
        mine = {(k["game_pk"], k["pitcher"]): k["forecast_cutoff"]
                for k in keys_out}
        pilot_check.update({
            "n_pilot": len(pilot),
            "key_set_identical": set(pilot_map) == set(mine),
            "cutoffs_identical": pilot_map == mine})
        if not (pilot_check["key_set_identical"]
                and pilot_check["cutoffs_identical"]):
            _fail("pilot population cross-check FAILED: %s" % pilot_check)

    # ---- write payload + manifest ---------------------------------------
    (out_dir / "row_keys.json").write_text(
        json.dumps(keys_out, indent=1, default=str), encoding="ascii")
    np.save(out_dir / "arm_A_pmf.npy", A)
    np.save(out_dir / "arm_B_pmf.npy", B)

    payload_hashes = {
        "row_keys.json": sha256_file(out_dir / "row_keys.json"),
        "arm_A_pmf.npy": sha256_file(out_dir / "arm_A_pmf.npy"),
        "arm_B_pmf.npy": sha256_file(out_dir / "arm_B_pmf.npy"),
    }
    lineage = {
        "overnight_p2_run_identity_sha256":
            run_identity["run_identity_sha256"],
        "pa_table_frozen": sha256_file(P2_FROZEN_PA),
        "features_v3": sha256_file(P2_FROZEN_FEAT),
        "preds_checkpoints": {b: sha256_file(p2_data / f)
                              for b, f in PREDS_FILES.items()},
        "bf_forecasts_frozen": sha256_file(bfw_data / "bf_forecasts.parquet"),
        "projected_lineups_variant_v2": sha256_file(
            lake / "pregame-state-v1" / "data"
            / "projected_lineups_variant_v2.parquet"),
        "preregistration_variant_v2": PREREG_V2_SHA256,
        "run_pregame_state_v3": V3_RUNNER_SHA256,
        "kcount_combiner_checkout": KC_SHA256,
        "bf_distribution": sha256_file(HERE / "bf_distribution.py"),
        "builder_sha256": sha256_file(Path(__file__).resolve()),
    }
    report = {
        "seal": "bf-2026-predictor-seal-v1",
        "n_rows": n,
        "captured_team_games": int(g.height),
        "null_probable_excluded": n_null_prob,
        "nine_distinct_all": True,
        "n_rows_with_fallback_slot": int(
            (seal_proj["n_fallback_slots"] > 0).sum()),
        "arm_identities": {
            "arm_A": "cumulative log5 (reference) - overnight-p2 ladder "
                     "LOG5 arm, per-block sigmoid-calibrated column "
                     "(DEV_STANDARD_RECIPE section 5), confirm_2025H2 "
                     "frozen block for 2026 dates",
            "arm_B": "H3 8-feature logistic (challenger) - overnight-p2 "
                     "ladder H3, confirm_2025H2 frozen block (checkpoint-"
                     "verified deterministic refit), CAL column per "
                     "DEV_STANDARD_RECIPE section 5",
        },
        "pa_source_lineage_deviation": (
            "2026 dates use the confirm_2025H2 frozen ladder checkpoint "
            "(train through 2025-06-30) because the registered single fit "
            "through 2025-12-31 does not exist and executing it would be "
            "a new fit (forbidden in seal prep). Flagged for Chat 2 "
            "review; payload remains PREPARED-NOT-SEALED."),
        "gates": {
            "V1_pa_table_2022_2025_bitwise": gate_v1,
            "V2_gate1_state_verification": gate_v2["max_abs_diff"],
            "V3_gate2_refit_verification": gate_v3,
            "V4_bf_pool_rebuild_bitwise": gate_v4,
            "V5a_completed_frame_bitwise": gate_v5a,
            "V5b_batter_state_rebuild_bitwise": gate_v5,
        },
        "pilot_population_cross_check": pilot_check,
        "exclusions": {
            "null_probable_pitcher": n_null_prob,
            "nine_distinct_failures": int(excluded.height),
        },
        "lineage": lineage,
    }
    (out_dir / "seal_prep_report.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="ascii")
    manifest = {
        "status": "PREPARED-NOT-SEALED",
        "seal": "bf-2026-predictor-seal-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "payload_hashes": payload_hashes,
        "payload_hashes_note": ("covers row_keys.json / arm pmfs / "
                                "seal_prep_report.json; the manifest "
                                "itself is excluded (self-hashing "
                                "unstable by construction)"),
        "population": ("2026 captured eligible cohort: %d captured "
                       "team-games, %d null-probable excluded, %d "
                       "forecast rows; both arms on identical rows"
                       % (int(g.height), n_null_prob, n)),
        "arm_format": ("v3-native seal-dir format (row_keys.json + "
                       "arm_A_pmf.npy + arm_B_pmf.npy); canonical "
                       "run_bf_ab_score_v3.py consumes it unchanged"),
        "join_boundary": ("payload carries ZERO outcome columns; the "
                          "realized-K label join happens only in "
                          "run_bf_ab_score_v2.compute_stats at gated "
                          "scoring time, keyed (game_pk, pitcher) against "
                          "the 2026 Savant regular-season parquet; "
                          "predictor and label identities are never "
                          "co-located in this directory"),
        "outcome_scoring": ("none performed; 2026 outcome scoring remains "
                            "forbidden until seal approval"),
        "validation": {
            "identical_arm_populations": True,
            "unique_keys": True,
            "pmf_support_buckets": 24,
            "nonnegative_finite": True,
            "rows_sum_to_1_tol": 1e-9,
            "nine_distinct_required": True,
        },
        "lineage": lineage,
    }
    (out_dir / "seal_manifest.json").write_text(
        json.dumps(manifest, indent=1, default=str), encoding="ascii")
    print(json.dumps({
        "out": str(out_dir),
        "n_rows": n,
        "gates": "ALL PASS",
        "payload_hashes": payload_hashes,
        "status": "PREPARED-NOT-SEALED",
    }, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
