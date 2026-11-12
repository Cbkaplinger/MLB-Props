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

import json
import math
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
        rc._require_pin("pinned", f, "0" * 64)


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


# ---------------- 5. main-entry synthetic success (outputs read back)
def _write_pinned(tmp_path):
    """Synthetic registered artifacts: 2 starts, uniform 24-bucket PMFs,
    observed K from class_label==0 counts, cohort, declared dates."""
    starts = [(1, "home", 100), (2, "away", 200)]
    rows = []
    for gpk, side, pid in starts:
        for b in range(24):
            rows.append({"game_pk": gpk, "side": side,
                         "pitcher": pid, "bucket": b,
                         "pmf_multinomial_control": 1.0 / 24.0,
                         "pmf_platoon": 1.0 / 24.0})
    k_pmf = pl.DataFrame(rows)
    pa_rows = []
    for gpk, side, pid, n_pas in ((1, "home", 100, 5),
                                  (2, "away", 200, 3)):
        for i in range(n_pas):
            pa_rows.append({"game_pk": gpk, "side": side,
                            "pitcher": pid, "at_bat_number": i + 1,
                            "batter": 9000 + i, "class_label": 0})
    assessment = pl.DataFrame(pa_rows)
    cohort = pl.DataFrame(starts, orient="row",
                          schema={"game_pk": pl.Int64, "side": pl.Utf8,
                                  "pitcher": pl.Int64})
    dates_src = pl.DataFrame({
        "game_pk": [1, 2], "side": ["home", "away"],
        "pitcher": [100, 200],
        "game_date": [date(2025, 4, 10), date(2025, 4, 11)],
        "block": ["block_2025H1", "block_2025H1"],
        "realized_k": [5, 3]}, orient="row")
    files = {}
    for name, frame in (("k_pmf.parquet", k_pmf),
                        ("assessment.parquet", assessment),
                        ("cohort.parquet", cohort),
                        ("count_agg.parquet", dates_src)):
        p = tmp_path / name
        frame.write_parquet(p)
        files[name] = p
    return files


def _fake_quotes(starts_bridge, quotes, join_meta):
    return starts_bridge, quotes, join_meta


def _make_fake_build_quotes(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    commence = datetime(2025, 4, 10, 23, 0, tzinfo=timezone.utc)
    commence2 = datetime(2025, 4, 11, 23, 0, tzinfo=timezone.utc)
    sb = pl.DataFrame({
        "game_pk": [1, 2], "pitcher_key": ["allen logan"] * 2,
        "pitcher": [100, 200],
        "first_pitch_ts": [commence, commence2],
        "has_commence": [True, True]}, orient="row")
    qrows = []
    for gpk, ts, comm in ((1, commence, commence),
                          (2, commence2, commence2)):
        for book in ("draftkings", "fanduel", "betmgm"):
            for side, price in (("over", -120), ("under", 105)):
                qrows.append({
                    "game_pk": gpk, "pitcher": "allen logan",
                    "book": book, "line": 4.5, "side": side,
                    "price": price,
                    "quote_timestamp": (comm - timedelta(minutes=30)
                                        ).isoformat(),
                    "snapshot": "morning"})
    quotes = pl.DataFrame(qrows)
    bl = tmp_path / "book_lines.parquet"
    bl.write_bytes(b"declared-quote-input")
    env = tmp_path / "envelope.parquet"
    env.write_bytes(b"declared-envelope-input")

    def fake_build_quotes(book_lines_path, envelope_path):
        return sb, quotes, {"starts_total_window": 2,
                            "workload_path": "synthetic://bf"}

    monkeypatch.setattr(rc, "build_quotes", fake_build_quotes)
    return bl, env


def test_main_entry_success_outputs_read_back(tmp_path, monkeypatch):
    from pregame_pa_ext import binary_k_comparison as bk
    files = _write_pinned(tmp_path)
    monkeypatch.setattr(rc, "FILE_PINS", {
        "k_pmf_per_start_v1": (
            files["k_pmf.parquet"], rc.sha256_file(files["k_pmf.parquet"])),
        "assessment_2025H1_v1": (
            files["assessment.parquet"],
            rc.sha256_file(files["assessment.parquet"])),
        "count_agg_eval_v1_dates": (
            files["count_agg.parquet"],
            rc.sha256_file(files["count_agg.parquet"])),
        "cohort": (files["cohort.parquet"], None),
    })
    cohort = pl.read_parquet(files["cohort.parquet"])
    monkeypatch.setattr(rc, "EXPECTED_COHORT_HASH",
                        rc._cohort_content_hash(cohort))
    bl, env = _make_fake_build_quotes(monkeypatch, tmp_path)
    out = tmp_path / "out"
    rc_code = rc.main([
        "--execution-ack", rc.EXECUTION_ACK_TOKEN,
        "--out-dir", str(out),
        "--book-lines", str(bl), "--envelope", str(env),
        "--n-boot", "20",
    ])
    assert rc_code == 0
    # receipt_final exists only because ALL declared outputs succeeded
    assert (out / "receipt_final.json").exists()
    # tables read back as parquet with expected structure
    mr = pl.read_parquet(out / "benchmark_model_rows.parquet")
    assert mr.height == 2
    assert set(mr.columns) >= {"game_pk", "side", "pitcher",
                               "realized_k", "line", "p_over",
                               "pmf_baseline"}
    for tbl in ("benchmark_consensus.parquet",
                "benchmark_book_probs.parquet", "benchmark_ltbo.parquet"):
        assert pl.read_parquet(out / tbl).height > 0
    summary = json.loads((out / "benchmark_summary.json").read_text(
        encoding="utf-8"))
    mc = summary["model_vs_consensus"]
    # hand-computed: uniform PMF -> p_m = 19/24; devig(-120,105) = p_c;
    # o = [1, 0] (realized_k 5 vs 3 at line 4.5)
    p_m, p_c = 19.0 / 24.0, 0.5278969957081545
    import math
    exp_ll_m = -(math.log(p_m) + math.log(1 - p_m)) / 2
    exp_ll_c = -(math.log(p_c) + math.log(1 - p_c)) / 2
    exp_br_m = ((p_m - 1) ** 2 + p_m ** 2) / 2
    exp_br_c = ((p_c - 1) ** 2 + p_c ** 2) / 2
    assert mc["n"] == 2
    assert abs(mc["log_loss_model"] - exp_ll_m) < 1e-9
    assert abs(mc["log_loss_close"] - exp_ll_c) < 1e-9
    assert abs(mc["brier_model"] - exp_br_m) < 1e-9
    assert abs(mc["brier_close"] - exp_br_c) < 1e-9
    assert "count_rps_model_mean" in mc
    # book-vs-LTBO: identical prices -> zero deltas per book
    bs = summary["book_scores"]
    assert set(bs) == {"draftkings", "fanduel", "betmgm"}
    for book, s in bs.items():
        assert s["n_starts"] == 2
        assert abs(s["log_loss_a"] - s["log_loss_b"]) < 1e-12
        assert abs(s["brier_a"] - s["brier_b"]) < 1e-12
    cov = summary["coverage"]
    assert cov["cohort"]["n_keys"] == 2
    assert cov["n_matched_model_starts"] == 2
    assert cov["consensus_starts_total"] == 2
    assert cov["n_consensus_unmatched_to_model"] == 0
    assert cov["ltbo_unavailable_rows"] == 0
    # contract: commence semantics + tiebreak gap recorded
    assert "NOT an observed" in summary["contract"]["commence_semantics"]
    assert "NOT independent identity validation" in \
        summary["contract"]["tiebreak_status"]
    # consumed identities recorded
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    ci = final["consumed_identities"]
    assert ci["cohort_content_hash"] == rc._cohort_content_hash(cohort)
    jc_ctx = ci["join_context"]
    assert "bridge" in jc_ctx and "book_lines_sha256" in jc_ctx


def test_missing_book_lines_path_refuses_before_outputs(tmp_path,
                                                        monkeypatch):
    files = _write_pinned(tmp_path)
    cohort = pl.read_parquet(files["cohort.parquet"])
    monkeypatch.setattr(rc, "FILE_PINS", {
        "k_pmf_per_start_v1": (
            files["k_pmf.parquet"], rc.sha256_file(files["k_pmf.parquet"])),
        "assessment_2025H1_v1": (
            files["assessment.parquet"],
            rc.sha256_file(files["assessment.parquet"])),
        "count_agg_eval_v1_dates": (
            files["count_agg.parquet"],
            rc.sha256_file(files["count_agg.parquet"])),
        "cohort": (files["cohort.parquet"], None),
    })
    monkeypatch.setattr(rc, "EXPECTED_COHORT_HASH",
                        rc._cohort_content_hash(cohort))
    missing = tmp_path / "nonexistent_book_lines.parquet"
    out = tmp_path / "out"
    with pytest.raises(FileNotFoundError, match="book-lines"):
        rc.main(["--execution-ack", rc.EXECUTION_ACK_TOKEN,
                 "--out-dir", str(out),
                 "--book-lines", str(missing),
                 "--envelope", str(tmp_path / "env.parquet")])
    # refused BEFORE output creation
    assert not out.exists()


def test_output_write_failure_no_completed_receipt(tmp_path,
                                                   monkeypatch):
    """An output-write failure must leave failure_record.json and
    NEVER a completed receipt_final.json."""
    files = _write_pinned(tmp_path)
    cohort = pl.read_parquet(files["cohort.parquet"])
    monkeypatch.setattr(rc, "FILE_PINS", {
        "k_pmf_per_start_v1": (
            files["k_pmf.parquet"], rc.sha256_file(files["k_pmf.parquet"])),
        "assessment_2025H1_v1": (
            files["assessment.parquet"],
            rc.sha256_file(files["assessment.parquet"])),
        "count_agg_eval_v1_dates": (
            files["count_agg.parquet"],
            rc.sha256_file(files["count_agg.parquet"])),
        "cohort": (files["cohort.parquet"], None),
    })
    monkeypatch.setattr(rc, "EXPECTED_COHORT_HASH",
                        rc._cohort_content_hash(cohort))
    bl, env = _make_fake_build_quotes(monkeypatch, tmp_path)

    def broken_persist(out_dir, result):
        raise OSError("simulated output-write failure")

    monkeypatch.setattr(rc, "_persist_results", broken_persist)
    out = tmp_path / "out"
    with pytest.raises(OSError, match="simulated"):
        rc.main(["--execution-ack", rc.EXECUTION_ACK_TOKEN,
                 "--out-dir", str(out),
                 "--book-lines", str(bl), "--envelope", str(env),
                 "--n-boot", "20"])
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    # receipt_initial (declared state) is allowed; completion is not
    assert (out / "receipt_initial.json").exists()
