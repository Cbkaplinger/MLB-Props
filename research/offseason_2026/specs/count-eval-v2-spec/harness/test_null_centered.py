"""Synthetic tests for the C3.8 null-centered approximate bootstrap test
(amendment registered 2026-10-15 in EXPERIMENT_CARD.md C3.8 + the
"hypothesis_test" section of freeze_recency_batch_v1.json).

All tests are synthetic-only; no real-data load happens here and no real-data
run is authorized by passing tests (spec section 8).

Run standalone:
    python -m pytest test_null_centered.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from comparison import (  # noqa: E402
    HOLM_FAMILY_ALPHA, HYPOTHESIS_TEST_CONTRASTS, RunConfig,
    holm_adjust, null_centered_contrast_test, null_centered_p_value,
    run_comparison, slate_date_bootstrap, slate_date_draws,
)

TOL = 1e-12


# ---------------------------------------------------------------------------
# (a) Hand-computed fixture: known deltas + draws -> exact p-value, tie case
# ---------------------------------------------------------------------------

def test_null_centered_p_value_hand_computed_with_tie():
    # delta_obs = 0.5; replicate deltas [0.6, 0.5, 0.0, 1.0]
    # centered errors: [0.1, 0.0, -0.5, 0.5]
    # |error| >= 0.5 -> the -0.5 and the 0.5 BOTH count (ties via >=) -> 2 hits
    # p = (1 + 2) / (4 + 1) = 0.6
    delta_rep = np.array([0.6, 0.5, 0.0, 1.0])
    p = null_centered_p_value(0.5, delta_rep)
    assert p == pytest.approx(0.6, abs=TOL)


def test_null_centered_p_value_tie_counts_toward_numerator():
    # |error| EXACTLY equal to |delta| must be counted (>=, not >).
    # delta_obs = 0.25, draw delta* = 0.50 -> centered error = +0.25 = |delta|
    # -> tie hit -> p = (1 + 1) / (1 + 1) = 1.0
    assert null_centered_p_value(0.25, np.array([0.50])) == 1.0
    # the same draw a hair inside the boundary misses -> p = 1/2, so the tie
    # handling is observable
    assert null_centered_p_value(0.25, np.array([0.499])) == 0.5


def test_contrast_test_hand_computed_from_shared_draw_matrix():
    # Two candidates over pooled rows; hand-built replicate matrix res.
    # x rows: constant 0.6; y rows: constant 0.1 -> observed delta = 0.5.
    # res columns (x, y) per replicate hand-set so delta*_b = res[:,x] - res[:,y]
    # = [0.6, 0.5, 0.0, 1.0] -> p = 0.6 exactly (same hand computation as
    # test_null_centered_p_value_hand_computed_with_tie).
    values = {"x": np.full(8, 0.6), "y": np.full(8, 0.1)}
    res = np.array([
        [0.6, 0.0],
        [0.5, 0.0],
        [0.0, 0.0],
        [1.0, 0.0],
    ])
    out = null_centered_contrast_test(
        values, [("c", "x", "y")], dates=["d"] * 8, blocks=["b"] * 8,
        n_boot=4, seed=1, res=res)
    c = out["contrasts"]["c"]
    assert c["delta"] == pytest.approx(0.5, abs=TOL)
    assert c["p_value"] == pytest.approx(0.6, abs=TOL)


def test_contrast_test_replicates_match_slate_date_draws():
    # The contrast replicates must be the differences of the SAME slate-date
    # replicate matrix slate_date_draws produces (shared-draw contract).
    rng = np.random.default_rng(11)
    n = 120
    dates = [f"2024-{1 + i // 60:02d}-{1 + i % 28:02d}" for i in range(n)]
    blocks = ["block_2024H1"] * (n // 2) + ["block_2024H2"] * (n - n // 2)
    values = {"a": rng.random(n), "b": rng.random(n)}
    out = null_centered_contrast_test(
        values, [("c", "a", "b")], dates, blocks, n_boot=50, seed=20261001)
    res = slate_date_draws(values, dates, blocks, n_boot=50, seed=20261001)
    delta_rep = res[:, 0] - res[:, 1]
    expected = (1.0 + int(np.sum(
        np.abs(delta_rep - out["contrasts"]["c"]["delta"])
        >= abs(out["contrasts"]["c"]["delta"])))) / 51.0
    assert out["contrasts"]["c"]["p_value"] == pytest.approx(expected, abs=TOL)


# ---------------------------------------------------------------------------
# (b) p in (0, 1]; decreases as |delta| moves away from the centered null
# ---------------------------------------------------------------------------

def test_p_in_unit_interval_and_decreases_away_from_null():
    rng = np.random.default_rng(3)
    delta_rep = rng.normal(0.0, 0.02, size=200)
    deltas = [0.0, 0.005, 0.02, 0.05, 0.2, 1.0]
    ps = [null_centered_p_value(d, delta_rep) for d in deltas]
    for p in ps:
        assert 0.0 < p <= 1.0
        assert p >= 1.0 / (delta_rep.size + 1.0)
    for small, big in zip(ps, ps[1:]):
        assert big <= small
    assert ps[-1] < ps[0]


# ---------------------------------------------------------------------------
# (c) Null-centered draws symmetric around 0 -> conservative behavior:
#     p >= 1/(B+1) always; a large |delta| (draws tracking the statistic, so
#     the centered errors are unchanged) gives the minimum p = 1/(B+1)
# ---------------------------------------------------------------------------

def test_symmetric_null_draws_conservative_and_large_delta_small_p():
    rng = np.random.default_rng(5)
    half = rng.normal(0.0, 1.0, size=500)
    errors = np.concatenate([half, -half])  # exactly symmetric around 0
    # null case: statistic replicates = errors + 0 -> draws symmetric around
    # 0; every |e| >= 0 counts (>= keeps ties) -> maximally conservative p
    p_null = null_centered_p_value(0.0, errors)
    assert p_null == 1.0
    assert p_null >= 1.0 / (errors.size + 1.0)
    # large |delta|: the replicate deltas track the statistic
    # (delta_b = delta + error_b), so the centered errors stay the symmetric
    # errors above and none reaches |delta| -> minimal p
    p_large = null_centered_p_value(50.0, 50.0 + errors)
    assert p_large == 1.0 / (errors.size + 1.0)
    assert p_large < p_null
    # mid-scale delta: p strictly inside (0, 1], still conservative
    p_mid = null_centered_p_value(2.0, 2.0 + errors)
    assert 1.0 / (errors.size + 1.0) <= p_mid < p_null


# ---------------------------------------------------------------------------
# (d) Holm: monotone adjusted p-values; family-level 0.05 respected
# ---------------------------------------------------------------------------

def test_holm_hand_computed_monotone_and_family_level():
    raw = {"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.20}
    adj = holm_adjust(raw)
    # hand computation: sorted a(.01) c(.03) b(.04) d(.20), m=4
    # a: 4*.01=.04; c: max(.04, 3*.03)=.09; b: max(.09, 2*.04)=.09;
    # d: max(.09, 1*.20)=.20
    assert adj["a"] == pytest.approx(0.04, abs=TOL)
    assert adj["c"] == pytest.approx(0.09, abs=TOL)
    assert adj["b"] == pytest.approx(0.09, abs=TOL)
    assert adj["d"] == pytest.approx(0.20, abs=TOL)
    order = sorted(raw, key=lambda k: raw[k])
    seq = [adj[k] for k in order]
    assert all(x <= y + TOL for x, y in zip(seq, seq[1:]))  # monotone
    for k in raw:
        assert adj[k] >= raw[k] - TOL  # never shrinks a p-value
        assert adj[k] <= 1.0
    # family-level 0.05 respected: Holm step-down rejects exactly {a}
    rejected = {k for k in order if adj[k] <= HOLM_FAMILY_ALPHA}
    assert rejected == {"a"}


def test_holm_capped_at_one_and_stable_under_ties():
    adj = holm_adjust({"x": 0.7, "y": 0.9, "z": 0.8})
    assert adj["x"] == 1.0 and adj["y"] == 1.0 and adj["z"] == 1.0
    tie = holm_adjust({"p": 0.03, "q": 0.03})
    assert tie["p"] == tie["q"] == pytest.approx(0.06, abs=TOL)


def test_holm_over_registered_contrasts_monotone_from_runner_output(
        synth_factory, tmp_path):
    out = synth_factory(tmp_path, CANDS4, "holm4")
    m = json.loads((out / "metrics.json").read_text())
    ht = m["pooled_dev"]["hypothesis_test_brier_raw"]
    assert set(ht["contrasts"]) == {cid for cid, _, _ in HYPOTHESIS_TEST_CONTRASTS}
    order = sorted(ht["contrasts"], key=lambda k: ht["contrasts"][k]["p_value"])
    seq = [ht["contrasts"][k]["p_holm"] for k in order]
    assert all(x <= y + TOL for x, y in zip(seq, seq[1:]))
    for cid, c in ht["contrasts"].items():
        assert 0.0 < c["p_value"] <= 1.0
        assert c["p_holm"] >= c["p_value"] - TOL
        assert c["p_holm"] <= 1.0
    # ordinary CIs elsewhere stay UNADJUSTED (no multiplicity inflation)
    assert "multiplicity" in ht and "UNADJUSTED" in ht["multiplicity"]


# ---------------------------------------------------------------------------
# (e) Arm swap reverses the signed delta; the two-sided p is unchanged
# ---------------------------------------------------------------------------

def test_arm_swap_reverses_delta_and_keeps_p():
    rng = np.random.default_rng(9)
    n = 100
    dates = [f"2024-{1 + i // 50:02d}-{1 + i % 28:02d}" for i in range(n)]
    blocks = ["block_2024H1"] * (n // 2) + ["block_2025H1"] * (n - n // 2)
    values = {"a": rng.random(n) + 0.03, "b": rng.random(n)}
    res = slate_date_draws(values, dates, blocks, n_boot=64, seed=20261001)
    fwd = null_centered_contrast_test(
        values, [("f", "a", "b")], dates, blocks, n_boot=64, seed=20261001,
        res=res)
    rev = null_centered_contrast_test(
        values, [("r", "b", "a")], dates, blocks, n_boot=64, seed=20261001,
        res=res)
    assert fwd["contrasts"]["f"]["delta"] == pytest.approx(
        -rev["contrasts"]["r"]["delta"], abs=TOL)
    assert fwd["contrasts"]["f"]["p_value"] == rev["contrasts"]["r"]["p_value"]


# ---------------------------------------------------------------------------
# Runner integration: the registered 4-contrast test on pooled dev, RAW Brier
# ---------------------------------------------------------------------------

CANDS4 = ["P1_B_logreg", "P1_H3_pitcher_ew_only", "P1_H3_batter_ew_only",
          "P1_H3_incumbent_refit"]


@pytest.fixture(scope="module")
def synth_factory(tmp_path_factory):
    pa, feat = _mini_synth()
    tmp = tmp_path_factory.mktemp("null_centered")
    pa_path = tmp / "pa.parquet"
    feat_path = tmp / "feat.parquet"
    pa.write_parquet(pa_path)
    feat.write_parquet(feat_path)
    counter = {"i": 0}

    def _factory(parent, candidates, label):
        counter["i"] += 1
        return run_comparison(RunConfig(
            pa_table_path=str(pa_path), features_path=str(feat_path),
            candidates=candidates, include_confirm=False,
            output_root=str(parent / f"out_{label}_{counter['i']}"),
            run_label=label))

    return _factory


def _mini_synth():
    """Small synthetic fixture (reuse of the test_comparison generator logic,
    shrunk for speed) covering 2023-01-01..2025-09-28."""
    import datetime as dt
    import polars as pl
    from comparison import log5

    rng = np.random.default_rng(7)
    days = []
    d = dt.date(2023, 1, 1)
    end = dt.date(2025, 9, 28)
    while d <= end:
        days.append(d)
        d += dt.timedelta(days=1)
    dates = np.repeat(np.array(days, dtype="datetime64[D]"), 3)
    n = dates.size
    game_pk = (np.arange(n) // 3 + 900_000).astype(np.int64)
    ab = (np.arange(n) % 3 + 1).astype(np.int64)
    batter = rng.integers(1000, 2000, size=n).astype(np.int64)
    lg = 0.22 + 0.02 * rng.random(n)
    p_p = np.clip(lg + rng.normal(0, 0.05, n), 0.05, 0.6)
    p_b = np.clip(lg + rng.normal(0, 0.05, n), 0.05, 0.6)
    y = (rng.random(n) < log5(p_p, p_b, lg)).astype(np.int8)
    gdate = pl.Series("game_date", dates).cast(pl.Date)
    src_date = pl.Series("src_date_pitcher",
                         dates - np.timedelta64(1, "D")).cast(pl.Date)
    pa = pl.DataFrame({
        "game_pk": game_pk, "game_date": gdate,
        "at_bat_number": ab, "batter": batter, "y": y,
    })
    feat = pl.DataFrame({
        "game_pk": game_pk, "at_bat_number": ab, "batter": batter,
        "game_date": gdate,
        "p_pitcher_prior_w150": p_p, "p_batter_prior_w150": p_b,
        "lg_rate": lg,
        "n_prior_pitcher": rng.integers(0, 800, n).astype(np.int64),
        "n_prior_batter": rng.integers(0, 800, n).astype(np.int64),
        "cold_start": (rng.random(n) < 0.02).astype(np.int8),
        "ew_pitcher": np.clip(p_p + rng.normal(0, 0.01, n), 0.01, 0.9),
        "ew_batter": np.clip(p_b + rng.normal(0, 0.01, n), 0.01, 0.9),
        "src_date_pitcher": src_date, "src_type_pitcher": "entity_history",
        "src_type_lg": "league_history",
    })
    return pa, feat


def test_runner_registers_all_four_contrasts(synth_factory, tmp_path):
    out = synth_factory(tmp_path, CANDS4, "reg4")
    m = json.loads((out / "metrics.json").read_text())
    ht = m["pooled_dev"]["hypothesis_test_brier_raw"]
    assert set(ht["contrasts"]) == {cid for cid, _, _ in HYPOTHESIS_TEST_CONTRASTS}
    assert ht["contrasts_skipped_endpoints_absent"] == []
    assert ht["n_resamples"] == 2000 and ht["seed"] == 20261001
    assert ht["metric"] == "Brier" and "RAW" in ht["lane"]
    # observed delta = difference of the pooled RAW Brier point estimates
    pooled = m["pooled_dev"]["candidates"]
    for cid, a, b in HYPOTHESIS_TEST_CONTRASTS:
        c = ht["contrasts"][cid]
        assert c["a"] == a and c["b"] == b
        assert c["delta"] == pytest.approx(
            pooled[a]["brier"] - pooled[b]["brier"], abs=1e-12)
    # deterministic: an identical rerun reproduces every p-value exactly
    out2 = synth_factory(tmp_path, CANDS4, "reg4")
    ht2 = json.loads((out2 / "metrics.json").read_text())[
        "pooled_dev"]["hypothesis_test_brier_raw"]
    assert ht2["contrasts"] == ht["contrasts"]


def test_runner_skips_contrasts_with_absent_endpoints(synth_factory, tmp_path):
    out = synth_factory(
        tmp_path, ["P0_log5", "P1_B_logreg", "P1_H3_incumbent_refit"], "reg3")
    m = json.loads((out / "metrics.json").read_text())
    ht = m["pooled_dev"]["hypothesis_test_brier_raw"]
    assert ht["contrasts"] == {}
    assert ht["contrasts_skipped_endpoints_absent"] == \
        [cid for cid, _, _ in HYPOTHESIS_TEST_CONTRASTS]


def test_shared_draw_stream_matches_paired_baseline_bootstrap(
        synth_factory, tmp_path):
    # The date draws behind the C3.8 test must be the SAME stream as the
    # slate-date bootstrap used for the paired intervals (same
    # blocks/dates/n_boot/seed), so candidate and contrast replicates are
    # paired at the draw level. Checked directly: with identical
    # blocks/dates/seed the bootstrap's replicate column and the contrast
    # test's replicate deltas come from the same draw matrix.
    out = synth_factory(tmp_path, CANDS4, "shared")
    m = json.loads((out / "metrics.json").read_text())
    ht = m["pooled_dev"]["hypothesis_test_brier_raw"]
    assert ht["seed"] == 20261001 and ht["n_resamples"] == 2000
    rng = np.random.default_rng(2)
    n = 60
    dates = [f"2024-{1 + i // 30:02d}-{1 + i % 28:02d}" for i in range(n)]
    blocks = ["block_2024H1"] * (n // 2) + ["block_2024H2"] * (n - n // 2)
    vals = {"u": rng.random(n), "v": rng.random(n)}
    bs = slate_date_bootstrap(vals, dates, blocks, n_boot=32, seed=20261001)
    ct = null_centered_contrast_test(
        vals, [("t", "u", "v")], dates, blocks, n_boot=32, seed=20261001)
    draws = slate_date_draws(vals, dates, blocks, 32, 20261001)
    # the bootstrap's ci95 is a percentile of the SAME replicate column the
    # contrast test differences are built from
    assert bs["u"]["ci95"][0] == pytest.approx(
        float(np.percentile(draws[:, 0], 2.5)), abs=TOL)
    assert ct["contrasts"]["t"]["delta"] == pytest.approx(
        float(vals["u"].mean() - vals["v"].mean()), abs=TOL)
    assert ct["contrasts"]["t"]["p_value"] == pytest.approx(
        null_centered_p_value(
            ct["contrasts"]["t"]["delta"], draws[:, 0] - draws[:, 1]),
        abs=TOL)
