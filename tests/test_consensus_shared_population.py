"""Synthetic tests for the declared shared-population consensus policy
(--consensus-policy shared_population in run_control_vs_books.py).

Covers the bounded follow-up assignment through the production entry
point (main()):
- default refusal preserved (exact-cohort coverage gate unchanged);
- shared_population scores model-vs-consensus ONLY on their declared
  shared population, with the ORIGINAL cohort as the coverage
  denominator;
- matched/unmatched start keys + reason codes persisted BEFORE scoring
  (consensus_matched_starts.parquet / consensus_unmatched_starts.parquet);
- reason codes: no_near_close_quotes / no_two_sided_quote_at_any_line;
- book/LTBO populations separate with their own denominators;
- hand-computed metrics on the shared population.

NO private lake reads, NO network, NO canonical overwrites.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import run_control_vs_books as rc  # noqa: E402
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402

FAIR_OVER = 0.5278969957081545  # devig(-120, 105)
P_MODEL = 19.0 / 24.0  # uniform 24-bucket PMF, line 4.5
COMM = datetime(2025, 4, 10, 23, 0, tzinfo=timezone.utc)
QT = (COMM - timedelta(minutes=30)).isoformat()


def _bl(gpk, key, snap, book, side, price):
    return {"game_pk": gpk,
            "event_id": f"e{gpk}{book}{side}{snap}", "snapshot": snap,
            "snapshot_ts": QT, "game_date": "2025-04-10",
            "season_type": "regular", "book": book,
            "market": "pitcher_strikeouts", "pitcher": key,
            "line": 4.5, "side": side, "price": price}


def _quote_rows():
    """s1: full two-sided DK+FD+betmgm (matched; 3 books so LTBO has
    >= 2 other books). s2: ONE-SIDED only (unmatched, reason
    no_two_sided_quote_at_any_line). s3: no quotes (unmatched, reason
    no_near_close_quotes)."""
    rows = []
    for book in ("draftkings", "fanduel", "betmgm"):
        for side, price in (("over", -120), ("under", 105)):
            rows.append(_bl(1, "aa p", "morning", book, side, price))
            rows.append(_bl(1, "aa p", "close", book, side, price))
    rows.append(_bl(2, "bb p", "close", "draftkings", "over", -120))
    return rows


def _starts_bridge():
    return pl.DataFrame({
        "game_pk": [1, 2, 3],
        "pitcher_key": ["aa p", "bb p", "cc p"],
        "pitcher": [100, 200, 300],
        "first_pitch_ts": [COMM, COMM, COMM],
        "has_commence": [True, True, True]}, orient="row")


def _write_pinned(tmp_path):
    starts = [(1, "home", 100), (2, "away", 200), (3, "home", 300)]
    rows = []
    for gpk, side, pid in starts:
        for b in range(24):
            rows.append({"game_pk": gpk, "side": side, "pitcher": pid,
                         "bucket": b,
                         "pmf_multinomial_control": 1.0 / 24.0,
                         "pmf_platoon": 1.0 / 24.0})
    k_pmf = pl.DataFrame(rows)
    pa_rows = []
    for gpk, side, pid, n_pas in ((1, "home", 100, 5), (2, "away", 200, 3),
                                  (3, "home", 300, 2)):
        for i in range(n_pas):
            pa_rows.append({"game_pk": gpk, "side": side, "pitcher": pid,
                            "at_bat_number": i + 1, "batter": 9000 + i,
                            "class_label": 0})
    assessment = pl.DataFrame(pa_rows)
    cohort = pl.DataFrame(starts, orient="row",
                          schema={"game_pk": pl.Int64, "side": pl.Utf8,
                                  "pitcher": pl.Int64})
    dates_src = pl.DataFrame({
        "game_pk": [1, 2, 3], "side": ["home", "away", "home"],
        "pitcher": [100, 200, 300],
        "game_date": [date(2025, 4, 10)] * 3,
        "block": ["block_2025H1"] * 3,
        "realized_k": [5, 3, 2]}, orient="row")
    files = {}
    for name, frame in (("k_pmf.parquet", k_pmf),
                        ("assessment.parquet", assessment),
                        ("cohort.parquet", cohort),
                        ("count_agg.parquet", dates_src)):
        p = tmp_path / name
        frame.write_parquet(p)
        files[name] = p
    return files, cohort


def _wire(monkeypatch, tmp_path, files, cohort, quote_rows):
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
    sb = pl.DataFrame({
        "game_pk": [1, 2, 3],
        "pitcher_key": ["aa p", "bb p", "cc p"],
        "pitcher": [100, 200, 300],
        "first_pitch_ts": [COMM, COMM, COMM],
        "has_commence": [True, True, True]}, orient="row")
    quotes = pl.DataFrame(quote_rows, schema={
        "game_pk": pl.Int64, "event_id": pl.Utf8, "snapshot": pl.Utf8,
        "snapshot_ts": pl.Utf8, "game_date": pl.Utf8,
        "season_type": pl.Utf8, "book": pl.Utf8, "market": pl.Utf8, "pitcher": pl.Utf8, "line": pl.Float64,
        "side": pl.Utf8, "price": pl.Int64})
    bl = tmp_path / "book_lines.parquet"
    bl.write_bytes(b"declared")
    env = tmp_path / "envelope.parquet"
    env.write_bytes(b"declared")

    def fake_build_quotes(book_lines_path, envelope_path):
        q = quotes.rename({"snapshot_ts": "quote_timestamp"})
        return sb, q, {"starts_total_window": 3,
                            "workload_path": "synthetic://bf"}

    monkeypatch.setattr(rc, "build_quotes", fake_build_quotes)
    return bl, env


SHARED_ARGS = ["--execution-ack", rc.EXECUTION_ACK_TOKEN,
               "--consensus-policy", "shared_population",
               "--n-boot", "20"]


def test_default_refusal_preserved(tmp_path, monkeypatch):
    files, cohort = _write_pinned(tmp_path)
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, _quote_rows())
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="model rows lost"):
        rc.main(["--execution-ack", rc.EXECUTION_ACK_TOKEN,
                 "--out-dir", str(out),
                 "--book-lines", str(bl), "--envelope", str(env),
                 "--n-boot", "20"])


def test_shared_population_scores_declared_subset(tmp_path, monkeypatch):
    files, cohort = _write_pinned(tmp_path)
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, _quote_rows())
    out = tmp_path / "out"
    assert rc.main(SHARED_ARGS + ["--out-dir", str(out),
                                  "--book-lines", str(bl),
                                  "--envelope", str(env)]) == 0
    # matched/unmatched keys persisted BEFORE scoring completed
    matched = pl.read_parquet(out / "consensus_matched_starts.parquet")
    unmatched = pl.read_parquet(out / "consensus_unmatched_starts.parquet")
    assert matched.height == 1 and unmatched.height == 2
    # metrics scored ONLY on the shared population (hand-computed):
    # uniform PMF -> p_m = 19/24; consensus p_over = devig(-120,105);
    # realized o = 1 (K=5 > 4.5)
    import math
    summary = json.loads((out / "benchmark_summary.json").read_text(
        encoding="utf-8"))
    mc = summary["model_vs_consensus"]
    assert mc["n"] == 1
    assert abs(mc["log_loss_model"] - (-math.log(P_MODEL))) < 1e-9
    assert abs(mc["log_loss_close"] - (-math.log(FAIR_OVER))) < 1e-9
    assert abs(mc["brier_model"] - (1 - P_MODEL) ** 2) < 1e-9
    assert abs(mc["brier_close"] - (1 - FAIR_OVER) ** 2) < 1e-9
    cov = summary["coverage"]
    sh = cov["consensus_shared_population"]
    # ORIGINAL cohort is the coverage denominator
    assert sh["cohort_denominator"] == 3
    assert sh["matched"] == 1 and sh["unmatched"] == 2


def test_reason_codes(tmp_path, monkeypatch):
    files, cohort = _write_pinned(tmp_path)
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, _quote_rows())
    out = tmp_path / "out"
    jr_ok = rc.main(SHARED_ARGS + ["--out-dir", str(out),
                                   "--book-lines", str(bl),
                                   "--envelope", str(env)])
    assert jr_ok == 0
    unmatched = pl.read_parquet(out / "consensus_unmatched_starts.parquet")
    reasons = {r["game_pk"]: r["reason"]
               for r in unmatched.iter_rows(named=True)}
    # s3: no near-close quotes at all
    assert reasons[3] == "no_near_close_quotes"
    # s2: quotes exist but one-sided only -> no two-sided book pair
    assert reasons[2] == "no_two_sided_quote_at_any_line"
    summary = json.loads((out / "benchmark_summary.json").read_text(
        encoding="utf-8"))
    by_reason = summary["coverage"]["consensus_shared_population"][
        "unmatched_by_reason"]
    assert by_reason == {"no_near_close_quotes": 1,
                         "no_two_sided_quote_at_any_line": 1}


def test_book_ltbo_denominators_separate(tmp_path, monkeypatch):
    files, cohort = _write_pinned(tmp_path)
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, _quote_rows())
    out = tmp_path / "out"
    assert rc.main(SHARED_ARGS + ["--out-dir", str(out),
                                  "--book-lines", str(bl),
                                  "--envelope", str(env)]) == 0
    summary = json.loads((out / "benchmark_summary.json").read_text(
        encoding="utf-8"))
    cov = summary["coverage"]
    # book/LTBO populations disclose their OWN denominators (per book)
    assert cov["book_vs_ltbo_denominators"] == {"betmgm": 1,
                                                "draftkings": 1,
                                                "fanduel": 1}
    assert cov["n_matched_model_starts"] == 3  # model frame unchanged
    # book-vs-LTBO scored per book on ITS OWN matched rows (n_starts=1)
    for book, s in summary["book_scores"].items():
        assert s["n_starts"] == 1
        assert abs(s["log_loss_a"] - s["log_loss_b"]) < 1e-12
    # book_probs/ltbo tables persisted separately
    assert pl.read_parquet(out / "benchmark_book_probs.parquet").height > 0
    assert pl.read_parquet(out / "benchmark_ltbo.parquet").height > 0


def test_shared_population_receipt_records_policy(tmp_path, monkeypatch):
    files, cohort = _write_pinned(tmp_path)
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, _quote_rows())
    out = tmp_path / "out"
    assert rc.main(SHARED_ARGS + ["--out-dir", str(out),
                                  "--book-lines", str(bl),
                                  "--envelope", str(env)]) == 0
    final = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert final["consensus_policy"] == "shared_population"
    assert final["status"] == "completed"
    # refusals elsewhere remain: receipt_final exists only after ALL
    # declared outputs (incl. matched/unmatched parquets) succeeded
    assert (out / "consensus_matched_starts.parquet").exists()


def test_membership_persists_through_scorer_failure(tmp_path, monkeypatch):
    """Durable pre-score membership boundary: when the scorer fails,
    the matched/unmatched membership parquets ALREADY EXIST (written by
    membership_sink before scoring), and the failure leaves a failure
    record but NO completed receipt."""
    files, cohort = _write_pinned(tmp_path)
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, _quote_rows())
    from pregame_pa_ext import market_eval_k as mk

    def broken_scorer(joined):
        raise RuntimeError("synthetic scorer failure")

    monkeypatch.setattr(mk, "score_starts", broken_scorer)
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="synthetic scorer failure"):
        rc.main(SHARED_ARGS + ["--out-dir", str(out),
                               "--book-lines", str(bl),
                               "--envelope", str(env)])
    # membership was durably persisted BEFORE scoring ran
    matched = pl.read_parquet(out / "consensus_matched_starts.parquet")
    unmatched = pl.read_parquet(out / "consensus_unmatched_starts.parquet")
    assert matched.height == 1 and unmatched.height == 2
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    # the selected policy is visible in the INITIAL receipt even on
    # failed attempts
    ri = json.loads((out / "receipt_initial.json").read_text(
        encoding="utf-8"))
    assert ri["consensus_policy"] == "shared_population"


def test_complete_coverage_accounting(tmp_path, monkeypatch):
    """Every cohort start carries a consensus: shared_population
    accounting is EXPLICIT (not absent), with complete_coverage True
    and the membership parquets persisted."""
    files, cohort = _write_pinned(tmp_path)
    rows = _quote_rows()
    # give s2 and s3 the same full two-sided quote set as s1
    for gpk, key in ((2, "bb p"), (3, "cc p")):
        for book in ("draftkings", "fanduel", "betmgm"):
            for side, price in (("over", -120), ("under", 105)):
                rows.append(_bl(gpk, key, "morning", book, side, price))
                rows.append(_bl(gpk, key, "close", book, side, price))
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, rows)
    out = tmp_path / "out"
    assert rc.main(SHARED_ARGS + ["--out-dir", str(out),
                                  "--book-lines", str(bl),
                                  "--envelope", str(env)]) == 0
    matched = pl.read_parquet(out / "consensus_matched_starts.parquet")
    assert matched.height == 3
    summary = json.loads((out / "benchmark_summary.json").read_text(
        encoding="utf-8"))
    sh = summary["coverage"]["consensus_shared_population"]
    assert sh["complete_coverage"] is True
    assert sh["cohort_denominator"] == 3
    assert sh["matched"] == 3 and sh["unmatched"] == 0


def test_zero_matched_controlled_refusal(tmp_path, monkeypatch):
    """NO cohort start has a consensus: an explicit controlled refusal
    (no-score result), not a crash and not silent empty scoring. The
    declared declaration: zero matches -> controlled refusal. Which
    gate fires first depends on the frames: with NO two-sided quotes
    anywhere, the consensus-construction gate refuses first; the empty-
    shared-population guard remains as defense in depth for the case
    where consensus rows exist but none match the cohort."""
    files, cohort = _write_pinned(tmp_path)
    # one-sided only + no quotes -> zero consensus matches
    rows = [r for r in _quote_rows() if r["game_pk"] == 2]
    bl, env = _wire(monkeypatch, tmp_path, files, cohort, rows)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="missing over/under bet sides"):
        rc.main(SHARED_ARGS + ["--out-dir", str(out),
                               "--book-lines", str(bl),
                               "--envelope", str(env)])
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    # the selected policy is visible in the initial receipt on failure
    ri = json.loads((out / "receipt_initial.json").read_text(
        encoding="utf-8"))
    assert ri["consensus_policy"] == "shared_population"
