"""Shared synthetic fixtures for the board-coverage probe tests."""
from __future__ import annotations

import json

import polars as pl


def _rows(spec: list[tuple[str, str]]) -> list[dict]:
    clocks = probe.CLOCKS
    out = []
    for gd, eid in spec:
        for clock in clocks:
            for side, price in (("over", -110), ("under", 110)):
                out.append({
                    "event_id": eid, "snapshot": clock,
                    "snapshot_ts": f"{gd}T15:00:00Z", "game_date": gd,
                    "season_type": "regular", "book": "draftkings",
                    "market": "pitcher_strikeouts", "player": "P A",
                    "player_norm": "a p", "line": 4.5, "side": side,
                    "price": price,
                })
    return out


def _setup(tmp, spec, *, name, row_group_size=6, write_statistics=True,
           out_name="board_coverage_2025H1.json"):
    probe.__dict__["BOOK_LINES"] = _write_book_lines(spec, tmp, name,
                                                     row_group_size,
                                                     write_statistics)
    probe.__dict__["ENVELOPE"] = _write_envelope(spec, tmp)
    probe.__dict__["OUT"] = tmp / "_probe" / out_name


def _write_book_lines(spec, tmp, name, row_group_size=6,
                      write_statistics=True):
    import pyarrow as pa
    import pyarrow.parquet as pq
    path = tmp / name
    pq.write_table(pa.Table.from_pylist(_rows(spec)), path,
                   row_group_size=row_group_size,
                   write_statistics=write_statistics)
    return path


def _write_envelope(spec, tmp, name="snapshot_envelope.parquet"):
    path = tmp / name
    pl.DataFrame(_envelope_rows(spec), schema={
        "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "vendor_timestamp": pl.Utf8, "reconstructed_ts": pl.Utf8,
        "commence_time": pl.Utf8,
        "lag_vendor_vs_commence_sec": pl.Int64},
        orient="row").write_parquet(path)
    return path


def _envelope_rows(spec):
    rows = []
    for gd, eid in spec:
        for clock in probe.CLOCKS:
            rows.append({"event_id": eid, "snapshot": clock,
                         "vendor_timestamp": f"{gd}T14:55:00Z",
                         "reconstructed_ts": f"{gd}T15:00:00Z",
                         "commence_time": f"{gd}T19:00:00Z",
                         "lag_vendor_vs_commence_sec": -300})
    return rows
