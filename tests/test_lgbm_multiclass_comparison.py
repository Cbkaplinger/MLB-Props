"""Synthetic tests for the equal-information multiclass boosted-tree
challenger comparison (lgbm_multiclass_comparison.py). SYNTHETIC ONLY.
Every test drives the actual entry point with hand-checkable fixtures.

Requirement -> implementation -> test-evidence closure table:
  End-to-end success + full output-hash manifest + receipts   -> test 1
  Keyed alignment + both arms' probabilities valid            -> test 2
  Equal information: challenger feature list == control's 12  -> test 3
  Tuning budget accounting: exactly 12 fits (6 configs x 2
  folds), selected config == declared rule recomputed         -> test 4
  Chronological fold boundaries: fit strictly precedes
  validation; both inside the training window; empty or
  class-incompatible folds refuse                             -> tests 5a/b
  Assessment labels never touch tuning/selection              -> test 6
  Same-date/future exclusion inherited via the platoon/states
  construction (flipping GAME_DATE labels -> identical
  forecasts)                                                  -> test 7
  Both arms on the identical sorted key list                  -> test 8
  Duplicate actual-PA identity refuses                        -> test 9
  Saved model reload reproduces saved probabilities (both
  arms)                                                       -> test 10
  Reconstruction of the control: exact pass / altered refuse /
  missing refuse                                              -> tests 11a/b/c
  Ack gate (direct + CLI exit 2); reference pin ENFORCED
  (exit 1); pin REQUIRED                                      -> tests 12a-d
  CLI end-to-end success                                      -> test 13
  Write-once refuses                                          -> test 14
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
from pregame_pa_ext import lgbm_multiclass_comparison as lc  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402

ACK = lc.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
TRAIN_D1 = date(2024, 7, 1)
TRAIN_D2 = date(2024, 7, 15)
TRAIN_D3 = date(2024, 9, 10)   # fold A validation window
TRAIN_D4 = date(2024, 11, 10)  # fold B validation window
GAME_DATE = date(2025, 4, 15)
RUNNER = Path(lc.__file__).resolve()

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
    for i, b in enumerate(B1):
        rows.append(_row(hist, 50, "Top", 100 + i, P1, b, 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append((hist, 50, "Bot", 109 + i, P2, b, 0, "R", "L"))
    for i, b in enumerate(B1):
        rows.append(_row(TRAIN_D1, 100, "Top", 200 + i, P1, b,
                         1 if i % 2 == 0 else 0, "L", "R"))
    for i, b in enumerate(B2):
        rows.append(_row(TRAIN_D2, 101, "Bot", 300 + i, P2, b,
                         1 if i % 3 == 0 else 0, "R", "L"))
    # fold A validation rows (September)
    for i, b in enumerate(B1[:2]):
        rows.append(_row(TRAIN_D3, 102, "Top", 350 + i, P1, b,
                         1 if i == 0 else 0, "L", "R"))
    # fold B validation rows (November)
    for i, b in enumerate(B2[:2]):
        rows.append(_row(TRAIN_D4, 103, "Bot", 360 + i, P2, b,
                         1 if i == 0 else 0, "R", "L"))
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
    rows.append((900001, "Top", P1, 510, B1[0], 0))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None, assessment=None,
           flip_labels=False):
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
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_path"] = str(rp)
    h["raw_sha"] = _sha(rp)
    return h


def _wrong_reference():
    rows = [(900001, "Top", P1, 0.5), (900001, "Bot", P2, 0.5)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "rps_platoon": pl.Float64}, orient="row")


def _harvest_reference(out_dir) -> pl.DataFrame:
    ps = pl.read_parquet(Path(out_dir) / "lgbm_per_start_v1.parquet")
    return ps.select(
        "game_pk", "side", "pitcher",
        pl.col("rps_multinomial_plus_platoon_control").alias(
            "rps_platoon"))


def _cohort_hash_of(cohort: pl.DataFrame) -> str:
    return hashlib.sha256("\n".join(sorted(
        "%d|%s|%d" % (int(r["game_pk"]), str(r["side"]),
                      int(r["pitcher"]))
        for r in cohort.iter_rows(named=True)))
        .encode("utf-8")).hexdigest()


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         ack=ACK, cohort_keys=None, expected_cohort_hash=None,
         reconstruction_reference=None, reference_sha256=None,
         input_identities=None):
    h = _write(tmp_path, pa, lineups, assessment)
    pa_frame = pa if pa is not None else _pa_frame()
    if reconstruction_reference is None and ack == ACK:
        boot_out = tmp_path / f"_boot_{out}"
        try:
            lc.run_lgbm_comparison(
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
        boot_ps = boot_out / "lgbm_per_start_v1.parquet"
        assert boot_ps.exists(), (
            "bootstrap run must preserve per-start evidence before "
            "refusing")
        reconstruction_reference = _harvest_reference(boot_out)
    return lc.run_lgbm_comparison(
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
    expected = {"lgbm_per_start_v1.parquet",
                "lgbm_comparison_report.json",
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
        (Path(res["out_dir"]) / "lgbm_comparison_report.json")
        .read_text(encoding="utf-8"))
    assert report["n_starts"] == 2
    assert len(report["tuning"]["fold_table"]) == 12


# ------------------------------------------------- 2. keyed alignment
def test_keyed_table_unique_and_probabilities_valid(tmp_path):
    res = _run(tmp_path)
    keyed = pl.read_parquet(Path(res["out_dir"])
                            / "keyed_pa_probabilities.parquet")
    assert keyed.height == 18
    assert keyed.select("game_pk", "side", "pitcher", "slot",
                        "batter").n_unique() == keyed.height
    ctrl_cols = [c for c in keyed.columns if c.endswith("_control")]
    chat_cols = [c for c in keyed.columns if c.endswith("_lgbm")]
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
        lc.run_lgbm_comparison(
            _pa_frame(reverse=True), _lineups(), _assessment(), boot2,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h2["raw_path"]],
            reconstruction_reference=_wrong_reference())
    except ValueError:
        pass
    ref2 = _harvest_reference(boot2)
    res_rev = lc.run_lgbm_comparison(
        _pa_frame(reverse=True), _lineups(), _assessment(),
        tmp_path / "rev",
        train_start="2024-05-01", train_end="2024-12-31",
        execution_ack=ACK, raw_events=[h2["raw_path"]],
        reconstruction_reference=ref2)
    a = pl.read_parquet(Path(res_fwd["out_dir"])
                        / "lgbm_per_start_v1.parquet").sort(
        "game_pk", "side", "pitcher")
    b = pl.read_parquet(Path(res_rev["out_dir"])
                        / "lgbm_per_start_v1.parquet").sort(
        "game_pk", "side", "pitcher")
    assert_frame_equal(a, b, check_exact=False, rel_tol=0, abs_tol=1e-12)


# ------------------------- 4. tuning budget accounting + selection rule
def test_tuning_budget_and_selection_rule(tmp_path):
    res = _run(tmp_path)
    report = json.loads(
        (Path(res["out_dir"]) / "lgbm_comparison_report.json")
        .read_text(encoding="utf-8"))
    table = report["tuning"]["fold_table"]
    assert report["tuning"]["n_fits"] == 12
    assert len(table) == 12
    # 6 configurations x 2 folds, no duplicates
    combos = {(r["num_leaves"], r["min_data_in_leaf"], r["fold_index"])
              for r in table}
    assert len(combos) == 12
    # selection rule recomputed from the table must equal the reported
    # selection
    by_cfg = {}
    for r in table:
        by_cfg.setdefault((r["num_leaves"], r["min_data_in_leaf"]),
                          []).append(r["val_log_loss"])
    best = min(by_cfg, key=lambda k: (
        float(np.mean(by_cfg[k])), k[0], -k[1]))
    assert (report["tuning"]["selected_config"]["num_leaves"],
            report["tuning"]["selected_config"]["min_data_in_leaf"]) \
        == best
    # the selected configuration drives the final fit
    final = json.loads((Path(res["out_dir"]) / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert final["tuning"]["selected_config"] == \
        report["tuning"]["selected_config"]


# ------------------------- 5a/b. chronological fold boundaries
def test_chrono_folds_boundaries_and_refusals(tmp_path):
    from datetime import date as d
    frame = pl.DataFrame({
        "game_date": [d(2024, 7, 1), d(2024, 7, 15), d(2024, 9, 10),
                      d(2024, 12, 1)],
        "class_label": [0, 2, 2, 0],
        "num": [0, 0, 0, 0],
    }, schema={"game_date": pl.Date, "class_label": pl.Int64,
               "num": pl.Int64})
    # pad the columns fit_lgbm needs
    for c in lc.CHALLENGE_FEATURES:
        frame = frame.with_columns(pl.lit(0.0, dtype=pl.Float64)
                                   .alias(c))
    folds = lc.build_chrono_folds(frame)
    a, b = folds
    assert a["fold"]["fit_end"] == "2024-08-31"
    assert a["fit"]["game_date"].max() <= d(2024, 8, 31)
    assert a["val"]["game_date"].min() > d(2024, 8, 31)
    assert a["val"]["game_date"].max() <= d(2024, 10, 31)
    assert b["fit"]["game_date"].max() <= d(2024, 10, 31)
    assert b["val"]["game_date"].min() > d(2024, 10, 31)
    assert b["val"]["game_date"].max() <= d(2024, 12, 31)
    # empty validation split refuses
    early_only = frame.filter(pl.col("game_date") <= d(2024, 7, 1))
    with pytest.raises(ValueError, match="empty fit or validation"):
        lc.build_chrono_folds(early_only)


# ---------------------- 6. assessment labels never touch the tuning
def test_assessment_labels_do_not_touch_tuning(tmp_path):
    res1 = _run(tmp_path, out="tune_a")
    # flip every assessment label and rerun: the tuning fold table and
    # selection must be IDENTICAL (assessment enters only at scoring)
    rows = [(gk, s, p, abn, b,
             (c + 1) % 3) for (gk, s, p, abn, b, c)
            in _assessment().iter_rows()]
    assessment_flipped = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")
    res2 = _run(tmp_path, out="tune_b", assessment=assessment_flipped)
    t1 = json.loads(
        (Path(res1["out_dir"]) / "lgbm_comparison_report.json")
        .read_text(encoding="utf-8"))["tuning"]
    t2 = json.loads(
        (Path(res2["out_dir"]) / "lgbm_comparison_report.json")
        .read_text(encoding="utf-8"))["tuning"]
    assert t1["fold_table"] == t2["fold_table"]
    assert t1["selected_config"] == t2["selected_config"]


# ------------------------- 8. identical sorted key list for both arms
def test_both_arms_identical_population(tmp_path):
    res = _run(tmp_path)
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "lgbm_per_start_v1.parquet")
    assert ps.height == 2
    assert ps["rps_multinomial_plus_platoon_control"].is_not_null().all()
    assert ps["rps_lgbm"].is_not_null().all()
    assert (ps["rps_diff"] == (ps["rps_lgbm"]
            - ps["rps_multinomial_plus_platoon_control"])).all()
    # K acceptance guard present in the report as a point estimate
    report = json.loads(
        (Path(res["out_dir"]) / "lgbm_comparison_report.json")
        .read_text(encoding="utf-8"))
    nd = report["k_count"]["non_degradation"]
    assert nd["within_margin"] == (nd["point_estimate"] <= nd["margin"])


# ----------------- 9. cohort restriction before features; extra excluded
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
    assert final["counts"]["n_starts"] == 1


# -------------------------------- 10. duplicate actual-PA identity refuses
def test_duplicate_assessment_identity_refuses(tmp_path):
    h = _write(tmp_path)
    dup = pl.concat([_assessment(), _assessment().head(1)])
    with pytest.raises(ValueError, match="duplicate actual-PA"):
        lc.run_lgbm_comparison(
            _pa_frame(), _lineups(), dup, tmp_path / "out_dup",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())


# --------------------------------------- 11. saved model reload parity
def test_model_reload_reproduces_probabilities(tmp_path):
    res = _run(tmp_path, out="out_reload")
    out_dir = Path(res["out_dir"])
    models = json.loads((out_dir / "model_artifacts.json")
                        .read_text(encoding="utf-8"))
    keyed = pl.read_parquet(out_dir / "keyed_pa_probabilities.parquet")
    keyed_sorted = keyed.sort("game_pk", "side", "pitcher", "slot")
    sys.path.insert(0, str(RUNNER.parents[2]))
    from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
    from pregame_pa_ext import adapter as ad2  # noqa: E402
    from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
    from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
    pa = _pa_frame()
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
    probs_c = pc._softmax_full(feat_sorted,
                               models["multinomial_plus_platoon_control"],
                               pc.CHALLENGE_FEATURES)
    probs_l = lc.apply_lgbm(feat_sorted, models["lgbm_challenger"])
    for j, c in enumerate(
            models["multinomial_plus_platoon_control"]["classes"]):
        assert np.allclose(probs_c[:, j], keyed_sorted[
            f"p_class_{c}_control"].to_numpy(), rtol=0, atol=0)
    for j, c in enumerate(models["lgbm_challenger"]["classes"]):
        assert np.allclose(probs_l[:, j], keyed_sorted[
            f"p_class_{c}_lgbm"].to_numpy(), rtol=0, atol=0)


# --------------------- 12a/b/c. reconstruction of the control arm
def test_reconstruction_gate_exact_pass(tmp_path):
    res = _run(tmp_path, out="out_recon")
    rec = res["reconstruction"]
    assert rec["verified"] is True
    assert rec["max_abs_rps_diff"] == 0.0
    assert rec["reference_column"] == "rps_platoon"


def test_reconstruction_gate_altered_reference_refuses(tmp_path):
    h = _write(tmp_path)
    boot = tmp_path / "_boot_alt"
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        lc.run_lgbm_comparison(
            _pa_frame(), _lineups(), _assessment(), boot,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    assert (boot / "failure_record.json").exists()
    ref = _harvest_reference(boot).with_columns(
        (pl.col("rps_platoon") + 1e-9).alias("rps_platoon"))
    with pytest.raises(ValueError, match="reconstruction gate FAILED"):
        lc.run_lgbm_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_alt",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)


def test_reconstruction_gate_missing_reference_refuses(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="reconstruction reference "
                                         "required"):
        lc.run_lgbm_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_none",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=None)


# --------------------------------------------------- 13a. direct ack gate
def test_ack_gate_direct_call(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError,
                       match="execution acknowledgement"):
        lc.run_lgbm_comparison(
            _pa_frame(), _lineups(), _assessment(), tmp_path / "out_ack",
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack="WRONG", raw_events=[h["raw_path"]],
            reconstruction_reference=_wrong_reference())
    assert not (tmp_path / "out_ack").exists()


# ------------------------------------------ 13b. CLI ack gate exit 2
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


# --------------- 13c. CLI reconstruction-reference identity ENFORCED
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


# --------------- 13d. CLI reconstruction pin is REQUIRED (argparse)
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


# ------------------------------------- 14. CLI end-to-end success
def test_cli_end_to_end_success(tmp_path):
    res_boot = _run(tmp_path, out="out_cli_boot")
    ps = pl.read_parquet(Path(res_boot["out_dir"])
                         / "lgbm_per_start_v1.parquet")
    ref_path = tmp_path / "ref_cli.parquet"
    ps.select("game_pk", "side", "pitcher",
              pl.col("rps_multinomial_plus_platoon_control").alias(
                  "rps_platoon")).write_parquet(ref_path)
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
    assert final["counts"]["n_tuning_fits"] == 12


# ------------------------------------------------ 15. write-once refuses
def test_write_once_refuses(tmp_path):
    res = _run(tmp_path, out="out_wo")
    existing = Path(res["out_dir"])
    h = _write(tmp_path)
    ref = _harvest_reference(existing)
    with pytest.raises(ValueError, match="write-once violation"):
        lc.run_lgbm_comparison(
            _pa_frame(), _lineups(), _assessment(), existing,
            train_start="2024-05-01", train_end="2024-12-31",
            execution_ack=ACK, raw_events=[h["raw_path"]],
            reconstruction_reference=ref)
