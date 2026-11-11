"""Synthetic tests for the research-side harness-to-market shadow
bridge (harness_to_market_bridge.py). SYNTHETIC ONLY: no private
checkpoint read, no real-artifact access, no live-path edit, no market
scoring. The integration case reuses the existing prediction fixture
pattern (synthetic 8-feature control model + synthetic PA/lineup/BF
frames) through the shared harness, then bridges its keyed 24-bucket
PMFs to the production line-probability columns.

Requirement -> implementation -> test-evidence closure table:
  Hand-calculated marginalization (mass 0.1@K2, 0.2@K3, 0.3@K10,
  tail 0.4@K23; p_over_2_5 = 0.9; p_over_3_5..9_5 = 0.7)  -> test 1
  Exact eight production column names; complete start
  identities; deterministic ordering under shuffled input -> test 2
  Tail contribution retained at every in-scope line       -> test 3
  Lines agree with the canonical PROJECTION_K_LINES       -> test 4
  Refusals: duplicate bucket, missing bucket, null key,
  invalid mass (negative/NaN), bad normalization          -> test 5
  Strict bucket labels BEFORE int conversion (fractional,
  nonfinite, null refuse; integral float accepted)        -> test 6
  Null PMF mass refuses with a clear validation error     -> test 7
  Synthetic harness -> bridge integration (existing
  prediction fixture; contract + direct-marginalization
  agreement)                                              -> test 8
"""
from __future__ import annotations

import sys
from datetime import date
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
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
from pregame_pa_ext import label_free_prediction as lp  # noqa: E402
from pregame_pa_ext import harness_to_market_bridge as hb  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402

P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
STARTS = [(900201, "Top", P1), (900201, "Bot", P2)]
HIST1, REQ = date(2025, 4, 10), date(2025, 5, 1)


def _hand_pmf() -> np.ndarray:
    """Mass 0.1@K=2, 0.2@K=3, 0.3@K=10, 0.4@overflow tail (K=23)."""
    pmf = np.zeros(ad.K_MAX)
    pmf[2] = 0.1
    pmf[3] = 0.2
    pmf[10] = 0.3
    pmf[ad.K_MAX - 1] = 0.4  # overflow bucket: K >= 23
    return pmf


def _k_pmf_frame(starts=STARTS, pmf=None, shuffle=True) -> pl.DataFrame:
    pmf = _hand_pmf() if pmf is None else pmf
    rows = []
    for gk, side, p in starts:
        for b in range(ad.K_MAX):
            rows.append((gk, side, p, b, float(pmf[b])))
    if shuffle:
        # deterministic row permutation; grouping must not care
        perm = np.random.default_rng(20261001).permutation(len(rows))
        rows = [rows[i] for i in perm]
    frame = pl.DataFrame(
        rows, schema={"game_pk": pl.Int64, "side": pl.Utf8,
                      "pitcher": pl.Int64, "bucket": pl.Int64,
                      "pmf_h3_raw": pl.Float64}, orient="row")
    return frame


# ------------------- 1. hand-calculated marginalization
def test_hand_calculated_lines():
    out = hb.bridge_pmf_to_lines(_k_pmf_frame())
    assert out.height == 2
    for r in out.iter_rows(named=True):
        assert r["p_over_2_5"] == pytest.approx(0.9)
        for line in (3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5):
            name = f"p_over_{str(line).replace('.', '_')}"
            assert r[name] == pytest.approx(0.7)


# ------------------- 2. exact names, identities, deterministic order
def test_exact_columns_and_identities():
    out = hb.bridge_pmf_to_lines(_k_pmf_frame())
    expected_cols = [f"p_over_{str(l).replace('.', '_')}"
                     for l in PROJECTION_K_LINES]
    assert [c for c in out.columns if c.startswith("p_over_")] == \
        expected_cols
    got = out.select(["game_pk", "side", "pitcher"]).rows()
    assert got == sorted(STARTS)
    assert out.schema["game_pk"] == pl.Int64
    assert out.schema["side"] == pl.Utf8
    assert out.schema["pitcher"] == pl.Int64
    # deterministic across shuffles: same rows, same order
    again = hb.bridge_pmf_to_lines(_k_pmf_frame())
    assert out.equals(again)


# ------------------- 3. tail contribution retained
def test_tail_retained():
    out = hb.bridge_pmf_to_lines(_k_pmf_frame())
    pmf = _hand_pmf()
    for line in PROJECTION_K_LINES:
        name = f"p_over_{str(line).replace('.', '_')}"
        expected = float(pmf[np.arange(ad.K_MAX) > line].sum())
        for r in out.iter_rows(named=True):
            assert r[name] == pytest.approx(expected)
        # tail mass (0.4 at K>=23) must survive every in-scope line
        assert expected == pytest.approx(0.4 + (0.3 if line < 10.5
                                                else 0.0)
                                         + (0.2 if line < 3.5 else 0.0)
                                         + (0.1 if line < 2.5 else 0.0))


# ------------------- 4. lines agree with the canonical constant
def test_lines_agree_with_canonical_constant():
    assert tuple(hb.PROJECTION_K_LINES) == tuple(PROJECTION_K_LINES)
    assert hb._line_column(2.5) == "p_over_2_5"
    assert hb._line_column(9.5) == "p_over_9_5"
    # the registered marginalization is the same function the market
    # path uses; agreement on a known vector pins the reuse
    pmf = _hand_pmf()
    assert hb.bridge_pmf_to_lines(_k_pmf_frame(shuffle=False))[
        "p_over_2_5"].to_list() == pytest.approx(
        [mk.model_p_over(pmf, 2.5)] * 2)


# ------------------- 5. focused refusals
def test_refusals():
    frame = _k_pmf_frame()
    with pytest.raises(ValueError, match="duplicate"):
        hb.bridge_pmf_to_lines(pl.concat([frame, frame.head(1)]))
    with pytest.raises(ValueError, match="bucket set"):
        hb.bridge_pmf_to_lines(
            _k_pmf_frame().filter(pl.col("bucket") != 5))
    with pytest.raises(ValueError, match="null identity"):
        bad = _k_pmf_frame()
        bad = bad.with_columns(
            pl.when(pl.col("bucket") == 0).then(None)
            .otherwise(pl.col("side")).alias("side"))
        hb.bridge_pmf_to_lines(bad)
    # the three PMF-gate refusals surface the registered adapter gate
    # (AdapterError extends RuntimeError, by design "fails loud")
    with pytest.raises(ad.AdapterError, match="non-finite PMF"):
        bad = _k_pmf_frame()
        bad = bad.with_columns(
            pl.when(pl.col("bucket") == 7).then(float("nan"))
            .otherwise(pl.col("pmf_h3_raw")).alias("pmf_h3_raw"))
        hb.bridge_pmf_to_lines(bad)
    with pytest.raises(ad.AdapterError, match="PMF out of"):
        bad = _k_pmf_frame()
        bad = bad.with_columns(
            pl.when(pl.col("bucket") == 0).then(-0.1)
            .otherwise(pl.col("pmf_h3_raw")).alias("pmf_h3_raw"))
        hb.bridge_pmf_to_lines(bad)
    with pytest.raises(ad.AdapterError, match="sum != 1"):
        bad = _k_pmf_frame()
        bad = bad.with_columns(
            pl.when(pl.col("bucket") == 0)
            .then(pl.col("pmf_h3_raw") + 0.05)
            .otherwise(pl.col("pmf_h3_raw")).alias("pmf_h3_raw"))
        hb.bridge_pmf_to_lines(bad)
    with pytest.raises(ValueError, match="missing required column"):
        hb.bridge_pmf_to_lines(
            _k_pmf_frame().drop("pmf_h3_raw"))


# ------------------- 8. synthetic harness -> bridge integration
def _synthetic_pa():
    rows = []
    for gi, (gk, side, p) in enumerate(STARTS):
        batters = B1 if side == "Top" else B2
        for dt, gkx in ((HIST1, 41), (REQ, gk)):
            for i, b in enumerate(batters):
                y = (i + gi) % 2
                rows.append((dt, gkx, 100 + i, p, b, y))
    return pl.DataFrame(rows, schema={
        "game_date": pl.Date, "game_pk": pl.Int64,
        "at_bat_number": pl.Int64, "pitcher": pl.Int64,
        "batter": pl.Int64, "y": pl.Int64}, orient="row")


def _synthetic_lineups():
    rows = [(gk, side, p, REQ, True,
             *(B1 if side == "Top" else B2))
            for gk, side, p in STARTS]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{s}": pl.Int64 for s in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _synthetic_control_model():
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


# ------------------- 6. strict bucket labels BEFORE int conversion
def test_strict_bucket_label_refusals():
    # fractional float bucket label refuses (never silently truncated)
    bad = _k_pmf_frame().with_columns(pl.col("bucket").cast(pl.Float64))
    bad = bad.with_columns(
        pl.when(pl.col("bucket") == 3).then(2.5)
        .otherwise(pl.col("bucket")).alias("bucket"))
    with pytest.raises(ValueError, match="fractional bucket label"):
        hb.bridge_pmf_to_lines(bad)
    # nonfinite float bucket label refuses
    bad = _k_pmf_frame().with_columns(pl.col("bucket").cast(pl.Float64))
    bad = bad.with_columns(
        pl.when(pl.col("bucket") == 3).then(float("nan"))
        .otherwise(pl.col("bucket")).alias("bucket"))
    with pytest.raises(ValueError, match="nonfinite bucket label"):
        hb.bridge_pmf_to_lines(bad)
    # null bucket label refuses
    bad = _k_pmf_frame().with_columns(
        pl.when(pl.col("bucket") == 3).then(None)
        .otherwise(pl.col("bucket")).alias("bucket"))
    with pytest.raises(ValueError, match="null bucket label"):
        hb.bridge_pmf_to_lines(bad)
    # non-numeric bucket dtype refuses (string AND boolean: a boolean
    # label must not become an integer bucket through coercion)
    bad = _k_pmf_frame().with_columns(pl.col("bucket").cast(pl.Utf8))
    with pytest.raises(ValueError, match="neither integer nor float"):
        hb.bridge_pmf_to_lines(bad)
    bad = _k_pmf_frame().with_columns(pl.col("bucket").cast(pl.Boolean))
    with pytest.raises(ValueError, match="neither integer nor float"):
        hb.bridge_pmf_to_lines(bad)


def test_integral_float_buckets_accepted():
    """Valid integer-valued producer output in float dtype passes and
    yields output identical to the integer-typed input."""
    as_int = _k_pmf_frame(shuffle=False)
    as_float = as_int.with_columns(pl.col("bucket").cast(pl.Float64))
    out_int = hb.bridge_pmf_to_lines(as_int)
    out_float = hb.bridge_pmf_to_lines(as_float)
    assert out_float.equals(out_int)


# ------------------- 7. null PMF mass refuses clearly
def test_null_pmf_mass_refused():
    bad = _k_pmf_frame().with_columns(
        pl.when(pl.col("bucket") == 3).then(None)
        .otherwise(pl.col("pmf_h3_raw")).alias("pmf_h3_raw"))
    with pytest.raises(ValueError, match="null PMF mass"):
        hb.bridge_pmf_to_lines(bad)


def test_synthetic_harness_to_bridge_integration():
    pa = _synthetic_pa()
    lineups = _synthetic_lineups()
    model = _synthetic_control_model()
    result = lp.run_prediction(model, pa, lineups,
                               _synthetic_bf_keyed_wide())
    k_pmf = result["k_pmf_per_start"]
    assert k_pmf.height == 2 * ad.K_MAX
    out = hb.bridge_pmf_to_lines(k_pmf)
    assert out.height == 2
    # output probabilities agree with direct marginalization of the
    # same harness PMFs through the registered function
    for r in out.iter_rows(named=True):
        rows = k_pmf.filter(
            (pl.col("game_pk") == r["game_pk"])
            & (pl.col("side") == r["side"])
            & (pl.col("pitcher") == r["pitcher"])).sort("bucket")
        pmf = rows["pmf_h3_raw"].to_numpy()
        for line in PROJECTION_K_LINES:
            name = f"p_over_{str(line).replace('.', '_')}"
            assert r[name] == pytest.approx(
                float(mk.model_p_over(pmf, float(line))))
            assert 0.0 <= r[name] <= 1.0


def _synthetic_bf_keyed_wide():
    v = np.zeros(37)
    v[:35] = 0.02
    v[35] = 0.20
    v[36] = 0.10
    rows = []
    for gk, side, p in STARTS:
        rows.append((gk, side, p, *[float(v[j]) for j in range(37)]))
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64}
    schema.update({f"pmf37_{j}": pl.Float64 for j in range(37)})
    return pl.DataFrame(rows, schema=schema, orient="row")
