"""Tests for the thin control-vs-books orchestration runner
(run_control_vs_books.py).

Production-entry-point fixtures covering:
- name-order normalization (canonical sorted key);
- declared start_dates derivation: exact cohort coverage, duplicate
  declared dates refuse, cohort-restricted (no date invention);
- pinned-input hash enforcement;
- execution-ack gate and write-once destination gate.

NO private lake reads; the join context is never imported here.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import run_control_vs_books as rc  # noqa: E402
from Python.odds_ledger import norm_player_name  # noqa: E402


def _sorted_key(s):
    return " ".join(sorted(norm_player_name(str(s or "")).split()))


# ---------------- 1. name-order normalization (canonical function)
def test_name_order_normalization():
    # L3 family-first vs vendor given-first orders normalize to ONE key
    assert _sorted_key("Allen Logan") == _sorted_key("logan allen")
    assert _sorted_key("Allen Logan") == "allen logan"
    assert _sorted_key("") == ""


def test_bridge_sorted_name_matches_canonical():
    jc = pytest.importorskip(
        "join_coverage",
        reason="private odds-coverage card not present")
    # the private bridge's sorted_name is a documented mirror of the
    # canonical norm_player_name: same output for both name orders
    assert jc.sorted_name("Allen Logan") == jc.sorted_name("logan allen")
    assert jc.sorted_name("Allen Logan") == _sorted_key("Allen Logan")


# ---------------- 2. declared start_dates derivation
def _cohort():
    return pl.DataFrame(
        {"game_pk": [1, 2], "side": ["home", "away"],
         "pitcher": [100, 200]}, orient="row")


def _count_agg():
    return pl.DataFrame({
        "game_pk": [1, 2, 3],
        "side": ["home", "away", "home"],
        "pitcher": [100, 200, 300],
        "game_date": [date(2025, 4, 10), date(2025, 4, 11),
                      date(2025, 5, 1)],
        "block": ["block_2025H1"] * 3,
        "realized_k": [5, 3, 7],
    }, orient="row")


def test_derive_start_dates_cohort_restricted():
    d = rc.derive_start_dates(_count_agg(), _cohort())
    # restricted to the cohort; the extra start (game_pk 3) is dropped
    assert d.height == 2
    assert set(d["game_pk"]) == {1, 2}
    # no date invention: dates come from the registered table verbatim
    assert d.sort("game_pk")["game_date"].to_list() == [
        date(2025, 4, 10), date(2025, 4, 11)]


def test_derive_start_dates_conflicting_dates_refuse():
    bad = pl.concat([_count_agg(),
                     _count_agg().head(1).with_columns(
                         pl.col("game_date") + pl.duration(days=1))])
    with pytest.raises(ValueError, match="conflicting declared"):
        rc.derive_start_dates(bad, _cohort())


def test_derive_start_dates_missing_column_refuse():
    with pytest.raises(ValueError, match="missing column"):
        rc.derive_start_dates(
            _count_agg().drop("game_date"), _cohort())


def test_seam_exact_cover_refuses_missing_cohort_date():
    """A cohort start absent from the declared dates must refuse
    inside the seam (no silent coverage gap, no join fan-out)."""
    from pregame_pa_ext import market_benchmark_seam as seam
    dates = rc.derive_start_dates(_count_agg(), _cohort()).filter(
        pl.col("game_pk") == 1)  # cohort start 2 has no declared date
    with pytest.raises(ValueError, match="declared dates"):
        seam.harness_model_frame(
            _k_pmf_frame(), _observed_frame(), dates, _cohort(),
            _cohort_hash(), rc.CONTROL_ARM)


# ---------------- 3. pin enforcement
def test_pin_enforcement_refuses_changed_input(tmp_path):
    f = tmp_path / "x.parquet"
    f.write_bytes(b"not the pinned bytes")
    with pytest.raises(ValueError, match="changed"):
        rc._require("pinned", f, "0" * 64)


# ---------------- 4. ack gate + write-once
def test_ack_gate(tmp_path):
    with pytest.raises(ValueError, match="acknowledgement"):
        rc.main(["--execution-ack", "WRONG-TOKEN",
                 "--out-dir", str(tmp_path / "out")])


def test_write_once_destination(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ValueError, match="write-once"):
        rc.main(["--execution-ack", rc.EXECUTION_ACK_TOKEN,
                 "--out-dir", str(dest)])


# ---------------- helpers shared with the exact-cover test
def _k_pmf_frame():
    rows = []
    for gpk, side, pid in ((1, "home", 100), (2, "away", 200)):
        for b in range(24):
            rows.append({"game_pk": gpk, "side": side,
                         "pitcher": pid, "bucket": b,
                         "pmf_multinomial_control": 1.0 / 24.0,
                         "pmf_platoon": 1.0 / 24.0})
    return pl.DataFrame(rows)


def _observed_frame():
    return pl.DataFrame(
        {"game_pk": [1, 2], "side": ["home", "away"],
         "pitcher": [100, 200], "realized_k": [5, 3]}, orient="row")


def _cohort_hash():
    # registered cohort content hash recipe (bk._cohort_hash over the
    # sorted unique start keys), exactly as cpd.validate_cohort uses it
    from pregame_pa_ext import binary_k_comparison as bk
    return bk._cohort_hash(
        [tuple(r) for r in _cohort().iter_rows()])
