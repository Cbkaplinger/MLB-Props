"""File-based integration test for the K-count scored runner.

Synthetic frames flow through the full run_diagnostic (saved-artifact
alignment, spine join, combination, arms, gate, sensitivity, manifest,
predictions.csv, pmfs.parquet) into a tmp directory. No real data, no
network, no BF refit.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import bf_distribution as bfd  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import run_pa_k_baseline_2023 as rpt  # noqa: E402


def synth_unified(rows, team_home="A", team_away="B"):
    return pl.DataFrame({
        "game_pk": [r[0] for r in rows],
        "pitcher": [r[1] for r in rows],
        "game_date": [r[2] for r in rows],
        "inning": [1] * len(rows),
        "inning_topbot": [r[5] for r in rows],
        "at_bat_number": [r[3] for r in rows],
        "pitch_number": [1] * len(rows),
        "home_team": [team_home] * len(rows),
        "away_team": [team_away] * len(rows),
        "p_throws": ["R"] * len(rows),
        "events": [r[4] for r in rows],
    })


def synth_raw(rows):
    return pl.DataFrame({
        "game_pk": [r[0] for r in rows],
        "game_date": [r[2] for r in rows],
        "pitcher": [r[1] for r in rows],
        "batter": [100 + i for i in range(len(rows))],
        "stand": ["L"] * len(rows),
        "p_throws": ["R"] * len(rows),
        "events": [r[4] for r in rows],
        "at_bat_number": [r[3] for r in rows],
    })


def make_pmf37(h=0.075):
    pmf = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf[n] = surv * h
        surv *= 1 - h
    pmf[36] = surv
    return pmf


def build_saved_artifacts(pa23, tmp_path):
    """Synthetic saved BF artifact pair: predictions.csv + pmfs.parquet
    covering every first-pitcher (game_pk, pitcher) eval key."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    ORIGINS = rpt.ORIGINS
    FINAL = rpt.FINAL
    keys = []
    for origin in ORIGINS:
        nxt = (ORIGINS[ORIGINS.index(origin) + 1]
               if ORIGINS.index(origin) + 1 < len(ORIGINS) else FINAL)
        ev = pa23.filter((pl.col("game_date") >= origin)
                         & (pl.col("game_date") < nxt))
        counts = ev.group_by(["game_pk", "pitcher"]).agg(
            pl.len().alias("PA"),
            pl.col("game_date").min().alias("game_date"))
        for r in counts.iter_rows(named=True):
            keys.append({"origin": str(origin), "game_pk": r["game_pk"],
                         "pitcher": r["pitcher"],
                         "game_date": str(r["game_date"]),
                         "PA": int(r["PA"])})
    pmf37 = make_pmf37()
    preds_rows = []
    pmf_rows = []
    for i, kk in enumerate(keys):
        rps = bfd.rps_score(pmf37, kk["PA"])
        preds_rows.append({
            "origin": kk["origin"], "game_pk": kk["game_pk"],
            "pitcher": kk["pitcher"], "game_date": kk["game_date"],
            "PA": kk["PA"], "q_A": float(pmf37[:8].sum()),
            "q_B": float(pmf37[:8].sum()), "rps_A": rps, "rps_B": rps,
            "nll_A": 1.0, "nll_B": 1.0,
        })
        pmf_rows.append(np.hstack([make_pmf37(0.08), pmf37]))
    preds = pl.DataFrame(preds_rows)
    pmf_cols = (["pmfA_%02d" % i for i in range(37)]
                + ["pmfB_%02d" % i for i in range(37)])
    pl.DataFrame(np.vstack(pmf_rows), schema=pmf_cols).write_parquet(
        tmp_path / "pmfs.parquet")
    preds.write_csv(tmp_path / "predictions.csv")
    return tmp_path / "predictions.csv", tmp_path / "pmfs.parquet"


def _synthetic_season():
    d_train = date(2023, 4, 1)
    d_apr = date(2023, 4, 20)
    d_jul = date(2023, 7, 5)
    d_aug = date(2023, 8, 10)
    d_sep = date(2023, 9, 10)
    rows23 = []
    an = 0
    # helper: per (game, half) accumulate PAs so PA>1 for some rows
    def add_game(g, dd, k_top, k_bot, n_pa):
        nonlocal an
        for j in range(n_pa):
            an += 1
            ev_top = "strikeout" if j < k_top else "single"
            rows23.append((g, 10, dd, an, ev_top, "Top"))
            an += 1
            ev_bot = "strikeout" if j < k_bot else "single"
            rows23.append((g, 11, dd, an, ev_bot, "Bottom"))
    for i in range(8):  # training (pre-April-15): pitcher 10 good
        add_game(1 + i, d_train, 3, 0, 9)
    for i in range(6):  # April eval
        add_game(20 + i, d_apr, 3, 0, 9)
    for i in range(6):  # July eval (reversed skill)
        add_game(40 + i, d_jul, 0, 3, 9)
    for i in range(4):  # Aug eval
        add_game(60 + i, d_aug, 3, 3, 9)
    for i in range(4):  # Sep eval
        add_game(80 + i, d_sep, 6, 0, 9)
    rows22 = []
    for i in range(60):
        rows22.append((i // 2 + 1, 10 + (i % 6), date(2022, 6, 1),
                       i + 1, "strikeout" if i % 4 == 0 else "single",
                       "Top" if i % 2 == 0 else "Bottom"))
    return rows23, rows22


def test_run_diagnostic_end_to_end(tmp_path):
    rows23, rows22 = _synthetic_season()
    uni23 = synth_unified(rows23)
    uni22 = synth_unified(rows22)
    pa23, pa22 = rpt.load_frames(synth_raw(rows23), synth_raw(rows22),
                                 uni23, uni22)
    keys23, _ = rpt.rch.audit_identity(uni23)
    keys22, _ = rpt.rch.audit_identity(uni22)
    raw23, raw22 = synth_raw(rows23), synth_raw(rows22)
    # raw needs team columns for the batting-team map
    raw23 = raw23.with_columns(
        pl.lit("A").alias("home_team"), pl.lit("B").alias("away_team"))
    raw22 = raw22.with_columns(
        pl.lit("A").alias("home_team"), pl.lit("B").alias("away_team"))
    bf_preds, bf_pmfs = build_saved_artifacts(pa23, tmp_path / "bf")

    out = tmp_path / "out"
    prereg = tmp_path / "prereg.md"
    prereg.write_text("frozen prereg stub " + "a" * 64, encoding="ascii")
    manifest = rkc.run_diagnostic(
        pa23, pa22, keys23, raw23, keys22, raw22,
        bf_preds, bf_pmfs, out, prereg)
    assert manifest["status"] == "COMPLETE"
    pooled = manifest["pooled"]
    assert pooled["n"] == sum(o["n_eval"] for o in manifest["per_origin"])
    assert set(pooled["gate1"]) >= {"estimate", "lo95", "hi95", "pass"}
    for a in rkc.ARMS:
        assert 0.0 <= pooled[a]["mean_rps"] < 1e9
        assert pooled[a]["mean_logscore"] >= 0.0
    assert pooled["paired"]["I1_vs_C1L1_PRIMARY"]["slate_date_primary"][
        "n_boot"] == 2000
    # PMFs: mass conservation, absorbing bucket, C1 n in range
    pmfs = pl.read_parquet(out / "pmfs.parquet")
    for a in rkc.ARMS:
        cols = [c for c in pmfs.columns if c.startswith("pk%s_" % a)]
        m = pmfs.select(cols).to_numpy()
        assert np.allclose(m.sum(axis=1), 1.0, atol=1e-9)
    preds_out = pl.read_csv(out / "predictions.csv")
    assert preds_out.height == pooled["n"]
    assert preds_out["n_c1"].min() >= 1
    assert preds_out["n_c1"].max() <= 60
    assert (preds_out["K"] <= preds_out["PA"]).all()
    # C2 oracle exposure equals realized BF
    assert preds_out["mean_C2"].min() >= 0.0
    # sensitivity block present with matched comparator
    sens = pooled["sensitivity_pooled"]
    assert set(sens["mean_rps_cap60"]) == set(sens["mean_rps_cap120"])
    # provenance: every entry a real 64-char sha
    for name, val in manifest["provenance"].items():
        assert len(val) == 64 and all(
            c in "0123456789abcdef" for c in val), name
    # cap-120 E[N] >= cap-60 E[N]
    assert (preds_out["EN120"] >= preds_out["EN60"] - 1e-12).all()


def test_alignment_guard_blocks_tampered_artifacts(tmp_path):
    rows23, rows22 = _synthetic_season()
    uni23 = synth_unified(rows23)
    uni22 = synth_unified(rows22)
    pa23, pa22 = rpt.load_frames(synth_raw(rows23), synth_raw(rows22),
                                 uni23, uni22)
    keys23, _ = rpt.rch.audit_identity(uni23)
    keys22, _ = rpt.rch.audit_identity(uni22)
    raw23 = synth_raw(rows23).with_columns(
        pl.lit("A").alias("home_team"), pl.lit("B").alias("away_team"))
    raw22 = synth_raw(rows22).with_columns(
        pl.lit("A").alias("home_team"), pl.lit("B").alias("away_team"))
    d = tmp_path / "bf"
    d.mkdir()
    bf_preds, bf_pmfs = build_saved_artifacts(pa23, d)
    # tamper: perturb the first row's arm-B PMF -> alignment must fail
    pmfs = pl.read_parquet(bf_pmfs).to_numpy()
    pmfs[0, 37] += 0.01  # mass-preserving perturbation of arm-B row 0
    pmfs[0, 38] -= 0.01
    pmf_cols = (["pmfA_%02d" % i for i in range(37)]
                + ["pmfB_%02d" % i for i in range(37)])
    pl.DataFrame(pmfs, schema=pmf_cols).write_parquet(d / "pmfs.parquet")
    with pytest.raises(rkc.RunFailure, match="alignment FAILED"):
        rkc.run_diagnostic(pa23, pa22, keys23, raw23, keys22, raw22,
                           bf_preds, d / "pmfs.parquet",
                           tmp_path / "out2", tmp_path / "prereg.md")


def test_point_exposure_pmf_tail_bucket():
    pm = rkc.point_exposure_pmf(60, 0.25)
    assert abs(pm.sum() - 1.0) < 1e-9
    assert pm[23] > 0  # absorbing bucket holds P(K>=23)
    assert kc.exceedance(pm, 23) == pytest.approx(pm[23])
    # beyond the count support, exceedance is structurally zero
    assert kc.exceedance(pm, 24) == 0.0
    pm_small = rkc.point_exposure_pmf(3, 0.2)
    assert abs(pm_small.sum() - 1.0) < 1e-9
    assert kc.exceedance(pm_small, 4) == 0.0


def test_main_rejects_missing_artifacts(tmp_path):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("stub", encoding="ascii")
    rc = rkc.main(["--out", str(tmp_path / "o"),
                   "--prereg", str(prereg),
                   "--bf-preds", str(tmp_path / "nope.csv"),
                   "--bf-pmfs", str(tmp_path / "nope.parquet")])
    assert rc == 1
