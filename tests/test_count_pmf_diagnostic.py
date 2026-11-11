"""Synthetic tests for the keyed K-PMF diagnostic (cohort contract).

SYNTHETIC ONLY: no private inputs, no real-artifact reads, no
re-runs of prior authorized executions, no fitting. The diagnostic
evaluates the DECLARED eligible cohort (registered hash convention,
bk._cohort_hash): forecast keys must equal the cohort exactly;
observations are restricted to the cohort; observed-only starts
outside the cohort are recorded as declared exclusions (exact key
lists, not count subtraction); after restriction the observations
must cover the cohort exactly.

Requirement -> implementation -> test-evidence closure table:
  Log-score sign (positive log loss) + RPS hand values,
  incl. overflow observed K=30 (bucket 23)                -> test 1
  Half-line boundaries (K=3 over 2.5 / under 3.5, etc.)   -> test 2
  Fixed reliability bins: edges, p=0/p=1, empty bins
  (null means, never zero)                                -> test 3
  Paired deltas + shuffled-row alignment; arms separate   -> test 4
  Observed-only starts outside the cohort are recorded
  as declared exclusions with EXACT key membership
  (broader observation source; scoring proceeds on the
  cohort)                                                 -> test 5
  Cohort start missing from observations refuses          -> test 6
  Forecast keys != declared cohort refuses (both
  directions)                                             -> test 7
  Bad cohort identity (wrong hash / duplicate / null /
  missing columns) refuses                                -> test 8
  Malformed labels, observed K, PMF mass refuse           -> test 9
  CLI: cohort args required; ack gate; write-once;
  success writes the diagnostic with cohort accounting    -> test 10
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import count_pmf_diagnostic as cpd  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402

START_A = (900201, "Top", 700001)
START_B = (900201, "Bot", 700002)
START_C = (900301, "Top", 700003)  # broader-observation extra start
START_D = (900401, "Bot", 700004)  # broader-observation extra start
STARTS = [START_A, START_B]
STARTS_WIDE = [START_A, START_B, START_C, START_D]


def _pmf_control() -> np.ndarray:
    pmf = np.zeros(ad.K_MAX)
    pmf[2] = 0.5
    pmf[3] = 0.5
    return pmf


def _pmf_challenger() -> np.ndarray:
    pmf = np.zeros(ad.K_MAX)
    pmf[5] = 0.25
    pmf[ad.K_MAX - 1] = 0.75
    return pmf


def _k_pmf_frame(starts=STARTS, shuffle=True) -> pl.DataFrame:
    rows = []
    for gk, side, p in starts:
        for b in range(ad.K_MAX):
            rows.append((gk, side, p, b, float(_pmf_control()[b]),
                         float(_pmf_challenger()[b])))
    if shuffle:
        perm = np.random.default_rng(20261001).permutation(len(rows))
        rows = [rows[i] for i in perm]
    return pl.DataFrame(
        rows, schema={"game_pk": pl.Int64, "side": pl.Utf8,
                      "pitcher": pl.Int64, "bucket": pl.Int64,
                      "pmf_control": pl.Float64,
                      "pmf_challenger": pl.Float64}, orient="row")


def _cohort_frame(starts=STARTS) -> pl.DataFrame:
    return pl.DataFrame(list(starts), schema={
        "game_pk": pl.Int64, "side": pl.Utf8,
        "pitcher": pl.Int64}, orient="row")


def _cohort_hash(starts=STARTS) -> str:
    return bk._cohort_hash(list(starts))


def _observed_frame(ks=(3, 30), starts=STARTS, shuffle=True):
    rows = [(gk, side, p, k) for (gk, side, p), k in zip(starts, ks)]
    if shuffle:
        perm = np.random.default_rng(20261001).permutation(len(rows))
        rows = [rows[i] for i in perm]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64}, orient="row")


def _assessment_frame(starts=STARTS, ks=(3, 30)) -> pl.DataFrame:
    """Per-PA prepared-assessment fixture: realized_k per start = the
    supplied ks (start B's 30 = declared overflow category)."""
    rows = []
    for (gk, side, p), k in zip(starts, ks):
        for i in range(max(int(k), 1)):
            label = 0 if i < k else 2
            rows.append((gk, side, p, i + 1, 900000 + i, label))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


def _diagnose(starts=STARTS, ks=(3, 30), **overrides):
    kwargs = dict(
        k_pmf=_k_pmf_frame(starts),
        observed=_observed_frame(ks=ks, starts=starts),
        pmf_columns=["pmf_control", "pmf_challenger"],
        cohort=_cohort_frame(starts),
        expected_cohort_hash=_cohort_hash(starts))
    kwargs.update(overrides)
    return cpd.diagnose(**kwargs)


# ------------------- 1. log-score sign + RPS (hand values, overflow)
def test_logscore_sign_and_rps_hand_values():
    result = cpd.diagnose(_k_pmf_frame(), _observed_frame(),
                          pmf_columns=["pmf_control",
                                       "pmf_challenger"],
                          cohort=_cohort_frame(),
                          expected_cohort_hash=_cohort_hash())
    ctrl = result["arms"]["pmf_control"]
    chall = result["arms"]["pmf_challenger"]
    # natural log, positive log loss; overflow K=30 reads bucket 23
    # (control: empty -> 1e-12 clip)
    assert ctrl["count_logloss_mean"] == pytest.approx(
        (-math.log(0.5) + -math.log(1e-12)) / 2)
    assert chall["count_logloss_mean"] == pytest.approx(
        (-math.log(1e-12) + -math.log(0.75)) / 2)
    assert ctrl["count_logloss_mean"] > 0
    # summed-CDF-squared RPS, hand-computed, tail-aware:
    #   A (K=3, control): cdf 0.5 at t=2 -> (0.5-0)^2 = 0.25
    #   B (K=30, control): cdf 1.0 from t=3, obs 1 from t=23
    #     -> (1-0)^2 x 20 = 20.25
    #   A (K=3, challenger): cdf 0 through t=4 -> 1 x 2 = 2, plus
    #     (0.25-1)^2 x 18 = 10.125 -> 12.125
    #   B (K=30, challenger): (0.25-0)^2 x 18 = 1.125
    assert ctrl["count_rps_mean"] == pytest.approx(
        (0.25 + 20.25) / 2)
    assert chall["count_rps_mean"] == pytest.approx(
        (12.125 + 1.125) / 2)
    # overflow start (K=30) is observed-over at every in-scope line
    for name, s in ctrl["lines"].items():
        expected_freq = 1.0 if name == "2.5" else 0.5
        assert s["observed_over_frequency"] == pytest.approx(
            expected_freq)


# ------------------- 2. half-line boundaries (parametrized)
@pytest.mark.parametrize("k,line,expected_over", [
    (3, 2.5, 1.0),   # K=3 is over 2.5
    (3, 3.5, 0.0),   # K=3 is under 3.5
    (2, 2.5, 0.0),   # boundary bucket itself is under
    (4, 3.5, 1.0),
    (30, 9.5, 1.0),  # overflow start is over every in-scope line
])
def test_half_line_boundaries(k, line, expected_over):
    pmf = _pmf_control()
    start = START_A
    rows = [(start[0], start[1], start[2], b, float(pmf[b]))
            for b in range(ad.K_MAX)]
    k_pmf = pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "bucket": pl.Int64, "pmf_control": pl.Float64}, orient="row")
    observed = pl.DataFrame([start + (k,)], schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64}, orient="row")
    result = cpd.diagnose(
        k_pmf, observed, pmf_columns=["pmf_control"],
        cohort=pl.DataFrame([start], schema={
            "game_pk": pl.Int64, "side": pl.Utf8,
            "pitcher": pl.Int64}, orient="row"),
        expected_cohort_hash=bk._cohort_hash([start]))
    s = result["arms"]["pmf_control"]["lines"][str(line)]
    assert s["observed_over_frequency"] == pytest.approx(
        expected_over)
    assert s["predicted_over_mean"] == pytest.approx(
        mk.model_p_over(pmf, line))


# ------------------- 3. reliability: fixed bins, edges, empty bins
def test_fixed_reliability_edges_and_empty_bins():
    pred = np.asarray([0.0, 0.1, 0.95, 1.0])
    obs = np.asarray([1.0, 0.0, 1.0, 0.0])
    summary = cpd._fixed_reliability(pred, obs)
    by_bin = {(s["bin_lo"], s["bin_hi"]): s for s in summary}
    assert len(summary) == 10
    first = by_bin[(0.0, 0.1)]
    assert first["n"] == 1
    assert first["mean_forecast"] == pytest.approx(0.0)
    assert first["observed_frequency"] == pytest.approx(1.0)
    second = by_bin[(0.1, 0.2)]
    assert second["n"] == 1
    assert second["mean_forecast"] == pytest.approx(0.1)
    assert second["observed_frequency"] == pytest.approx(0.0)
    last = by_bin[(0.9, 1.0)]
    assert last["n"] == 2  # p = 1 included in the last bin
    assert last["mean_forecast"] == pytest.approx(0.975)
    assert last["observed_frequency"] == pytest.approx(0.5)
    for (lo, hi), s in by_bin.items():
        if s["n"] == 0:
            assert s["mean_forecast"] is None
            assert s["observed_frequency"] is None
    assert by_bin[(0.2, 0.3)]["n"] == 0


# ------------------- 4. paired deltas + shuffled-row alignment
def test_paired_deltas_and_shuffle_alignment():
    result_shuffled = cpd.diagnose(
        _k_pmf_frame(shuffle=True), _observed_frame(shuffle=True),
        pmf_columns=["pmf_control", "pmf_challenger"],
        cohort=_cohort_frame(), expected_cohort_hash=_cohort_hash())
    result_sorted = cpd.diagnose(
        _k_pmf_frame(shuffle=False), _observed_frame(shuffle=False),
        pmf_columns=["pmf_control", "pmf_challenger"],
        cohort=_cohort_frame(), expected_cohort_hash=_cohort_hash())
    assert result_shuffled == result_sorted
    paired = result_shuffled["paired"]
    assert paired["challenger"] == "pmf_challenger"
    assert paired["control"] == "pmf_control"
    assert paired["n_paired_starts"] == 2
    ctrl = result_shuffled["arms"]["pmf_control"]
    chall = result_shuffled["arms"]["pmf_challenger"]
    assert paired["count_logloss_delta_mean"] == pytest.approx(
        chall["count_logloss_mean"] - ctrl["count_logloss_mean"])
    assert paired["count_rps_delta_mean"] == pytest.approx(
        chall["count_rps_mean"] - ctrl["count_rps_mean"])
    assert paired["per_line_brier_delta_mean"]["2.5"] == \
        pytest.approx(0.0 - 0.25)
    for name in ("3.5", "4.5"):
        assert paired["per_line_brier_delta_mean"][name] == \
            pytest.approx(0.5 - 0.5)
    for name in ("5.5", "6.5", "7.5", "8.5", "9.5"):
        assert paired["per_line_brier_delta_mean"][name] == \
            pytest.approx(0.3125 - 0.5)
    assert paired["count_rps_delta_mean"] == pytest.approx(-3.625)
    assert (ctrl["per_start_count_rps"]
            != chall["per_start_count_rps"])


def test_single_arm_has_no_paired_section():
    result = cpd.diagnose(_k_pmf_frame(), _observed_frame(),
                          pmf_columns=["pmf_control"],
                          cohort=_cohort_frame(),
                          expected_cohort_hash=_cohort_hash())
    assert result["paired"] is None
    assert list(result["arms"]) == ["pmf_control"]


# ------------------- 5. observed-only starts OUTSIDE the cohort:
#     declared exclusions with EXACT key membership
def test_observed_outside_cohort_excluded_exactly():
    """Broader observation source: two extra observed starts that are
    NOT in the declared cohort. The exclusion list must be exactly
    those keys (membership, not count subtraction); scoring proceeds
    on the cohort only."""
    extra_starts = [START_C, START_D]
    observed = _observed_frame(ks=(3, 30, 2, 5),
                               starts=STARTS + extra_starts)
    cohort = _cohort_frame()
    result = cpd.diagnose(_k_pmf_frame(), observed,
                          pmf_columns=["pmf_control",
                                       "pmf_challenger"],
                          cohort=cohort,
                          expected_cohort_hash=_cohort_hash())
    excl = result["accounting"]["declared_exclusions"][
        "observed_only_outside_cohort"]
    assert excl["n"] == 2
    assert [tuple(k) for k in excl["keys"]] == \
        sorted([START_C, START_D])
    assert result["accounting"]["n_observed_starts_full"] == 4
    assert result["accounting"]["n_observed_starts_restricted"] == 2
    assert result["accounting"]["n_matched_starts"] == 2
    for arm in result["arms"].values():
        assert arm["n_matched_starts"] == 2


# ------------------- 6. cohort start missing from observations
def test_cohort_start_missing_from_observations_refused():
    observed = _observed_frame(ks=(3,), starts=[START_A])
    with pytest.raises(ValueError) as exc:
        cpd.diagnose(_k_pmf_frame(), observed,
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())
    msg = str(exc.value)
    assert "observations after restriction/declared cohort" in msg
    assert "missing_from_observations after restriction=0" in msg \
        or "missing_from_observations after restriction" in msg
    assert "missing_from_observations after restriction" in msg \
        or "missing_from" in msg
    assert "1" in msg


# ------------------- 7. forecast keys != declared cohort
def test_forecast_keys_not_equal_cohort_refused():
    # forecast missing a cohort start -> forecast/cohort mismatch
    partial = _k_pmf_frame().filter(
        ~((pl.col("game_pk") == START_B[0])
          & (pl.col("side") == START_B[1])
          & (pl.col("pitcher") == START_B[2])))
    with pytest.raises(ValueError) as exc:
        cpd.diagnose(partial, _observed_frame(),
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())
    assert "forecast/declared cohort" in str(exc.value)
    # forecast has an extra start outside the cohort -> same gate
    extra_rows = []
    for b in range(ad.K_MAX):
        extra_rows.append((START_C[0], START_C[1], START_C[2], b,
                           float(_pmf_control()[b]),
                           float(_pmf_challenger()[b])))
    bad = pl.concat([_k_pmf_frame(), pl.DataFrame(extra_rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "bucket": pl.Int64, "pmf_control": pl.Float64,
        "pmf_challenger": pl.Float64}, orient="row")])
    with pytest.raises(ValueError) as exc:
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())
    assert "missing_from_declared cohort=1" in str(exc.value)


# ------------------- 8. bad cohort identity
def test_cohort_identity_failures():
    with pytest.raises(ValueError, match="cohort identity mismatch"):
        cpd.diagnose(_k_pmf_frame(), _observed_frame(),
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash="0" * 64)
    dup = pl.concat([_cohort_frame(), _cohort_frame().head(1)])
    with pytest.raises(ValueError, match="duplicate identity"):
        cpd.validate_cohort(dup, _cohort_hash())
    null_cohort = _cohort_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001).then(None)
        .otherwise(pl.col("pitcher")).alias("pitcher"))
    with pytest.raises(ValueError, match="null value"):
        cpd.validate_cohort(null_cohort, _cohort_hash())
    with pytest.raises(ValueError, match="missing required column"):
        cpd.validate_cohort(_cohort_frame().drop("side"),
                            _cohort_hash())


# ------------------- 9. malformed labels / observed K / PMF mass
def test_malformed_labels_and_observed_k_refused():
    bad = _assessment_frame().with_columns(
        pl.when(pl.col("at_bat_number") == 1).then(9)
        .otherwise(pl.col("class_label")).alias("class_label"))
    with pytest.raises(ValueError, match="class labels outside"):
        cpd.derive_observed_k(bad)
    bad = _observed_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001).then(2.5)
        .otherwise(pl.col("realized_k")).cast(pl.Float64)
        .alias("realized_k"))
    with pytest.raises(ValueError, match="integer-valued"):
        cpd.diagnose(_k_pmf_frame(), bad,
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())
    bad = _observed_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001).then(-1)
        .otherwise(pl.col("realized_k")).alias("realized_k"))
    with pytest.raises(ValueError, match="nonnegative"):
        cpd.diagnose(_k_pmf_frame(), bad,
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())


def test_malformed_pmf_mass_refused():
    bad = _k_pmf_frame().with_columns(
        pl.when((pl.col("bucket") == 2)
                & (pl.col("pitcher") == 700001)).then(-0.1)
        .otherwise(pl.col("pmf_control")).alias("pmf_control"))
    with pytest.raises(ad.AdapterError, match="PMF out of"):
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())
    bad = _k_pmf_frame().with_columns(
        pl.when(pl.col("bucket") == 3).then(float("nan"))
        .otherwise(pl.col("pmf_challenger")).alias("pmf_challenger"))
    with pytest.raises(ad.AdapterError, match="non-finite PMF"):
        cpd.diagnose(bad, _observed_frame(),
                     pmf_columns=["pmf_control", "pmf_challenger"],
                     cohort=_cohort_frame(),
                     expected_cohort_hash=_cohort_hash())


# ------------------- 10. CLI: cohort args, ack, write-once, success
def test_cli_cohort_args_and_success(tmp_path):
    k_pmf_path = tmp_path / "k_pmf.parquet"
    assessment_path = tmp_path / "assessment.parquet"
    cohort_path = tmp_path / "cohort.parquet"
    _k_pmf_frame().write_parquet(k_pmf_path)
    _assessment_frame().write_parquet(assessment_path)
    _cohort_frame().write_parquet(cohort_path)
    out = tmp_path / "diag_out"
    argv = ["--k-pmf", str(k_pmf_path),
            "--assessment", str(assessment_path),
            "--arms", "pmf_control,pmf_challenger",
            "--cohort-keys", str(cohort_path),
            "--expected-cohort-hash", _cohort_hash(),
            "--out-dir", str(out),
            "--execution-ack", cpd.EXECUTION_ACK_TOKEN]
    assert cpd.main(argv) == 0
    payload = json.loads(
        (out / "count_pmf_diagnostic.json").read_text(
            encoding="utf-8"))
    assert payload["diagnostic_id"] == "count_pmf_diagnostic_v1"
    assert payload["accounting"]["cohort_identity"]["match"] is True
    assert payload["arms"]["pmf_control"]["n_matched_starts"] == 2
    assert payload["paired"]["count_rps_delta_mean"] == \
        pytest.approx(-3.625)
    # write-once: same destination refuses
    with pytest.raises(ValueError, match="destination exists"):
        cpd.main(argv)
    # missing cohort args refuse at parse time
    with pytest.raises(SystemExit):
        cpd.main(["--k-pmf", str(k_pmf_path), "--assessment",
                  str(assessment_path), "--arms", "pmf_control",
                  "--out-dir", str(tmp_path / "out2"),
                  "--execution-ack", cpd.EXECUTION_ACK_TOKEN])
    # wrong ack refuses
    bad_argv = list(argv)
    bad_argv[bad_argv.index("--execution-ack") + 1] = "WRONG"
    with pytest.raises(ValueError, match="execution acknowledgement"):
        cpd.main(bad_argv)
