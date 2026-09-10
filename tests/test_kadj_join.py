"""Tests for the L3 kAdj join (leakage, gates, hand-computed value)."""

from __future__ import annotations

import polars as pl

from Python.pipeline.training import _join_kadj_features, _null_kadj_frame


def _synthetic() -> tuple[pl.DataFrame, pl.DataFrame, int]:
    rows = []
    gp = 100
    # Pitcher 1: 6 prior starts (D1-D6) + target start S7 (D7) + same-date dup.
    for day in range(1, 8):
        gp += 1
        date = f"2024-04-{day:02d}"
        rows.append({"game_pk": gp, "pitcher": 1, "game_date": date,
                     "pitch_type": "ff", "Pitches": 30, "CSW": 12})
        rows.append({"game_pk": gp, "pitcher": 1, "game_date": date,
                     "pitch_type": "sl", "Pitches": 30, "CSW": 6})
    gp += 1
    rows.append({"game_pk": gp, "pitcher": 1, "game_date": "2024-04-07",
                 "pitch_type": "ff", "Pitches": 30, "CSW": 0})
    rows.append({"game_pk": gp, "pitcher": 1, "game_date": "2024-04-07",
                 "pitch_type": "sl", "Pitches": 30, "CSW": 0})
    # Pitcher 2: league ballast (moves the prior).
    for day in range(1, 7):
        gp += 1
        date = f"2024-04-{day:02d}"
        rows.append({"game_pk": gp, "pitcher": 2, "game_date": date,
                     "pitch_type": "ff", "Pitches": 30, "CSW": 6})
        rows.append({"game_pk": gp, "pitcher": 2, "game_date": date,
                     "pitch_type": "sl", "Pitches": 30, "CSW": 6})
    # Pitcher 3: single late start (no priors -> gate fail). Dated after D7
    # so its rows never enter any queried league prior.
    gp += 1
    rows.append({"game_pk": gp, "pitcher": 3, "game_date": "2024-04-08",
                 "pitch_type": "ff", "Pitches": 30, "CSW": 6})
    rows.append({"game_pk": gp, "pitcher": 3, "game_date": "2024-04-08",
                 "pitch_type": "sl", "Pitches": 30, "CSW": 6})
    gate_pk = gp
    pt = pl.DataFrame(rows)
    frame = pl.DataFrame([
        {"game_pk": 107, "pitcher": 1, "game_date": "2024-04-07"},  # S7
        {"game_pk": 108, "pitcher": 1, "game_date": "2024-04-07"},  # same-date dup
        {"game_pk": gate_pk, "pitcher": 3, "game_date": "2024-04-08"},  # no history
    ])
    return frame, pt, gate_pk


def test_hand_computed_value_and_same_date_exclusion() -> None:
    frame, pt, _ = _synthetic()
    out = _join_kadj_features(frame, pt)
    assert out.height == frame.height
    # League prior D7: ff (72+36)/360 = 0.30; sl (36+36)/360 = 0.20.
    # Pitcher-1 roll: ff 0.40, sl 0.20; usage 0.5/0.5.
    # kadj = 0.5*(0.40-0.30) + 0.5*(0.20-0.20) = 0.05.
    got = out.filter(pl.col("game_pk") == 107)["kadj"].to_list()
    assert len(got) == 1 and abs(got[0] - 0.05) < 1e-9
    # Same-date dup sees the identical prior-only history.
    dup = out.filter(pl.col("game_pk") == 108)["kadj"].to_list()
    assert dup == got
    assert out.filter(pl.col("game_pk") == 107)["kadj_missing"].to_list() == [0]


def test_history_gates_emit_null_plus_flag() -> None:
    frame, pt, gate_pk = _synthetic()
    out = _join_kadj_features(frame, pt)
    row = out.filter(pl.col("game_pk") == gate_pk)
    assert row["kadj"].to_list() == [None]
    assert row["kadj_missing"].to_list() == [1]


def test_leading_null_rows_do_not_break_schema() -> None:
    # Regression: schema inference failed when the first rows were null-gated
    # (ComputeError on real L3, whose earliest seasons lack history).
    frame, pt, gate_pk = _synthetic()
    reordered = pl.concat([frame.filter(pl.col("game_pk") == gate_pk),
                           frame.filter(pl.col("game_pk") != gate_pk)])
    out = _join_kadj_features(reordered, pt)
    assert out.height == frame.height
    assert out.filter(pl.col("game_pk") == 107)["kadj"].to_list()[0] is not None
    assert out.filter(pl.col("game_pk") == gate_pk)["kadj"].to_list() == [None]


def test_null_fallback_frame_shape() -> None:
    # The CI/no-data fallback: null column + all-missing flag, row-preserving.
    frame = pl.DataFrame([{"game_pk": 1, "pitcher": 1, "game_date": "2024-04-01"}])
    out = _null_kadj_frame(frame)
    assert out.height == 1
    assert out["kadj"].to_list() == [None]
    assert out["kadj_missing"].to_list() == [1]


def test_duplicate_keys_fail_loudly() -> None:
    frame, pt, _ = _synthetic()
    bad = pl.concat([frame, frame.head(1)])
    try:
        _join_kadj_features(bad, pt)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("expected duplicate-key ValueError")
