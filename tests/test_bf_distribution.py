"""Synthetic tests for the BF distribution module (no real data)."""

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))

import bf_distribution as bd  # noqa: E402

def test_pmf_contract():
    pmf = np.zeros(37)
    pmf[4] = 1.0
    bd.check_pmf(pmf)
    with pytest.raises(ValueError):
        bd.check_pmf(np.full(37, 1.0 / 36.0))
    with pytest.raises(ValueError):
        bad = np.zeros(37)
        bad[0] = -0.1
        bad[1] = 1.1
        bd.check_pmf(bad)
    with pytest.raises(ValueError):
        bd.check_pmf(np.zeros(36))


def test_hazard_conversion_and_off_by_one():
    hazards = np.zeros(36)
    hazards[0] = 1.0
    pmf = bd.hazard_to_pmf(hazards)
    assert pmf[0] == 1.0 and pmf[1:].sum() == 0.0
    hazards = np.zeros(36)
    hazards[0] = hazards[1] = 0.5
    pmf = bd.hazard_to_pmf(hazards)
    assert pmf[0] == pytest.approx(0.5)
    assert pmf[1] == pytest.approx(0.25)
    assert pmf[36] == pytest.approx(0.25)  # overflow absorbs the rest
    assert pmf.sum() == pytest.approx(1.0)
    with pytest.raises(ValueError):
        bd.hazard_to_pmf(np.full(36, 1.5))
    with pytest.raises(ValueError):
        bd.hazard_to_pmf(np.zeros(35))


def test_bf_one_and_overflow_outcomes():
    pmf = np.zeros(37)
    pmf[0] = 1.0  # certain one-batter outing
    assert bd.rps_score(pmf, 1) == 0.0
    assert bd.count_nll(pmf, 1)[0] == 0.0
    empty_hazards = np.zeros(36)
    overflow = bd.hazard_to_pmf(empty_hazards)
    assert overflow[36] == 1.0
    nll, clipped = bd.count_nll(overflow, 50)
    assert np.isfinite(nll) and not clipped


def test_scores_on_hand_case():
    pmf = np.zeros(37)
    pmf[4] = 0.25
    pmf[9] = 0.75
    nll, clipped = bd.count_nll(pmf, 5)
    assert nll == pytest.approx(-np.log(0.25)) and not clipped
    nll0, clipped0 = bd.count_nll(pmf, 7)
    assert clipped0 and nll0 == pytest.approx(-np.log(1e-12))
    assert bd.rps_score(pmf, 5) >= 0.0
    assert bd.short_outing_brier(pmf, 5) == pytest.approx((0.25 - 1.0) ** 2)
    assert bd.short_outing_brier(pmf, 12) == pytest.approx(0.25 ** 2)


def test_cdf_monotone_and_intervals():
    pmf = np.zeros(37)
    pmf[10] = 1.0
    cdf = bd.pmf_to_cdf(pmf)
    assert bool((np.diff(cdf) >= 0).all()) and cdf[-1] == 1.0
    lo, hi, width = bd.central_interval(pmf, 0.80)
    assert (lo, hi, width) == (11, 11, 1)
    assert bd.interval_covered((lo, hi, width), 11) is True
    assert bd.interval_covered((lo, hi, width), 5) is False
    with pytest.raises(ValueError):
        bd.central_interval(pmf, 1.5)


def test_empirical_baseline_laplace():
    counts = np.zeros(37)
    counts[0] = 2.0
    pmf = bd.empirical_baseline(counts)
    assert pmf[0] == pytest.approx(3.0 / 39.0)
    assert pmf.sum() == pytest.approx(1.0)
    assert (pmf > 0).all()  # finite log scores everywhere
    with pytest.raises(ValueError):
        bd.empirical_baseline(np.zeros(37))
    with pytest.raises(ValueError):
        bd.empirical_baseline(np.zeros(36))


def test_risk_rows_and_corrupt_inputs():
    rows, y = bd.build_risk_rows(np.array([1, 3]))
    assert rows.tolist() == [[0, 1], [1, 1], [1, 2], [1, 3]]
    assert y.tolist() == [1.0, 0.0, 0.0, 1.0]
    with pytest.raises(ValueError, match="below support"):
        bd.build_risk_rows(np.array([0]))
    with pytest.raises(ValueError, match="below support"):
        bd.counts_from_outcomes([0])
    assert bd.counts_from_outcomes([1, 37, 50]).tolist()[:2] == [1.0, 0.0]
    assert bd.counts_from_outcomes([1, 37, 50])[36] == 2.0


def test_outcome_invariance_of_predictions():
    rng = np.random.default_rng(0)
    train_x = rng.normal(size=(12, 2))
    train_n = np.array([20, 22, 5, 21, 8, 19, 23, 4, 20, 18, 22, 6])
    bundle = bd.fit_hazard(train_x, train_n, ["a", "b"])
    row = np.array([[0.5, -0.5]])
    first = bd.predict_pmf(bundle, row)
    second = bd.predict_pmf(bundle, row)
    assert np.array_equal(first, second)  # realized N never enters


def test_preprocessing_uses_train_only():
    train_x = np.array([[1.0, np.nan], [3.0, 1.0], [5.0, 3.0]])
    train_n = np.array([20, 21, 22])
    bundle = bd.fit_hazard(train_x, train_n, ["a", "b"])
    assert bundle["preprocess"]["medians"][1] == 2.0  # train median
    with pytest.raises(ValueError, match="all-null"):
        bd.fit_hazard(np.full((3, 2), np.nan), train_n, ["a", "b"])
    with pytest.raises(ValueError):
        bd.fit_hazard(np.empty((0, 2)), np.array([]), ["a", "b"])


def test_end_to_end_synthetic_diagnostic():
    rng = np.random.default_rng(7)
    train_x = rng.normal(size=(16, 2))
    train_n = np.array([20, 22, 5, 21, 8, 19, 23, 4, 20, 18, 22, 6,
                        21, 3, 19, 24])
    eval_x = rng.normal(size=(6, 2))
    eval_n = np.array([21, 7, 20, 2, 22, 19])
    out = bd.run_diagnostic(train_x, train_n, eval_x, eval_n, ["a", "b"])
    assert out["n_train"] == 16 and out["n_eval"] == 6
    assert out["mass_checks"] is True
    assert np.isfinite(out["mean_rps"]) and np.isfinite(out["mean_nll"])
    assert out["nll_clipped"] == 0
    assert 0.0 <= out["coverage_80"] <= 1.0
    assert out["mean_width_80"] >= 1.0
    assert out["baseline_mean_rps"] >= 0.0


# ---------------------------------------------------------------------------
# File-based CLI integration (synthetic parquet, isolated tmp data root)
# ---------------------------------------------------------------------------

import datetime as dt  # noqa: E402
import hashlib  # noqa: E402


def _pitch(game_pk, pitcher, date, inning, topbot, ab, pn,
           events="field_out", home="AAA", away="BBB", hand="R"):
    return (game_pk, pitcher, date, inning, topbot, ab, pn, events,
            home, away, hand)


def _frame(rows):
    return pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "inning": pl.Int64,
                "inning_topbot": pl.String, "at_bat_number": pl.Int64,
                "pitch_number": pl.Int64, "events": pl.String,
                "home_team": pl.String, "away_team": pl.String,
                "p_throws": pl.String},
        orient="row",
    )


def _game(game_pk, date, specs):
    rows = []
    ab = 0
    for pitcher, topbot, n_ab, hand in specs:
        for _ in range(n_ab):
            ab += 1
            rows.append(_pitch(game_pk, pitcher, date, 1, topbot, ab, 1,
                               "strikeout" if (ab + pitcher) % 4 == 0
                               else "field_out",
                               hand=hand))
    return rows


def _cli_data_root(tmp_path):
    root = tmp_path / "data"
    digests = {}
    rows_2022 = (_game(901, dt.date(2022, 6, 1),
                       [(501, "Top", 2, "R"), (502, "Bot", 2, "L")])
                 + [_pitch(901, 503, dt.date(2022, 6, 1), 8, "Bot",
                           500, 1)]
                 + _game(902, dt.date(2022, 6, 2),
                         [(503, "Top", 3, "R"), (504, "Bot", 1, "L")]))
    rows_2023 = (_game(1, dt.date(2023, 4, 1),
                       [(501, "Top", 2, "R"), (502, "Bot", 2, "L")])
                 + [_pitch(1, 503, dt.date(2023, 4, 1), 7, "Top",
                           600, 1)]
                 + _game(2, dt.date(2023, 4, 2),
                         [(503, "Top", 3, "R"), (504, "Bot", 1, "L")])
                 + _game(3, dt.date(2023, 4, 3),
                         [(501, "Top", 2, "R"), (503, "Bot", 2, "L")])
                 + _game(4, dt.date(2023, 4, 4),
                         [(502, "Top", 1, "R"), (504, "Bot", 3, "L")])
                 + _game(5, dt.date(2023, 4, 10),
                         [(501, "Top", 2, "R"), (502, "Bot", 2, "L")]))
    for year, rows in ((2022, rows_2022), (2023, rows_2023)):
        dest = root / "Savant-Data" / "regular" / str(year)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / ("statcast_%d_regular.parquet" % year)
        _frame(rows).write_parquet(path)
        digests[year] = hashlib.sha256(path.read_bytes()).hexdigest()
    return root, digests


def _cli_args(tmp_path, root, digests, prereg_name="bf-distribution-design-prereg.md"):
    return ["--out", str(tmp_path / "dist-out"),
            "--data-root", str(root),
            "--prereg", str(ROOT / "research" / "offseason_2026"
                            / prereg_name),
            "--origins", "2023-04-10", "--final-date", "2023-04-20",
            "--fallback-mean", "20.0",
            "--fallback-source", "synthetic test provenance",
            "--fallback-cutoff", "2022-12-31",
            "--season-sha", "2022:%s" % digests[2022],
            "--season-sha", "2023:%s" % digests[2023]]


def test_cli_end_to_end_synthetic_pass(tmp_path):
    from run_bf_distribution_2023 import main  # noqa: E402

    root, digests = _cli_data_root(tmp_path)
    code = main(_cli_args(tmp_path, root, digests))
    assert code == 0
    out = tmp_path / "dist-out"
    import json as _json

    manifest = _json.loads(
        (out / "bf_distribution_manifest.json").read_text())
    assert manifest["status"] == "COMPLETE"
    assert manifest["pooled"]["n_eval"] == 2
    pmfs = pl.read_parquet(out / "pmfs.parquet")
    assert pmfs.shape == (2, 37)
    assert abs(pmfs.sum_horizontal().sum() - 2.0) < 1e-6
    preds = pl.read_csv(out / "predictions.csv")
    assert preds.height == 2
    assert manifest["code"]["run_bf_distribution_2023.py"]
    assert manifest["inputs"]["savant_2023"]["sha256"] == digests[2023]


def test_cli_missing_input_fails(tmp_path):
    from run_bf_distribution_2023 import main  # noqa: E402

    root, digests = _cli_data_root(tmp_path)
    (root / "Savant-Data" / "regular" / "2023"
     / "statcast_2023_regular.parquet").unlink()
    args = _cli_args(tmp_path, root, digests)
    code = main(args)
    assert code == 1
    assert not (tmp_path / "dist-out"
                / "bf_distribution_manifest.json").exists()


def test_cli_digest_mismatch_fails(tmp_path):
    from run_bf_distribution_2023 import main  # noqa: E402

    root, digests = _cli_data_root(tmp_path)
    out = tmp_path / "out2"
    args = ["--out", str(out), "--data-root", str(root),
            "--prereg", str(ROOT / "research" / "offseason_2026"
                            / "bf-distribution-design-prereg.md"),
            "--origins", "2023-04-10", "--final-date", "2023-04-20",
            "--fallback-mean", "20.0",
            "--fallback-source", "synthetic test provenance",
            "--fallback-cutoff", "2022-12-31",
            "--season-sha", "2022:%s" % digests[2022],
            "--season-sha", "2023:%s" % ("0" * 64)]
    code = main(args)
    assert code == 1
    assert not (out / "bf_distribution_manifest.json").exists()


def test_cli_empty_training_blocked(tmp_path):
    from run_bf_distribution_2023 import main  # noqa: E402

    root, digests = _cli_data_root(tmp_path)
    base = _cli_args(tmp_path, root, digests)
    args = (base[:base.index("--origins")]
            + ["--origins", "2023-01-15", "--final-date", "2023-02-01"]
            + base[base.index("--final-date") + 2:])
    out = tmp_path / "dist-out"
    code = main(args)
    assert code == 1  # fail fast: origins cover no training rows
    assert (out / "failure_receipt.json").is_file()
    assert not (out / "bf_distribution_manifest.json").exists()
