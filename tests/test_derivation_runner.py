"""Synthetic integration tests for the historical derivation/overlap
execution entry point (derivation_runner.py). SYNTHETIC ONLY: no real
artifacts, no real-source reads, no scoring/fitting/calibration. Every
test invokes the exact registered entry point (run_derivation_overlap
or its CLI main) and covers: successful derivation with identical
overlap, incorrect file identity, existing output destination,
malformed source, overlap discrepancy (never presented as validated
success), preservation of failure evidence, and exclusion of
out-of-window target rows on BOTH sides."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import derivation_runner as dr  # noqa: E402
from pregame_pa_ext import starter_outcomes as so  # noqa: E402

P1, P2, P3, P9 = 700001, 700002, 700004, 700005
ACK = dr.EXECUTION_ACK_TOKEN

PA_SCHEMA = {"game_pk": pl.Int64, "game_date": pl.Date,
             "pitcher": pl.Int64, "y": pl.Int64,
             "pitcher_role": pl.Utf8, "inning_topbot": pl.Utf8,
             "at_bat_number": pl.Int64}
REG_SCHEMA = {"game_pk": pl.Int64, "side": pl.Utf8,
              "pitcher": pl.Int64, "game_date": pl.Date,
              "realized_bf": pl.Int64, "realized_k": pl.Int64}


def _pa_frame():
    """2023 train game + 2024H1 train game + 2024H2 overlap game +
    one 2022 row and one 2025 row (both OUT of the declared window)."""
    rows = [
        # 2023 (train-only): Top P1 4 PA -> bf 4 k 2; Bot P2 2 PA -> bf 2 k 1
        (920001, date(2023, 5, 2), P1, 1, "starter_pa", "Top", 1),
        (920001, date(2023, 5, 2), P1, 0, "starter_pa", "Top", 2),
        (920001, date(2023, 5, 2), P1, 1, "starter_pa", "Top", 3),
        (920001, date(2023, 5, 2), P1, 0, "starter_pa", "Top", 4),
        (920001, date(2023, 5, 2), P2, 1, "starter_pa", "Bot", 1),
        (920001, date(2023, 5, 2), P2, 0, "starter_pa", "Bot", 2),
        # 2024H1 (inside train window, OUTSIDE the 2024H2 overlap):
        # Top P3 2 PA -> bf 2 k 2
        (920002, date(2024, 5, 10), P3, 1, "starter_pa", "Top", 1),
        (920002, date(2024, 5, 10), P3, 1, "starter_pa", "Top", 2),
        # 2024H2 (overlap): Top P3 3 PA -> bf 3 k 2; Bot P1 2 PA -> bf 2 k 0
        (920003, date(2024, 8, 15), P3, 1, "starter_pa", "Top", 1),
        (920003, date(2024, 8, 15), P3, 1, "starter_pa", "Top", 2),
        (920003, date(2024, 8, 15), P3, 0, "starter_pa", "Top", 3),
        (920003, date(2024, 8, 15), P1, 0, "starter_pa", "Bot", 1),
        (920003, date(2024, 8, 15), P1, 0, "starter_pa", "Bot", 2),
        # 2022: OUT of the declared training window
        (920004, date(2022, 5, 1), P1, 1, "starter_pa", "Top", 1),
        # 2025: OUT of the declared training window (protected target)
        (920005, date(2025, 4, 1), P9, 1, "starter_pa", "Top", 1),
        (920005, date(2025, 4, 1), P9, 0, "starter_pa", "Top", 2),
    ]
    return pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")


def _registered_frame():
    """Existing start artifact: EXACTLY the derived 2024H2 starts for
    the overlap game, plus one 2025H1 row that must be excluded by the
    registered-side overlap-window filter (never enters the join)."""
    rows = [
        (920003, "Top", P3, date(2024, 8, 15), 3, 2),
        (920003, "Bot", P1, date(2024, 8, 15), 2, 0),
        (920005, "Top", P9, date(2025, 4, 1), 2, 1),
    ]
    return pl.DataFrame(rows, schema=REG_SCHEMA, orient="row")


def _write_inputs(tmp_path: Path, pa: pl.DataFrame = None,
                  reg: pl.DataFrame = None):
    pa = _pa_frame() if pa is None else pa
    reg = _registered_frame() if reg is None else reg
    pa_path = tmp_path / "pa_source.parquet"
    reg_path = tmp_path / "registered_starts.parquet"
    pa.write_parquet(pa_path)
    reg.write_parquet(reg_path)
    return (str(pa_path), str(reg_path),
            hashlib.sha256(pa_path.read_bytes()).hexdigest(),
            hashlib.sha256(reg_path.read_bytes()).hexdigest())


def _run(tmp_path: Path, *, pa=None, reg=None, out_name="out_v1",
         pa_sha=None, reg_sha=None, ack=ACK):
    pa_path, reg_path, pa_h, reg_h = _write_inputs(tmp_path, pa, reg)
    return dr.run_derivation_overlap(
        pa_path, reg_path, tmp_path / out_name,
        expected_pa_sha256=pa_sha if pa_sha is not None else pa_h,
        expected_registered_sha256=(reg_sha if reg_sha is not None
                                    else reg_h),
        execution_ack=ack)


# ------------------------------------------------- 1. success + identity
def test_runner_success_identical_overlap_and_receipt_chain(tmp_path):
    res = _run(tmp_path)
    assert res["verdict"] == "IDENTICAL"
    assert res["validated"] is True
    out = Path(res["out_dir"])
    # receipt chain: initial receipt intact and referenced
    initial = json.loads((out / "receipt_initial.json").read_text(
        encoding="utf-8"))
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert final["acceptance"]["receipt_chain"] == res[
        "receipt_initial_sha256"]
    # initial receipt is immutable: expected identities pinned,
    # actual identities live in the FINAL receipt (verified equal)
    assert initial["actual_input_identities"] is None
    assert final["actual_input_identities"]["pa_source_sha256"] \
        == initial["expected_input_identities"]["pa_source_sha256"]
    assert final["actual_input_identities"][
        "registered_starts_sha256"] \
        == initial["expected_input_identities"][
            "registered_starts_sha256"]
    # derived output identity recorded and reproducible
    dp = out / "derived_start_outcomes_v1.parquet"
    assert hashlib.sha256(dp.read_bytes()).hexdigest() \
        == res["outputs"]["derived_start_outcomes_v1.parquet"]
    assert final["outputs"]["derived_start_outcomes_v1.parquet"] \
        == res["outputs"]["derived_start_outcomes_v1.parquet"]
    # derived parquet carries the full declared window, sorted, with
    # the registered starter/BF/K definitions preserved
    d = pl.read_parquet(dp)
    assert d.height == 5  # 2023: 2, 2024H1: 1, 2024H2: 2
    assert set(d["game_date"].to_list()) == {
        date(2023, 5, 2), date(2024, 5, 10), date(2024, 8, 15)}
    top = d.filter((pl.col("game_pk") == 920003)
                   & (pl.col("side") == "Top")).row(0, named=True)
    assert (top["pitcher"], top["realized_bf"], top["realized_k"]) \
        == (P3, 3, 2)
    # overlap report on disk matches the returned report
    ovl = json.loads((out / "overlap_report.json").read_text(
        encoding="utf-8"))
    assert ovl["overlap_report"]["verdict"] == "IDENTICAL"
    assert ovl["overlap_report"]["n_key_intersection"] == 2


def test_runner_cli_success_exit_zero(tmp_path):
    pa_path, reg_path, pa_h, reg_h = _write_inputs(tmp_path)
    rc = dr.main(["--pa-source", pa_path,
                  "--registered-starts", reg_path,
                  "--expected-pa-sha256", pa_h,
                  "--expected-registered-sha256", reg_h,
                  "--out-dir", str(tmp_path / "out_cli"),
                  "--execution-ack", ACK])
    assert rc == 0
    final = json.loads((tmp_path / "out_cli" / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["validated"] is True
    assert final["execution_acknowledgement"]["route"] == "cli"


# ------------------------------------------------- 2. file identity
def test_runner_incorrect_file_identity_refused(tmp_path):
    bad_sha = "0" * 64
    with pytest.raises(ValueError, match="PA source identity mismatch"):
        _run(tmp_path, out_name="out_bad_id", pa_sha=bad_sha)
    out = tmp_path / "out_bad_id"
    # failure evidence preserved and chained to the initial receipt
    failure = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert failure["failure"] is True
    assert failure["initial_receipt_sha256"] == hashlib.sha256(
        (out / "receipt_initial.json").read_bytes()).hexdigest()
    # no partial outputs: the derived parquet was never written
    assert not (out / "derived_start_outcomes_v1.parquet").exists()


# ------------------------------------------------- 3. write-once output
def test_runner_existing_output_destination_refused(tmp_path):
    out_dir = tmp_path / "out_exists"
    out_dir.mkdir()
    (out_dir / "sentinel.txt").write_text("preserve", encoding="utf-8")
    pa_path, reg_path, pa_h, reg_h = _write_inputs(tmp_path)
    with pytest.raises(ValueError, match="write-once violation"):
        dr.run_derivation_overlap(
            pa_path, reg_path, out_dir,
            expected_pa_sha256=pa_h,
            expected_registered_sha256=reg_h, execution_ack=ACK)
    # nothing was written into the existing destination
    assert [p.name for p in out_dir.iterdir()] == ["sentinel.txt"]


# ------------------------------------------------- 4. malformed source
def test_runner_malformed_source_fails_loud(tmp_path):
    bad = _pa_frame().drop("y")
    pa_path, reg_path, pa_h, reg_h = _write_inputs(tmp_path, pa=bad)
    with pytest.raises(so.DerivationError, match="missing field"):
        dr.run_derivation_overlap(
            pa_path, reg_path, tmp_path / "out_malformed",
            expected_pa_sha256=pa_h,
            expected_registered_sha256=reg_h, execution_ack=ACK)
    out = tmp_path / "out_malformed"
    failure = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert "missing field" in failure["error"]


# ------------------------------------------------- 5. overlap discrepancy
def test_runner_overlap_discrepancy_not_validated_success(tmp_path):
    reg = _registered_frame().with_columns(
        pl.when((pl.col("game_pk") == 920003)
                & (pl.col("side") == "Top"))
        .then(pl.lit(4)).otherwise(pl.col("realized_bf"))
        .alias("realized_bf"))
    res = _run(tmp_path, reg=reg, out_name="out_disc")
    # the discrepancy verdict is returned verbatim and NEVER reported
    # as validated success
    assert res["verdict"] == "DISCREPANCIES_REQUIRE_EXPLANATION"
    assert res["validated"] is False
    assert res["overlap_report"]["bf_mismatches"] == 1
    out = tmp_path / "out_disc"
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert final["overlap_verdict"] == "DISCREPANCIES_REQUIRE_EXPLANATION"
    assert final["validated"] is False
    # CLI surfaces the discrepancy with a distinct nonzero exit code
    pa_path, reg_path, pa_h, reg_h = _write_inputs(
        tmp_path, reg=reg)
    rc = dr.main(["--pa-source", pa_path,
                  "--registered-starts", reg_path,
                  "--expected-pa-sha256", pa_h,
                  "--expected-registered-sha256", reg_h,
                  "--out-dir", str(tmp_path / "out_disc_cli"),
                  "--execution-ack", ACK])
    assert rc == 3


# ------------------------------------------------- 6. ack gate
def test_runner_ack_gate_no_side_effects(tmp_path):
    pa_path, reg_path, pa_h, reg_h = _write_inputs(tmp_path)
    with pytest.raises(ValueError,
                       match="execution acknowledgement missing"):
        dr.run_derivation_overlap(
            pa_path, reg_path, tmp_path / "out_ack",
            expected_pa_sha256=pa_h,
            expected_registered_sha256=reg_h,
            execution_ack="WRONG-TOKEN")
    assert not (tmp_path / "out_ack").exists()
    assert dr.main(["--pa-source", pa_path,
                    "--registered-starts", reg_path,
                    "--expected-pa-sha256", pa_h,
                    "--expected-registered-sha256", reg_h,
                    "--out-dir", str(tmp_path / "out_ack_cli"),
                    "--execution-ack", "WRONG-TOKEN"]) == 2
    assert not (tmp_path / "out_ack_cli").exists()


# ------------------------------------------------- 7. window exclusion
def test_runner_excludes_out_of_window_rows_both_sides(tmp_path):
    res = _run(tmp_path, out_name="out_window")
    counts = res["counts"]
    # PA side: 2022 row + two 2025 rows excluded BEFORE the derivation
    assert counts["pa_source_rows"] == 16
    assert counts["pa_rows_in_train_window"] == 13
    assert counts["pa_rows_excluded_out_of_window"] == 3
    # registered side: the 2025H1 artifact row must NOT enter overlap
    assert counts["registered_rows_total"] == 3
    assert counts["registered_rows_in_overlap_window"] == 2
    assert counts["registered_rows_excluded_out_of_window"] == 1
    assert res["overlap_report"]["n_registered"] == 2
    # derived parquet: no out-of-window game_dates anywhere
    d = pl.read_parquet(Path(res["out_dir"])
                        / "derived_start_outcomes_v1.parquet")
    assert d.filter((pl.col("game_date") < pl.date(2023, 1, 1))
                    | (pl.col("game_date") > pl.date(2024, 12, 31))
                    ).height == 0


# ------------------------------------------- empty/disjoint overlap
def test_runner_both_overlap_slices_empty_insufficient(tmp_path):
    """No 2024H2 rows on EITHER side: the raw validate report would be
    vacuously IDENTICAL (no mismatches possible), so the runner must
    record INSUFFICIENT_OVERLAP, keep validated false, write evidence,
    and exit nonzero (CLI 3)."""
    pa = _pa_frame().filter(pl.col("game_pk") != 920003)
    reg = _registered_frame().filter(
        pl.col("game_date") > pl.date(2024, 12, 31))
    res = _run(tmp_path, pa=pa, reg=reg, out_name="out_empty_both")
    assert res["overlap_sufficiency"]["sufficient"] is False
    assert res["overlap_report"]["n_key_intersection"] == 0
    assert res["verdict"] == "INSUFFICIENT_OVERLAP"
    assert res["validated"] is False
    out = tmp_path / "out_empty_both"
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert final["overlap_verdict"] == "INSUFFICIENT_OVERLAP"
    assert final["validated"] is False
    ovl = json.loads((out / "overlap_report.json").read_text(
        encoding="utf-8"))
    assert ovl["overlap_sufficiency"]["sufficient"] is False
    # the raw validate report is preserved verbatim (vacuous IDENTICAL)
    assert ovl["overlap_report"]["verdict"] == "IDENTICAL"
    # CLI surfaces insufficiency as nonzero, never success
    pa_path, reg_path, pa_h, reg_h = _write_inputs(
        tmp_path, pa=pa, reg=reg)
    assert dr.main(["--pa-source", pa_path,
                    "--registered-starts", reg_path,
                    "--expected-pa-sha256", pa_h,
                    "--expected-registered-sha256", reg_h,
                    "--out-dir", str(tmp_path / "out_empty_both_cli"),
                    "--execution-ack", ACK]) == 3


def test_runner_one_overlap_side_empty_insufficient(tmp_path):
    """One side empty (registered carries no 2024H2 rows) can never
    validate: the derived population has nothing to compare against."""
    reg = _registered_frame().filter(
        pl.col("game_date") > pl.date(2024, 12, 31))
    res = _run(tmp_path, reg=reg, out_name="out_empty_reg")
    assert res["overlap_sufficiency"]["registered_nonempty"] is False
    assert res["overlap_sufficiency"]["derived_nonempty"] is True
    assert res["verdict"] == "INSUFFICIENT_OVERLAP"
    assert res["validated"] is False


def test_runner_disjoint_overlap_keys_insufficient(tmp_path):
    """Both slices nonempty but the key sets share nothing: recorded as
    INSUFFICIENT_OVERLAP with the raw report (only-in-registered keys)
    preserved verbatim for explanation."""
    reg = pl.DataFrame(
        [(929999, "Top", P3, date(2024, 9, 1), 4, 2)],
        schema=REG_SCHEMA, orient="row")
    res = _run(tmp_path, reg=reg, out_name="out_disjoint")
    assert res["overlap_sufficiency"]["derived_nonempty"] is True
    assert res["overlap_sufficiency"]["registered_nonempty"] is True
    assert res["overlap_sufficiency"]["n_key_intersection"] == 0
    assert res["overlap_sufficiency"]["sufficient"] is False
    assert res["verdict"] == "INSUFFICIENT_OVERLAP"
    assert res["validated"] is False
    # the raw report explains the disjointness (never patched)
    assert res["overlap_report"]["keys_only_in_registered"] == 1
    assert res["overlap_report"]["keys_only_in_derived"] == 2


def test_runner_undateable_rows_refused_not_dropped(tmp_path):
    """A row with null game_date cannot be assigned to any authorized
    window: explicit refusal with exact count, never a silent drop."""
    bad = _pa_frame().with_columns(
        pl.when((pl.col("game_pk") == 920003)
                & (pl.col("pitcher") == P3)
                & (pl.col("at_bat_number") == 1))
        .then(None).otherwise(pl.col("game_date"))
        .alias("game_date"))
    pa_path, reg_path, pa_h, reg_h = _write_inputs(tmp_path, pa=bad)
    with pytest.raises(so.DerivationError, match="undateable"):
        dr.run_derivation_overlap(
            pa_path, reg_path, tmp_path / "out_undateable",
            expected_pa_sha256=pa_h,
            expected_registered_sha256=reg_h, execution_ack=ACK)
    failure = json.loads(
        (tmp_path / "out_undateable" / "failure_record.json")
        .read_text(encoding="utf-8"))
    assert "undateable" in failure["error"]


# ------------------------------------------------- 8. guards unchanged
def test_runner_preserves_derivation_guards(tmp_path):
    """A role anomaly inside the window fails loud through the exact
    entry point (the runner adds no tolerances and swallows nothing)."""
    bad = _pa_frame()
    opener = pl.DataFrame(
        [(920001, date(2023, 5, 2), 700006, 1, "starter_pa", "Top", 1)],
        schema=PA_SCHEMA, orient="row")
    pa_path, reg_path, pa_h, reg_h = _write_inputs(
        tmp_path, pa=pl.concat([bad, opener]))
    with pytest.raises(so.DerivationError, match="role anomaly"):
        dr.run_derivation_overlap(
            pa_path, reg_path, tmp_path / "out_guard",
            expected_pa_sha256=pa_h,
            expected_registered_sha256=reg_h, execution_ack=ACK)
    failure = json.loads((tmp_path / "out_guard" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "role anomaly" in failure["error"]
