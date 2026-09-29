"""Read-only PA funnel builder (Phase 4, Step 3).

Reads lake inputs; writes ONLY to research/offseason_2026/datasets/.
Reconciles against Phase-3 measured counts (audit §AA).
Run: python research/offseason_2026/datasets/build_funnel.py  (from repo root)
"""

import glob
import hashlib
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from boundary import assert_workspace_path

REPO = Path(__file__).resolve().parents[3]

# From src/Python/statcast.py:26-45 (spec duplication documented in specs/).
NON_PA_EVENTS = {
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b", "pickoff_caught_stealing_2b",
    "pickoff_caught_stealing_3b", "pickoff_caught_stealing_home",
    "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "wild_pitch", "passed_ball", "other_out",
}
STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
# Phase-3 observed eligible batting outcomes (audit §AA).
KNOWN_BATTING_EVENTS = {
    "field_out", "strikeout", "single", "walk", "double", "home_run",
    "force_out", "grounded_into_double_play", "hit_by_pitch", "sac_fly",
    "field_error", "triple", "intent_walk", "sac_bunt", "double_play",
    "fielders_choice", "fielders_choice_out", "truncated_pa",
    "strikeout_double_play", "catcher_interf", "sac_fly_double_play",
    "triple_play",
}

EXPECTED = {  # Phase-3 §AA, updated 2026-09-28 after full-season refresh.
    2023: (105385, 0), 2024: (106267, 0), 2025: (106123, 76151), 2026: (103031, 42548),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalpha() or c == " ")


def funnel_year(year: int, out: dict, inputs: list) -> None:
    sav = REPO / f"data/Savant-Data/regular/{year}/statcast_{year}_regular.parquet"
    inputs.append({"path": str(sav.relative_to(REPO)), "bytes": sav.stat().st_size,
                   "sha256": sha256(sav)})
    base = (
        pl.scan_parquet(sav)
        .select("game_pk", "at_bat_number", "pitch_number", "events", "pitcher",
                "batter", "stand", "p_throws", "zone", "game_type", "description")
    )
    m = {}
    m["pitch_rows"] = base.select(pl.len()).collect().item()
    m["distinct_pa"] = base.select("game_pk", "at_bat_number").unique().select(
        pl.len()).collect().item()
    term = base.filter(pl.col("events").is_not_null() & ~pl.col("events").is_in(NON_PA_EVENTS))
    m["terminal_rows"] = term.select(pl.len()).collect().item()
    m["terminal_pa"] = term.select("game_pk", "at_bat_number").unique().select(
        pl.len()).collect().item()
    m["multi_terminal"] = m["terminal_rows"] - m["terminal_pa"]
    m["no_terminal_pa"] = m["distinct_pa"] - m["terminal_pa"]
    ev = term.group_by("events").len().sort("len", descending=True).collect()
    m["event_counts"] = {r["events"]: r["len"] for r in ev.to_dicts()}
    m["non_pa_hits"] = int(sum(v for k, v in m["event_counts"].items() if k in NON_PA_EVENTS))
    m["unknown_events"] = {k: v for k, v in m["event_counts"].items()
                           if k not in KNOWN_BATTING_EVENTS}
    m["k_events"] = int(sum(v for k, v in m["event_counts"].items() if k in STRIKEOUT_EVENTS))
    subs = base.group_by(["game_pk", "at_bat_number"]).agg(
        pl.col("pitcher").n_unique().alias("np"),
        pl.col("batter").n_unique().alias("nb")).collect()
    m["mid_pa_pitcher_sub"] = subs.filter(pl.col("np") > 1).height
    m["mid_pa_batter_sub"] = subs.filter(pl.col("nb") > 1).height
    dup = base.group_by(["game_pk", "at_bat_number", "pitch_number"]).len().filter(
        pl.col("len") > 1).select(pl.len()).collect().item()
    m["dup_pitch_rows"] = dup
    m["zone10_pitches"] = base.filter(pl.col("zone") == 10).select(pl.len()).collect().item()
    nulls = base.select(
        pl.col("pitcher").is_null().sum().alias("pitcher"),
        pl.col("batter").is_null().sum().alias("batter"),
        pl.col("stand").is_null().sum().alias("stand"),
        pl.col("p_throws").is_null().sum().alias("p_throws")).collect().to_dicts()[0]
    m["null_ids"] = nulls
    m["game_types"] = base.group_by("game_type").len().collect().to_dicts()

    # Terminal-PA frame (small: ~184k rows).
    tpa = term.sort(["game_pk", "at_bat_number", "pitch_number"]).unique(
        ["game_pk", "at_bat_number"], keep="last", maintain_order=True).collect()
    tpa = tpa.with_columns(pl.col("events").is_in(STRIKEOUT_EVENTS).alias("is_k"))

    pg = pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").filter(
        pl.col("season") == year).select("game_pk", "pitcher", "game_date", "PA").collect()
    m["kept_starts"] = pg.height
    kept = tpa.join(pg.select("game_pk", "pitcher"), on=["game_pk", "pitcher"], how="inner")
    m["training_pa"] = kept.height
    grp = tpa.group_by(["game_pk", "pitcher"]).len()
    m["short_groups_lt9"] = grp.filter(pl.col("len") < 9).height
    m["short_groups_vol"] = grp.filter(pl.col("len") < 9).select(pl.col("len").sum()).item() or 0

    pr = pl.scan_parquet(REPO / "data/processed/pitcher_rolling.parquet").filter(
        pl.col("season") == year).select(
        pl.col("k_rate_P5").is_null().sum().alias("p5_null"), pl.len().alias("n")).collect().to_dicts()[0]
    m["pitcher_history_null"] = {"n": pr["n"], "k_rate_P5_null": pr["p5_null"]}
    br = pl.scan_parquet(REPO / "data/processed/batter_rolling.parquet").filter(
        pl.col("season") == year).select(
        pl.col("k_rate_std").is_null().sum().alias("std_null"), pl.len().alias("n")).collect().to_dicts()[0]
    m["batter_history_null"] = {"n": br["n"], "k_rate_std_null": br["std_null"]}
    slots = pl.scan_parquet(REPO / "data/processed/batter_rolling.parquet").filter(
        (pl.col("season") == year) & pl.col("is_initial_lineup")).group_by(
        ["game_pk", "bat_team"]).len()
    bad = slots.filter(pl.col("len") != 9).select(pl.len()).collect().item()
    m["oracle_nine_valid"] = {"team_games": slots.select(pl.len()).collect().item(),
                              "bad_team_games": bad}
    out[str(year)] = m


def main() -> None:
    manifest = {"built_utc": date.today().isoformat(), "years": {}, "inputs": [],
                "lineups": {}, "odds": {}, "deferred": {}, "reconciliation": {}}
    for year in (2023, 2024, 2025, 2026):
        funnel_year(year, manifest["years"], manifest["inputs"])

    for f in ["data/processed/pitcher_games.parquet",
              "data/processed/pitcher_rolling.parquet",
              "data/processed/batter_rolling.parquet"]:
        p = REPO / f
        manifest["inputs"].append({"path": f, "bytes": p.stat().st_size, "sha256": sha256(p)})

    snaps = sorted(glob.glob(str(REPO / "data/processed/daily_lineups_*.parquet")))
    manifest["lineups"] = {"snapshot_files": [Path(s).name for s in snaps]}
    null_ids = 0
    n_rows = 0
    for s in snaps:
        df = pl.scan_parquet(s).select("batter", "batting_order", "game_pk").collect()
        n_rows += df.height
        null_ids += df.filter(pl.col("batter").is_null()).height
    manifest["lineups"]["rows"] = n_rows
    manifest["lineups"]["null_batter_rate_retained"] = null_ids / n_rows if n_rows else None
    manifest["lineups"]["note"] = ("0% on retained rows; upstream bad-game drops are "
                                   "WARNING-only with no ID ledger (rate unmeasurable from parquets).")

    csv = REPO / "data/Odds-Open-Close-2025-2026/pitcher_strikeouts_early_open_2025_2026.csv"
    if not csv.exists():
        # Retired 2026-09-28 (choice log): friend-only rows preserved in
        # workspace artifacts; early-open join skipped, board clock is canonical.
        manifest["inputs"].append({"path": str(csv.relative_to(REPO)), "status": "RETIRED"})
        manifest["odds"] = {"note": "early-open join retired with friend CSVs; see odds_clocks_canonical"}
    else:
        manifest["inputs"].append({"path": str(csv.relative_to(REPO)), "bytes": csv.stat().st_size,
                                   "sha256": sha256(csv)})
        opens = pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").select(
            "game_pk", "pitcher", "game_date", "season").collect()
        early = (pl.read_csv(csv, columns=["game_date", "pitcher_id"])
                 .with_columns(pl.col("game_date").str.to_date(),
                               pl.col("pitcher_id").cast(pl.Int64))
                 .unique(["game_date", "pitcher_id"]))
        for year in (2025, 2026):
            sub = opens.filter(pl.col("season") == year)
            hit = sub.join(early, left_on=["game_date", "pitcher"],
                           right_on=["game_date", "pitcher_id"], how="semi")
            tpa_vol = manifest["years"][str(year)]["training_pa"]
            manifest["odds"][str(year)] = {
                "starts_covered": hit.height, "starts_total": sub.height,
                "note": "early-open join only; full odds-evaluable vol needs book_lines panels",
            }

    ledger = REPO / "artifacts/odds_log/ledger.parquet"
    manifest["deferred"]["void_season_rate"] = (
        "UNMEASURABLE: live ledger lives in cloud volume; repo holds no season ledger.")
    manifest["deferred"]["unresolved_id_rate"] = manifest["lineups"]["null_batter_rate_retained"]

    raw_root = REPO / "data/Odds-Historical/theoddsapi/raw/snapshots"
    if raw_root.is_dir():
        files = sorted(raw_root.rglob("*.json"))
        y25 = [f for f in files if "2025" in f.name][:3]
        y26 = [f for f in files if "2026" in f.name][:3]
        import json as js
        audit = {}
        for tag, sample in (("2025", y25), ("2026", y26)):
            keys = []
            for f in sample:
                try:
                    d = js.loads(f.read_text(encoding="utf-8")[:2000000])
                    node = d if isinstance(d, dict) else (d[0] if d else {})
                    keys.append(sorted(node.keys())[:20])
                except Exception as e:  # noqa: BLE001 - audit must not fail the build
                    keys.append([f"READ_ERROR:{type(e).__name__}"])
            audit[tag] = {"n_files_total": len(files), "sample": [f.name for f in sample],
                          "top_keys": keys}
        manifest["deferred"]["raw_json_2025_vs_2026"] = audit
    else:
        manifest["deferred"]["raw_json_2025_vs_2026"] = "ABSENT: raw snapshots dir not on disk."

    manifest["deferred"]["envelope_gap"] = "OPEN: snapshot envelopes stop 09-10; closes 09-11…26 unjudgeable until backfill."

    for year, (exp_train, exp_odds) in EXPECTED.items():
        got = manifest["years"][str(year)]["training_pa"]
        manifest["reconciliation"][str(year)] = {
            "expected_training_pa": exp_train, "measured_training_pa": got,
            "match": got == exp_train, "expected_odds_note": exp_odds,
        }

    dest = assert_workspace_path(REPO / "research/offseason_2026/datasets/pa_funnel_manifest.json")
    dest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"dest": str(dest), "reconciliation": manifest["reconciliation"]}, indent=2))


if __name__ == "__main__":
    main()
