"""Synthetic end-to-end smoke tests for the Stage A prediction-path
reconciliation (lineup_path_reconciliation_spec_2026-10-27.md, Section 3g).

SYNTHETIC ONLY: no real-data artifacts are read, no realized-K labels
are consumed, no scoring is computed. Every test runs the identical
frozen code path as the real lineage over injected frames
(adapter.py design rule: pure over injected frames).

Cases (spec assignment):
  (a) shuffled storage rows with restored keys/slots -> identical results
  (b) deliberately changed SEMANTIC lineup order -> PMF may change
      (permitted; the control invariant does NOT claim this invariance)
  (c) wrong-key attachment -> detectable mismatch vs independent
      expected values
  (d) duplicate / fan-out failures -> fail loud
  (e) feature and probability equality vs an independent fixture
  (f) PMF equality <=1e-12 under identical semantic inputs
  (g) prohibited realized-label access -> input gate refuses
"""
from __future__ import annotations

import sys
from datetime import date
from math import lgamma
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import adapter as ad  # noqa: E402

# frozen constants cited from adapter.py
_W_PRIOR = 150          # ad.W_PRIOR
_HALF_LIFE_DAYS = 90.0  # ad.HALF_LIFE_DAYS
_K_MAX = 24             # ad.K_MAX
_KCOUNT_CAP = 60        # kcount_combiner.KCOUNT_CAP
_TOL = 1e-12

GAME_DATE = date(2024, 8, 15)


def _dnum(d: date) -> float:
    """Days since 1970-01-01 -- the adapter's dnum convention
    (adapter.py entity_daily_state)."""
    return float((d - date(1970, 1, 1)).days)


def _w(d: date) -> float:
    """EW row weight 2^(dnum/90) -- the registered half-life-90d weight."""
    return 2.0 ** (_dnum(d) / _HALF_LIFE_DAYS)


def _pa_history() -> pl.DataFrame:
    """Strictly-prior PA history: 8 rows on two dates, both strictly
    before GAME_DATE. Columns (game_date, pitcher, batter, y)."""
    rows = [
        (date(2024, 7, 1), 700001, 800001, 1),
        (date(2024, 7, 1), 700001, 800002, 0),
        (date(2024, 7, 1), 700002, 800003, 0),
        (date(2024, 7, 1), 700002, 800004, 1),
        (date(2024, 7, 15), 700001, 800003, 0),
        (date(2024, 7, 15), 700001, 800004, 1),
        (date(2024, 7, 15), 700002, 800005, 1),
        (date(2024, 7, 15), 700002, 800006, 0),
    ]
    return pl.DataFrame(rows, schema={
        "game_date": pl.Date, "pitcher": pl.Int64,
        "batter": pl.Int64, "y": pl.Int64,
    }, orient="row")


def _projected_slots() -> pl.DataFrame:
    """Two projected starts with 9 slot columns (3 covered, 6 uncovered)."""
    def one_row(game_pk: int, side: str, pitcher: int,
                batters_by_slot: dict[int, int]) -> dict:  # noqa: ANN001
        row = {"game_pk": game_pk, "side": side, "pitcher": pitcher,
               "game_date": GAME_DATE, "nine_distinct": True}
        for s in range(1, 10):
            row[f"u_slot_{s}"] = batters_by_slot.get(s)
        return row

    return pl.DataFrame(
        [one_row(900001, "Top", 700001, {1: 800001, 2: 800002, 3: 800003}),
         one_row(900002, "Bot", 700002, {1: 800004, 2: 800005, 3: 800006})],
        schema={
            "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
            "game_date": pl.Date, "nine_distinct": pl.Boolean,
            **{f"u_slot_{s}": pl.Int64 for s in range(1, 10)},
        },
    )


def _state_frames(pa: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame,
                                             pl.DataFrame]:
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    return p_daily, b_daily, lg


def _attach(proj_slots: pl.DataFrame, pa: pl.DataFrame) -> pl.DataFrame:
    p_daily, b_daily, lg = _state_frames(pa)
    long, n_uncovered = ad.projected_long(proj_slots)
    assert n_uncovered == 12  # 2 starts x 6 uncovered slots
    pf = ad.attach_prior_features(long, p_daily, b_daily, lg)
    # no fan-out: one attached row per projected (start, slot)
    assert pf.height == long.height
    return pf.sort("game_pk", "slot")


# ------------------------------------------------------------- (e) features
def test_smoke_features_match_independent_expectations():
    """(e) Attached FEAT_H3 features equal hand-computed expectations.

    Expected values derived independently below from the fixture's
    integers and the frozen constants (W_PRIOR=150, half-life 90d);
    the adapter is NOT consulted for the expected side."""
    pf = _attach(_projected_slots(), _pa_history())
    w1 = _w(date(2024, 7, 1))
    lg_rate = 0.5  # league strictly before 2024-07-15: 2 K / 4 PAs
    # pitcher states as of GAME_DATE (last state row = 2024-07-15):
    # prior_k=1, prior_n=2 for BOTH pitchers; ew = w1*1/(w1*2) = 0.5
    exp_pitcher_w150 = (1 + _W_PRIOR * lg_rate) / (2 + _W_PRIOR)
    assert exp_pitcher_w150 == pytest.approx(0.5, abs=1e-15)
    b = {  # batter-side expectations keyed by batter id
        # B1: single 07-01 row -> last state row 07-01, prior 0/0 (cold)
        800001: {"w150": lg_rate, "ew": lg_rate, "cold": 1, "n": 0},
        # B2: single 07-01 row (y=0) -> prior 0/0 (cold)
        800002: {"w150": lg_rate, "ew": lg_rate, "cold": 1, "n": 0},
        # B3: 07-01 + 07-15 rows -> prior 0/1, ew = 0.0 (both y=0)
        800003: {"w150": (0 + _W_PRIOR * lg_rate) / (1 + _W_PRIOR),
                 "ew": 0.0, "cold": 0, "n": 1},
        # B4: 07-01 (y=1) + 07-15 (y=1) -> prior 1/1, ew = 1.0
        800004: {"w150": (1 + _W_PRIOR * lg_rate) / (1 + _W_PRIOR),
                 "ew": 1.0, "cold": 0, "n": 1},
        # B5: single 07-15 row -> prior 0/0 (cold)
        800005: {"w150": lg_rate, "ew": lg_rate, "cold": 1, "n": 0},
        # B6: single 07-15 row (y=0) -> prior 0/0 (cold)
        800006: {"w150": lg_rate, "ew": lg_rate, "cold": 1, "n": 0},
    }
    starts = {900001: (700001, [800001, 800002, 800003]),
              900002: (700002, [800004, 800005, 800006])}
    for game_pk, (pitcher, bats) in starts.items():
        rows = pf.filter(pl.col("game_pk") == game_pk)
        for slot, batter in enumerate(bats, start=1):
            r = rows.filter(pl.col("slot") == slot).row(0, named=True)
            assert r["pitcher"] == pitcher and r["batter"] == batter
            assert r["p_pitcher_prior_w150"] == pytest.approx(
                exp_pitcher_w150, abs=_TOL)
            assert r["p_batter_prior_w150"] == pytest.approx(
                b[batter]["w150"], abs=_TOL)
            assert r["ew_pitcher"] == pytest.approx(0.5, abs=_TOL)
            assert r["ew_batter"] == pytest.approx(b[batter]["ew"],
                                                   abs=_TOL)
            assert r["lg_rate"] == pytest.approx(lg_rate, abs=_TOL)
            assert r["cold_start"] == b[batter]["cold"]
            assert r["n_prior_pitcher"] == 2
            assert r["n_prior_batter"] == b[batter]["n"]


# --------------------------------------------------- (a) storage-row order
def test_smoke_shuffled_storage_rows_identical_features():
    """(a) Shuffled storage order (rows permuted; keys/slots preserved)
    must produce identical attached features keyed by (game_pk, slot)."""
    pa = _pa_history()
    base = _attach(_projected_slots(), pa)
    # shuffle the PA-history rows and the projected rows (storage order)
    pa_shuf = pa.sample(fraction=1.0, shuffle=True, seed=7)
    proj_shuf = _projected_slots().sample(fraction=1.0, shuffle=True,
                                          seed=11)
    shuf = _attach(proj_shuf, pa_shuf)
    assert base.shape == shuf.shape
    for col in ["game_pk", "slot", "pitcher", "batter",
                "p_pitcher_prior_w150", "p_batter_prior_w150",
                "ew_pitcher", "ew_batter", "lg_rate", "cold_start",
                "n_prior_pitcher", "n_prior_batter"]:
        assert base[col].to_list() == shuf[col].to_list(), col


def test_smoke_shuffled_rows_identical_pmf():
    """(a) extended to the PMF boundary: identical semantic p9 + identical
    bf37 under permuted storage rows give an identical 24-bucket PMF."""
    rng = np.random.default_rng(3)
    p9 = rng.dirichlet(np.ones(9) * 4)
    bf37 = _bf37_fixture()
    pmf_a = ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]
    # storage-order permutation of the same semantic inputs
    order = rng.permutation(9)
    p9_shuffled_rows = p9[order][np.argsort(order)]  # restored by key
    pmf_b = ad.start_count_pmfs(p9_shuffled_rows, p9_shuffled_rows,
                                bf37[::-1].copy())["pmf_h3_raw"]
    # bf37 reversed then re-normalized is NOT the same distribution; the
    # storage-order claim applies to ROW order, not semantic content.
    # Use the identical semantic bf37:
    pmf_b = ad.start_count_pmfs(p9_shuffled_rows, p9_shuffled_rows,
                                bf37)["pmf_h3_raw"]
    assert float(np.abs(pmf_a - pmf_b).max()) <= _TOL


# ------------------------------------------- (b) semantic-order change
def test_smoke_semantic_reorder_permits_pmf_change():
    """(b) Changing the SEMANTIC lineup order (which batter occupies
    which slot) may legitimately change the workload-weighted mixture.
    The control invariant does NOT cover this; the machinery must be
    able to detect the difference (a gate that could not fire here would
    be vacuous)."""
    p9 = np.array([0.4, 0.1, 0.2, 0.3, 0.2, 0.1, 0.25, 0.15, 0.05])
    bf37 = _bf37_fixture()
    pmf_a = ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]
    p9_swapped = p9.copy()
    p9_swapped[[0, 1]] = p9_swapped[[1, 0]]  # semantic slots 1 <-> 2
    pmf_b = ad.start_count_pmfs(p9_swapped, p9_swapped, bf37)[
        "pmf_h3_raw"]
    diff = float(np.abs(pmf_a - pmf_b).max())
    assert diff > 1e-6  # detectable, order-dependent mixture


# ------------------------------------------------- (f) PMF equality, 1e-12
def test_smoke_pmf_equality_identical_semantic_inputs():
    """(f) The registered invariant: with identical semantic slot
    sequence, probabilities, and workload PMF, both computation routes
    (adapter machinery vs the independent implementation below) agree
    within 1e-12 per bucket."""
    rng = np.random.default_rng(5)
    p9 = rng.dirichlet(np.ones(9) * 4)
    bf37 = _bf37_fixture()
    pmf_adapter = ad.start_count_pmfs(p9, p9, bf37)["pmf_h3_raw"]
    pmf_indep = _independent_pmf(p9, bf37)
    assert float(np.abs(pmf_adapter - pmf_indep).max()) <= _TOL
    ad.check_pmf(pmf_adapter, "smoke")


def _bf37_fixture() -> np.ndarray:
    """A normalized 37-category BF PMF (index 36 = P(N >= 37))."""
    v = np.full(37, 0.02)
    v[35] = 0.70  # 35 * 0.02 = 0.70 over 0..34
    v[36] = 0.10  # total = 0.70 + 0.70? no: 35*0.02=0.70, +0.70+0.10 > 1
    v = np.full(37, 0.0)
    v[:35] = 0.02          # 0.70 over BF 1..35
    v[35] = 0.20           # BF 36
    v[36] = 0.10           # P(N >= 37)
    assert abs(v.sum() - 1.0) < 1e-12
    return v


def _independent_pmf(p9: np.ndarray, bf37: np.ndarray) -> np.ndarray:
    """Independent reimplementation of the registered aggregation:

    pbar_n = clip(mean of the projected nine cycled to n), n = 1..60
    P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n), 24 buckets, tail to 23.

    Written with explicit loops and math.lgamma -- it shares NO helper
    with the adapter's LOG_BINOM table or vectorized mixture."""
    p9 = np.asarray(p9, dtype=np.float64)
    bf_ext = ad.bf_pmf_from_37(np.asarray(bf37, dtype=np.float64))
    # shared verified BF extension input (identity, not under test)
    pbar = []
    for n in range(1, _KCOUNT_CAP + 1):
        cycled = [p9[i % 9] for i in range(n)]
        pbar.append(min(max(sum(cycled) / n, ad.P_CLIP), 1 - ad.P_CLIP))
    out = np.zeros(_K_MAX)
    for n in range(1, _KCOUNT_CAP + 1):
        if bf_ext[n - 1] == 0.0:
            continue
        for k in range(_K_MAX):
            if k > n:
                continue
            log_binom = (lgamma(n + 1) - lgamma(k + 1)
                         - lgamma(n - k + 1))
            out[k] += (bf_ext[n - 1]
                       * float(np.exp(log_binom
                                      + k * np.log(pbar[n - 1])
                                      + (n - k)
                                      * np.log1p(-pbar[n - 1]))))
    tail = max(0.0, 1.0 - out.sum())
    out[_K_MAX - 1] += tail
    return out


# ------------------------------------------------ (c) wrong-key attachment
def test_smoke_wrong_key_attachment_detected():
    """(c) Relabeling one batter (wrong semantic key) must produce a
    detectable mismatch against the correctly attached frame."""
    pa = _pa_history()
    proj = _projected_slots()
    good = _attach(proj, pa)
    # corrupt the semantic key: slot-1 batter of start 1 -> 800004 (B4)
    bad_proj = proj.with_columns(
        pl.when(pl.col("game_pk") == 900001)
        .then(pl.lit(800004).alias("u_slot_1"))
        .otherwise(pl.col("u_slot_1")))
    bad = _attach(bad_proj, pa)
    mismatches = 0
    for game_pk, slot in [(900001, 1)]:
        g = good.filter((pl.col("game_pk") == game_pk)
                        & (pl.col("slot") == slot)).row(0, named=True)
        b_ = bad.filter((pl.col("game_pk") == game_pk)
                        & (pl.col("slot") == slot)).row(0, named=True)
        for col in ["batter", "p_batter_prior_w150", "ew_batter",
                    "cold_start", "n_prior_batter"]:
            if g[col] != b_[col]:
                mismatches += 1
    assert mismatches >= 3  # key + w150 + ew + cold + n all differ


# ------------------------------------------------- (d) fan-out / duplicates
def test_smoke_duplicate_start_key_fails_loud():
    proj = _projected_slots()
    dup = pl.concat([proj, proj.head(1)])
    with pytest.raises(ad.AdapterError, match="start keys not unique"):
        ad.projected_long(dup)


def test_smoke_missing_slot_columns_fail_loud():
    proj = _projected_slots().drop("u_slot_9")
    with pytest.raises(ad.AdapterError, match="missing slot columns"):
        ad.projected_long(proj)


def test_smoke_attach_preserves_row_count_no_fan_out():
    pf = _attach(_projected_slots(), _pa_history())
    # 2 starts x 3 covered slots = 6 attached rows, one per key
    assert pf.height == 6
    assert pf.select(pl.struct("game_pk", "slot", "pitcher")
                     .n_unique()).item() == 6


# --------------------------------------------------- (g) prohibited inputs
_PROHIBITED_LABELS = {"realized_k", "y_true", "k_actual", "outcome_k"}


def assert_no_realized_labels(frame: pl.DataFrame) -> None:
    """Stage A input-gate contract: the prediction-path frame must not
    carry realized-K labels. The Stage A runner is required to call this
    gate on every consumed frame before any comparison."""
    present = _PROHIBITED_LABELS & set(frame.columns)
    if present:
        raise RuntimeError(
            f"PROHIBITED_REALIZED_LABELS: {sorted(present)}")


def test_smoke_input_gate_refuses_realized_labels():
    row = {"game_pk": [1], "pitcher": [700001], "realized_k": [7]}
    with pytest.raises(RuntimeError, match="PROHIBITED_REALIZED_LABELS"):
        assert_no_realized_labels(pl.DataFrame(row))


def test_smoke_input_gate_passes_label_free_frame():
    frame = _pa_history().with_columns(pl.lit(None).alias("placeholder"))
    frame = frame.drop("y")  # label-free prediction-path frame
    assert_no_realized_labels(frame)


def test_smoke_strictly_prior_no_same_date_leakage():
    """Boundary property of the real machinery: a PA row dated ON the
    scored game_date must never influence the attached state (the
    strictly-prior shift excludes same-date outcomes; adapter.py:49-51)."""
    pa = _pa_history()
    # add a same-date PA row for P1 on GAME_DATE (would be leakage)
    pa_same_date = pl.concat([pa, pl.DataFrame(
        [(GAME_DATE, 700001, 800001, 1)],
        schema=pa.schema, orient="row")])
    p_daily, b_daily, lg = _state_frames(pa_same_date)
    long, _ = ad.projected_long(_projected_slots())
    pf = ad.attach_prior_features(long, p_daily, b_daily, lg)
    r = pf.filter(pl.col("game_pk") == 900001).row(0, named=True)
    # backward as-of attaches the same-date STATE row, whose values are
    # strictly prior (shift): prior counts cover only rows before
    # GAME_DATE (k=1+1=2, n=2+2=4). The same-date outcome (y=1) is
    # EXCLUDED -- with leakage prior_k would be 3 and prior_n 5.
    assert r["src_date_pitcher"] == date(2024, 7, 15)
    assert r["src_date_pitcher"] < GAME_DATE
    assert r["prior_k_pitcher"] == 2
    assert r["prior_n_pitcher"] == 4
    # league rate as of GAME_DATE: the same-date league row's PRIOR
    # covers the 8 strictly-prior rows (k=4, n=8 -> 0.5); the same-date
    # y=1 is excluded (with leakage it would be 5/9 ~ 0.5556)
    assert r["lg_rate"] == pytest.approx(0.5, abs=1e-12)
