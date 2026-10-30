"""Synthetic end-to-end tests for the pregame multiclass baseline
(pregame_multiclass_baseline.py) under the APPROVED forecast-cutoff
state contract (forecast_states_v2). SYNTHETIC ONLY: no real data, no
real fitting/scoring. Every test drives the actual entry point."""
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

from pregame_pa_ext import forecast_states_v2 as fsv  # noqa: E402
from pregame_pa_ext import pregame_multiclass_baseline as pm  # noqa: E402
from pregame_pa_ext import adapter as ad  # noqa: E402

ACK = pm.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001, 800002, 800003, 800004, 800005, 800006, 800007, 800008,
      800009]
B2 = [800101, 800102, 800103, 800104, 800105, 800106, 800107, 800108,
      800109]
TRAIN_D1 = date(2024, 7, 1)
TRAIN_D2 = date(2024, 7, 15)
GAME_DATE = date(2024, 8, 15)
FUTURE = date(2024, 9, 1)

EVENTS = {0: "strikeout", 1: "walk", 2: "field_out", 3: "single"}


def _pa_rows():
    """Completed-PA source. A declared pre-training history window
    (2024-06-20 rows) precedes the training dates; training rows are
    strictly before the 08-15 forecast date; every event maps into the
    four-class taxonomy."""
    rows = []
    ab = [0]
    hist = date(2024, 5, 20)
    # declared pre-training history: every entity has eligible prior rows
    for b in B1:
        rows.append((hist, 50, 0, P1, b, "field_out", 0))
    for b in B2:
        rows.append((hist, 50, 0, P2, b, "single", 0))
    # pitcher P1: mostly strikeouts pre-cutoff; batters mixed
    def nxt():
        ab[0] += 1
        return ab[0]
    for i, b in enumerate(B1):
        ev = "strikeout" if i % 2 == 0 else "single"
        rows.append((TRAIN_D1, 100, nxt(), P1, b, ev, 1 if ev == "strikeout"
                     else 0))
    for i, b in enumerate(B2):
        ev = "strikeout" if i % 2 == 0 else "walk"
        rows.append((TRAIN_D2, 100, nxt(), P1, b, ev, 1 if ev == "strikeout"
                     else 0))
    # pitcher P2: few strikeouts pre-cutoff
    for i, b in enumerate(B1):
        ev = "field_out" if i % 2 == 0 else "double"
        rows.append((TRAIN_D2, 101, nxt(), P2, b, ev, 0))
    return rows


def _pa_frame(extra=None):
    """ENRICHED frame (events + y): the tests' source of truth. The
    consumed PA parquet drops events (actual declared schema); labels
    arrive via the explicit raw-file bridge."""
    rows = _pa_rows()
    if extra:
        rows = rows + extra
    return pl.DataFrame(rows, schema={
        "game_date": pl.Date, "game_pk": pl.Int64,
        "at_bat_number": pl.Int64, "pitcher": pl.Int64,
        "batter": pl.Int64, "events": pl.Utf8, "y": pl.Int64},
        orient="row")


def _write_raw(tmp_path: Path, pa: pl.DataFrame, name="raw_events.parquet"):
    """Terminal-event rows for every PA in the events-bearing pa frame
    (multi-pitch rows precede the terminal row for the first PA)."""
    rows = []
    first = True
    for r in pa.iter_rows(named=True):
        key = (r["game_pk"], r["at_bat_number"], r["batter"])
        if first:  # ordinary pitch rows before the terminal row
            rows.append({"game_pk": key[0], "at_bat_number": key[1],
                         "batter": key[2], "events": None})
            rows.append({"game_pk": key[0], "at_bat_number": key[1],
                         "batter": key[2], "events": None})
            first = False
        rows.append({"game_pk": key[0], "at_bat_number": key[1],
                     "batter": key[2], "events": r["events"]})
    schema = {"game_pk": pl.Int64, "at_bat_number": pl.Int64,
              "batter": pl.Int64, "events": pl.Utf8}
    return pl.DataFrame(rows, schema=schema, orient="row")


def _write_raw(tmp_path: Path, pa: pl.DataFrame, name="raw_events.parquet"):
    """Terminal-event rows for every PA in the events-bearing pa frame
    (multi-pitch rows precede each terminal row for the first PA)."""
    rows = []
    first = True
    for r in pa.iter_rows(named=True):
        key = (r["game_pk"], r["at_bat_number"], r["batter"])
        if first:  # simulate ordinary pitch rows before the terminal row
            rows.append({"game_pk": key[0], "at_bat_number": key[1],
                         "batter": key[2], "events": None})
            rows.append({"game_pk": key[0], "at_bat_number": key[1],
                         "batter": key[2], "events": None})
            first = False
        rows.append({"game_pk": key[0], "at_bat_number": key[1],
                     "batter": key[2], "events": r["events"]})
    schema = {"game_pk": pl.Int64, "at_bat_number": pl.Int64,
              "batter": pl.Int64, "events": pl.Utf8}
    return pl.DataFrame(rows, schema=schema, orient="row")


def _lineups():
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _assessment(y_k1=None, y_k2=None):
    """SEPARATE per-PA outcome frame, REAL SHAPED: actual PA identity
    (at_bat_number), a repeated encounter, one projected hitter who never
    bats, and one replacement batter not in the projection."""
    y1 = y_k1 or [1 if i % 2 == 0 else 0 for i in range(9)]
    y2 = y_k2 or [1 if i % 2 else 0 for i in range(9)]
    rows = []
    ab = 0
    for i, b in enumerate(B1):
        if b == 800005:
            continue  # projection without actual PA
        ab += 1
        cls = 0 if y1[i] else 2
        rows.append((900001, "Top", P1, ab, b, cls))
        if b == 800001:  # repeated encounter: second PA, same matchup
            ab += 1
            rows.append((900001, "Top", P1, ab, b, cls))
    ab += 1
    rows.append((900001, "Top", P1, ab, 800999, 0))  # replacement batter: K
    for i, b in enumerate(B2):
        ab += 1
        rows.append((900001, "Bot", P2, ab, b, 0 if y2[i] else 3))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64},
        orient="row")


def _bf():
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date}
    schema.update({f"pmf37_{j}": pl.Float64 for j in range(37)})
    rows = []
    for (gk, side, p) in [(900001, "Top", P1), (900001, "Bot", P2)]:
        r = {"game_pk": gk, "side": side, "pitcher": p,
             "game_date": GAME_DATE}
        for j in range(37):
            r[f"pmf37_{j}"] = 1.0 if j == 4 else 0.0  # BF=5 workload
        rows.append(r)
    return pl.DataFrame(rows, schema=schema)


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None, assessment=None, bf=None):
    """pa must be events-bearing; the consumed PA parquet drops events
    (the actual declared schema), while the raw file carries the
    terminal events for the label bridge."""
    pa = pa if pa is not None else _pa_frame()
    raw = _write_raw(tmp_path, pa)
    pa_consumed = pa.drop("events")
    frames = {"pa": pa_consumed,
              "lineups": lineups if lineups is not None else _lineups(),
              "assessment": assessment if assessment is not None
              else _assessment(),
              "bf": bf if bf is not None else _bf()}
    h = {}
    for name, frame in frames.items():
        p = tmp_path / f"{name}.parquet"
        frame.write_parquet(p)
        h[f"{name}_path"] = str(p)
        h[f"{name}_sha"] = _sha(p)
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_events_path"] = str(rp)
    h["raw_events_sha"] = _sha(rp)
    return h


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         bf=None, ack=ACK, cohort_hash=None):
    h = _write(tmp_path, pa, lineups, assessment, bf)
    res = pm.run_pregame_multiclass_baseline(
        h and (pa if pa is not None else _pa_frame()),
        lineups if lineups is not None else _lineups(),
        assessment if assessment is not None else _assessment(),
        bf if bf is not None else _bf(), tmp_path / out,
        train_start="2024-06-01", train_end="2024-07-31",
        execution_ack=ack,
        raw_events=[h["raw_events_path"]],
        expected_cohort_hash=cohort_hash)
    return res, h


# ------------------------------------------------- invariants (directive)
def test_all_eligible_precutoff_rows_contribute_to_support(tmp_path):
    """Hand math: pitcher P1's pre-cutoff support = BOTH training dates
    (18 PAs); the forecast-cutoff contract must include the most recent
    eligible date (07-15) without any target-date row present."""
    res, _ = _run(tmp_path)
    out = Path(res["out_dir"])
    report = json.loads((out / "multiclass_baseline_report.json")
                        .read_text(encoding="utf-8"))
    assert report["state_meta"]["state_contract"] == fsv.STATES_V2_ID
    # hand math: P1 prior at 08-15 = ALL strictly-prior PAs:
    # 9 (2024-05-20 declared history) + 9 (07-01) + 9 (07-15) = 27
    feats = _feature_rows()
    p1 = feats.filter((pl.col("pitcher") == P1)
                      & (pl.col("slot") == 1))
    assert p1["n_prior_pitcher"][0] == 27
    # direct state check: the v2 state row at the cutoff carries both
    # training dates plus the declared history window
    st = fsv.build_v2_states(_pa_frame(), [GAME_DATE])[0]
    p1_state = st.filter((pl.col("pitcher") == P1)
                         & (pl.col("game_date") == GAME_DATE))
    assert p1_state["prior_n"][0] == 27.0


def _feature_rows(pa_frame=None):
    """Reconstruct the request-level feature frame the same way the
    runner does (documented path), for hand-math assertions."""
    from pregame_pa_ext import m0_multiclass as m0
    labeled = m0.build_multiclass_labels(pa_frame or _pa_frame())
    long, _ = ad.projected_long(_lineups())
    p_v2, b_v2, lg_v2, _ = fsv.build_v2_states(
        labeled, labeled["game_date"].unique().to_list()
        + [GAME_DATE])
    return ad.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk", "side",
                    "slot"),
        p_v2, b_v2, lg_v2)


def test_same_date_and_future_rows_cannot_change_forecasts(tmp_path):
    """Row-presence AND value invariance at the forecast cutoff: adding
    target-date and future PA rows changes nothing."""
    res_a, _ = _run(tmp_path, out="out_a")
    contaminated = _pa_frame(extra=[
        (GAME_DATE, 900001, 99, P1, 800001, "strikeout", 1),
        (FUTURE, 100, 98, P1, 800001, "hit", 0),
        (FUTURE, 101, 97, P2, 800101, "walk", 0)])
    res_b, _ = _run(tmp_path, out="out_b", pa=contaminated)
    r1 = json.loads((Path(res_a["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    r2 = json.loads((Path(res_b["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    # forecasts identical: PA log loss and count scores unchanged
    assert r1["results"] == r2["results"]
    # hand math: P1 support 27 (9 hist + 9 + 9), P2 support 18 (9 + 9)
    feats_b = _feature_rows()
    assert feats_b.filter((pl.col("pitcher") == P1)
                          & (pl.col("slot") == 1))[
        "n_prior_pitcher"][0] == 27
    assert feats_b.filter((pl.col("pitcher") == P2)
                          & (pl.col("slot") == 1))[
        "n_prior_pitcher"][0] == 18


def test_eligible_history_change_moves_state(tmp_path):
    """Positive control: changing an ELIGIBLE pre-cutoff observation
    (pitcher P1's 07-15 strikeout -> walk) changes pitcher support rates
    and therefore the forecasts."""
    pa_mod = _pa_frame().with_columns(
        pl.when((pl.col("game_date") == TRAIN_D2)
                & (pl.col("pitcher") == P1) & (pl.col("batter") == B2[0]))
        .then(pl.lit("walk")).otherwise(pl.col("events")).alias("events")
    ).with_columns(
        # the label bridge requires y consistency: a walk is not a K
        pl.when((pl.col("game_date") == TRAIN_D2)
                & (pl.col("pitcher") == P1) & (pl.col("batter") == B2[0]))
        .then(pl.lit(0)).otherwise(pl.col("y")).alias("y"))
    res_a, _ = _run(tmp_path, out="out_a")
    res_b, _ = _run(tmp_path, out="out_b", pa=pa_mod)
    r1 = json.loads((Path(res_a["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    r2 = json.loads((Path(res_b["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    assert r1["results"]["pa_multiclass_log_loss"][
        "ref1_multinomial"] != r2["results"]["pa_multiclass_log_loss"][
        "ref1_multinomial"]


def test_both_starters_same_game_distinct_keys_and_valid_probs(tmp_path):
    res, _ = _run(tmp_path, out="out_keys")
    assert res["counts"]["request_slots"] == 18
    assert res["counts"]["assessment_starts"] == 2
    out = Path(res["out_dir"])
    ps = pl.read_parquet(out / "multiclass_baseline_per_start_v1.parquet")
    assert ps.height == 2
    assert set(zip(ps["side"].to_list(), ps["pitcher"].to_list())) == {
        ("Top", P1), ("Bot", P2)}
    report = json.loads((out / "multiclass_baseline_report.json")
                        .read_text(encoding="utf-8"))
    pop = np.asarray(report["results"]["population_class_proportions"])
    assert abs(pop.sum() - 1.0) < 1e-12 and np.all(pop >= 0)
    assert report["results"]["k_marginal_column"] == 0
    # K-marginal binary scores + paired count-RPS delta are reported
    km = report["results"]["k_marginal_binary"]
    for ref in ("ref0_population", "ref1_multinomial"):
        assert 0.0 <= km[ref]["brier"] <= 1.0
        assert km[ref]["log_loss"] > 0
    paired = report["results"]["paired_count_rps_delta"]
    assert paired["primary_pair"] == "ref1_multinomial_vs_ref0_population"
    assert paired["n_boot"] == 2000 and paired["seed"] == 20261001
    assert paired["n_starts"] == 2


def test_assessment_outcomes_cannot_change_estimation(tmp_path):
    res_a, _ = _run(tmp_path, out="out_a")
    res_b, _ = _run(tmp_path, out="out_b",
                    assessment=_assessment(y_k1=[0] * 9, y_k2=[1] * 9))
    r1 = json.loads((Path(res_a["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    r2 = json.loads((Path(res_b["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    # fitted model + forecasts identical; only scores move
    assert r1["results"]["population_class_proportions"] == \
        r2["results"]["population_class_proportions"]
    assert r1["results"]["pa_multiclass_log_loss"] != \
        r2["results"]["pa_multiclass_log_loss"]


def test_empty_training_population_refused(tmp_path):
    with pytest.raises(ValueError, match="empty training population"):
        _run(tmp_path, out="out_empty",
             pa=_pa_frame().with_columns(
                 pl.lit(date(2025, 1, 1)).alias("game_date")))


# (missing workload coverage is COUNTED per start, not refused:
#  see test_missing_workload_start_is_counted_not_refused)


def test_subprocess_file_identity_mismatch_refuses(tmp_path):
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "pregame_multiclass_baseline.py")
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--assessment", h["assessment_path"], "--bf-source",
            h["bf_path"], "--raw-events", h["raw_events_path"],
            "--expected-pa-sha256", "0" * 64,
            "--train-start", "2024-06-01", "--train-end", "2024-07-31",
            "--out-dir", str(tmp_path / "out_sha"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode != 0
    assert "input identity mismatch" in r.stderr
    assert not (tmp_path / "out_sha").exists()


from pregame_pa_ext import forecast_states_v2 as fsv  # noqa: E402
from pregame_pa_ext import pregame_multiclass_baseline as pm  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
from pregame_pa_ext import adapter as ad  # noqa: E402


# ------------------- conflict-path structured-evidence regression test
def test_conflicting_terminal_events_preserve_structured_evidence(
        tmp_path):
    """The bridge's conflict gate must write its structured failure
    record BEFORE raising (regression: json.dumps fired on an unimported
    json, so out_dir runs raised NameError and lost the evidence)."""
    raw = pl.DataFrame({"game_pk": [900001, 900001],
                        "at_bat_number": [1, 1],
                        "batter": [800001, 800001],
                        "events": ["strikeout", "single"]},
                       schema={"game_pk": pl.Int64,
                               "at_bat_number": pl.Int64,
                               "batter": pl.Int64, "events": pl.Utf8},
                       orient="row")
    raw_path = tmp_path / "raw_conflict.parquet"
    raw.write_parquet(raw_path)
    pa = pl.DataFrame({"game_pk": [900001], "at_bat_number": [1],
                       "pitcher": [700001], "batter": [800001], "y": [1]},
                      schema={"game_pk": pl.Int64, "at_bat_number": pl.Int64,
                              "pitcher": pl.Int64, "batter": pl.Int64,
                              "y": pl.Int64}, orient="row")
    with pytest.raises(ValueError, match="conflicting_terminal_events"):
        seb.attach_terminal_event_labels(pa, [raw_path],
                                         out_dir=tmp_path / "evd")
    record = json.loads((tmp_path / "evd" / "failure_record.json")
                        .read_text(encoding="utf-8"))
    assert record["gate"] == "conflicting_terminal_events"
    assert record["n_conflicting_pa_identities"] == 1
    assert record["examples"][0][2] == 800001
    assert "first-record" in record["detail"]


def test_subprocess_invocation_produces_evidence(tmp_path):
    h = _write(tmp_path)
    script = (Path(__file__).resolve().parents[1] / "research"
              / "offseason_2026" / "pregame_pa_ext"
              / "pregame_multiclass_baseline.py")
    argv = [sys.executable, str(script),
            "--pa-source", h["pa_path"], "--lineups", h["lineups_path"],
            "--assessment", h["assessment_path"], "--bf-source",
            h["bf_path"], "--raw-events", h["raw_events_path"],
            "--train-start", "2024-06-01",
            "--train-end", "2024-07-31",
            "--out-dir", str(tmp_path / "out_sub"),
            "--execution-ack", ACK]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0
    out = tmp_path / "out_sub"
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert final["execution_acknowledgement"]["route"] == "cli"
    assert final["acceptance"]["status"] == "COMPLETED"
    initial_sha = hashlib.sha256(
        (out / "receipt_initial.json").read_bytes()).hexdigest()
    assert final["acceptance"]["receipt_chain"] == initial_sha
    for name, dig in final["outputs"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == dig


def test_invalid_ack_no_side_effects(tmp_path):
    h = _write(tmp_path)
    with pytest.raises(ValueError, match="execution acknowledgement"):
        pm.run_pregame_multiclass_baseline(
            _pa_frame(), _lineups(), _assessment(), _bf(),
            tmp_path / "out_ack", train_start="2024-06-01",
            train_end="2024-07-31", execution_ack="WRONG")
    assert not (tmp_path / "out_ack").exists()


# ------------------------- real-shaped accounting + permutation proof
def test_real_shaped_assessment_accounting(tmp_path):
    """Repeated encounters preserved (matched PAs = 18 projections + 1
    repeat, minus the never-batted projection); the replacement batter is
    excluded from PA scoring but COUNTED in realized starter K; the
    never-batted projection's would-be K is absent."""
    res, _ = _run(tmp_path, out="out_real")
    c = res["counts"]
    assert c["assessment_pas"] == 19
    assert c["assessment_pas_matched_to_projections"] == 18
    assert c["assessment_pas_excluded_no_projected_matchup"] == 1
    assert c["projections_without_actual_pa"] == 1
    assert c["count_scored_starts"] == 2
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "multiclass_baseline_per_start_v1.parquet")
    top = ps.filter((pl.col("side") == "Top")).row(0, named=True)
    bot = ps.filter((pl.col("side") == "Bot")).row(0, named=True)
    # Top realized K: 800001 x2 (both K), 800003, 800007, 800009 and the
    # replacement 800999 (K) = 6; the never-batted 800005's would-be K is
    # NOT counted (realized K comes from actual PAs only)
    assert top["realized_k"] == 6
    assert bot["realized_k"] == 4


def test_row_permutation_preserves_alignment(tmp_path):
    """Prediction/outcome alignment is key-based: permuting the actual-PA
    rows cannot change any score, count, or paired interval."""
    res_a, _ = _run(tmp_path, out="out_ord")
    shuffled = _assessment().sample(fraction=1.0, shuffle=True, seed=7)
    res_b, _ = _run(tmp_path, out="out_shuf", assessment=shuffled)
    r1 = json.loads((Path(res_a["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    r2 = json.loads((Path(res_b["out_dir"])
                     / "multiclass_baseline_report.json").read_text())
    assert r1["counts"] == r2["counts"]
    # float associativity: permuting rows reorders the mean's summation,
    # so scores may differ in the last ulp - assert to 1e-12
    for key in ("pa_multiclass_log_loss",):
        assert r1["results"][key]["ref0_population"] == \
            pytest.approx(r2["results"][key]["ref0_population"], abs=1e-12)
        assert r1["results"][key]["ref1_multinomial"] == \
            pytest.approx(r2["results"][key]["ref1_multinomial"], abs=1e-12)
    for ref in ("ref0_population", "ref1_multinomial"):
        a = r1["results"]["k_marginal_binary"][ref]
        b = r2["results"]["k_marginal_binary"][ref]
        assert a["log_loss"] == pytest.approx(b["log_loss"], abs=1e-12)
        assert a["brier"] == pytest.approx(b["brier"], abs=1e-12)
        assert r1["results"]["mean_count_rps"][ref] == \
            pytest.approx(r2["results"]["mean_count_rps"][ref], abs=1e-12)
    assert r1["results"]["paired_count_rps_delta"][
        "delta_a_minus_b"] == pytest.approx(
        r2["results"]["paired_count_rps_delta"]["delta_a_minus_b"],
        abs=1e-12)
    ps1 = pl.read_parquet(Path(res_a["out_dir"])
                          / "multiclass_baseline_per_start_v1.parquet")
    ps2 = pl.read_parquet(Path(res_b["out_dir"])
                          / "multiclass_baseline_per_start_v1.parquet")
    assert ps1.sort("game_pk", "side").rows() == \
        ps2.sort("game_pk", "side").rows()


def test_missing_workload_start_is_counted_not_refused(tmp_path):
    """Count-scoring coverage exclusions are reported per start; PA
    exclusions are reported separately."""
    res, _ = _run(tmp_path, out="out_cov", bf=_bf().head(1))
    c = res["counts"]
    assert c["count_scored_starts"] == 1
    assert c["count_excluded_starts"] == {"missing_bf": 1}
    assert c["assessment_pas_matched_to_projections"] == 18


# ------------------- keyed forecast table: reorder + cohort identity
def _with_invalid_label(matchup_batter: int, value) -> pl.DataFrame:
    """Assessment frame with one row's class_label set to an invalid
    value (matched projected batters AND the unmatched replacement are
    both coverable)."""
    return _assessment().with_columns(
        pl.when(pl.col("batter") == matchup_batter)
        .then(value).otherwise(pl.col("class_label"))
        .alias("class_label"))


def test_negative_class_label_refuses(tmp_path):
    with pytest.raises(ValueError, match="invalid class labels"):
        _run(tmp_path, out="out_neg",
             assessment=_with_invalid_label(800001, -1))
    failure = json.loads((tmp_path / "out_neg" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "invalid class labels" in failure["error"]
    assert not (tmp_path / "out_neg"
                / "multiclass_baseline_per_start_v1.parquet").exists()


def test_out_of_range_class_label_refuses(tmp_path):
    with pytest.raises(ValueError, match="invalid class labels"):
        _run(tmp_path, out="out_oob",
             assessment=_with_invalid_label(800002, 7))
    failure = json.loads((tmp_path / "out_oob" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "invalid class labels" in failure["error"]


def test_null_class_label_refuses(tmp_path):
    bad = _assessment().with_columns(
        pl.when(pl.col("batter") == 800001)
        .then(None).otherwise(pl.col("class_label"))
        .alias("class_label"))
    with pytest.raises(ValueError, match="invalid class labels"):
        _run(tmp_path, out="out_null", assessment=bad)
    failure = json.loads((tmp_path / "out_null" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "invalid class labels" in failure["error"]


def test_non_integer_class_label_dtype_refuses(tmp_path):
    bad = _assessment().with_columns(
        pl.col("class_label").cast(pl.Float64))
    with pytest.raises(ValueError, match="integer dtype"):
        _run(tmp_path, out="out_type", assessment=bad)


def test_invalid_label_on_unmatched_replacement_refuses(tmp_path):
    """800999 is the replacement batter with NO projected matchup: the
    validity guard still refuses (the guard precedes matchup alignment
    and realized-K derivation)."""
    with pytest.raises(ValueError, match="invalid class labels"):
        _run(tmp_path, out="out_rep",
             assessment=_with_invalid_label(800999, -1))
    failure = json.loads((tmp_path / "out_rep" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "invalid class labels" in failure["error"]
    assert "800999" in failure["error"]  # representative identity kept


def test_invalid_label_error_preserves_identities(tmp_path):
    with pytest.raises(ValueError, match="invalid class labels"):
        _run(tmp_path, out="out_ident",
             assessment=_with_invalid_label(800001, -1))
    failure = json.loads((tmp_path / "out_ident" / "failure_record.json")
                         .read_text(encoding="utf-8"))
    assert "900001" in failure["error"] and "800001" in failure["error"]


# ------------------- keyed forecast table: reorder + cohort identity
def test_reordered_feature_output_keeps_probabilities_keyed(tmp_path):
    """Deliberately reorder the feature-constructor output rows: each
    matchup must keep ITS OWN probability (keyed carry-through), so any
    positional transfer to another frame would be detected."""
    from pregame_pa_ext import m0_multiclass as m0
    pa = _pa_frame()
    labeled = m0.build_multiclass_labels(pa)
    long, _ = ad.projected_long(_lineups())
    cutoffs = labeled["game_date"].unique().to_list() + [GAME_DATE]
    p_v2, b_v2, lg_v2, _ = fsv.build_v2_states(labeled, cutoffs)
    feat = ad.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk", "side",
                    "slot"), p_v2, b_v2, lg_v2)
    labels = _assessment().select("game_pk", "side", "pitcher", "batter",
                                  "class_label")
    feat_l = feat.join(labels, on=["game_pk", "side", "pitcher", "batter"],
                       how="left")
    model = m0.fit_multinomial(feat_l)  # synthetic fit, >=2 classes
    probs_canon = m0.apply_multinomial(feat, model)
    table_canon = feat.with_columns(
        pl.Series("p_k", probs_canon[:, 0])).select(
        "game_pk", "side", "pitcher", "slot", "batter", "p_k")
    # DELIBERATELY REORDERED feature output (reverse), then predict and
    # key from the reordered frame
    feat_rev = feat.reverse()
    probs_rev = m0.apply_multinomial(feat_rev, model)
    table_rev = feat_rev.with_columns(
        pl.Series("p_k", probs_rev[:, 0])).select(
        "game_pk", "side", "pitcher", "slot", "batter", "p_k")
    # different rows carry different probabilities in this fixture
    assert table_canon["p_k"].n_unique() > 1
    joined = table_canon.join(
        table_rev, on=["game_pk", "side", "pitcher", "slot", "batter"],
        suffix="_rev")
    assert joined["p_k"].to_list() == \
        pytest.approx(joined["p_k_rev"].to_list())


def test_scored_cohort_identity_enforced(tmp_path):
    correct = hashlib.sha256("\n".join(
        sorted(["%d|%s|%d" % (900001, "Top", P1),
                "%d|%s|%d" % (900001, "Bot", P2)]))
        .encode("utf-8")).hexdigest()
    res, _ = _run(tmp_path, out="out_cohort", cohort_hash=correct)
    report = json.loads(
        (Path(res["out_dir"]) / "multiclass_baseline_report.json")
        .read_text(encoding="utf-8"))
    assert report["scored_cohort_sha256"] == correct
    with pytest.raises(ValueError, match="scored cohort identity mismatch"):
        _run(tmp_path, out="out_cohort_bad", cohort_hash="0" * 64)
