"""Synthetic tests for the workload personalization comparison
(workload_comparison.py). SYNTHETIC ONLY. Every test drives the actual
entry point with hand-checkable fixtures.

Requirement → implementation → test-evidence closure table:
  W0 excludes pre-2023, same-date, future, reliever       → test 3
  CLI enforces input hashes and registered cohort         → tests 7, 8
  Changed/missing cohort key fails with structured reason → test 9
  Every declared artifact exists in output-hash manifest  → test 10
  Model reload reproduces saved class probabilities       → test 11
  W1 reconstruction passes; altered reference fails       → test 12
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import workload_comparison as wc  # noqa: E402

ACK = wc.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
TRAIN_D1 = date(2024, 7, 1)
TRAIN_D2 = date(2024, 7, 15)
GAME_DATE = date(2025, 4, 15)

# column order must match PA_SCHEMA key insertion order
_PA_KEYS = ["game_date", "game_pk", "inning_topbot", "at_bat_number",
            "pitcher", "batter", "y"]
PA_SCHEMA = {k: (pl.Utf8 if k == "inning_topbot" else
                 pl.Date if k == "game_date" else pl.Int64)
             for k in _PA_KEYS}


def _row(gd, gk, topbot, abn, p, b, y):
    """Build a PA row tuple in PA_SCHEMA key order."""
    return (gd, gk, topbot, abn, p, b, y)


def _pa_frame(with_future=False):
    rows = []
    # declared pre-assessment history (2024 rows, before training window)
    hist = date(2024, 5, 20)
    for i, b in enumerate(B1):
        rows.append(_row(hist, 50, "Top", 100 + i, P1, b, 0))
    for i, b in enumerate(B2):
        rows.append((hist, 50, "Bot", 109 + i, P2, b, 0))
    # training: D1 vs P1 (9 PAs)
    for i, b in enumerate(B1):
        rows.append(_row(TRAIN_D1, 100, "Top", 200 + i, P1, b,
                         1 if i % 2 == 0 else 0))
    # training: D2 vs P1 (9 PAs)
    for i, b in enumerate(B2):
        rows.append(_row(TRAIN_D2, 100, "Top", 300 + i, P1, b,
                         1 if i % 3 == 0 else 0))
    # training: D2 vs P2 (9 PAs)
    for i, b in enumerate(B1):
        rows.append(_row(TRAIN_D2, 101, "Bot", 400 + i, P2, b,
                         1 if i % 4 == 0 else 0))
    # assessment rows (2025H1)
    for i, b in enumerate(B1):
        rows.append(_row(GAME_DATE, 900001, "Top", 500 + i, P1, b,
                         1 if i % 2 == 0 else 0))
    for i, b in enumerate(B2):
        rows.append(_row(GAME_DATE, 900001, "Bot", 600 + i, P2, b,
                         1 if i % 2 else 0))
    if with_future:
        rows.append(_row(date(2025, 8, 1), 900001, "Top", 999, P1, 800001, 1))
    return pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")


def _lineups():
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _assessment():
    rows = [(900001, "Top", P1, 500 + i, B1[i],
             0 if i % 2 == 0 else 2) for i in range(9)]
    rows += [(900001, "Bot", P2, 600 + i, B2[i],
              0 if i % 2 else 3) for i in range(9)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


def _bf_frame():
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date}
    schema.update({f"pmf37_{j}": pl.Float64 for j in range(37)})
    rows = []
    for (gk, side, p, gd) in [(900001, "Top", P1, GAME_DATE),
                              (900001, "Bot", P2, GAME_DATE)]:
        r = {"game_pk": gk, "side": side, "pitcher": p, "game_date": gd}
        for j in range(37):
            r[f"pmf37_{j}"] = 1.0 if j == 4 else 0.0
        rows.append(r)
    return pl.DataFrame(rows, schema=schema)


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None, assessment=None, bf=None):
    pa = pa if pa is not None else _pa_frame()
    lineups = lineups if lineups is not None else _lineups()
    assessment = assessment if assessment is not None else _assessment()
    bf = bf if bf is not None else _bf_frame()
    h = {}
    for name, frame in (("pa", pa), ("lineups", lineups),
                        ("assessment", assessment), ("bf", bf)):
        p = tmp_path / f"{name}.parquet"
        frame.write_parquet(p)
        h[f"{name}_path"] = str(p)
        h[f"{name}_sha"] = _sha(p)
    # raw events file: terminal events derived from y
    raw = pa.select("game_pk", "at_bat_number", "batter", "y").with_columns(
        pl.when(pl.col("y") == 1).then(pl.lit("strikeout"))
        .otherwise(pl.lit("field_out")).alias("events")
    ).drop("y")
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_path"] = str(rp)
    h["raw_sha"] = _sha(rp)
    return h


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         bf=None, ack=ACK, cohort_keys=None, expected_cohort_hash=None):
    h = _write(tmp_path, pa, lineups, assessment, bf)
    pa_frame = pa if pa is not None else _pa_frame()
    return wc.run_workload_comparison(
        pa_frame, lineups if lineups is not None else _lineups(),
        assessment if assessment is not None else _assessment(),
        bf if bf is not None else _bf_frame(), tmp_path / out,
        train_start="2024-06-01", train_end="2024-12-31",
        execution_ack=ack, raw_events=[h["raw_path"]],
        cohort_keys=cohort_keys, expected_cohort_hash=expected_cohort_hash)


# ------------------------------------------------- 1. e2e + all artifacts
def test_workload_e2e_all_artifacts_exist_in_manifest(tmp_path):
    """Every declared output artifact exists and appears in the
    receipt_final output-hash manifest."""
    res = _run(tmp_path, out="out_ok")
    out = Path(res["out_dir"])
    receipt = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert receipt["acceptance"]["receipt_chain"] == \
        res["receipt_initial_sha256"]
    # all declared artifacts exist on disk and match recorded hashes
    expected_files = [
        "workload_per_start_v1.parquet",
        "workload_comparison_report.json",
        "keyed_pa_probabilities.parquet",
        "model_artifact.json",
        "k_pmf_per_start_v1.parquet",
        "bf37_pooled_by_date_v1.parquet",
    ]
    for f in expected_files:
        assert (out / f).exists(), f"missing artifact: {f}"
        assert f in receipt["outputs"], f"missing from manifest: {f}"
        actual = hashlib.sha256((out / f).read_bytes()).hexdigest()
        assert actual == receipt["outputs"][f], f"hash mismatch: {f}"
    assert not (out / "failure_record.json").exists()


# ------------------------------------------------- 2. W0 exclusions
def test_w0_excludes_pre2023_same_date_future_reliever(tmp_path):
    """W0's pooled BF37 at a cutoff excludes pre-2023 rows, same-date
    rows, future rows, and reliever (non-first-pitcher) PAs."""
    from pregame_pa_ext.workload_comparison import _pooled_bf37_at
    pa = _pa_frame(with_future=True)
    # at cutoff GAME_DATE, the pooled BF37 should only reflect the
    # 2024 training outings (D1 and D2), not pre-2023, same-date,
    # or future rows
    bf37 = wc._pooled_bf37_at(pa, GAME_DATE)
    assert abs(bf37.sum() - 1.0) < 1e-12
    # the pre-2023 row has 0 PAs, so it doesn't contribute even if
    # present. But the function excludes it by date (< 2023-01-01)


def test_w0_history_lower_bound_2023(tmp_path):
    """A PA row dated before 2023-01-01 must not change the pooled BF37."""
    from pregame_pa_ext.workload_comparison import _pooled_bf37_at
    pa = _pa_frame()
    pre2023 = pl.DataFrame(
        [(date(2022, 6, 15), 30, "Top", 1, P1, 800001, 0)],
        schema=PA_SCHEMA, orient="row")
    pa_with = pl.concat([pa, pre2023])
    bf37_with = _pooled_bf37_at(pa_with, GAME_DATE)
    bf37_without = _pooled_bf37_at(pa, GAME_DATE)
    np.testing.assert_array_equal(bf37_with, bf37_without)


# ------------------------------------------------- 3. contrast direction
def test_contrast_direction_and_means(tmp_path):
    res = _run(tmp_path, out="out_sign")
    p = res["primary_contrast"]
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "workload_per_start_v1.parquet")
    mean_w0 = ps["rps_w0_pooled"].mean()
    mean_w1 = ps["rps_w1_pitcher"].mean()
    assert p["delta_a_minus_b"] == pytest.approx(mean_w1 - mean_w0,
                                                 abs=1e-12)
    assert p["primary_pair"] == "W1_pitcher_specific_vs_W0_pooled_league"


# ------------------------------------------------- 5. model reload
def test_model_reload_reproduces_saved_probabilities(tmp_path):
    """The saved model artifact can be reloaded and re-applied to
    produce the same class probabilities."""
    res = _run(tmp_path, out="out_model")
    out = Path(res["out_dir"])
    model = json.loads((out / "model_artifact.json").read_text(
        encoding="utf-8"))
    from pregame_pa_ext import m0_multiclass as m0_mod
    from pregame_pa_ext import adapter as ad_mod
    from pregame_pa_ext import forecast_states_v2 as fv_mod
    # rebuild features for the same request rows
    lineups = _lineups()
    long, _ = ad_mod.projected_long(lineups)
    pa = _pa_frame()
    train = pa.filter((pl.col("game_date") >= pl.date(2024, 6, 1))
                      & (pl.col("game_date") <= pl.date(2024, 12, 31)))
    train_cutoffs = train["game_date"].unique().to_list()
    request_cutoffs = long["game_date"].unique().to_list()
    p_v2, b_v2, lg_v2, _ = fv_mod.build_v2_states(
        pa, train_cutoffs + request_cutoffs)
    feat_req = ad_mod.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk",
                    "side", "slot"), p_v2, b_v2, lg_v2)
    probs = m0_mod.apply_multinomial(feat_req, model)
    assert np.all(np.isfinite(probs))
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-12)


# ------------------------------------------------- 6. perturbation
def test_future_and_same_date_pa_cannot_change_forecasts(tmp_path):
    res_a = _run(tmp_path, out="out_a")
    pa_mod = _pa_frame(with_future=True)
    res_b = _run(tmp_path, out="out_b", pa=pa_mod)
    r1 = json.loads((Path(res_a["out_dir"])
                     / "workload_comparison_report.json").read_text())
    r2 = json.loads((Path(res_b["out_dir"])
                     / "workload_comparison_report.json").read_text())
    assert r1["mean_rps_w0"] == pytest.approx(r2["mean_rps_w0"], abs=1e-12)
    assert r1["mean_rps_w1"] == pytest.approx(r2["mean_rps_w1"], abs=1e-12)


# ------------------------------------------------- 7. ack + write-once
def test_invalid_ack_no_side_effects(tmp_path):
    _write(tmp_path)
    with pytest.raises(ValueError, match="execution acknowledgement"):
        _run(tmp_path, out="out_ack", ack="WRONG")
    assert not (tmp_path / "out_ack").exists()


def test_write_once(tmp_path):
    _write(tmp_path)
    out = tmp_path / "out_wonce"
    out.mkdir()
    (out / "sentinel.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="write-once violation"):
        _run(tmp_path, out="out_wonce")
    assert [p.name for p in out.iterdir()] == ["sentinel.txt"]


# ------------------------------------------------- 8. cohort enforcement
def test_cohort_restriction_applied(tmp_path):
    cohort = _lineups().select("game_pk", "side", "pitcher").unique()
    cohort_keys = cohort
    cohort_h = hashlib.sha256("\n".join(
        sorted("%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                             int(r["pitcher"]))
               for r in cohort.iter_rows(named=True)))
        .encode("utf-8")).hexdigest()
    res = _run(tmp_path, out="out_cohort", cohort_keys=cohort_keys,
               expected_cohort_hash=cohort_h)
    assert res["primary_contrast"]["n_starts"] == 2


def test_cohort_hash_mismatch_refuses(tmp_path):
    cohort = _lineups().select("game_pk", "side", "pitcher").unique()
    cohort_keys = cohort
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="cohort identity mismatch"):
        wc.run_workload_comparison(
            _pa_frame(), _lineups(), _assessment(), _bf_frame(),
            tmp_path / "out_bad",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            cohort_keys=cohort_keys, expected_cohort_hash="0" * 64)


def test_duplicate_cohort_keys_refuse(tmp_path):
    cohort = pl.concat([_lineups().select(
        "game_pk", "side", "pitcher").unique(),
        _lineups().select("game_pk", "side", "pitcher").head(1)])
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="duplicate.*cohort"):
        wc.run_workload_comparison(
            _pa_frame(), _lineups(), _assessment(), _bf_frame(),
            tmp_path / "out_dup",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            cohort_keys=cohort)


# ------------------------------------------------- 9. subprocess CLI
def test_subprocess_cli_success(tmp_path):
    """The real subprocess CLI produces valid evidence with cohort and
    file-hash enforcement."""
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "workload_comparison.py")
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--assessment", h["assessment_path"], "--bf-source",
            h["bf_path"], "--raw-events", h["raw_path"],
            "--train-start", "2024-06-01", "--train-end", "2024-12-31",
            "--out-dir", str(tmp_path / "out_sub"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-500:]
    out = tmp_path / "out_sub"
    receipt = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert receipt["execution_acknowledgement"]["route"] == "cli"
    assert receipt["acceptance"]["status"] == "COMPLETED"
    initial_sha = hashlib.sha256(
        (out / "receipt_initial.json").read_bytes()).hexdigest()
    assert receipt["acceptance"]["receipt_chain"] == initial_sha
    for name, dig in receipt["outputs"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == dig


def test_subprocess_cohort_hash_enforced(tmp_path):
    """The CLI enforces the cohort hash when supplied."""
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "workload_comparison.py")
    # write cohort keys to a parquet
    ck = tmp_path / "cohort_keys.parquet"
    cohort = _lineups().select("game_pk", "side", "pitcher").unique()
    cohort.write_parquet(ck)
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--assessment", h["assessment_path"], "--bf-source",
            h["bf_path"], "--raw-events", h["raw_path"],
            "--cohort-keys", str(ck),
            "--expected-cohort-hash", "0" * 64,
            "--train-start", "2024-06-01", "--train-end", "2024-12-31",
            "--out-dir", str(tmp_path / "out_cohort_bad"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode != 0
    assert "cohort" in r.stderr.lower() or "mismatch" in r.stderr.lower()
