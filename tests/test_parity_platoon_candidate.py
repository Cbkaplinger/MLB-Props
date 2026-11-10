"""Synthetic tests for the candidate-parity entry point
(parity_platoon_candidate_v1.py). SYNTHETIC ONLY: every artifact is a
temporary synthetic JSON/Parquet file built in pytest tmp_path; the
reference forecasts are constructed through the registered construction
seams (NOT through the wrapper under test), so a successful comparison
is a real end-to-end parity exercise. No real/private input reads, no
inference on historical data, no fitting, no R3/2026 access.

Requirement -> implementation -> test-evidence closure table:
  Successful known comparison (exact parity through the entry
  point; reference built independently from the registered
  seams)                                                    -> test 1
  Wrong reference-receipt identity refused BEFORE decode
  (destination never created)                               -> test 2
  Existing destination refused (write-once)                 -> test 3
  Duplicate comparison identities refused                   -> test 4
  Missing/extra comparison keys refused (no inner-join)     -> test 5
  Missing BF date refused                                   -> test 6
  Malformed BF categories refused                           -> test 7
  Invalid BF distribution refused                           -> test 8
  Numerical mismatch stops the action; exact observed
  difference reported; no success receipt left              -> test 9
  Nonfinite reference values refused before differences     -> test 10
  CLI success and ack-gate behavior                         -> test 11
   receipt_initial mutation detected BEFORE success
   publication (finalization ordering regression)            -> test 12
   Finalization-write failure leaves NO valid COMPLETED
   receipt (atomic publication regression)                   -> test 13
   Control arm (multinomial_control): successful known
   comparison against its registered seam + explicit
   arm_selection receipt                                     -> test 14
   Unsupported arm selection refuses before any write        -> test 15
   CLI --arm selects the control arm; default stays
   challenger                                                -> test 16
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import label_free_inference as lfi  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
from pregame_pa_ext import parity_platoon_candidate_v1 as pp  # noqa: E402

FEATURES = pc.CHALLENGE_FEATURES
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
HIST1, HIST2, REQ = date(2024, 5, 10), date(2025, 4, 20), date(2025, 5, 1)
STARTS = [(900201, "Top", P1), (900201, "Bot", P2)]
EVENTS = ["strikeout", "walk", "field_out", "single"]  # classes 0..3
BF_V = None


def _bf_vector():
    v = np.zeros(37)
    v[:35] = 0.02
    v[35] = 0.20
    v[36] = 0.10  # sums to 1.0
    return v


def _pa_rows():
    rows = []
    for gi, (gk, side, p) in enumerate(STARTS):
        batters = B1 if side == "Top" else B2
        stand, throws = ("L", "R") if side == "Top" else ("R", "L")
        for dt, gkx in ((HIST1, 41), (HIST2, 42), (REQ, gk)):
            for i, b in enumerate(batters):
                cls = (i + gi) % 4
                rows.append((dt, gkx, 100 + i, p, b,
                             1 if cls == 0 else 0, stand, throws))
    return rows


PA_SCHEMA = {"game_date": pl.Date, "game_pk": pl.Int64,
             "at_bat_number": pl.Int64, "pitcher": pl.Int64,
             "batter": pl.Int64, "y": pl.Int64, "stand": pl.Utf8,
             "p_throws": pl.Utf8}


def _raw_rows(pa, gks):
    df = pa.filter(pl.col("game_pk").is_in(gks))
    ev = [EVENTS[(r["at_bat_number"] + r["batter"]) % 4]
          for r in df.iter_rows(named=True)]
    return df.select("game_pk", "at_bat_number",
                     "batter").with_columns(
        pl.Series("events", ev))


def _model():
    n = len(FEATURES)
    return {
        "features": FEATURES,
        "classes": [0, 1, 2, 3],
        "coef": [[round(0.011 * (c + 1) * (j + 2), 6) for j in range(n)]
                 for c in range(4)],
        "intercept": [-0.30, -0.10, 0.10, 0.30],
        "mean": [0.0] * n,
        "scale": [1.0] * n,
    }


def _control_model():
    n = len(pc.FEATURES)
    return {
        "features": pc.FEATURES,
        "classes": [0, 1, 2, 3],
        "coef": [[round(0.013 * (c + 1) * (j + 1), 6) for j in range(n)]
                 for c in range(4)],
        "intercept": [-0.35, -0.05, 0.15, 0.25],
        "mean": [0.0] * n,
        "scale": [1.0] * n,
    }


def _lineups():
    rows = [(gk, side, p, REQ, True,
             *(B1 if side == "Top" else B2))
            for gk, side, p in STARTS]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{s}": pl.Int64 for s in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _reference(pa_labeled, model, arm):
    """Build the saved-reference forecasts through the REGISTERED
    construction seams (independent of the wrapper under test). One
    arm at a time; the challenger arm consumes the platoon family,
    the control arm consumes the 8 base features only."""
    lineups = _lineups()
    long, _ = ad.projected_long(lineups)
    req_dates = sorted(long["game_date"].unique().to_list())
    p, b, lg, _ = fv.build_v2_states(pa_labeled, req_dates)
    feat = ad.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk",
                    "side", "slot"), p, b, lg)
    if arm == pp.ARM_CHALLENGER:
        rates = pf.build_split_class_rates(pa_labeled, req_dates,
                                           alpha=pc.ALPHA, n_classes=4)
        hands = pf.forecast_matchup_hands(
            pa_labeled, feat.select(pl.col("batter"), pl.col("pitcher"),
                                    pl.col("game_date").alias("cutoff")))
        feat = (feat.join(hands.select("batter", "pitcher", "cutoff",
                                       "f_stand", "f_hand"),
                          left_on=["batter", "pitcher", "game_date"],
                          right_on=["batter", "pitcher", "cutoff"],
                          how="left")
                .with_columns(pl.col("game_date").alias("cutoff"),
                              pl.col("f_stand").alias("stand"),
                              pl.col("f_hand").alias("p_throws"))
                .drop(["f_stand", "f_hand"]))
        feat = pf.attach_platoon_features(feat, rates, n_classes=4)
    feat = feat.select(lfi.KEY_COLS + list(model["features"]))
    probs = pc._softmax_full(feat, model, model["features"])
    suffix = pp.SUPPORTED_ARMS[arm]["keyed_suffix"]
    pmf_col = pp.SUPPORTED_ARMS[arm]["pmf_column"]
    keyed = feat.select(lfi.KEY_COLS)
    for j, c in enumerate(model["classes"]):
        keyed = keyed.with_columns(
            pl.Series(f"p_class_{c}{suffix}", probs[:, j]))
    # start-grain PMFs from the same keyed probabilities
    vec_by_date = {REQ: _bf_vector()}
    pmf_rows = []
    for gk, side, p in STARTS:
        rows = keyed.filter((pl.col("game_pk") == gk)
                            & (pl.col("side") == side)
                            & (pl.col("pitcher") == p)).sort("slot")
        p9 = rows[f"p_class_0{suffix}"].to_numpy()
        pmf = ad.start_count_pmfs(p9, p9, vec_by_date[REQ])[
            "pmf_h3_raw"]
        for k in range(24):
            pmf_rows.append({"game_pk": gk, "side": side,
                             "pitcher": p, "bucket": k,
                             pmf_col: float(pmf[k])})
    return keyed, pl.DataFrame(pmf_rows)


def _write_world(tmp: Path, *, drop_bf_date=False, drop_bf_cat=False,
                 break_bf_sum=False):
    d = tmp / "in"
    ref = tmp / "ref"
    d.mkdir(parents=True)
    ref.mkdir(parents=True)
    pa = pl.DataFrame(_pa_rows(), schema=PA_SCHEMA, orient="row")
    pa_path = d / "pa.parquet"
    pa.write_parquet(pa_path)
    raw24 = _raw_rows(pa, [41])
    raw25 = _raw_rows(pa, [42, 900201])
    r24, r25 = d / "raw2024.parquet", d / "raw2025.parquet"
    raw24.write_parquet(r24)
    raw25.write_parquet(r25)
    lu = _lineups()
    lu_path = d / "lineups.parquet"
    lu.write_parquet(lu_path)
    ck = pl.DataFrame(STARTS, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64},
        orient="row")
    ck_path = d / "cohort_keys.parquet"
    ck.write_parquet(ck_path)
    cohort_hash = bk._cohort_hash(list(STARTS))

    pa_labeled, _ = seb.attach_terminal_event_labels(
        pa, [r24, r25])
    model = _model()
    ctrl_model = _control_model()
    # both arms' saved forecasts live in ONE platoon_comparison
    # reference dir (matches the registered layout)
    keyed_p, pmf_p = _reference(pa_labeled, model, pp.ARM_CHALLENGER)
    keyed_c, pmf_c = _reference(pa_labeled, ctrl_model, pp.ARM_CONTROL)
    keyed = keyed_p.join(keyed_c, on=lfi.KEY_COLS, how="inner")
    pmf = pmf_p.join(pmf_c, on=["game_pk", "side", "pitcher", "bucket"],
                     how="inner")

    bf_rows = []
    bf_dates = [date(2025, 5, 2)] if drop_bf_date else [REQ]
    for dt in bf_dates:
        v = _bf_vector()
        if break_bf_sum:
            v = v * 0.9
        cats = [j for j in range(37)
                if not (drop_bf_cat and j == 5)]
        for j in cats:
            bf_rows.append({"cutoff_date": str(dt), "bf_category": j,
                            "bf37_w0_pooled": float(v[j])})
    bf_path = ref / "bf37_pooled_by_date_v1.parquet"
    pl.DataFrame(bf_rows).write_parquet(bf_path)

    model_path = ref / "model_artifacts.json"
    model_path.write_text(json.dumps(
        {"platoon_challenger": model,
         "multinomial_control": ctrl_model}, indent=1),
        encoding="utf-8")
    keyed_path = ref / "keyed_pa_probabilities.parquet"
    keyed.write_parquet(keyed_path)
    pmf_path = ref / "k_pmf_per_start_v1.parquet"
    pmf.write_parquet(pmf_path)

    receipt = {"outputs": {
        "model_artifacts.json": pp._sha_file(model_path),
        "keyed_pa_probabilities.parquet": pp._sha_file(keyed_path),
        "k_pmf_per_start_v1.parquet": pp._sha_file(pmf_path),
        "bf37_pooled_by_date_v1.parquet": pp._sha_file(bf_path)}}
    receipt_path = ref / "receipt_final.json"
    receipt_path.write_text(json.dumps(receipt, indent=1),
                            encoding="utf-8")
    return {
        "pa": str(pa_path), "lineups": str(lu_path),
        "cohort": str(ck_path),
        "raws": [str(r24), str(r25)],
        "ref": str(ref),
        "ref_receipt": pp._sha_file(receipt_path),
        "pa_sha": pp._sha_file(pa_path),
        "lu_sha": pp._sha_file(lu_path),
        "raw_shas": [pp._sha_file(r24), pp._sha_file(r25)],
        "cohort_hash": cohort_hash,
        "model": model,
    }


def _run(tmp: Path, world, out_name="out", **overrides):
    out = tmp / out_name
    kwargs = dict(
        pa_path=world["pa"], lineups_path=world["lineups"],
        cohort_keys_path=world["cohort"],
        raw_event_paths=world["raws"], reference_dir=world["ref"],
        expected_reference_receipt_sha256=world["ref_receipt"],
        expected_pa_sha256=world["pa_sha"],
        expected_lineups_sha256=world["lu_sha"],
        expected_raw_event_sha256s=world["raw_shas"],
        expected_cohort_hash=world["cohort_hash"],
        out_dir=str(out), execution_ack=pp.EXECUTION_ACK_TOKEN)
    kwargs.update(overrides)
    return out, pp.run_parity(**kwargs)


# ------------------- 1. successful known comparison
def test_successful_comparison(tmp_path):
    world = _write_world(tmp_path)
    out, comp = _run(tmp_path, world)
    assert comp["within_tolerance"] is True
    assert comp["pa_grain_max_abs_diff"] <= 1e-12
    assert comp["pmf_grain_max_abs_diff"] <= 1e-12
    assert comp["n_starts"] == 2
    assert comp["n_pa_rows"] == 18
    assert comp["n_pmf_rows"] == 48
    assert (out / "receipt_final.json").exists()
    assert (out / "parity_comparison.json").exists()
    assert not (out / "failure_record.json").exists()


# --------- 2. wrong reference-receipt identity refused pre-decode
def test_wrong_reference_receipt_refused(tmp_path):
    world = _write_world(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="reference receipt identity"):
        _run(tmp_path, world, out_name="out",
             expected_reference_receipt_sha256="0" * 64)
    assert not out.exists()


# ------------------- 3. existing destination refused
def test_existing_destination_refused(tmp_path):
    world = _write_world(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError, match="destination exists"):
        _run(tmp_path, world)
    assert not (out / "receipt_final.json").exists()


# ------------------- 4. duplicate comparison identities refused
def test_duplicate_reference_keys_refused(tmp_path):
    world = _write_world(tmp_path)
    kp = Path(world["ref"]) / "keyed_pa_probabilities.parquet"
    kf = pl.read_parquet(kp)
    pl.concat([kf, kf.head(1)]).write_parquet(kp)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="duplicate identity key"):
        _run(tmp_path, world)


# ------------------- 5. missing / extra comparison keys refused
def test_missing_reference_key_refused(tmp_path):
    world = _write_world(tmp_path)
    kp = Path(world["ref"]) / "keyed_pa_probabilities.parquet"
    pl.read_parquet(kp).head(17).write_parquet(kp)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="reference keyed row count"):
        _run(tmp_path, world)


def test_extra_reference_key_refused(tmp_path):
    world = _write_world(tmp_path)
    kp = Path(world["ref"]) / "keyed_pa_probabilities.parquet"
    kf = pl.read_parquet(kp)
    # swap one row's batter id (height preserved) so the key-SET
    # equality gate fires rather than the row-count gate
    kf = kf.with_columns(
        pl.when(pl.col("slot") == 1)
        .then(pl.lit(999999))
        .otherwise(pl.col("batter"))
        .alias("batter"))
    kf.write_parquet(kp)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="PA-grain key sets differ"):
        _run(tmp_path, world)


# ------------------- 6-8. workload mapping refusals
def test_missing_bf_date_refused(tmp_path):
    world = _write_world(tmp_path, drop_bf_date=True)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="absent from the saved BF"):
        _run(tmp_path, world)


def test_malformed_bf_categories_refused(tmp_path):
    world = _write_world(tmp_path, drop_bf_cat=True)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="categories malformed"):
        _run(tmp_path, world)


def test_invalid_bf_distribution_refused(tmp_path):
    world = _write_world(tmp_path, break_bf_sum=True)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="distribution invalid"):
        _run(tmp_path, world)


# --------- 9. numerical mismatch stops; no success receipt
def test_numerical_mismatch_stops(tmp_path):
    world = _write_world(tmp_path)
    kp = Path(world["ref"]) / "keyed_pa_probabilities.parquet"
    kf = pl.read_parquet(kp)
    kf = kf.with_columns(
        pl.when(pl.col("slot") == 1)
        .then(pl.col("p_class_0_platoon") + 1e-9)
        .otherwise(pl.col("p_class_0_platoon"))
        .alias("p_class_0_platoon"))
    kf.write_parquet(kp)
    _rewrite_receipt(world)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="PARITY MISMATCH"):
        _run(tmp_path, world)
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    assert not (out / "parity_comparison.json").exists()


# --------- 10. nonfinite reference values refused
def test_nonfinite_reference_refused(tmp_path):
    world = _write_world(tmp_path)
    kp = Path(world["ref"]) / "keyed_pa_probabilities.parquet"
    kf = pl.read_parquet(kp)
    kf = kf.with_columns(
        pl.when(pl.col("slot") == 1)
        .then(float("nan"))
        .otherwise(pl.col("p_class_1_platoon"))
        .alias("p_class_1_platoon"))
    kf.write_parquet(kp)
    _rewrite_receipt(world)
    with pytest.raises(ValueError, match="nonfinite"):
        _run(tmp_path, world)


# ------------------- 11. CLI success and ack gate
def test_cli_success_and_ack_gate(tmp_path):
    world = _write_world(tmp_path)
    argv = ["--pa-source", world["pa"], "--lineups", world["lineups"],
            "--cohort-keys", world["cohort"],
            "--raw-events", ",".join(world["raws"]),
            "--reference-dir", world["ref"],
            "--expected-reference-receipt-sha256",
            world["ref_receipt"],
            "--expected-pa-sha256", world["pa_sha"],
            "--expected-lineups-sha256", world["lu_sha"],
            "--expected-raw-event-sha256s",
            ",".join(world["raw_shas"]),
            "--expected-cohort-hash", world["cohort_hash"],
            "--out-dir", str(tmp_path / "cli_out"),
            "--execution-ack", pp.EXECUTION_ACK_TOKEN]
    assert pp.main(argv) == 0
    assert (tmp_path / "cli_out" / "receipt_final.json").exists()
    bad = [a for a in argv]
    bad[bad.index("--execution-ack") + 1] = "WRONG-TOKEN"
    with pytest.raises(ValueError, match="execution acknowledgement"):
        pp.main(bad)


# --------- 12. receipt_initial mutation detected BEFORE publication
def test_receipt_initial_mutation_detected_before_publication(
        tmp_path, monkeypatch):
    world = _write_world(tmp_path)
    out = tmp_path / "out"
    orig = pp.lp.run_prediction

    def mutate_then_predict(model, pa, lineups, bf):
        # mutate receipt_initial mid-run, before finalization
        ri = out / "receipt_initial.json"
        ri.write_text(ri.read_text(encoding="utf-8") + "\n",
                      encoding="utf-8")
        return orig(model, pa, lineups, bf)

    monkeypatch.setattr(pp.lp, "run_prediction", mutate_then_predict)
    with pytest.raises(ValueError, match="immutability check FAILED"):
        _run(tmp_path, world)
    assert not (out / "receipt_final.json").exists()
    assert not (out / "parity_comparison.json").exists()
    fr = json.loads(
        (out / "failure_record.json").read_text(encoding="utf-8"))
    assert fr["failure_stage"] == "finalization"
    assert "receipt_initial.json" in fr["files_written"]
    assert "receipt_final.json" not in fr["files_written"]


# --------- 13. finalization-write failure leaves NO COMPLETED receipt
def test_finalization_write_failure_leaves_no_completed_receipt(
        tmp_path, monkeypatch):
    world = _write_world(tmp_path)
    out = tmp_path / "out"
    real = pp._write_json

    def failing_write(path, payload):
        if Path(path).name == "receipt_final.json":
            raise OSError("simulated finalization write failure")
        return real(path, payload)

    monkeypatch.setattr(pp, "_write_json", failing_write)
    with pytest.raises(OSError, match="simulated finalization"):
        _run(tmp_path, world)
    # parity_comparison was published; receipt_final was not
    assert (out / "parity_comparison.json").exists()
    assert not (out / "receipt_final.json").exists()
    assert not (out / "receipt_final.json.tmp").exists()
    fr = json.loads(
        (out / "failure_record.json").read_text(encoding="utf-8"))
    assert fr["failure_stage"] == "finalization"
    assert "parity_comparison.json" in fr["files_written"]
    assert "receipt_final.json" not in fr["files_written"]


# --------- 14. control arm: successful known comparison
def test_control_arm_comparison(tmp_path):
    world = _write_world(tmp_path)
    out, comp = _run(tmp_path, world, out_name="out_ctrl",
                     arm=pp.ARM_CONTROL)
    assert comp["within_tolerance"] is True
    assert comp["pa_grain_max_abs_diff"] <= 1e-12
    assert comp["pmf_grain_max_abs_diff"] <= 1e-12
    assert comp["n_starts"] == 2
    assert comp["n_pa_rows"] == 18
    assert comp["n_pmf_rows"] == 48
    assert comp["column_mappings"]["pmf"] == {
        "pmf_multinomial_control": "pmf_h3_raw"}
    assert sorted(comp["column_mappings"]["keyed"].values()) == \
        [f"p_class_{c}" for c in range(4)]
    ri = json.loads(
        (out / "receipt_initial.json").read_text(encoding="utf-8"))
    assert ri["arm_selection"] == {
        "arm": "multinomial_control",
        "model_key": "multinomial_control",
        "keyed_suffix": "_control",
        "pmf_column": "pmf_multinomial_control"}
    assert (out / "receipt_final.json").exists()
    assert (out / "parity_comparison.json").exists()
    assert not (out / "failure_record.json").exists()


# --------- 15. unsupported arm selection refuses pre-write
def test_unsupported_arm_refused(tmp_path):
    world = _write_world(tmp_path)
    out = tmp_path / "out_bad"
    with pytest.raises(ValueError, match="unsupported arm"):
        _run(tmp_path, world, out_name="out_bad", arm="binary_k")
    assert not out.exists()


# --------- 16. CLI --arm selects the control arm
def test_cli_arm_selection(tmp_path):
    world = _write_world(tmp_path)
    argv = ["--arm", pp.ARM_CONTROL,
            "--pa-source", world["pa"], "--lineups", world["lineups"],
            "--cohort-keys", world["cohort"],
            "--raw-events", ",".join(world["raws"]),
            "--reference-dir", world["ref"],
            "--expected-reference-receipt-sha256",
            world["ref_receipt"],
            "--expected-pa-sha256", world["pa_sha"],
            "--expected-lineups-sha256", world["lu_sha"],
            "--expected-raw-event-sha256s",
            ",".join(world["raw_shas"]),
            "--expected-cohort-hash", world["cohort_hash"],
            "--out-dir", str(tmp_path / "cli_ctrl"),
            "--execution-ack", pp.EXECUTION_ACK_TOKEN]
    assert pp.main(argv) == 0
    final = json.loads(
        (tmp_path / "cli_ctrl" / "receipt_final.json")
        .read_text(encoding="utf-8"))
    assert final["arm_selection"]["arm"] == "multinomial_control"


# ------------------- helper: rewrite receipt after artifact edits
def _rewrite_receipt(world):
    ref = Path(world["ref"])
    outputs = {}
    for name in ("model_artifacts.json",
                 "keyed_pa_probabilities.parquet",
                 "k_pmf_per_start_v1.parquet",
                 "bf37_pooled_by_date_v1.parquet"):
        outputs[name] = pp._sha_file(ref / name)
    receipt_path = ref / "receipt_final.json"
    receipt_path.write_text(json.dumps({"outputs": outputs}, indent=1),
                            encoding="utf-8")
    world["ref_receipt"] = pp._sha_file(receipt_path)
