"""Synthetic integration tests for the history-sensitivity scorecard
entry point (history_sensitivity_scorecard.py). SYNTHETIC ONLY: no real
artifacts, no real-source reads, and no real-data scoring. Every test
drives the exact registered entry point (main() or
run_history_sensitivity) with synthetic files."""
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

from pregame_pa_ext import history_sensitivity_scorecard as hs  # noqa: E402

ACK = hs.EXECUTION_ACK_TOKEN
A, B, D, Z = 700001, 700002, 700004, 700009

EST_SCHEMA = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "realized_bf": pl.Int64,
              "realized_k": pl.Int64}
EVAL_SCHEMA = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
               "game_date": pl.Date, "block": pl.Utf8,
               "realized_k": pl.Int64,
               "pmf_baseline": pl.List(pl.Float64)}
BF_SCHEMA = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
             "game_date": pl.Date}
BF_SCHEMA.update({f"pmf37_{j}": pl.Float64 for j in range(37)})


def _onehot24(k: int) -> list:
    v = [0.0] * 24
    v[k] = 1.0
    return v


def est_frame(with_2025_row: bool = False, h2_only: bool = False):
    """Estimation outcomes. A in BOTH windows (2023: 0 K / 10 BF;
    2024H2: 10 K / 10 BF), B only in 2023 (0 K / 6 BF), D only in
    2024H2 (0 K / 4 BF). The optional 2025 row is FORBIDDEN training
    data and must be excluded."""
    rows = []
    if not h2_only:
        rows += [(100, "Top", A, date(2023, 5, 2), 10, 0),
                 (100, "Top", B, date(2023, 6, 1), 6, 0)]
    rows += [(101, "Top", A, date(2024, 8, 1), 10, 10),
             (101, "Bot", D, date(2024, 8, 2), 4, 0)]
    if with_2025_row:
        rows.append((999, "Top", A, date(2025, 7, 1), 5, 5))
    return pl.DataFrame(rows, schema=EST_SCHEMA, orient="row")


def eval_frame(extra_confirm_row: bool = False,
               mislabeled_row: bool = False, realized=None):
    realized = [0, 0, 0, 0] if realized is None else realized
    f_pmf = {201: _onehot24(0), 202: _onehot24(1), 203: _onehot24(2),
             204: None}
    meta = [(201, A, date(2025, 2, 1)), (202, D, date(2025, 3, 2)),
            (203, B, date(2025, 4, 3)), (204, Z, date(2025, 5, 4))]
    rows = [(gk, "Top", p, gd, "block_2025H1", realized[i], f_pmf[gk])
            for i, (gk, p, gd) in enumerate(meta)]
    if extra_confirm_row:
        rows.append((299, "Top", A, date(2025, 8, 1), "confirm_2025H2",
                     1, _onehot24(1)))
    if mislabeled_row:
        rows.append((298, "Top", D, date(2024, 11, 1), "block_2025H1",
                     3, _onehot24(3)))
    return pl.DataFrame(rows, schema=EVAL_SCHEMA, orient="row")


def bf_frame(cover=(201, 202, 203, 204)):
    gdates = {201: date(2025, 2, 1), 202: date(2025, 3, 2),
              203: date(2025, 4, 3), 204: date(2025, 5, 4)}
    pitchers = {201: A, 202: D, 203: B, 204: Z}
    rows = []
    for gk in cover:
        r = {"game_pk": gk, "side": "Top", "pitcher": pitchers[gk],
             "game_date": gdates[gk]}
        for j in range(37):
            r[f"pmf37_{j}"] = 1.0 if j == 0 else 0.0
        rows.append(r)
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date}
    schema.update({f"pmf37_{j}": pl.Float64 for j in range(37)})
    return pl.DataFrame(rows, schema=schema)


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _cohort_hash_of(ev: pl.DataFrame) -> str:
    cohort = ev.filter(
        (pl.col("block") == hs.EVAL_BLOCK)
        & (pl.col("game_date") >= pl.date(2025, 1, 1))
        & (pl.col("game_date") <= pl.date(2025, 6, 30)))
    lines = sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"]))
        for r in cohort.select("game_pk", "side", "pitcher")
        .iter_rows(named=True))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _write(tmp_path: Path, s1=None, s2=None, ev=None, bf=None) -> dict:
    s1 = est_frame(with_2025_row=True, h2_only=True) if s1 is None else s1
    s2 = est_frame() if s2 is None else s2
    ev = eval_frame() if ev is None else ev
    bf = bf_frame() if bf is None else bf
    h = {}
    for name, frame in (("s1", s1), ("s2", s2), ("eval", ev),
                        ("bf", bf)):
        p = tmp_path / f"{name}.parquet"
        frame.write_parquet(p)
        h[f"{name}_path"] = str(p)
        h[f"{name}_sha"] = _sha(p)
    h["eval_hash"] = _cohort_hash_of(ev)
    return h


def _run(tmp_path: Path, out: str = "out", *, s1=None, s2=None, ev=None,
         bf=None, sha_overrides: dict = None, eval_hash: str = None,
         ack: str = ACK):
    h = _write(tmp_path, s1=s1, s2=s2, ev=ev, bf=bf)
    sha_overrides = sha_overrides or {}
    return hs.run_history_sensitivity(
        h["s1_path"], h["s2_path"], h["eval_path"], h["bf_path"],
        tmp_path / out,
        expected_s_v1_sha256=sha_overrides.get("s1", h["s1_sha"]),
        expected_s_v2_sha256=sha_overrides.get("s2", h["s2_sha"]),
        expected_eval_pmfs_sha256=sha_overrides.get(
            "eval", h["eval_sha"]),
        expected_bf_sha256=sha_overrides.get("bf", h["bf_sha"]),
        expected_eval_cohort_hash=(eval_hash if eval_hash is not None
                                   else h["eval_hash"]),
        execution_ack=ack)


def _h2_only():
    return est_frame(h2_only=True)


def _report(res) -> dict:
    return json.loads((Path(res["out_dir"])
                       / "history_sensitivity_report.json")
                      .read_text(encoding="utf-8"))


def _per_start(res) -> pl.DataFrame:
    return pl.read_parquet(
        Path(res["out_dir"])
        / "history_sensitivity_per_start_v1.parquet")


# ------------------------------------------------- 1. end-to-end success
def test_end_to_end_success_receipts_and_truthful_labels(tmp_path):
    res = _run(tmp_path)
    assert res["scorecard_identity"] == \
        "baseline_history_sensitivity_scorecard_v1"
    p = res["primary_contrast"]
    assert p["primary_pair"] == "S_v2_vs_S_v1"
    assert p["contrast"] == "RPS(S_v2) - RPS(S_v1) per start"
    assert "S_v2" in p["helper_label_note"]
    assert "S_v1" in p["helper_label_note"]
    out = Path(res["out_dir"])
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    initial = json.loads((out / "receipt_initial.json").read_text(
        encoding="utf-8"))
    assert final["acceptance"]["receipt_chain"] == \
        res["receipt_initial_sha256"]
    assert initial["actual_input_identities"] is None
    assert initial["counts"] is None
    assert final["actual_input_identities"][
        "s_v1_registered_starts_sha256"] == \
        initial["expected_input_identities"]["s_v1_registered_starts_sha256"]
    assert res["receipt_initial_sha256"] == _sha(out
                                                 / "receipt_initial.json")
    for name, dig in res["outputs"].items():
        assert _sha(out / name) == dig
    report = _report(res)
    assert report["windows"] == {
        "s_v1_estimation": ["2024-07-01", "2024-12-31"],
        "s_v2_estimation": ["2023-01-01", "2024-12-31"],
        "assessment": ["2025-01-01", "2025-06-30"]}
    assert report["scorecard_contract_sha256"] == \
        hs.scorecard_contract_sha()
    counts = report["counts"]
    assert counts["s_v1_train_rows"] == 2
    assert counts["s_v1_rows_excluded_out_of_window"] == 1
    assert counts["s_v2_train_rows"] == 4
    assert counts["s_v2_rows_excluded_out_of_window"] == 0
    assert counts["assessment_starts"] == 4
    assert counts["assessment_rows_excluded_from_cohort"] == 0
    assert report["workload"]["refit"] is False


def test_cli_success_route_and_exit_zero(tmp_path):
    h = _write(tmp_path)
    rc = hs.main([
        "--s-v1-source", h["s1_path"],
        "--s-v2-source", h["s2_path"],
        "--eval-pmfs", h["eval_path"],
        "--bf-source", h["bf_path"],
        "--expected-s-v1-sha256", h["s1_sha"],
        "--expected-s-v2-sha256", h["s2_sha"],
        "--expected-eval-pmfs-sha256", h["eval_sha"],
        "--expected-bf-sha256", h["bf_sha"],
        "--expected-eval-cohort-hash", h["eval_hash"],
        "--out-dir", str(tmp_path / "out_cli"),
        "--execution-ack", ACK])
    assert rc == 0
    out = tmp_path / "out_cli"
    initial = json.loads((out / "receipt_initial.json").read_text(
        encoding="utf-8"))
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert initial["execution_acknowledgement"]["route"] == "cli"
    assert final["primary_contrast"]["primary_pair"] == "S_v2_vs_S_v1"
    assert final["counts"]["assessment_starts"] == 4


# ------------------------------------------- 2. hand-checked arithmetic
def test_hand_checkable_rps_and_unambiguous_contrast(tmp_path):
    res = _run(tmp_path)
    ps = pl.read_parquet(
        Path(res["out_dir"])
        / "history_sensitivity_per_start_v1.parquet").sort("game_pk")
    w = 150
    lg1 = 10.0 / 14.0
    lg2 = 10.0 / 30.0
    expected = {
        201: ((10 + w * lg1) / (10 + w), (10 + w * lg2) / (20 + w)),
        # D carries a 2024H2 row, which lies INSIDE the v2 window:
        # v1-only pitchers (B, Z) are the ones exercising the fallback
        202: ((w * lg1) / (4 + w), (w * lg2) / (4 + w)),
        203: (lg1, (0 + w * lg2) / (6 + w)),              # B cold in v1
        204: (lg1, lg2),                                  # Z cold in both
    }
    for row in ps.iter_rows(named=True):
        p1, p2 = expected[row["game_pk"]]
        assert row["rps_s_v1"] == pytest.approx(p1 ** 2)
        assert row["rps_s_v2"] == pytest.approx(p2 ** 2)
        assert row["rps_s_v2"] < row["rps_s_v1"]
    prim = res["primary_contrast"]
    assert prim["delta_a_minus_b"] < 0
    assert prim["ci95"][1] < 0
    assert prim["n_starts"] == 4
    assert prim["n_boot"] == 2000 and prim["seed"] == 20261001


# --------------------------------- 3. identical estimation, identical preds
def test_identical_estimation_identical_predictions(tmp_path):
    same = _h2_only()
    res = _run(tmp_path, s1=same, s2=same, out="out_ident")
    ps = pl.read_parquet(
        Path(res["out_dir"])
        / "history_sensitivity_per_start_v1.parquet")
    assert ps["rps_s_v1"].to_list() == ps["rps_s_v2"].to_list()
    assert res["primary_contrast"]["delta_a_minus_b"] == 0.0
    report = _report(res)
    assert report["arm_settings_v1"]["population_rate"] == \
        report["arm_settings_v2"]["population_rate"]


# ------------------------- 4. evaluation outcomes cannot enter estimation
def test_eval_outcomes_cannot_change_fitted_rates(tmp_path):
    res1 = _run(tmp_path, out="out_a")
    res2 = _run(tmp_path, out="out_b",
                ev=eval_frame(realized=[1, 1, 1, 1]))
    r1, r2 = _report(res1), _report(res2)
    for arm in ("arm_settings_v1", "arm_settings_v2"):
        assert r1[arm]["population_rate"] == r2[arm]["population_rate"]
        assert r1[arm]["n_population_train_starts"] == \
            r2[arm]["n_population_train_starts"]
    ps1 = pl.read_parquet(Path(res1["out_dir"])
                          / "history_sensitivity_per_start_v1.parquet")
    ps2 = pl.read_parquet(Path(res2["out_dir"])
                          / "history_sensitivity_per_start_v1.parquet")
    assert ps1["rps_s_v1"].to_list() != ps2["rps_s_v1"].to_list()


# --------------------------------------- 5. out-of-window row exclusion
def test_out_of_window_estimation_rows_excluded_both_sides(tmp_path):
    res = _run(tmp_path, out="out_forbid")
    counts = res["counts"]
    assert counts["s_v1_rows_excluded_out_of_window"] == 1
    assert counts["s_v1_train_rows"] == 2
    assert counts["s_v2_train_rows"] == 4
    assert counts["s_v2_rows_excluded_out_of_window"] == 0
    # forbidden 2025 row (5 K / 5 BF for A) must not move any rate
    report = _report(res)
    assert report["arm_settings_v1"]["population_rate"] == \
        pytest.approx(10.0 / 14.0)
    assert report["arm_settings_v2"]["population_rate"] == \
        pytest.approx(10.0 / 30.0)
    s2_forbidden = pl.DataFrame(
        [(999, "Top", A, date(2025, 7, 1), 5, 5),
         (100, "Top", A, date(2023, 5, 2), 10, 0),
         (100, "Top", B, date(2023, 6, 1), 6, 0),
         (101, "Top", A, date(2024, 8, 1), 10, 10),
         (101, "Bot", D, date(2024, 8, 2), 4, 0)],
        schema=EST_SCHEMA, orient="row")
    res2 = _run(tmp_path, out="out_forbid2", s2=s2_forbidden)
    assert res2["counts"]["s_v2_rows_excluded_out_of_window"] == 1
    assert res2["counts"]["s_v2_train_rows"] == 4
    assert _report(res2)["arm_settings_v2"]["population_rate"] == \
        pytest.approx(10.0 / 30.0)


# ---------------------- 6. protected/mislabeled assessment rows excluded
def test_confirm_and_mislabeled_rows_never_scored(tmp_path):
    res = _run(tmp_path, ev=eval_frame(extra_confirm_row=True,
                                       mislabeled_row=True),
               out="out_conf")
    counts = res["counts"]
    assert counts["assessment_source_rows"] == 6
    assert counts["assessment_starts"] == 4
    assert counts["assessment_rows_excluded_from_cohort"] == 2
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "history_sensitivity_per_start_v1.parquet")
    assert set(ps["game_pk"].to_list()) == {201, 202, 203, 204}


# ------------------------------------------------- 7. refusal behaviors
def test_empty_estimation_refused(tmp_path):
    forbidden_only = pl.DataFrame(
        [(999, "Top", A, date(2025, 7, 1), 5, 5)],
        schema=EST_SCHEMA, orient="row")
    with pytest.raises(Exception, match="empty S_v1 estimation window"):
        _run(tmp_path, out="out_e1", s1=forbidden_only)
    failure = json.loads((tmp_path / "out_e1" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "empty S_v1 estimation window" in failure["error"]
    assert not (tmp_path / "out_e1"
                / "history_sensitivity_per_start_v1.parquet").exists()
    with pytest.raises(Exception, match="empty S_v2 estimation window"):
        _run(tmp_path, out="out_e2", s2=forbidden_only)


def test_empty_assessment_refused(tmp_path):
    confirm_only = eval_frame(extra_confirm_row=True).filter(
        pl.col("block") == "confirm_2025H2")
    with pytest.raises(Exception, match="empty assessment cohort"):
        _run(tmp_path, out="out_e3", ev=confirm_only)
    assert not (tmp_path / "out_e3").exists() or not list(
        (tmp_path / "out_e3").glob("history_sensitivity*"))


def test_missing_workload_key_refused(tmp_path):
    with pytest.raises(Exception, match="BF_PMF_COVERAGE_MISSING"):
        _run(tmp_path, out="out_bf", bf=bf_frame(cover=(201, 202, 203)))
    failure = json.loads((tmp_path / "out_bf" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "BF_PMF_COVERAGE_MISSING" in failure["error"]


def test_duplicate_assessment_keys_refused(tmp_path):
    ev = pl.concat([eval_frame(), eval_frame().head(1)])
    with pytest.raises(Exception, match="duplicate assessment start"):
        _run(tmp_path, out="out_dup", ev=ev)
    failure = json.loads((tmp_path / "out_dup" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "duplicate" in failure["error"]


# --------------------------------------------- 8. identity/gate guards
def test_wrong_input_identity_refused_before_decode(tmp_path):
    with pytest.raises(ValueError, match="input identity mismatch"):
        _run(tmp_path, out="out_bad", sha_overrides={"s1": "0" * 64})
    out = tmp_path / "out_bad"
    failure = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert "input identity mismatch" in failure["error"]
    assert failure["initial_receipt_sha256"] == _sha(
        out / "receipt_initial.json")
    assert not (out / "history_sensitivity_per_start_v1.parquet").exists()


def test_wrong_cohort_hash_refused(tmp_path):
    with pytest.raises(Exception,
                       match="assessment cohort identity mismatch"):
        _run(tmp_path, out="out_cohort", eval_hash="a" * 64)


def test_ack_gate_no_side_effects(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError,
                       match="execution acknowledgement missing"):
        hs.run_history_sensitivity(
            h["s1_path"], h["s2_path"], h["eval_path"], h["bf_path"],
            tmp_path / "out_ack",
            expected_s_v1_sha256=h["s1_sha"],
            expected_s_v2_sha256=h["s2_sha"],
            expected_eval_pmfs_sha256=h["eval_sha"],
            expected_bf_sha256=h["bf_sha"],
            expected_eval_cohort_hash=h["eval_hash"],
            execution_ack="WRONG-TOKEN")
    assert not (tmp_path / "out_ack").exists()
    argv = ["--s-v1-source", h["s1_path"],
            "--s-v2-source", h["s2_path"],
            "--eval-pmfs", h["eval_path"], "--bf-source", h["bf_path"],
            "--expected-s-v1-sha256", h["s1_sha"],
            "--expected-s-v2-sha256", h["s2_sha"],
            "--expected-eval-pmfs-sha256", h["eval_sha"],
            "--expected-bf-sha256", h["bf_sha"],
            "--expected-eval-cohort-hash", h["eval_hash"],
            "--out-dir", str(tmp_path / "out_ack_cli"),
            "--execution-ack", "WRONG-TOKEN"]
    assert hs.main(argv) == 2
    assert not (tmp_path / "out_ack_cli").exists()


def test_existing_destination_untouched(tmp_path):
    h = _write(tmp_path)
    d = tmp_path / "out_exists"
    d.mkdir()
    (d / "sentinel.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="write-once violation"):
        hs.run_history_sensitivity(
            h["s1_path"], h["s2_path"], h["eval_path"], h["bf_path"], d,
            expected_s_v1_sha256=h["s1_sha"],
            expected_s_v2_sha256=h["s2_sha"],
            expected_eval_pmfs_sha256=h["eval_sha"],
            expected_bf_sha256=h["bf_sha"],
            expected_eval_cohort_hash=h["eval_hash"],
            execution_ack=ACK)
    assert [p.name for p in d.iterdir()] == ["sentinel.txt"]


def test_receipt_linkage_and_output_hashes(tmp_path):
    res = _run(tmp_path)
    out = Path(res["out_dir"])
    assert res["receipt_initial_sha256"] == _sha(out
                                                 / "receipt_initial.json")
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert final["acceptance"]["receipt_chain"] == \
        res["receipt_initial_sha256"]
    for name, dig in res["outputs"].items():
        assert _sha(out / name) == dig
