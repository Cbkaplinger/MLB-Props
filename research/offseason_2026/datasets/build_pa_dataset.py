"""PA dataset builder (authorized: specify + build hashed board-time-safe PA
dataset; STOP BEFORE TRAINING).

Reads lake + L1/L2 (frozen); writes ONLY to research/offseason_2026/datasets/.
Seasons 2023-2024 (development). Features are pre-PA by construction (L2
shift(1) + same-date collapse); lineup inputs are realized initial-lineup
rows labeled mode=3 (oracle, non-actionable).
"""

import hashlib
import json
import sys
from pathlib import Path

import polars as pl

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))
from boundary import assert_workspace_path  # noqa: E402

REPO = WS.parents[1]
NON_PA = {"caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
          "pickoff_1b", "pickoff_2b", "pickoff_3b", "pickoff_caught_stealing_2b",
          "pickoff_caught_stealing_3b", "pickoff_caught_stealing_home",
          "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
          "wild_pitch", "passed_ball", "other_out"}
K_EVENTS = {"strikeout", "strikeout_double_play"}
P_FEATS = ["k_rate_P5", "k_rate_P10", "k_rate_P20", "k_rate_std",
           "whiff_rate_P5", "swstr_rate_P5", "chase_rate_P5",
           "bb_rate_P5", "zone_rate_P5", "contact_rate_P5"]
B_FEATS = ["k_rate_std", "k_rate_std_vL", "k_rate_std_vR", "k_rate_std_shrunk",
           "whiff_rate_std", "swstr_rate_std", "chase_rate_std"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def build_year(year: int, excl: dict, inputs: list) -> pl.DataFrame:
    sav = REPO / f"data/Savant-Data/regular/{year}/statcast_{year}_regular.parquet"
    inputs.append({"path": str(sav.relative_to(REPO)), "sha256": sha(sav)})
    t = pl.scan_parquet(sav).select(
        "game_pk", "at_bat_number", "pitch_number", "events", "pitcher",
        "batter", "stand", "p_throws", "game_date").collect()
    n0 = t.select("game_pk", "at_bat_number").unique().height
    term = (t.filter(pl.col("events").is_not_null() & ~pl.col("events").is_in(NON_PA))
            .sort(["game_pk", "at_bat_number", "pitch_number"])
            .unique(["game_pk", "at_bat_number"], keep="last", maintain_order=True))
    excl[f"{year}_no_terminal"] = n0 - term.select("game_pk", "at_bat_number").unique().height
    excl[f"{year}_truncated_or_error_as_pa"] = term.filter(
        pl.col("events").is_in(["truncated_pa", "field_error"])).height
    term = term.with_columns(pl.col("events").is_in(K_EVENTS).alias("is_k"))
    pg = pl.scan_parquet(REPO / "data/processed/pitcher_games.parquet").filter(
        pl.col("season") == year).select("game_pk", "pitcher").collect()
    st = term.join(pg.select("game_pk", "pitcher").unique(), on=["game_pk", "pitcher"], how="semi")
    excl[f"{year}_non_starter_or_short"] = (
        term.height - st.height)  # bullpen (~42%) + sub-9 openers, by design
    pr = pl.scan_parquet(REPO / "data/processed/pitcher_rolling.parquet").filter(
        pl.col("season") == year).collect()
    missing_p = [c for c in P_FEATS if c not in pr.columns]
    assert not missing_p, f"pitcher rolling missing {missing_p}"
    st = st.join(pr.select(["game_pk", "pitcher"] + P_FEATS),
                 on=["game_pk", "pitcher"], how="left")
    br = pl.scan_parquet(REPO / "data/processed/batter_rolling.parquet").filter(
        pl.col("season") == year).collect()
    missing_b = [c for c in B_FEATS if c not in br.columns]
    assert not missing_b, f"batter rolling missing {missing_b}"
    st = st.join(br.select(
        ["game_pk", "batter"] + [pl.col(c).alias(f"b_{c}") for c in B_FEATS]),
        on=["game_pk", "batter"], how="left")
    bg = pl.scan_parquet(REPO / "data/processed/batter_games.parquet").filter(
        pl.col("game_date").cast(pl.String).str.slice(0, 4) == str(year)).select(
        "game_pk", "batter", "lineup_slot", "is_initial_lineup",
        "prior_league_k_rate").collect()
    st = st.join(bg, on=["game_pk", "batter"], how="left")
    lg = bg.select("prior_league_k_rate").drop_nulls().unique()
    assert lg.height == 1, "league scalar must be single-valued"
    st = st.with_columns(pl.lit(float(lg.item())).alias("league_k_prior"),
                         pl.lit(3).alias("lineup_mode"),
                         pl.lit(year).alias("season"))
    return st.select(["game_pk", "at_bat_number", "season", "game_date", "pitcher",
                      "batter", "stand", "p_throws", "is_k", "league_k_prior",
                      "lineup_slot", "is_initial_lineup", "lineup_mode"]
                     + P_FEATS + [f"b_{c}" for c in B_FEATS])


def main() -> None:
    excl, inputs = {}, []
    for f in ["data/processed/pitcher_games.parquet",
              "data/processed/pitcher_rolling.parquet",
              "data/processed/batter_rolling.parquet",
              "data/processed/batter_games.parquet"]:
        p = REPO / f
        inputs.append({"path": f, "sha256": sha(p)})
    frames = [build_year(y, excl, inputs) for y in (2023, 2024)]
    pa = pl.concat(frames).sort(["game_pk", "at_bat_number"])
    avail = {c: float(pa.select(pl.col(c).is_not_null().mean()).item())
             for c in P_FEATS + [f"b_{c}" for c in B_FEATS] + ["lineup_slot"]}
    dest = assert_workspace_path(REPO / "research/offseason_2026/datasets/pa_table_2023_2024.parquet")
    pa.write_parquet(dest)
    man = {
        "built": "2026-09-28", "seasons": [2023, 2024], "rows": pa.height,
        "k_rate": float(pa.select(pl.col("is_k").mean()).item()),
        "inputs": inputs, "exclusions": excl,
        "feature_availability": avail,
        "lineup_mode": "3 (oracle realized initial-lineup; non-actionable)",
        "output_sha256": sha(dest),
        "note": "No model trained. Rookie rows kept with nulls (fallback at train time).",
    }
    with open(assert_workspace_path(
            REPO / "research/offseason_2026/datasets/pa_dataset_manifest.json"),
            "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2)
    print(json.dumps({"rows": pa.height, "k_rate": man["k_rate"],
                      "exclusions": excl,
                      "worst_availability": sorted(avail.items(), key=lambda kv: kv[1])[:5],
                      "sha": man["output_sha256"][:16]}, indent=1))


if __name__ == "__main__":
    main()
