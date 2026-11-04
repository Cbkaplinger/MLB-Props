"""Synthetic tests for the platoon-information value comparison
(platoon_comparison.py + platoon_features.py). SYNTHETIC ONLY. Every
test drives the actual entry point with hand-checkable fixtures.

Requirement -> implementation -> test-evidence closure table:
  End-to-end success + full output-hash manifest + receipts   -> test 1
  Keyed alignment: one row per matchup+slot, both arms' full
  class-probability vectors in [0,1] summing to 1             -> test 2
  Keyed alignment survives reversed PA row order              -> test 3
  Platoon rate math hand-check (alpha shrinkage formula)      -> test 4
  Unseen split -> exactly the global prior (full shrinkage)   -> test 5
  Sparse-split shrinkage: small-n cell pulled toward prior,
  large-n cell ~ empirical                                   -> test 6
  Switch-hitter forecast stand: modal conditional, tie rule,
  overall fallback, unknown -> global fallback                -> test 7
  Same-date/future exclusion: flipping same-date or future
  labels changes NO platoon feature or forecast               -> test 8
  Both arms on the identical sorted key list                  -> test 9
  Cohort restriction before features; extra start excluded    -> test 10
  Duplicate actual-PA identity refuses                        -> test 11
  Saved model reload reproduces saved class probabilities     -> test 12
  Reconstruction of the control: exact pass / altered refuse /
  missing refuse                                              -> tests 13a/b/c
  Ack gate (direct + CLI exit 2 zero side effects); reference
  pin ENFORCED pre-decode (exit 1); missing pin refused       -> tests 14a-d
  CLI end-to-end success                                      -> test 15
  Write-once refuses                                          -> test 16
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
from polars.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402

ACK = pc.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]   # all L stands vs P1 (RHP)
B2 = [800101 + i for i in range(9)]   # all R stands vs P2 (LHP)
SWITCH = 800501                        # switch hitter: L and R vs RHP
TRAIN_D1 = date(2024, 7, 1)
TRAIN_D2 = date(2024, 7, 15)
GAME_DATE = date(2025, 4, 15)
RUNNER = Path(pc.__file__).resolve()

_PA_KEYS = ["game_date", "game_pk", "inning_topbot", "at_bat_number",
            "pitcher", "batter", "y", "stand", "p_throws"]
PA_SCHEMA = {k: (pl.Utf8 if k in ("inning_topbot", "stand", "p_throws")
                 else pl.Date if k == "game_date" else pl.Int64)
             for k in _PA_KEYS}


def _row(gd, gk, tb, abn, p, b, y, stand, throws):
    return (gd, gk, tb, abn, p, b, y, stand, throws)


def _pa_rows():
    rows = []
    hist = date(2024, 4, 20)
    # history: B1 (L) vs P1 (R)
    for i, b in enumerate(B1):
        rows.append(_row(hist, 50, "Top", 100 + i, P1, b, 0, "L", "R"))
    # history: B2 (R) vs P2 (L)
    for i, b in enumerate(B2):
        rows.append((hist, 50, "Bot", 109 + i, P2, b, 0, "R", "L"))
    # switch hitter history vs RHP: 3 L, 1 R (modal conditional = L)
    for i in range(3):
        rows.append(_row(hist, 51, "Top", 130 + i, P1, SWITCH, 0,
                         "L", "R"))
    rows.append(_row(hist, 51, "Top", 133, P1, SWITCH, 0, "R", "R"))
    # training D1: B1 vs P1
    for i, b in enumerate(B1):
        rows.append(_row(TRAIN_D1, 100, "Top", 200 + i, P1, b,
                         1 if i % 2 == 0 else 0, "L", "R"))
    # training D2: B2 vs P2
    for i, b in enumerate(B2):
        rows.append(_row(TRAIN_D2, 101, "Bot", 300 + i, P2, b,
                         1 if i % 3 == 0 else 0, "R", "L"))
    # assessment rows (2025H1)
    for i, b in enumerate(B1):
        rows.append(_row(GAME_DATE, 900001, "Top", 500 + i, P1, b,
                         1 if i % 2 == 0 else 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(GAME_DATE, 900001, "Bot", 600 + i, P2, b,
                         1 if i % 2 else 0, "R", "L"))
    return rows


def _pa_frame(reverse=False):
    rows = _pa_rows()
    if reverse:
        rows = rows[::-1]
    return pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")


def _lineups(extra_start=False):
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    if extra_start:
        rows.append((900002, "Top", P1, GAME_DATE, True, *B1))
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _assessment():
    rows = [(900001, "Top", P1, 500 + i, B1[i],
             0 if i % 2 == 0 else 2) for i in range(9)]
    rows += [(900001, "Bot", P2, 600 + i, B2[i],
              0 if i % 2 else 1) for i in range(9)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None, assessment=None,
           events=None):
    pa = pa if pa is not None else _pa_frame()
    lineups = lineups if lineups is not None else _lineups()
    assessment = assessment if assessment is not None else _assessment()
    h = {}
    for name, frame in (("pa", pa), ("lineups", lineups),
                        ("assessment", assessment)):
        p = tmp_path / f"{name}.parquet"
        frame.write_parquet(p)
        h[f"{name}_path"] = str(p)
        h[f"{name}_sha"] = _sha(p)
    if events is None:
        # strikeout / walk / field_out mix so training has >=3 classes
        ev = []
        for r in pa.iter_rows(named=True):
            if r["y"] == 1:
                ev.append("strikeout")
            elif r["batter"] in B1 and r["game_date"] in (
                    TRAIN_D1, TRAIN_D2) and r["at_bat_number"] % 5 == 0:
                ev.append("walk")
            else:
                ev.append("field_out")
        raw = pa.select("game_pk", "at_bat_number", "batter").with_columns(
            pl.Series("events", ev))
    else:
        raw = events
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_path"] = str(rp)
    h["raw_sha"] = _sha(rp)
    return h


def _wrong_reference():
    rows = [(900001, "Top", P1, 0.5), (900001, "Bot", P2, 0.5)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "rps_w0_pooled": pl.Float64}, orient="row")


def _harvest_reference(out_dir) -> pl.DataFrame:
    ps = pl.read_parquet(Path(out_dir) / "platoon_per_start_v1.parquet")
    return ps.select(
        "game_pk", "side", "pitcher",
        pl.col("rps_multinomial_control").alias("rps_w0_pooled"))


def _cohort_hash_of(cohort: pl.DataFrame) -> str:
    return hashlib.sha256("\n".join(sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"]))
        for r in cohort.iter_rows(named=True)))
        .encode("utf-8")).hexdigest()


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         events=None, ack=ACK, cohort_keys=None, expected_cohort_hash=None,
         reconstruction_reference=None, reference_sha256=None,
         input_identities=None):
    h = _write(tmp_path, pa, lineups, assessment, events)
    pa_frame = pa if pa is not None else _pa_frame()
    if reconstruction_reference is None and ack == ACK:
        boot_out = tmp_path / f"_boot_{out}"
        try:
            pc.run_platoon_comparison(
                pa_frame,
                lineups if lineups is not None else _lineups(),
                assessment if assessment is not None else _assessment(),
                boot_out,
                train_start="2024-05-01", train_end="2024-12-31",
                execution_ack=ack, raw_events=[h["raw_path"]],
                cohort_keys=cohort_keys,
                expected_cohort_hash=expected_cohort_hash,
                reconstruction_reference=_wrong_reference())
        except ValueError:
            pass
        boot_ps = boot_out / "platoon_per_start_v1.parquet"
        assert boot_ps.exists(), (
            "bootstrap run must preserve per-start evidence before "
            "refusing")
        reconstruction_reference = _harvest_reference(boot_out)
    return pc.run_platoon_comparison(
        pa_frame, lineups if lineups is not None else _lineups(),
        assessment if assessment is not None else _assessment(),
        tmp_path / out,
        train_start="2024-05-01", train_end="2024-12-31",
        execution_ack=ack, raw_events=[h["raw_path"]],
        cohort_keys=cohort_keys, expected_cohort_hash=expected_cohort_hash,
        reconstruction_reference=reconstruction_reference,
        reconstruction_reference_sha256=reference_sha256,
        input_identities=input_identities)


# ------------------------------------- 1. e2e + output-hash manifest closure
def test_e2e_all_artifacts_in_manifest(tmp_path):
    res = _run(tmp_path)
    expected = {"platoon_per_start_v1.parquet",
                "platoon_comparison_report.json",
                "keyed_pa_probabilities.parquet",
                "model_artifacts.json",
                "k_pmf_per_start_v1.parquet",
                "bf37_pooled_by_date_v1.parquet",
                "platoon_split_rates_v1.parquet",
                "receipt_initial.json", "receipt_final.json"}
    for name in expected:
        assert (Path(res["out_dir"]) / name).exists(), name
    final = json.loads(
        (Path(res["out_dir"]) / "receipt_final.json")
        .read_text(encoding="utf-8"))
    for name, sha in res["outputs"].items():
        assert final["outputs"][name] == sha
        assert final["outputs"][name] == _sha(
            Path(res["out_dir"]) / name)
    assert final["reconstruction"]["verified"] is True
    assert final["acceptance"]["status"] == "COMPLETED"
    report = json.loads(
        (Path(res["out_dir"]) / "platoon_comparison_report.json")
        .read_text(encoding="utf-8"))
    assert report["n_starts"] == 2
    assert report["n_matched_pas"] == 18
    assert "classwise" in report and "non_degradation" in report["k_count"]


# ------------------------------------------------- 2. keyed alignment
def test_keyed_table_unique_and_probabilities_valid(tmp_path):
    res = _run(tmp_path)
    keyed = pl.read_parquet(Path(res["out_dir"])
                            / "keyed_pa_probabilities.parquet")
    assert keyed.height == 18
    assert keyed.select("game_pk", "side", "pitcher", "slot",
                        "batter").n_unique() == keyed.height
    ctrl_cols = [c for c in keyed.columns if c.endswith("_control")]
    chat_cols = [c for c in keyed.columns if c.endswith("_platoon")]
    assert len(ctrl_cols) == len(chat_cols) == 3
    for cols in (ctrl_cols, chat_cols):
        s = keyed.select(pl.sum_horizontal(cols).alias("t"))["t"]
        assert np.allclose(s.to_numpy(), 1.0, atol=1e-9)
        for c in cols:
            assert keyed[c].min() >= 0.0 and keyed[c].max() <= 1.0


# --------------------------- 3. reversed PA row order -> identical result
def test_reversed_pa_row_order_identical_per_start(tmp_path):
    res_fwd = _run(tmp_path, out="fwd")
    h2 = _write(tmp_path, pa=_pa_frame(reverse=True))
    boot2 = tmp_path / "_boot_rev"
    try:
        pc.run_platoon_comparison(
            _pa_frame(reverse=True), _lineups(), _assessment(), boot2,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h2["raw_path"]],
            reconstruction_reference=_wrong_reference())
    except ValueError:
        pass
    ref2 = _harvest_reference(boot2)
    res_rev = pc.run_platoon_comparison(
        _pa_frame(reverse=True), _lineups(), _assessment(),
        tmp_path / "rev",
        train_start="2024-05-01", train_end="2024-12-31",
        execution_ack=ACK, raw_events=[h2["raw_path"]],
        reconstruction_reference=ref2)
    a = pl.read_parquet(Path(res_fwd["out_dir"])
                        / "platoon_per_start_v1.parquet").sort(
        "game_pk", "side", "pitcher")
    b = pl.read_parquet(Path(res_rev["out_dir"])
                        / "platoon_per_start_v1.parquet").sort(
        "game_pk", "side", "pitcher")
    assert_frame_equal(a, b, check_exact=False, rel_tol=0, abs_tol=1e-12)


# ------------------------------------ 4. platoon rate math hand-check
def test_split_rate_shrinkage_formula_hand_check():
    rows = []
    # strictly-prior cell (L,R): 6 rows -> 3 class 0, 3 class 2
    for i in range(3):
        rows.append((date(2024, 1, 1), "L", "R", 0))
        rows.append((date(2024, 1, 2), "L", "R", 2))
    labeled = pl.DataFrame(rows, schema={
        "game_date": pl.Date, "stand": pl.Utf8, "p_throws": pl.Utf8,
        "class_label": pl.Int64}, orient="row")
    labeled = labeled.with_columns(pl.lit(1).alias("pitcher"),
                                   pl.lit(1).alias("batter"))
    rates = pf.build_split_class_rates(labeled, [date(2024, 2, 1)],
                                       alpha=40.0, n_classes=4)
    lr = rates.filter((pl.col("stand") == "L")
                      & (pl.col("p_throws") == "R"))
    assert lr.height == 1
    r = lr.row(0, named=True)
    assert r["n_hist"] == 6
    # (3 + 40*0.5) / (6 + 40) = 23/46 = 0.5 (prior q0 = q2 = 0.5)
    assert abs(r["p_class_0"] - (3 + 40 * 0.5) / (6 + 40.0)) < 1e-12
    assert abs(r["p_class_2"] - (3 + 40 * 0.5) / (6 + 40.0)) < 1e-12
    # unseen cells (L,L), (R,L), (R,R): exactly the global prior
    for cell in (("L", "L"), ("R", "L"), ("R", "R")):
        u = rates.filter((pl.col("stand") == cell[0])
                         & (pl.col("p_throws") == cell[1])).row(
            0, named=True)
        assert u["n_hist"] == 0
        assert abs(u["p_class_0"] - 0.5) < 1e-12
        assert abs(u["p_class_2"] - 0.5) < 1e-12


# ----------------------------- 6. sparse-split shrinkage direction
def test_sparse_split_shrinkage_pulls_toward_prior():
    # sparse cell (R,R): 10 rows all class 0; dense cell (L,R): 600
    # class-0 + 300 class-2 -> non-degenerate global prior; the sparse
    # cell's empirical rate is pulled toward the prior strictly harder
    rows2 = []
    for i in range(10):
        rows2.append((date(2024, 1, 1), "R", "R", 0))
    for i in range(600):
        rows2.append((date(2024, 1, 2), "L", "R", 0))
    for i in range(300):
        rows2.append((date(2024, 1, 2), "L", "R", 2))
    labeled2 = pl.DataFrame(rows2, schema={
        "game_date": pl.Date, "stand": pl.Utf8, "p_throws": pl.Utf8,
        "class_label": pl.Int64}, orient="row")
    labeled2 = labeled2.with_columns(pl.lit(1).alias("pitcher"),
                                     pl.lit(1).alias("batter"))
    rates2 = pf.build_split_class_rates(labeled2, [date(2024, 2, 1)],
                                        alpha=40.0, n_classes=4)
    sparse2 = rates2.filter((pl.col("stand") == "R")
                            & (pl.col("p_throws") == "R")).row(0,
                                                               named=True)
    dense2 = rates2.filter((pl.col("stand") == "L")
                           & (pl.col("p_throws") == "R")).row(0,
                                                              named=True)
    # global prior for class 0 = 610/910
    prior0 = 610.0 / 910.0
    # hand-check both cells' shrinkage formulas
    assert abs(sparse2["p_class_0"]
               - (10 + 40 * prior0) / 50.0) < 1e-12
    assert abs(dense2["p_class_0"]
               - (600 + 40 * prior0) / 940.0) < 1e-12
    # shrinkage pulls each cell's empirical rate toward the prior; the
    # sparse cell is pulled strictly harder than the dense cell
    sparse_emp, dense_emp = 1.0, 600.0 / 900.0
    pull_sparse = abs(sparse_emp - sparse2["p_class_0"])
    pull_dense = abs(dense_emp - dense2["p_class_0"])
    assert pull_sparse > pull_dense


# ------------------------------- 7. switch-hitter forecast stand rules
def test_switch_hitter_forecast_stand_rules():
    pa = _pa_frame().with_columns(
        pl.lit(0, dtype=pl.Int64).alias("class_label"))
    req = pl.DataFrame({
        "batter": [SWITCH, SWITCH, 999999999],
        "pitcher": [P1, P2, P1],
        "cutoff": [GAME_DATE, GAME_DATE, GAME_DATE],
    }, schema={"batter": pl.Int64, "pitcher": pl.Int64,
               "cutoff": pl.Date})
    out = pf.forecast_matchup_hands(pa, req)
    r1 = out.filter(pl.col("batter") == SWITCH).filter(
        pl.col("pitcher") == P1).row(0, named=True)
    # switch hitter vs RHP: 3 L rows + 1 R row strictly before cutoff
    assert r1["f_hand"] == "R"
    assert r1["f_stand"] == "L"
    # conditional history unseen (vs LHP): overall modal = L (3 vs 1)
    r2 = out.filter(pl.col("batter") == SWITCH).filter(
        pl.col("pitcher") == P2).row(0, named=True)
    assert r2["f_hand"] == "L"
    assert r2["f_stand"] == "L"
    # unknown batter -> unknown stand (global fallback downstream)
    r3 = out.filter(pl.col("batter") == 999999999).row(0, named=True)
    assert r3["f_hand"] == "R"
    assert r3["f_stand"] is None


# ------------------------- 8. same-date/future exclusion (labels only)
def test_same_date_and_future_labels_excluded(tmp_path):
    h = _write(tmp_path)
    boot = tmp_path / "_boot_sdf"
    try:
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), _assessment(), boot,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    except ValueError:
        pass
    ref = _harvest_reference(boot)
    res1 = pc.run_platoon_comparison(
        _pa_frame(), _lineups(), _assessment(), tmp_path / "sdf_a",
        train_start="2024-05-01", train_end="2024-12-31",
        execution_ack=ACK, raw_events=[h["raw_path"]],
        reconstruction_reference=ref)
    # flip EVERY label at or after the earliest request cutoff (the
    # GAME_DATE rows are same-date for the request cutoffs) and rerun:
    # forecast rows and their keyed probabilities must be unchanged
    rows = []
    for r in _pa_rows():
        gd, gk, tb, abn, p, b, y, s, t = r
        if gd == GAME_DATE:
            y = 1 - y
        rows.append((gd, gk, tb, abn, p, b, y, s, t))
    pa_flip = pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")
    h2 = _write(tmp_path, pa=pa_flip)
    boot2 = tmp_path / "_boot_sdf2"
    try:
        pc.run_platoon_comparison(
            pa_flip, _lineups(), _assessment(), boot2,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h2["raw_path"]],
            reconstruction_reference=_wrong_reference())
    except ValueError:
        pass
    ref2 = _harvest_reference(boot2)
    res2 = pc.run_platoon_comparison(
        pa_flip, _lineups(), _assessment(), tmp_path / "sdf_b",
        train_start="2024-05-01", train_end="2024-12-31",
        execution_ack=ACK, raw_events=[h2["raw_path"]],
        reconstruction_reference=ref2)
    k1 = pl.read_parquet(Path(res1["out_dir"])
                         / "keyed_pa_probabilities.parquet").sort(
        "game_pk", "side", "pitcher", "slot")
    k2 = pl.read_parquet(Path(res2["out_dir"])
                         / "keyed_pa_probabilities.parquet").sort(
        "game_pk", "side", "pitcher", "slot")
    assert_frame_equal(k1, k2, check_exact=False, rel_tol=0,
                       abs_tol=1e-12)


# ------------------------- 9. identical sorted key list for both arms
def test_both_arms_identical_population(tmp_path):
    res = _run(tmp_path)
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "platoon_per_start_v1.parquet")
    assert ps.height == 2
    assert ps["rps_multinomial_control"].is_not_null().all()
    assert ps["rps_platoon"].is_not_null().all()
    assert (ps["rps_diff"]
            == (ps["rps_platoon"] - ps["rps_multinomial_control"])).all()
    assert ps["logloss_multinomial_control"].is_not_null().all()
    assert ps["logloss_platoon"].is_not_null().all()


# ----------------- 10. cohort restriction before features; extra excluded
def test_cohort_restriction_excludes_extra_start(tmp_path):
    cohort = _lineups().select("game_pk", "side", "pitcher").head(1)
    cohort_h = _cohort_hash_of(cohort)
    res = _run(tmp_path, out="out_cohort", lineups=_lineups(
        extra_start=True), cohort_keys=cohort,
        expected_cohort_hash=cohort_h)
    final = json.loads((Path(res["out_dir"]) / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["cohort_identity"]["restriction_applied"] is True
    assert final["cohort_identity"]["hash_match"] is True
    assert final["counts"]["n_requests_after_cohort"] == 9
    assert final["counts"]["n_starts"] == 1


# -------------------------------- 11. duplicate actual-PA identity refuses
def test_duplicate_assessment_identity_refuses(tmp_path):
    h = _write(tmp_path)
    dup = pl.concat([_assessment(), _assessment().head(1)])
    with pytest.raises(ValueError, match="duplicate actual-PA"):
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), dup, tmp_path / "out_dup",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())


# --------------------------------------- 12. saved model reload parity
def test_model_reload_reproduces_probabilities(tmp_path):
    res = _run(tmp_path, out="out_reload")
    out_dir = Path(res["out_dir"])
    models = json.loads((out_dir / "model_artifacts.json")
                        .read_text(encoding="utf-8"))
    keyed = pl.read_parquet(out_dir
                            / "keyed_pa_probabilities.parquet")
    keyed_sorted = keyed.sort("game_pk", "side", "pitcher", "slot")
    sys.path.insert(0, str(RUNNER.parents[2]))
    from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
    from pregame_pa_ext import adapter as ad2  # noqa: E402
    from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
    pa = _pa_frame()
    raw = pl.read_parquet(tmp_path / "raw_events.parquet")
    pa_labeled, _ = seb.attach_terminal_event_labels(
        pa, [str(tmp_path / "raw_events.parquet")])
    train = pa_labeled.filter(
        (pl.col("game_date") >= date(2024, 5, 1))
        & (pl.col("game_date") <= date(2024, 12, 31))
        & (pl.col("class_label") >= 0))
    long, _ = ad2.projected_long(_lineups())
    cutoffs = train["game_date"].unique().to_list() + \
        long["game_date"].unique().to_list()
    p_v2, b_v2, lg_v2, _ = fv.build_v2_states(pa, cutoffs)
    # rebuild the platoon features exactly as the runner does
    rates = pf.build_split_class_rates(pa_labeled, cutoffs,
                                       alpha=pc.ALPHA, n_classes=4)
    feat_req = ad2.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk",
                    "side", "slot"), p_v2, b_v2, lg_v2)
    hands = pf.forecast_matchup_hands(
        pa_labeled,
        long.select(pl.col("batter"), pl.col("pitcher"),
                    pl.col("game_date").alias("cutoff")))
    feat_req = (feat_req
                .join(hands.select("batter", "pitcher", "cutoff",
                                   "f_stand", "f_hand"),
                      left_on=["batter", "pitcher", "game_date"],
                      right_on=["batter", "pitcher", "cutoff"],
                      how="left")
                .with_columns(pl.col("game_date").alias("cutoff"),
                              pl.col("f_stand").alias("stand"),
                              pl.col("f_hand").alias("p_throws"))
                .drop(["f_stand", "f_hand"]))
    feat_req = pf.attach_platoon_features(feat_req, rates, n_classes=4)
    feat_sorted = feat_req.sort("game_pk", "side", "pitcher", "slot")
    probs_c = pc._softmax_full(feat_sorted, models["multinomial_control"],
                               bk.FEATURES)
    probs_p = pc._softmax_full(feat_sorted, models["platoon_challenger"],
                               pc.CHALLENGE_FEATURES)
    for j, c in enumerate(models["multinomial_control"]["classes"]):
        assert np.allclose(probs_c[:, j], keyed_sorted[
            f"p_class_{c}_control"].to_numpy(), rtol=0, atol=0)
    for j, c in enumerate(models["platoon_challenger"]["classes"]):
        assert np.allclose(probs_p[:, j], keyed_sorted[
            f"p_class_{c}_platoon"].to_numpy(), rtol=0, atol=0)


# --------------------- 13a/b/c. reconstruction of the control arm
def test_reconstruction_gate_exact_pass(tmp_path):
    res = _run(tmp_path, out="out_recon")
    rec = res["reconstruction"]
    assert rec["verified"] is True
    assert rec["max_abs_rps_diff"] == 0.0


def test_reconstruction_gate_altered_reference_refuses(tmp_path):
    h = _write(tmp_path)
    boot = tmp_path / "_boot_alt"
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), _assessment(), boot,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    assert (boot / "failure_record.json").exists()
    ref = _harvest_reference(boot).with_columns(
        (pl.col("rps_w0_pooled") + 1e-9).alias("rps_w0_pooled"))
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_alt",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)


def test_reconstruction_gate_missing_reference_refuses(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="reconstruction reference "
                                         "required"):
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_none",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=None)


# --------------------------------------------------- 14a. direct ack gate
def test_ack_gate_direct_call(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError,
                       match="execution acknowledgement"):
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_ack",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack="WRONG", raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    assert not (tmp_path / "out_ack").exists()


# ------------------------------------------ 14b. CLI ack gate exit 2
def test_cli_ack_gate_zero_side_effects(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", "nope.parquet", "--lineups", "nope.parquet",
         "--assessment", "nope.parquet", "--raw-events", "nope.parquet",
         "--train-start", "2024-05-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_ack"),
         "--execution-ack", "WRONG",
         "--cohort-keys", "nope.parquet", "--expected-cohort-hash",
         "0" * 64,
         "--reconstruction-reference", "nope.parquet",
         "--expected-reconstruction-sha256", "0" * 64,
         "--expected-pa-sha256", "0" * 64,
         "--expected-lineups-sha256", "0" * 64,
         "--expected-assessment-sha256", "0" * 64],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "EXECUTION REFUSED" in proc.stderr
    assert not (tmp_path / "out_cli_ack").exists()


# --------------- 14c. CLI reconstruction-reference identity ENFORCED
def test_cli_reference_hash_enforced_before_decode(tmp_path):
    h = _write(tmp_path)
    ref_path = tmp_path / "ref.parquet"
    _wrong_reference().write_parquet(ref_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-05-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_ref"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"], "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", "0" * 64,
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "INPUT IDENTITY MISMATCH for reconstruction reference" \
        in proc.stderr
    assert not (tmp_path / "out_cli_ref").exists()


# --------------- 14d. CLI reconstruction pin is REQUIRED (argparse)
def test_cli_reference_hash_pin_required(tmp_path):
    h = _write(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-05-01", "--train-end", "2024-12-31",
         "--out-dir", str(tmp_path / "out_cli_nopin"),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"], "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", "whatever.parquet",
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "--expected-reconstruction-sha256" in proc.stderr


# ------------------------------------- 15. CLI end-to-end success
def test_cli_end_to_end_success(tmp_path):
    res_boot = _run(tmp_path, out="out_cli_boot")
    ps = pl.read_parquet(Path(res_boot["out_dir"])
                         / "platoon_per_start_v1.parquet")
    ref_path = tmp_path / "ref_cli.parquet"
    ps.select("game_pk", "side", "pitcher",
              pl.col("rps_multinomial_control").alias("rps_w0_pooled")
              ).write_parquet(ref_path)
    h = _write(tmp_path)
    out_dir = tmp_path / "out_cli"
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
         "--assessment", h["assessment_path"],
         "--raw-events", h["raw_path"],
         "--train-start", "2024-05-01", "--train-end", "2024-12-31",
         "--out-dir", str(out_dir),
         "--execution-ack", ACK,
         "--cohort-keys", h["lineups_path"], "--expected-cohort-hash",
         _cohort_hash_of(_lineups().select("game_pk", "side", "pitcher")),
         "--reconstruction-reference", str(ref_path),
         "--expected-reconstruction-sha256", _sha(ref_path),
         "--expected-pa-sha256", h["pa_sha"],
         "--expected-lineups-sha256", h["lineups_sha"],
         "--expected-assessment-sha256", h["assessment_sha"]],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    final = json.loads((out_dir / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["acceptance"]["status"] == "COMPLETED"
    assert final["reconstruction"]["verified"] is True


# ------------------------------------------------ 16. write-once refuses
def test_write_once_refuses(tmp_path):
    res = _run(tmp_path, out="out_wo")
    existing = Path(res["out_dir"])
    h = _write(tmp_path)
    ref = _harvest_reference(existing)
    with pytest.raises(ValueError, match="write-once violation"):
        pc.run_platoon_comparison(
            _pa_frame(), _lineups(), _assessment(), existing,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)
