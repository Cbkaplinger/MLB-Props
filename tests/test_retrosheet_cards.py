"""Tests for the Retrosheet card source (I4): parser, mapping,
previous-game builder, and runner integration (synthetic event text).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import retrosheet_cards as rc  # noqa: E402
import run_i4_card_source_2023 as r4  # noqa: E402
from test_i3_runner import (  # noqa: E402
    build_kc_and_bf_artifacts, _setup)


def event_text():
    return "\n".join([
        "id,ANA202304070", "version,2",
        "info,visteam,TOR", "info,hometeam,ANA",
        "info,date,2023/04/07", "info,number,0",
        "info,gametype,regular", "info,usedh,true",
        "start,sprig001,\"George Springer\",0,1,9",
        "start,bichb001,\"Bo Bichette\",0,2,6",
        "start,guerv002,\"Vladimir Guerrero Jr.\",0,3,3",
        "start,mtomk001,\"Kevin Kiermaier\",0,4,8",
        "start,chadk001,\"Daulton Varsho\",0,5,7",
        "start,whitj002,\"Whit Merrifield\",0,6,4",
        "start,chapa001,\"Alejandro Kirk\",0,7,2",
        "start,chaqm001,\"Matt Chapman\",0,8,5",
        "start,bauma001,\"Brandon Belt\",0,9,3",
        "start,rengm001,\"Anthony Rendon\",1,2,5",
        "start,ohts001,\"Shohei Ohtani\",1,1,10",
        "start,troum001,\"Mike Trout\",1,3,8",
        "start,wardt001,\"Taylor Ward\",1,4,7",
        "start,rengz001,\"Zach Neto\",1,5,6",
        "start,drurs001,\"Brandon Drury\",1,6,4",
        "start,rencb001,\"Hunter Renfroe\",1,7,9",
        "start,urisg001,\"Gio Urshela\",1,8,3",
        "start,tholm001,\"Chad Wallach\",1,9,2",
        "sub,moorm003,\"Matt Moore\",1,0,1",
        "play,1,0,0,1,sprig001,32,CBBFX,HR",
    ])


def test_parser_slots_and_pitcher_exclusion(tmp_path):
    f = tmp_path / "2023ANA.EVA"
    f.write_text(event_text(), encoding="latin-1")
    df = rc.load_season(tmp_path)
    assert df.height == 1
    r = df.row(0, named=True)
    assert r["retro_id"] == "ANA202304070"
    assert r["game_number"] == 0
    assert r["gametype"] == "regular"
    assert len(r["away_card"]) == 9
    assert r["away_card"][0] == "sprig001"
    # sub record never enters the starting card; Ohtani (fielding 1)
    # would invalidate the home card if he were a batting slot
    assert r["home_card"][0] == "ohts001"  # DH in slot 1 is legal


def test_parser_pitcher_batting_slot_invalidates(tmp_path):
    txt = event_text().replace(
        "start,ohts001,\"Shohei Ohtani\",1,1,10",
        "start,ohtp001,\"Dummy Pitcher\",1,1,1")
    f = tmp_path / "2023ANA.EVA"
    f.write_text(txt, encoding="latin-1")
    df = rc.load_season(tmp_path)
    assert df["home_card"][0] is None  # pitcher batting -> ineligible


def test_previous_game_chronology_and_mapping(tmp_path):
    # two ANA games (Apr 5 -> Apr 7): the Apr 7 row's previous game is
    # the Apr 5 game; the first game has no prior
    two_games = event_text().replace(
        "id,ANA202304070", "id,ANA202304050").replace(
        "info,date,2023/04/07", "info,date,2023/04/05")
    f = tmp_path / "2023ANA.EVA"
    f.write_text(event_text() + "\n" + two_games, encoding="latin-1")
    df = rc.load_season(tmp_path)
    assert df.height == 2
    reg = tmp_path / "reg"
    reg.mkdir()
    ids = [r for r in df["home_card"][0]]
    pl.DataFrame({
        "key_retro": ids,
        "key_mlbam": [str(5000 + i) for i in range(len(ids))],
    }).write_csv(reg / "people-0.csv")
    mapping = rc.load_register(reg)
    assert mapping[ids[0]] == 5000
    cards = rc.previous_game_cards(df, mapping)
    apr7 = cards.filter((pl.col("team") == "ANA")
                        & (pl.col("date") == "2023-04-07"))
    assert apr7.height == 1
    r = apr7.row(0, named=True)
    assert r["prev_retro_id"] == "ANA202304050"
    assert len(r["rs_card"]) == 9
    assert all(v is not None for v in r["rs_card"])
    apr5 = cards.filter((pl.col("team") == "ANA")
                        & (pl.col("date") == "2023-04-05"))
    assert apr5["rs_card"][0] is None  # no prior game -> fallback


def test_schedule_match_rate(tmp_path):
    f = tmp_path / "2023ANA.EVA"
    f.write_text(event_text(), encoding="latin-1")
    df = rc.load_season(tmp_path)
    sched = pl.DataFrame({
        "home": ["LAA"], "d": ["2023-04-07"], "game_pk": [717563]})
    m = rc.schedule_match(df, sched)
    assert m["match_rate"] == 1.0 and m["threshold_match"]


def test_team_code_map_complete():
    statcast_teams = {"ATL", "AZ", "BAL", "BOS", "CHC", "CIN", "CLE",
                      "COL", "CWS", "DET", "HOU", "KC", "LAA", "LAD",
                      "MIA", "MIL", "MIN", "NYM", "NYY", "OAK", "PHI",
                      "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX",
                      "TOR", "WSH"}
    assert statcast_teams == set(rc.STATCAST_TO_RETRO)


def test_run_diagnostic_end_to_end(tmp_path):
    pa23, pa22, keys23, raw23, raw22 = _setup(tmp_path)
    kc_preds, kc_pmfs, bf_preds, bf_pmfs = \
        build_kc_and_bf_artifacts(pa23, tmp_path / "art", pa22, raw23)
    # synthetic retrosheet tree: one prior game per team before the
    # eval dates, with 9 mapped starters
    rs = tmp_path / "rs"
    (rs / "raw" / "2022").mkdir(parents=True)
    (rs / "raw" / "2023").mkdir(parents=True)

    def rs_game_lines(game_pk, date_str, num=0):
        lines = ["id,ANA%s%d" % (date_str.replace("-", ""), num),
                 "info,visteam,TOR", "info,hometeam,ANA",
                 "info,date,%s" % date_str.replace("-", "/"),
                 "info,number,%d" % num, "info,gametype,regular"]
        for s in range(1, 10):
            lines.append("start,rplayer%03d,\"P%d\",1,%d,%d"
                         % (s, s, s, 10 if s == 1 else 2))
        for s in range(1, 10):
            lines.append("start,aplayer%03d,\"Q%d\",0,%d,%d"
                         % (s, s, s, 10 if s == 1 else 2))
        return lines

    seen = set()
    all_lines = []
    for r in raw23.select("game_pk", "game_date").unique().iter_rows():
        gpk, dd = r
        key = str(dd)
        if key in seen:
            continue
        seen.add(key)
        all_lines.extend(rs_game_lines(gpk, key))
    (rs / "raw" / "2023" / "2023ANA.EVA").write_text(
        "\n".join(all_lines), encoding="latin-1")
    # a 2022 season file too: the runner loads both seasons (a prior
    # game may point into the prior season)
    (rs / "raw" / "2022" / "2022ANA.EVA").write_text(
        "\n".join(rs_game_lines(999, "2022-06-30")), encoding="latin-1")
    reg = rs / "register"
    reg.mkdir()
    rows = {"key_retro": (["rplayer%03d" % s for s in range(1, 10)]
                          + ["aplayer%03d" % s for s in range(1, 10)]),
            "key_mlbam": [str(1000 + s) for s in range(1, 10)]
            + [str(2000 + s) for s in range(1, 10)]}
    pl.DataFrame(rows).write_csv(reg / "people-0.csv")
    out = tmp_path / "out"
    contract = tmp_path / "contract.md"
    contract.write_text("frozen i4 contract " + "c" * 64,
                        encoding="ascii")
    manifest = r4.run_diagnostic(
        pa23, pa22, keys23, raw23,
        kc_preds, kc_pmfs, tmp_path / "art" / "kc_pmfs.parquet",
        bf_preds, bf_pmfs, rs / "raw", reg, out, contract)
    assert manifest["status"] == "COMPLETE"
    p = manifest["pooled"]
    assert set(p["gate1"]) >= {"estimate", "lo95", "hi95", "pass"}
    assert p["n"] == sum(o["n_eval"] for o in manifest["per_origin"])
    assert p["source"]["schedule_match"]["threshold_match"]
    preds = pl.read_csv(out / "predictions.csv")
    assert preds["rs_card_flag"].null_count() == 0
    pmfs = pl.read_parquet(out / "pmfs.parquet")
    for a in ("I3b", "I4"):
        cols = [c for c in pmfs.columns if c.startswith("pk%s_" % a)]
        assert np.allclose(
            pmfs.select(cols).to_numpy().sum(axis=1), 1.0, atol=1e-9)
    for name, val in manifest["provenance"].items():
        assert len(val) == 64 and all(
            c in "0123456789abcdef" for c in val), name
