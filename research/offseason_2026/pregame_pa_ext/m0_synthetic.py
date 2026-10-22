"""M0 synthetic-input factory (support module beside the research
runner).

IMPORTABLE SUPPORT MODULE — not a test module. Both the test suite
(tests/test_m0_multiclass.py) and the runner's preflight command
(m0_multiclass.py --verify-receipt-check) consume this factory, so the
documented preflight command runs in a fresh subprocess without pytest
import state.

Fully synthetic: no private lake, no raw Statcast directory, no real
paths are read. The frame identities recorded in the receipt are
deterministic content hashes of these synthetic frames.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl

EVENT_BY_SLOT = {0: "strikeout", 1: "walk", 2: "field_out", 3: "single"}


def synthetic_m0_inputs():
    """Synthetic pa_table (+ events), preserved-ledger stand-in, BF PMF
    artifact, and the derived event-label frame - sized for the gated
    runner end-to-end. Deterministic (seeded); touches no private
    data."""
    rng = np.random.default_rng(5)
    # -- training-era PA rows: 2023 season + 2024 pre-break, every class
    pa_rows = []
    events = []
    pid_train, bat_base = 900001, 700001
    d = date(2023, 4, 1)
    pa_id = 1
    for day in range(300):
        gd = d + timedelta(days=day // 3)
        for _ in range(6):
            cls = int(rng.integers(0, 4))
            ev = EVENT_BY_SLOT[cls]
            pa_rows.append((pa_id, pa_id * 10 + 1, bat_base + (pa_id % 12),
                            pid_train, gd, int(cls == 0)))
            events.append((pa_id, pa_id * 10 + 1, bat_base + (pa_id % 12),
                           ev))
            pa_id += 1
        d = d + timedelta(days=1) if day % 3 == 2 else d
    # -- evaluation-era games (block_2024H2): projected starts
    start_rows = []
    led_rows = []
    eval_day = date(2024, 7, 10)
    gid = 746000
    pitcher = 800001
    for g in range(6):
        gd = eval_day + timedelta(days=g)
        for side in ("Top", "Bot"):
            gid += 1
            for slot in range(1, 10):
                batter = 700100 + (gid % 40) * 9 + slot
                cls = int(rng.integers(0, 4))
                ev = EVENT_BY_SLOT[cls]
                n_pa = 1 + (slot % 2)
                for k in range(n_pa):
                    ab = 10 * slot + k
                    pa_rows.append((gid, ab, batter, pitcher, gd,
                                    int(cls == 0)))
                    events.append((gid, ab, batter, ev))
                led_rows.append((gid, side, pitcher, batter, slot, gd,
                                 None, 0.22 + 0.01 * slot,
                                 0.30 - 0.01 * slot, 0.21,
                                 40 + slot, 150 - slot, 0, 0.25, 0.28,
                                 0))
                start_rows.append((gid, side, pitcher, gd))
    pa = pl.DataFrame(
        pa_rows,
        schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                "batter": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8}, orient="row")
    ev_df = pl.DataFrame(
        events, schema=["game_pk", "at_bat_number", "batter", "events"],
        orient="row")
    pa = pa.join(ev_df, on=["game_pk", "at_bat_number", "batter"],
                 how="left")
    ledger = pl.DataFrame(
        led_rows,
        schema={"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
                "batter": pl.Int64, "slot": pl.Int8, "game_date": pl.Date,
                "exclusion_reason": pl.Utf8, "p_h3_raw": pl.Float64,
                "p_pitcher_prior_w150": pl.Float64,
                "p_batter_prior_w150": pl.Float64, "lg_rate": pl.Float64,
                "n_prior_pitcher": pl.Int64, "n_prior_batter": pl.Int64,
                "cold_start": pl.Int8, "ew_pitcher": pl.Float64,
                "ew_batter": pl.Float64}, orient="row")
    bf = pl.DataFrame([{"game_pk": s[0], "side": s[1],
                        "pitcher": s[2],
                        **{f"pmf37_{j}": 1.0 / 37 for j in range(37)}}
                       for s in start_rows])
    labels, _ = __import__(
        "pregame_pa_ext.m0_multiclass", fromlist=["x"]
    ).event_label_frame(pa)
    return pa, ledger, labels, bf
