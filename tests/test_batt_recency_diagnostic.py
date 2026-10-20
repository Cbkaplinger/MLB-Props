"""Synthetic tests for the batter-history challenger diagnostic
(pregame-pa-ext-v2, card proposal_batt_recency_diagnostic_2026-10-20.md
v3). SYNTHETIC ONLY: no real-data fitting, no preserved-run modification,
no frozen-artifact writes. Covers the eleven review-mandated properties:

1  cross-season continuity        7  strictly-prior dates
2  empty/short history            8  identical train/inference construction
3  long inactivity                9  unique pitcher-matched observed-PA joins
4  recent/anchor boundary        10  unchanged exclusion policy
5  no double counting            11  unchanged baseline artifacts
6  forecast-relative decay       +  canonical key-hash determinism
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402

T = date(2025, 6, 1)  # canonical forecast date for most tests


def pa_rows(rows: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(rows).with_columns(pl.col("game_date").cast(pl.Date))
    if "y" in df.columns:
        df = df.with_columns(pl.col("y").cast(pl.Int8))
    return df


def one(batter: int, d: date, y: int, pitcher: int = 1,
        game_pk: int = 1, ab: int = 0) -> dict:
    return {"game_pk": game_pk, "at_bat_number": ab, "batter": batter,
            "pitcher": pitcher, "game_date": d, "y": y}


def daily_and_lg(pa: pl.DataFrame):
    return br.batt_daily_cums(pa), ad.league_daily_state(pa)


def features_for(pa: pl.DataFrame, rows: list[dict]) -> pl.DataFrame:
    """Challenger features for arbitrary (batter, game_date) rows via the
    SAME builder used for training rows."""
    daily, lg = daily_and_lg(pa)
    r = pa_rows(rows)
    return br.attach_batt_recency(r, daily, lg)


# ------------------------------------------------------ 1 cross-season continuity
def test_cross_season_continuity_no_reset():
    """A batter's 2022 and 2023 PAs both enter the prior state at a 2024
    forecast; no Opening-Day reset (career-cumulative machinery). Under the
    FROZEN asof convention the prior state is the PAs strictly before the
    last game date <= t (the 2023-04-04 row itself is excluded, exactly as
    adapter prior_n behaves)."""
    pa = pa_rows([
        one(7, date(2022, 5, 10), 1), one(7, date(2022, 5, 11), 1),
        one(7, date(2023, 4, 3), 0), one(7, date(2023, 4, 4), 0),
        # another batter shapes a league rate distinct from batter 7's
        one(8, date(2022, 6, 1), 0), one(8, date(2022, 6, 2), 0),
        one(8, date(2023, 5, 1), 0), one(8, date(2023, 5, 2), 0),
    ])
    f = features_for(pa, [{"batter": 7, "game_date": date(2024, 6, 1)}])
    row = f.row(0, named=True)
    # frozen convention: rows < L where L = 2023-04-04 -> 3 prior PAs
    assert row["n_batt_win"] + row["n_batt_anchor_raw"] == 3
    assert row["n_batt_anchor_raw"] == 3  # all pre-window (older than 60d)
    assert row["k_batt_win"] == 0 and row["n_batt_win"] == 0
    # anchor rate = career 2/3 shrunk toward the league rate (0.25); NOT
    # equal to either
    assert 0.25 < row["p_batt_anchor"] < 2.0 / 3.0


# ------------------------------------------------------ 2 empty/short history
def test_empty_history_defaults_to_league_internal_only():
    """A zero-history batter: anchor = league rate (INTERNAL FEATURE
    DEFAULT), zero mass, and the module never touches exclusion columns
    (no scoring permission is created)."""
    # league history from another batter so lg_rate is finite at T
    pa = pa_rows([one(9, date(2024, 3, 1), 0), one(9, date(2024, 4, 1), 1),
                  one(9, date(2024, 5, 1), 0)])
    f = features_for(pa, [{"batter": 42, "game_date": T}])
    row = f.row(0, named=True)
    assert row["mass_anchor"] == 0.0 and row["n_batt_win"] == 0
    assert row["p_batt_anchor"] == pytest.approx(row["lg_rate"])
    assert row["p_batt_recent"] == pytest.approx(row["lg_rate"])
    assert "exclusion_reason" not in f.columns
    assert "cold_start" not in f.columns  # challenger adds no policy columns


def test_short_history_recent_anchored_not_raw():
    """A batter with recent PAs: the challenger estimate is the ANCHORED
    blend, not the raw recent ratio (unlike the frozen EW feature). Under
    the FROZEN asof convention the last game date's own PAs (t-9d here)
    are excluded from the prior state exactly as the frozen recipe does -
    the challenger inherits that convention (identical construction), and
    the diagnostic's observed-PA evaluation rows always fall on game dates
    where the batter played (L = t), where the convention is exact."""
    pa = pa_rows([one(5, date(2024, 3, 1), 0), one(5, date(2024, 3, 2), 0),
                  one(5, T - timedelta(days=10), 1),
                  one(5, T - timedelta(days=9), 1)])
    f = features_for(pa, [{"batter": 5, "game_date": T}])
    row = f.row(0, named=True)
    assert row["n_batt_win"] == 1 and row["k_batt_win"] == 1
    assert row["n_batt_anchor_raw"] == 2
    # raw recent ratio = 1.0; anchored blend must sit strictly between the
    # anchor rate and the raw ratio
    assert row["p_batt_recent"] < 1.0
    assert row["p_batt_recent"] > row["p_batt_anchor"]


# ------------------------------------------------------ 3 long inactivity
def test_long_inactivity_decays_toward_league():
    """A batter whose only history is one old season block inside the
    ANCHOR region for both forecasts, with a player rate distinct from the
    league rate: the anchor's decayed PA mass shrinks with absolute
    staleness and the anchor rate moves toward the league rate (the frozen
    EW feature cannot do this)."""
    pa = pa_rows([
        one(3, date(2022, 5, 2), 1), one(3, date(2022, 5, 3), 1),
        one(3, date(2022, 5, 4), 0),
        # league-shaping rows from another batter (low K rate)
        one(4, date(2022, 5, 2), 0), one(4, date(2022, 5, 3), 0),
        one(4, date(2022, 5, 4), 0), one(4, date(2022, 5, 5), 0),
    ])
    # near forecast: the 2022-05 rows are already past the recent-window
    # boundary (t-60d = 2022-06-02) -> the whole shifted prior set is the
    # anchor with full-ish decayed mass; far forecast: same rows, ~3 years
    # stale -> mass ~ 2^(-3y/90d), anchor ~ league rate.
    near = features_for(pa, [{"batter": 3, "game_date": date(2022, 8, 1)}])
    far = features_for(pa, [{"batter": 3, "game_date": date(2025, 6, 1)}])
    assert near.row(0, named=True)["mass_anchor"] > 0
    assert near.row(0, named=True)["mass_anchor"] > \
        far.row(0, named=True)["mass_anchor"]
    lg_near = near.row(0, named=True)["lg_rate"]
    assert abs(far.row(0, named=True)["p_batt_anchor"] - lg_near) < \
        abs(near.row(0, named=True)["p_batt_anchor"] - lg_near)


# ------------------------------------------------------ 4 recent/anchor boundary
def test_boundary_date_belongs_to_anchor():
    """A PA exactly on t-60d enters the ANCHOR pool (d_i <= t-60d); a PA on
    t-59d enters RECENT; a same-day PA enters NEITHER (strictly prior)."""
    b = 11
    d_anchor = T - timedelta(days=60)
    pa = pa_rows([one(b, d_anchor, 1), one(b, T - timedelta(days=59), 0),
                  one(b, T, 1)])
    f = features_for(pa, [{"batter": b, "game_date": T}])
    row = f.row(0, named=True)
    assert row["n_batt_win"] == 1 and row["k_batt_win"] == 0
    assert row["n_batt_anchor_raw"] == 1  # the t-60d PA
    # same-day PA counted nowhere
    assert row["n_batt_win"] + row["n_batt_anchor_raw"] == 2


# ------------------------------------------------------ 5 no double counting
def test_no_double_counting_disjoint_components():
    """Every prior PA enters exactly one component: n_win + n_anchor_raw
    equals the adapter's career-cumulative prior_n for many random
    forecast dates; the anchor EW mass is built ONLY from pre-window rows."""
    rng = np.random.default_rng(20261020)
    rows = []
    d = date(2022, 4, 15)
    for i in range(120):
        d = d + timedelta(days=int(rng.integers(1, 9)))
        rows.append(one(21, d, int(rng.random() < 0.35)))
    pa = pa_rows(rows)
    daily, lg = daily_and_lg(pa)
    forecasts = [{"batter": 21, "game_date": date(2023, 1, 1) + timedelta(days=int(g))}
                 for g in (10, 61, 200, 455, 700)]
    f = br.attach_batt_recency(pa_rows(forecasts), daily, lg)
    # independent prior_n reference from the ADAPTER's own machinery:
    # asof(t) on the SHIFTED daily table (identical convention)
    b_daily = ad.entity_daily_state(pa, "batter")
    ref = (pa_rows(forecasts).sort("game_date").join_asof(
        b_daily, left_on="game_date", right_on="game_date", by="batter",
        strategy="backward")
        .with_columns(pl.col("prior_n").fill_null(0)))
    n_prior = ref["prior_n"].to_list()
    assert (f["n_batt_win"] + f["n_batt_anchor_raw"]).to_list() == n_prior
    # disjointness by construction: window rows are strictly after the
    # anchor boundary, anchor rows strictly at/before it
    assert (f["n_batt_win"] >= 0).all() and (f["n_batt_anchor_raw"] >= 0).all()


# ------------------------------------------------------ 6 forecast-relative decay
def test_forecast_relative_decay_halves_per_90d():
    """Same frozen history, two forecast dates 90 days apart: the anchor's
    decayed PA mass exactly halves (w_i(t) = 2^(-(t-d_i)/90))."""
    pa = pa_rows([one(2, date(2024, 8, 1), 0), one(2, date(2024, 8, 2), 1)])
    t1 = date(2025, 6, 1)
    f1 = features_for(pa, [{"batter": 2, "game_date": t1}])
    f2 = features_for(pa, [{"batter": 2, "game_date": t1 + timedelta(days=90)}])
    m1 = f1.row(0, named=True)["mass_anchor"]
    m2 = f2.row(0, named=True)["mass_anchor"]
    assert m1 > 0
    assert m2 == pytest.approx(m1 / 2.0, rel=1e-9)


# ------------------------------------------------------ 7 strictly-prior dates
def test_same_day_pa_never_enters_and_gate_columns_strictly_prior():
    """A PA on the forecast date itself enters no component and no source
    date reaches the forecast date (hard cutoff semantics preserved)."""
    b = 31
    pa = pa_rows([one(b, T - timedelta(days=5), 0), one(b, T, 1)])
    f = features_for(pa, [{"batter": b, "game_date": T}])
    row = f.row(0, named=True)
    assert row["n_batt_win"] + row["n_batt_anchor_raw"] == 1
    for c in ("src_date_batt_recent", "src_date_batt_anchor"):
        assert f[c][0] is not None and f[c][0] < T


# ------------------------------------------------------ 8 train/inference identity
def test_identical_construction_training_and_inference():
    """The same builder produces bit-identical challenger features for
    identical (entity, date, history) whether the row is a 'training' row
    or an 'evaluation' row."""
    pa = pa_rows([one(8, date(2024, 3, 1), 0), one(8, date(2024, 3, 2), 1),
                  one(8, T - timedelta(days=20), 1)])
    daily, lg = daily_and_lg(pa)
    a = br.attach_batt_recency(
        pa_rows([{"batter": 8, "game_date": T}]), daily, lg)
    b = br.attach_batt_recency(
        pa_rows([{"batter": 8, "game_date": T, "y": 1, "game_pk": 5,
                  "pitcher": 2}]), daily, lg)
    for c in ("p_batt_recent", "p_batt_anchor", "n_batt_win", "k_batt_win",
              "mass_anchor", "wk_anchor"):
        assert a[c][0] == b[c][0]


# ------------------------------------------------------ 9 unique observed-PA join
def _synth_projected_and_pa():
    """Two projected starts (one game, both sides) where batter 646240 is
    projected on BOTH sides (the 777417 cross-side trade pattern), plus a
    plain start. Observed PAs: 3 vs the Bot-side forecast pitcher, 1 vs a
    reliever, 2 vs the Top-side forecast pitcher for another batter."""
    proj = pl.DataFrame([
        {"game_pk": 900, "side": "Bot", "pitcher": 500, "game_date": T,
         "slot": 3, "batter": 646240},
        {"game_pk": 900, "side": "Top", "pitcher": 700, "game_date": T,
         "slot": 2, "batter": 646240},
        {"game_pk": 901, "side": "Bot", "pitcher": 700, "game_date": T,
         "slot": 1, "batter": 777},
    ])
    pa = pa_rows([
        # batter 646240 vs Bot forecast pitcher 500: two observed PAs
        one(646240, T, 0, pitcher=500, game_pk=900, ab=11),
        one(646240, T, 1, pitcher=500, game_pk=900, ab=21),
        # same batter vs a reliever: NOT the projected matchup
        one(646240, T, 1, pitcher=999, game_pk=900, ab=58),
        # a different batter vs Top forecast pitcher 700
        one(777, T, 1, pitcher=700, game_pk=901, ab=7),
    ])
    return proj, pa


def test_observed_pa_join_unique_grain_and_pitcher_match():
    proj, pa = _synth_projected_and_pa()
    j = br.observed_pa_join(proj, pa)
    assert j.height == 3  # 2 (Bot slot) + 1 (game 901); reliever PA excluded
    assert j.group_by("game_pk", "at_bat_number").agg(n=pl.len())["n"].max() == 1
    # the Top-side projection of 646240 has NO observed PA vs pitcher 700
    assert j.filter((pl.col("game_pk") == 900) & (pl.col("side") == "Top")
                    ).height == 0
    with pytest.raises(ValueError, match="at_bat_number"):
        # force an ambiguous join: same observed PA matching two projected
        # slots of the same start (defective projection) -> fail loud
        proj_bad = pl.concat([proj, proj.filter(
            (pl.col("game_pk") == 900) & (pl.col("side") == "Bot")).with_columns(
            pl.lit(4, dtype=pl.Int64).alias("slot"))])
        br.observed_pa_join(proj_bad, pa)


# ------------------------------------------------------ 10 exclusion policy
def test_eligibility_never_readmits_excluded_rows():
    """The ledger filter keeps scored rows only; excluded (cold) rows are
    never re-admitted and the module writes no policy columns."""
    ledger = pl.DataFrame([
        {"game_pk": 1, "side": "Bot", "pitcher": 10, "batter": 100,
         "slot": 1, "game_date": date(2024, 8, 1), "block": "block_2024H2",
         "exclusion_reason": None},
        {"game_pk": 1, "side": "Bot", "pitcher": 10, "batter": 101,
         "slot": 2, "game_date": date(2024, 8, 1), "block": "block_2024H2",
         "exclusion_reason": ad.EXCLUSION_REASON_COLD},
        {"game_pk": 2, "side": "Top", "pitcher": 11, "batter": 102,
         "slot": 1, "game_date": date(2025, 8, 1), "block": "confirm_2025H2",
         "exclusion_reason": None},
    ])
    e = br.eligible_slots_from_ledger(ledger, br.DEV_BLOCKS)
    assert e.height == 1 and e["batter"][0] == 100
    assert "exclusion_reason" not in e.columns


# ------------------------------------------------------ 11 baseline artifacts
def test_baseline_artifacts_untouched_by_diagnostic_calls(tmp_path,
                                                          monkeypatch):
    """Pure diagnostic functions + key verification perform NO writes to
    the frozen artifact paths (checkpoint, freeze config, preserved
    output); synthetic stand-ins stay byte-identical."""
    ck = tmp_path / "h3_raw_checkpoint.json"
    ck.write_text(json.dumps({"format": "x", "sha256": "a" * 64,
                              "payload": {}}), encoding="utf-8")
    led = tmp_path / "projected_pa_probs_v1.parquet"
    out = pl.DataFrame([
        {"game_pk": 1, "side": "Bot", "pitcher": 10, "batter": 100,
         "slot": 1, "game_date": date(2024, 8, 1),
         "exclusion_reason": None}])
    out.write_parquet(led)
    pat = tmp_path / "pa_table.parquet"
    pa_rows([one(100, date(2024, 8, 1), 0, pitcher=10, game_pk=1)]
            ).write_parquet(pat)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (ck, led, pat)}
    monkeypatch.setattr(br.ad, "PAEXT_OUT_DIR", tmp_path)
    ledger = pl.read_parquet(led)
    pa = pl.read_parquet(pat)
    e = br.eligible_slots_from_ledger(
        ledger.with_columns(pl.lit("block_2024H2").alias("block")),
        br.DEV_BLOCKS)
    assert e.height == 1
    f = features_for(pa, [{"batter": 100, "game_date": date(2024, 8, 1)}])
    assert f.height == 1
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (ck, led, pat)}
    assert before == after
    assert not (tmp_path / "diagnostics").exists()


# ------------------------------------------------- canonical hash determinism
def test_canonical_hash_determinism_sensitivity_and_order():
    k1 = [(900, "Bot", 1), (900, "Bot", 2), (901, "Top", 3)]
    b1 = br.serialize_slot_keys(k1)
    assert br.sha256_stream(b1) == br.sha256_stream(br.serialize_slot_keys(
        [(901, "Top", 3), (900, "Bot", 1), (900, "Bot", 2)]))  # order-free
    # NUMERIC ordering: 901 < 1000 numerically though "1000" < "901" as text
    k3 = [(900, "Bot", 1), (1000, "Bot", 2), (901, "Top", 3)]
    b3 = br.serialize_slot_keys(k3)
    assert b3.index(b"900|") < b3.index(b"901|") < b3.index(b"1000|")
    k2 = k1[:-1] + [(901, "Top", 4)]
    assert br.serialize_slot_keys(k1) != br.serialize_slot_keys(k2)
    e1 = br.serialize_eval_keys([(900, 5), (900, 6)])
    e2 = br.serialize_eval_keys([(900, 5), (900, 7)])
    assert e1 != e2
    # numeric ordering for evaluation keys too (variable-width ids)
    e3 = br.serialize_eval_keys([(900, 5), (1000, 2), (901, 40)])
    assert e3.index(b"900|") < e3.index(b"901|") < e3.index(b"1000|")
    with pytest.raises(ValueError, match="duplicate key"):
        br.serialize_slot_keys(k1 + [k1[0]])
    # declared constants are 64-hex and distinct
    for c in (br.PUBLISHED_DEV_SLOT_KEYS_SHA256,
              br.PUBLISHED_DEV_EVAL_KEYS_SHA256):
        assert len(c) == 64 and all(ch in "0123456789abcdef" for ch in c)


def test_published_dev_key_constants_shape():
    """The published counts/hashes are the reviewed values (82592f18... /
    c6568151...); recomputation against REAL artifacts happens only via
    --verify-keys-only (real-data read), never in synthetic tests."""
    assert br.PUBLISHED_DEV_SLOT_KEYS_N == 43407
    assert br.PUBLISHED_DEV_EVAL_KEYS_N == 82817
    assert br.PUBLISHED_DEV_SLOT_KEYS_SHA256.startswith("82592f18")
    assert br.PUBLISHED_DEV_EVAL_KEYS_SHA256.startswith("c6568151")
