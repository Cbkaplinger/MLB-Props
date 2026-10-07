"""File-based integration test for the PA-K scored runner.

Synthetic frames flow through load_frames-style table building and the
full run_diagnostic (fits, gate, manifest, predictions.csv) into a tmp
directory. No real data, no network.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pa_k_baseline as pak  # noqa: E402
import run_pa_k_baseline_2023 as rpt  # noqa: E402


def synth_unified(rows):
    """Minimal unified-schema frame for audit_identity (both half-innings
    of inning 1 per game so first-pitcher identity is well-defined)."""
    return pl.DataFrame({
        "game_pk": [r[0] for r in rows],
        "pitcher": [r[1] for r in rows],
        "game_date": [r[2] for r in rows],
        "inning": [1] * len(rows),
        "inning_topbot": [r[5] for r in rows],
        "at_bat_number": [r[3] for r in rows],
        "pitch_number": [1] * len(rows),
        "home_team": ["A"] * len(rows),
        "away_team": ["B"] * len(rows),
        "p_throws": ["R"] * len(rows),
        "events": [r[4] for r in rows],
    })


def synth_raw(rows):
    return pl.DataFrame({
        "game_pk": [r[0] for r in rows],
        "game_date": [r[2] for r in rows],
        "pitcher": [r[1] for r in rows],
        "batter": [100 + i for i in range(len(rows))],
        "stand": ["L"] * len(rows),
        "p_throws": ["R"] * len(rows),
        "events": [r[4] for r in rows],
        "at_bat_number": [r[3] for r in rows],
    })


def test_run_diagnostic_end_to_end(tmp_path):
    d_train = date(2023, 4, 1)
    d_apr = date(2023, 4, 20)
    d_jul = date(2023, 7, 5)
    rows23 = []
    an = 0
    for i in range(30):  # 30 games x 2 first pitchers, pre-April-15
        g = 1 + i % 4
        an += 1
        pit_top = 10 if i % 2 == 0 else 11
        ev_top = "strikeout" if (pit_top == 10 and i % 3 != 0) else "single"
        rows23.append((g, pit_top, d_train, an, ev_top, "Top"))
        an += 1
        pit_bot = 11 if i % 2 == 0 else 10
        ev_bot = "strikeout" if (pit_bot == 10 and i % 3 != 0) else "single"
        rows23.append((g, pit_bot, d_train, an, ev_bot, "Bottom"))
    for i in range(10):  # April eval games
        g = 5 + i % 4
        an += 1
        pit_top = 10 if i % 2 == 0 else 11
        rows23.append((g, pit_top, d_apr, an,
                       "strikeout" if pit_top == 10 else "single", "Top"))
        an += 1
        pit_bot = 11 if i % 2 == 0 else 10
        rows23.append((g, pit_bot, d_apr, an,
                       "strikeout" if pit_bot == 10 else "single", "Bottom"))
    for i in range(10):  # July eval games (reversed skill on purpose)
        g = 9 + i % 4
        an += 1
        pit_top = 10 if i % 2 == 0 else 11
        rows23.append((g, pit_top, d_jul, an,
                       "strikeout" if pit_top == 11 else "single", "Top"))
        an += 1
        pit_bot = 11 if i % 2 == 0 else 10
        rows23.append((g, pit_bot, d_jul, an,
                       "strikeout" if pit_bot == 11 else "single", "Bottom"))
    for lbl, dd in (("aug", date(2023, 8, 10)), ("sep", date(2023, 9, 10))):
        for i in range(10):
            g = 20 + (i % 4) + (0 if lbl == "aug" else 4)
            an += 1
            pit_top = 10 if i % 2 == 0 else 11
            rows23.append((g, pit_top, dd, an,
                           "strikeout" if pit_top == 10 else "single", "Top"))
            an += 1
            pit_bot = 11 if i % 2 == 0 else 10
            rows23.append((g, pit_bot, dd, an,
                           "strikeout" if pit_bot == 10 else "single",
                           "Bottom"))
    rows22 = [(i // 2 + 1, 10 + (i % 6), date(2022, 6, 1), i + 1,
               "strikeout" if i % 4 == 0 else "single",
               "Top" if i % 2 == 0 else "Bottom") for i in range(80)]
    uni23 = synth_unified(rows23)
    uni22 = synth_unified(rows22)
    pa23, pa22 = rpt.load_frames(synth_raw(rows23), synth_raw(rows22),
                                 uni23, uni22)
    assert pa23.height > 0 and pa22.height > 0
    prereg = tmp_path / "prereg.md"
    prereg.write_text("frozen prereg stub", encoding="ascii")
    manifest = rpt.run_diagnostic(pa23, pa22, tmp_path, prereg)
    assert manifest["status"] == "COMPLETE"
    assert manifest["pooled"]["n"] == sum(
        o["n_eval"] for o in manifest["per_origin"])
    assert set(manifest["pooled"]["gate1"]) >= {
        "estimate", "lo95", "hi95", "pass"}
    preds = pl.read_csv(tmp_path / "predictions.csv")
    assert preds.height == manifest["pooled"]["n"]
    assert preds["p_A"].is_finite().all() and preds["p_B"].is_finite().all()
    manifest["inputs"] = {"x": {"sha256": "0" * 64}}
    (tmp_path / "pa_k_baseline_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="ascii")
