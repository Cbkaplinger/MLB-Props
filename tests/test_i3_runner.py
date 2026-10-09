"""File-based integration test for the I3 opportunity scored runner.

Synthetic frames flow through the full run_diagnostic (saved-artifact
reproduction, proxy cards, ordered PB mixture, parity, gate, cap-120,
manifest, outputs) into a tmp directory. No real data, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import kcount_combiner as kc  # noqa: E402
import run_i3_opportunity_2023 as r3  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import pa_k_baseline as pak
import run_pa_k_baseline_2023 as rpt  # noqa: E402
from test_kcount_runner import (  # noqa: E402
    _synthetic_season, synth_raw, synth_unified)


def make_pmf37(h=0.075):
    pmf = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf[n] = surv * h
        surv *= 1 - h
    pmf[36] = surv
    return pmf


def build_kc_and_bf_artifacts(pa23, d, pa22=None, raw23=None):
    """Synthetic K-count run artifact pair (predictions.csv + pmfs with
    pkI1/pkI3b/pkC2) AND the upstream BF artifact pair (74-col pmfs),
    all positionally consistent. With raw23 supplied, saved I3b rows
    are built through the SAME proxy-card + p* path the runners use
    (mirror path), so the I4 reproduction check is meaningful."""
    import run_i3_opportunity_2023 as r3
    import lineup_opportunity as lo
    d.mkdir(parents=True, exist_ok=True)
    ORIGINS = rpt.ORIGINS
    FINAL = rpt.FINAL
    pmf37 = make_pmf37()
    ext60 = kc.bf_pmf_from_37(pmf37)
    mirror = raw23 is not None and pa22 is not None
    rates_by_origin = {}
    cards_f = sched_f = None
    pool = None
    if mirror:
        import pandas as pd
        cards_f, sched_f = r3.build_cards(raw23)
        pool = pl.concat([pa22, pa23], how="vertical")
        for o in ORIGINS:
            pr, lg, _ = pak.prior_rates(pool, pd.Timestamp(o), "pitcher",
                                        pak.W_SHRINK)
            br, _, _ = pak.prior_rates(pool, pd.Timestamp(o), "batter",
                                       pak.W_SHRINK)
            rates_by_origin[str(o)] = (pr, br, lg if lg == lg else 0.22)
    pred_rows, kc_rows, pkI1, pkI3b, pkC2 = [], [], [], [], []
    for pi, origin in enumerate(ORIGINS):
        nxt = (ORIGINS[ORIGINS.index(origin) + 1]
               if ORIGINS.index(origin) + 1 < len(ORIGINS) else FINAL)
        ev = pa23.filter((pl.col("game_date") >= origin)
                         & (pl.col("game_date") < nxt))
        counts = ev.group_by(["game_pk", "pitcher"]).agg(
            pl.len().alias("PA"), pl.col("y").sum().alias("K"),
            pl.col("game_date").min().alias("game_date"))
        for r in counts.iter_rows(named=True):
            pri = len(pred_rows)
            pred_rows.append(pri)
            pk_i1 = rkc.point_exposure_pmf(int(r["PA"]), 0.22)
            pk_c2 = rkc.point_exposure_pmf(int(r["PA"]), 0.24)
            pkI1.append(pk_i1)
            pkI3b.append(None)  # filled by the mirror path below
            pkC2.append(pk_c2)
            kc_rows.append({
                "origin": str(origin), "pred_row_idx": pri,
                "game_pk": r["game_pk"], "pitcher": r["pitcher"],
                "game_date": str(r["game_date"]), "PA": int(r["PA"]),
                "K": int(r["K"]), "batting_team": "TOR",
                "is_home": True, "p_bar_l1": 0.22, "p_bar_c2": 0.24,
                "rps_I1": kc.count_rps(pk_i1, int(r["K"])),
            })
    if mirror:
        from datetime import date as _d
        for kr in kc_rows:
            pids, _pd, _g = r3._prior_card(
                cards_f, sched_f, kr["batting_team"],
                _d.fromisoformat(kr["game_date"]))
            pr, br, lg = rates_by_origin[kr["origin"]]
            lg_safe = lg if lg == lg else 0.2
            p_p = pr.get(kr["pitcher"], (lg_safe, 0))[0]
            if pids:
                slots = lo.slot_probs(pids, p_p, br, lg, pak.W_SHRINK)
            else:
                slots = np.full(9, lg_safe)
            pstar = lo.p_star(ext60, slots)
            pkI3b[kr["pred_row_idx"]] = kc.combine_count(ext60, pstar)
    else:
        for i in range(len(kc_rows)):
            pkI3b[i] = pkI3b[i] or pkI1[i]
    pl.DataFrame({
        "pmfA_%02d" % i: [make_pmf37(0.08)[i]] * len(pred_rows)
        for i in range(37)} | {
        "pmfB_%02d" % i: [pmf37[i]] * len(pred_rows)
        for i in range(37)}).write_parquet(d / "bf_pmfs.parquet")
    pl.DataFrame({"x": [0]}).write_csv(d / "bf_preds.csv")
    kc_df = pl.DataFrame(kc_rows)
    kc_df.write_csv(d / "kc_preds.csv")
    pk_cols = (["pkI1_%02d" % i for i in range(24)]
               + ["pkI3b_%02d" % i for i in range(24)]
               + ["pkC2_%02d" % i for i in range(24)] + ["EN60"])
    pl.DataFrame(np.hstack([
        np.vstack(pkI1), np.vstack(pkI3b), np.vstack(pkC2),
        np.full((len(kc_rows), 1), 22.0)]),
        schema=pk_cols).write_parquet(d / "kc_pmfs.parquet")
    return d / "kc_preds.csv", d / "kc_pmfs.parquet", d / "bf_preds.csv", \
        d / "bf_pmfs.parquet"


def _setup(tmp_path):
    rows23, rows22 = _synthetic_season()
    uni23 = synth_unified(rows23)
    uni22 = synth_unified(rows22)
    # cyclic batters per side so each team-game yields >=9 distinct
    # card candidates AND rate-pool histories for the same ids
    def raw23_cyclic():
        return pl.DataFrame({
            "game_pk": [r[0] for r in rows23],
            "game_date": [r[2] for r in rows23],
            "pitcher": [r[1] for r in rows23],
            "batter": [(101 + (i % 9)) if r[5] == "Top"
                       else (201 + (i % 9))
                       for i, r in enumerate(rows23)],
            "stand": ["L"] * len(rows23),
            "p_throws": ["R"] * len(rows23),
            "events": [r[4] for r in rows23],
            "at_bat_number": [r[3] for r in rows23],
            "inning_topbot": [r[5] for r in rows23],
            "home_team": ["LAA"] * len(rows23),
            "away_team": ["TOR"] * len(rows23)})

    raw23 = raw23_cyclic()
    pa23, pa22 = rpt.load_frames(raw23, synth_raw(rows22), uni23, uni22)
    keys23, _ = rpt.rch.audit_identity(uni23)
    keys22, _ = rpt.rch.audit_identity(uni22)
    raw22 = synth_raw(rows22).with_columns(
        pl.lit("A").alias("home_team"), pl.lit("B").alias("away_team"))
    return pa23, pa22, keys23, raw23, raw22


def test_run_diagnostic_end_to_end(tmp_path):
    pa23, pa22, keys23, raw23, raw22 = _setup(tmp_path)
    kc_preds, kc_pmfs, bf_preds, bf_pmfs = \
        build_kc_and_bf_artifacts(pa23, tmp_path / "art", pa22, raw23)
    out = tmp_path / "out"
    contract = tmp_path / "contract.md"
    contract.write_text("frozen contract stub " + "b" * 64,
                        encoding="ascii")
    manifest = r3.run_diagnostic(
        pa23, pa22, keys23, raw23, raw22,
        kc_preds, kc_pmfs, bf_preds, bf_pmfs, out, contract)
    assert manifest["status"] == "COMPLETE"
    p = manifest["pooled"]
    assert p["label"].startswith("chronological fallback")
    assert p["opportunity_model"].startswith("FIRST-NINE-OBSERVED")
    assert p["parity_max_absdiff"] <= 1e-12
    assert set(p["gate1"]) >= {"estimate", "lo95", "hi95", "pass"}
    assert p["paired"]["I3a_vs_I1_PRIMARY"]["slate_date_primary"][
        "n_boot"] == 2000
    for a in r3.ARMS:
        assert 0.0 <= p[a]["mean_rps"] < 1e9
        assert p[a]["logscore_floor_hit_rows"] >= 0
    assert set(p["descriptive_pit"]) == {"I1", "I3a"}
    assert sum(p["descriptive_pit"]["I3a"]["hist"]) == p["n"]
    assert set(p["descriptive_dispersion"]["pooled"]) == {"I1", "I3a"}
    preds = pl.read_csv(out / "predictions.csv")
    assert preds.height == p["n"]
    # proxy-card provenance columns populated
    assert preds["card_date"].null_count() == 0
    assert (preds["card_staleness_days"] >= 1).all()
    assert preds["proxy_card"].null_count() == 0
    pmfs = pl.read_parquet(out / "pmfs.parquet")
    for a in ("I1", "I3a", "I3b", "C2"):
        cols = [c for c in pmfs.columns if c.startswith("pk%s_" % a)]
        m = pmfs.select(cols).to_numpy()
        assert np.allclose(m.sum(axis=1), 1.0, atol=1e-9)
    for name, val in manifest["provenance"].items():
        assert len(val) == 64 and all(
            c in "0123456789abcdef" for c in val), name


def test_reproduction_guard_blocks_tampered_i1(tmp_path):
    pa23, pa22, keys23, raw23, raw22 = _setup(tmp_path)
    kc_preds, kc_pmfs, bf_preds, bf_pmfs = \
        build_kc_and_bf_artifacts(pa23, tmp_path / "art", pa22, raw23)
    kp = pl.read_csv(kc_preds)
    kp = kp.with_columns(pl.col("rps_I1") + 0.01)
    kp.write_csv(kc_preds)
    with pytest.raises(r3.RunFailure, match="reproduction failed"):
        r3.run_diagnostic(
            pa23, pa22, keys23, raw23, raw22,
            kc_preds, kc_pmfs, bf_preds, bf_pmfs,
            tmp_path / "out2", tmp_path / "c.md")


def test_main_rejects_missing_contract(tmp_path):
    rc = r3.main(["--out", str(tmp_path / "o"),
                  "--contract", str(tmp_path / "nope.md"),
                  "--kc-preds", str(tmp_path / "a.csv"),
                  "--kc-pmfs", str(tmp_path / "b.parquet"),
                  "--bf-preds", str(tmp_path / "c.csv"),
                  "--bf-pmfs", str(tmp_path / "d.parquet")])
    assert rc == 1
