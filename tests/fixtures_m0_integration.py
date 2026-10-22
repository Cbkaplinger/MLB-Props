"""Fixture module for M0 integration tests. Creates a self-contained
synthetic lake with DETERMINISTIC four-class coverage in every
development block. No real data, no shared state with other test
modules, no fallback to local real-data directories.

Path claims: tests/fixtures_m0_integration.py and
tests/test_m0_integration.py are owned by Chat 1 (builder).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

# deterministic class cycle: 4 classes cycling across PAs
CLASS_CYCLE = [0, 1, 2, 3] * 5  # 20 PAs per game covers all 4 classes
BATTERS = list(range(100, 109))
PITCHER = 500

CLASS_TO_EVENT = {
    0: "strikeout", 1: "walk", 2: "field_out", 3: "single",
}


def _event_for_class(cls: int) -> str:
    return CLASS_TO_EVENT[cls]


def _class_for_pa(pa_index: int) -> int:
    return CLASS_CYCLE[pa_index % len(CLASS_CYCLE)]


def _dev_blocks(n_games: int):
    """Generate n_games dates spanning BOTH dev blocks (45-day spacing
    covers 2024-07-01..2025-06-30 with 8 games)."""
    dates = []
    d = date(2024, 7, 1)
    for _ in range(n_games):
        block = "block_2024H2" if d <= date(2024, 12, 31) else "block_2025H1"
        dates.append((d, block))
        d += timedelta(days=45)
    return dates


def build_integration_lake(
    tmp_path: Path,
    *,
    include_confirm: bool = True,
    include_2022: bool = True,
    confirm_outcome_flip: bool = False,
) -> dict:
    """Build a self-contained synthetic lake with deterministic four-class
    coverage. Returns dict with pa_with_events, ledger, bf, realized,
    paths, grid, class_counts_by_block."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = []
    led = []
    gpk = 900
    ab = 0

    # 2022 feature-history rows (before the training window)
    if include_2022:
        d22 = date(2022, 4, 10)
        for i in range(6):
            cls = _class_for_pa(i)
            rows.append(one(BATTERS[i % 9], d22 + timedelta(days=i),
                            1 if cls == 0 else 0,
                            events=_event_for_class(cls)))

    # 2023 training warm-up rows
    d = date(2023, 1, 5)
    for i in range(12):
        for slot in range(9):
            for k in range(2):
                ab += 1
                cls = _class_for_pa(slot * 2 + k)
                rows.append(one(BATTERS[slot], d,
                                1 if cls == 0 else 0,
                                game_pk=gpk, ab=ab,
                                events=_event_for_class(cls)))
        gpk += 1
        d += timedelta(days=15)

    # dev-block games
    dev_blocks = _dev_blocks(8)
    grid = []
    class_counts = {"block_2024H2": {c: 0 for c in range(4)},
                    "block_2025H1": {c: 0 for c in range(4)}}
    for game_date, block in dev_blocks:
        grid.append((gpk, game_date))
        for slot in range(9):
            b = BATTERS[slot]
            for k in range(2):
                ab += 1
                cls = _class_for_pa(slot * 2 + k)
                rows.append(one(b, game_date, 1 if cls == 0 else 0,
                                game_pk=gpk, ab=ab,
                                events=_event_for_class(cls)))
                class_counts[block][cls] += 1
        for slot in range(9):
            led.append({"game_pk": gpk, "side": "Bot", "pitcher": PITCHER,
                        "batter": BATTERS[slot], "slot": slot + 1,
                        "game_date": game_date,
                        "p_h3_raw": 0.2 + 0.05 * slot,
                        "exclusion_reason": None})
        gpk += 1

    # confirm-block game (after 2025-06-30)
    if include_confirm:
        d_conf = date(2025, 7, 15)
        y_flip_base = 1 if confirm_outcome_flip else 0
        for slot in range(9):
            b = BATTERS[slot]
            for k in range(2):
                ab += 1
                cls = _class_for_pa(slot * 2 + k)
                y_val = y_flip_base if cls == 0 else (0 if confirm_outcome_flip else int(cls > 0))
                rows.append(one(b, d_conf, y_val, game_pk=gpk, ab=ab,
                                events=_event_for_class(cls)))
        led.append({"game_pk": gpk, "side": "Bot", "pitcher": PITCHER,
                    "batter": 100, "slot": 1, "game_date": d_conf,
                    "p_h3_raw": 0.4, "exclusion_reason": None})
        gpk += 1

    pa_raw = pl.DataFrame(rows).with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("y").cast(pl.Int8),
    )
    ledger = pl.DataFrame(led, schema_overrides={
        "exclusion_reason": pl.Utf8, "p_h3_raw": pl.Float64,
    }).with_columns(pl.col("game_date").cast(pl.Date))

    # map to multi-class labels
    pa_with_events = m0.build_multiclass_labels(pa_raw)

    # compute features using the frozen recipe's machinery
    # (same as build_checkpoint.build_feature_frame)
    p_daily = ad.entity_daily_state(pa_with_events, "pitcher")
    b_daily = ad.entity_daily_state(pa_with_events, "batter")
    lg = ad.league_daily_state(pa_with_events)
    realized_identity = pa_with_events.select(
        "game_pk", "at_bat_number", "batter", "pitcher",
        "game_date").sort("game_date")
    feat = ad.attach_prior_features(realized_identity, p_daily, b_daily, lg)
    feat = feat.filter(pl.col("lg_rate").is_finite())
    # join back the class_label
    feat = feat.join(
        pa_with_events.select("game_pk", "at_bat_number", "batter",
                              "class_label", "events", "side", "y"),
        on=["game_pk", "at_bat_number", "batter"], how="inner")
    pa_with_events = feat

    # BF artifact
    bf_rows = []
    seen = set()
    for r in led:
        key = (r["game_pk"], r["side"], r["pitcher"])
        if key in seen:
            continue
        seen.add(key)
        pmf37 = np.full(37, 0.5 / 36.0)
        pmf37[0] = 0.5
        pmf37 /= pmf37.sum()
        bf_rows.append({"game_pk": r["game_pk"], "side": r["side"],
                        "pitcher": r["pitcher"],
                        **{f"pmf37_{j}": float(v)
                           for j, v in enumerate(pmf37)}})
    bf = pl.DataFrame(bf_rows)

    # realized counts
    realized = (pa_with_events.group_by("game_pk", "side", "pitcher")
                .agg(realized_k=pl.col("y").sum().cast(pl.Int64)))

    # artifact files
    pat = tmp_path / "pa_table.parquet"
    pa_with_events.write_parquet(pat)
    led_path = tmp_path / "projected_pa_probs_v1.parquet"
    ledger.write_parquet(led_path)
    bf_path = tmp_path / "bf_forecasts.parquet"
    bf.write_parquet(bf_path)
    realized_path = tmp_path / "start_metrics_v2.parquet"
    realized.write_parquet(realized_path)
    ck = tmp_path / "h3_raw_checkpoint.json"
    ck.write_text(json.dumps({"format": "synthetic", "sha256": "c" * 64,
                              "payload": {}}), encoding="utf-8")
    lu = tmp_path / "projected_lineups_variant_v2.parquet"
    pa_with_events.head(1).write_parquet(lu)
    fr = tmp_path / "freeze_pregame_pa_ext_v2.json"
    fr.write_text(json.dumps({"freeze_id": "synthetic"}), encoding="utf-8")

    return {
        "pa_with_events": pa_with_events,
        "ledger": ledger,
        "bf": bf,
        "realized": realized,
        "paths": {
            "pa_table": str(pat),
            "preserved_run_ledger": str(led_path),
            "bf_pmf": str(bf_path),
            "realized_counts_source": str(realized_path),
            "checkpoint": str(ck),
            "lineups": str(lu),
            "freeze_config": str(fr),
        },
        "grid": grid,
        "class_counts_by_block": class_counts,
    }


def one(batter, d, y, pitcher=500, game_pk=1, ab=0, events=None,
        side="Bot"):
    row = {"game_pk": game_pk, "at_bat_number": ab, "batter": batter,
           "pitcher": pitcher, "game_date": d, "y": y, "side": side}
    if events is not None:
        row["events"] = events
    return row
