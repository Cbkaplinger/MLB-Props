"""A/B forecast-only integration (NO scoring, NO outcome joins).

Row-keyed ledger for the captured 2026 cohort, actual declared cutoffs
(scheduled first pitch), confirmed-only adapter, and FINAL count PMFs
for both arms (A = scalar I1_ref path on reconstructed BF; B = lineup
mean with frozen A-fallback). Tail via frozen bf_pmf_from_37.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import bf_distribution as bfd  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import pa_lgbm_scaffold as sc  # noqa: E402
import pregame_lineup_capture as pc  # noqa: E402
import run_pa_aggregation_abc as agg  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_pa_lgbm_comparison as base  # noqa: E402
import pandas  # noqa: E402,F401
import run_i3_transfer_2024 as tr  # noqa: E402

FAILED_BUNDLES = ("bf-bundle-2026-20261012_130026",
                  "bf-bundle-2026-20261012_131334")
APPROVED_BUNDLE_SHA = "c7ff78b104a88cf7c124aafc48ad051d55a428af0605531fb8c49ef0076a6fcd"


def verify_bundle_identity(path: Path) -> str:
    """Mandatory pre-load identity guard (pickle loads execute code)."""
    actual = __import__("hashlib").sha256(
        (Path(path) / "bf_bundle.pkl").read_bytes()).hexdigest()
    if actual != APPROVED_BUNDLE_SHA:
        raise rch.MechanicalFailure(
            "bundle identity mismatch: approved %s got %s"
            % (APPROVED_BUNDLE_SHA, actual))
    return actual


def build_team_map(raw_map):
    """(game_pk, is_home)-keyed team binding; both sides coexist."""
    return {(int(r["game_pk"]), bool(r["is_home"])):
            (r["away_team"], r["home_team"])
            for r in raw_map.iter_rows(named=True)}


def assert_distinct_nine(batters):
    """Input-integrity guard (explicit failure, not debug assert)."""
    if batters is None or len(set(batters)) != 9 or len(batters) != 9:
        raise rch.MechanicalFailure(
            "lineup must have 9 distinct ordered slots; got %r" % (batters,))


def opponent_of(is_home, away_team, home_team):
    return home_team if is_home == 0 else away_team


def build_reconciliation_notes(captured, excluded, forecasted,
                               n_ub, n_fb, n_proj=0, n_late=0):
    """Computed receipt text (single source; imported by tests)."""
    return {
        "counts_reconciliation":
            "%d captured = %d null-probable excluded + %d forecasted "
            "(%d usable-B + %d fallback)" % (
                captured, excluded, forecasted, n_ub, n_fb),
        "fallback_mask_note":
            "fallback rows = %d (%d projected + %d late-only); %d "
            "usable-B rows are NOT fallback; B==A asserted bitwise on "
            "exactly the fallback mask" % (n_fb, n_proj, n_late, n_ub),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--preflight", required=True)
    ap.add_argument("--dump-intermediates", action="store_true")
    ap.add_argument("--bundle-sha", default=None)
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        assert not any(f in str(args.bundle) for f in FAILED_BUNDLES)
        # pre-load identity guard: verify approved bytes BEFORE
        # deserialization (pickle can execute code on load)
        bundle_pkl = Path(args.bundle) / "bf_bundle.pkl"
        actual_sha = verify_bundle_identity(args.bundle)
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        raws = {y: pl.read_parquet(
            root / "Savant-Data" / "regular" / str(y)
            / ("statcast_%d_regular.parquet" % y)) for y in
            (2022, 2023, 2024, 2025, 2026)}
        fb = rch.derive_fallback_2022(raws[2022])
        appearances, _q = tr._appearances(
            [raws[y] for y in (2022, 2023, 2024, 2025, 2026)])
        b = {y: rch.build_batting_rows(raws[y]) for y in raws}
        frame26 = tr._season_frame(raws[2026], appearances, b[2026],
                                   b[2025], 2026, 2025, fb["mean_bf"])
        pdf26 = frame26.to_pandas()
        # label tables for priors (2022-2025 + 2026 pre-cutoff features)
        pooled_label = pl.concat(
            [sc.build_pa_label_table(raws[y]) for y in (2022, 2023, 2024,
                                                        2025)],
            how="vertical")
        snaps = pc.load_snapshots(sorted(
            (root / "processed").glob("daily_lineups_*.parquet")))
        import pandas as pd
        g = snaps.group_by(["game_pk", "is_home"]).agg(
            pl.col("game_time").max().alias("game_time"),
            pl.col("game_date").max().alias("game_date"))
        cutoffs = {}
        for r in g.iter_rows(named=True):
            # the writer stores scheduled first pitch as tz-aware UTC
            gt = r["game_time"]
            malformed = gt is None
            cutoffs[int(r["game_pk"])] = {
                "utc": gt, "malformed": malformed}
        probs = (snaps.select(["game_pk", "is_home",
                               "home_probable_pitcher_id",
                               "away_probable_pitcher_id",
                               "team", "fetched_at"])
                 .unique(subset=["game_pk", "is_home"], keep="last")
                 .with_columns(
                     pl.when(pl.col("is_home") == 1)
                     .then(pl.col("home_probable_pitcher_id"))
                     .otherwise(pl.col("away_probable_pitcher_id"))
                     .cast(pl.Int64).alias("pitcher")))
        pdf26 = tr._season_frame(raws[2026], appearances, b[2026],
                                 b[2025], 2026, 2025, fb["mean_bf"])
        pdf26 = pdf26.to_pandas()
        ledger = []
        gd_map = {int(r["game_pk"]): str(r["game_date"])
                  for r in g.iter_rows(named=True)}
        for r in probs.iter_rows(named=True):
            gp = int(r["game_pk"])
            pid = r["pitcher"]
            if pid is None if False else pid is None:
                ledger.append({"game_pk": gp, "pitcher": None,
                               "matched": False,
                               "exclusion_reason": "null_probable_pitcher",
                               "cutoff_utc": str(
                                   cutoffs.get(gp, {}).get("utc")),
                               "game_date": str(gd_map.get(gp, ""))})
                continue
            m = pdf26[(pdf26["game_pk"] == gp)
                      & (pdf26["pitcher"] == int(pid))]
            cut = cutoffs.get(gp)
            ledger.append({"game_pk": gp, "pitcher": int(pid),
                           "matched": bool(len(m)),
                           "cutoff_utc": str(cut),
                           "game_date": str(gd_map.get(gp, ""))})
        n_match = sum(1 for x in ledger if x["matched"])
        bundle = pickle.load(open(bundle_pkl, "rb"))
        pdf26i = pl.from_pandas(pdf26)
        fp = probs.filter(pl.col("pitcher").is_not_null()).with_columns(
            pl.col("pitcher").cast(pl.Int64))
        matched = fp.join(pdf26i, on=["game_pk", "pitcher"],
                          how="inner").unique(subset=["game_pk",
                                                      "pitcher"])
        matched = matched.sort(["game_pk", "pitcher"])
        feats = matched.to_pandas()[
            rch.CHALLENGER_FEATURES].to_numpy(dtype=float)
        pmfs37 = bfd.predict_pmf(bundle, feats)
        bf60 = np.array([kc.bf_pmf_from_37(p) for p in pmfs37])
        # priors (v1, strictly prior dates) for the scalar arms
        keys = sc.pitcher_snapshot_keys(
            matched.select(["game_pk", "game_date", "pitcher"]))
        pp = keys.join(sc.pitcher_rate_priors(pooled_label, keys),
                       on=sc.PITCHER_SNAPSHOT_COLUMNS, how="left")
        pp = pp.with_columns([pl.col("k_prior").fill_null(0),
                              pl.col("n_prior").fill_null(0)])
        # arm construction
        out_rows = []
        pA_all, pB_all = [], []
        km = matched.to_pandas().sort_values(["game_pk", "pitcher"])
        km = km.reset_index(drop=True)
        # revision inventory at (game_pk, is_home) grain: distinct
        # fetched_at, probable IDs, scheduled times; fail closed on
        # conflicting revisions (no frozen selection rule exists)
        rev = (snaps.group_by(["game_pk", "is_home"]).agg(
            pl.col("fetched_at").n_unique().alias("n_fetch"),
            pl.col("home_probable_pitcher_id").n_unique().alias("n_hp"),
            pl.col("away_probable_pitcher_id").n_unique().alias("n_ap"),
            pl.col("game_time").n_unique().alias("n_time")))
        n_rev_conf = int(((rev["n_fetch"] > 1) | (rev["n_hp"] > 1)
                          | (rev["n_ap"] > 1)
                          | (rev["n_time"] > 1)).sum())
        if n_rev_conf:
            raise rch.MechanicalFailure(
                "conflicting capture revisions at (game_pk,is_home) "
                "grain: %d groups (no frozen revision rule; fail-closed)"
                % n_rev_conf)
        # (game_pk, is_home) must resolve to exactly one team triple
        raw_map = snaps.select(["game_pk", "is_home", "away_team",
                                "home_team"]).unique()
        conf = (raw_map.group_by(["game_pk", "is_home"])
                .agg(pl.struct(["away_team", "home_team"])
                     .n_unique().alias("n")))
        n_conf = int((conf["n"] > 1).sum())
        if n_conf:
            raise rch.MechanicalFailure(
                "team-map conflict: %d (game_pk,is_home) groups carry "
                "conflicting team triples" % n_conf)
        team_map = build_team_map(raw_map)
        malformed_gp = {gp for gp, c in cutoffs.items()
                        if c.get("malformed", False)}
        for i in range(len(km)):
            gp = int(km.iloc[i]["game_pk"])
            pdt = km.iloc[i]["game_date"]
            cutoff = cutoffs[gp]["utc"]
            row_p = pp.filter((pl.col("key_game_pk") == gp)
                              & (pl.col("pitcher")
                                 == int(km.iloc[i]["pitcher"])))
            kp = int(row_p["k_prior"][0]) if row_p.height else 0
            npit = int(row_p["n_prior"][0]) if row_p.height else 0
            prior = pooled_label.filter(
                (pl.col("pa_class") == sc.CLASS_COMPLETED)
                & (pl.col("game_date") < pdt.date()))
            lg = float(prior["y"].mean())  # event-weighted sumK/sumPA
            p_p = (kp + sc.W_SHRINK * lg) / (npit + sc.W_SHRINK) \
                if npit > 0 else lg  # zero-history rule: p_p = lg
            # neutral-batter identity: log5(p, lg, lg) == p
            z = np.log(p_p / (1 - p_p))
            assert abs(1 / (1 + np.exp(-z)) - p_p) < 1e-12
            pkA = kc.combine_count(bf60[i], float(p_p), agg.K_MAX)
            agg.check_mass(pkA, "A")
            ih = bool(km.iloc[i]["is_home"])
            away_t, home_t = team_map.get((gp, ih), (None, None))
            opp = home_t if ih == 0 else away_t
            if gp in malformed_gp:
                sel = {"ok": False, "reason": "malformed_cutoff_quarantined"}
            elif opp is None:
                sel = {"ok": False, "reason": "no_team_identity"}
            else:
                sel = pc.select_pregame_lineup(
                    snaps, gp, opp, cutoff, mode=pc.MODE_CONFIRMED_ONLY)
            if sel["ok"]:
                bid = sel["batters"]
                assert_distinct_nine(bid)
                bdf = base.batter_rate_priors_fast(
                    pooled_label,
                    pl.DataFrame({"batter": bid,
                                  "cutoff_date": [pdt.date()] * 9}))
                bl = {r["batter"]: r for r in bdf.iter_rows(named=True)}
                bks = [int((bl.get(b) or {"b_k_prior": 0})["b_k_prior"])
                       for b in bid]
                bns = [int((bl.get(b) or {"b_n_prior": 0})["b_n_prior"])
                       for b in bid]
                seq9 = agg.row_seq9(p_p, bks, bns, lg, sc.W_SHRINK)
                seq = np.tile(seq9, agg.CAP // 9 + 1)[:agg.CAP]
                mb, mc = [], []
                pkB = agg.mixture_b(bf60[i], seq, mb)
                # independent conditional target: sum of first n cycled
                # probabilities (uncapped; bucket 23 collapsed separately)
                csum = np.cumsum(seq)
                target = [(n, float(csum[n - 1])) for n, _ in mb]
                agg.assert_mean_gate(bf60[i], seq, mb, target)
                agg.check_mass(pkB, "B")
                b_status = "ok_confirmed"
            else:
                pkB = pkA.copy()
                b_status = "A_fallback_%s" % sel["reason"]
            out_rows.append({
                "game_pk": gp, "pitcher": int(km.iloc[i]["pitcher"]),
                "forecast_cutoff": str(cutoff),
                "bf_pmf_source": "corrected bundle inference",
                "arm_A_mean_K": float((np.arange(agg.K_MAX) * pkA).sum()),
                "arm_B_status": b_status,
                "arm_B_equals_A": bool(np.array_equal(pkA, pkB)),
                "tail_overflow_mass": float(1.0 - bf60[i][:36].sum())})
            pA_all.append(pkA)
            pB_all.append(pkB)
            if args.dump_intermediates:
                out_rows[-1].update({
                    "lg_event_weighted": lg, "p_pitcher": float(p_p),
                    "pitcher_k_prior": kp, "pitcher_n_prior": npit,
                    "batters": bid if sel["ok"] else None,
                    "seq9": seq9.tolist() if sel["ok"] else None,
                    "bf_row_hash": __import__("hashlib").sha256(
                        bf60[i].tobytes()).hexdigest()[:16],
                    "pkA_hash": __import__("hashlib").sha256(
                        pkA.tobytes()).hexdigest()[:16],
                    "pkB_hash": __import__("hashlib").sha256(
                        pkB.tobytes()).hexdigest()[:16],
                    "lg_k": int(prior["y"].sum()),
                    "lg_pa": int(prior.height)})
        from collections import Counter
        status_counts = Counter(x["arm_B_status"] for x in out_rows)
        n_fb = sum(1 for x in out_rows if x["arm_B_equals_A"])
        rep = {
            "n_captured_team_games": int(g.height),
            "n_probable_rows": int(probs.height),
            "n_matched_feature_rows": n_match,
            "n_unmatched": int(probs.height) - n_match,
            "n_forecast_rows": len(out_rows),
            "arm_B_status_counts": dict(status_counts),
            "n_usable_confirmed_B": status_counts.get("ok_confirmed", 0),
            "n_A_fallback": status_counts.get(
                "A_fallback_full_projected_confirmed_only_mode", 0)
            + status_counts.get("A_fallback_all_snapshots_after_cutoff", 0),
            "arm_description": "A = I1_ref shrunk scalar pitcher rate "
                               "with reconstructed BF; B = confirmed-"
                               "lineup mean log5 matchup rate, same BF; "
                               "lineup-composition adjustment comparison",
        }
        n_fb = sum(1 for x in out_rows
                   if x["arm_B_status"].startswith("A_fallback"))
        n_ub = sum(1 for x in out_rows if x["arm_B_status"] == "ok_confirmed")
        # GENERAL reconciliation identities (no hardcoded cohort counts)
        assert n_match + (int(probs.height) - n_match) == int(probs.height)
        assert len(out_rows) == n_match
        assert n_fb + n_ub == len(out_rows)
        rep["n_A_fallback"] = n_fb
        rep["n_usable_confirmed_B"] = n_ub
        assert all(x["arm_B_equals_A"] for x in out_rows
                   if x["arm_B_status"].startswith("A_fallback"))
        rep["fallback_mask_verified"] = True
        n_late = status_counts.get("A_fallback_all_snapshots_after_cutoff",
                                   0)
        n_proj = status_counts.get(
            "A_fallback_full_projected_confirmed_only_mode", 0)
        rep["fallback_mask_note"] = (
            "fallback rows = %d (%d projected + %d late-only); %d "
            "usable-B rows are NOT fallback; B==A asserted bitwise on "
            "exactly the fallback mask"
            % (n_fb, n_proj, n_late, n_ub))
        notes = build_reconciliation_notes(
            int(probs.height), int(probs.height) - n_match, n_match,
            n_ub, n_fb, n_proj, n_late)
        rep["counts_reconciliation"] = notes["counts_reconciliation"]
        rep["fallback_mask_note"] = notes["fallback_mask_note"]
        (out_dir / "ab_forecast_ledger.json").write_text(
            json.dumps(rep, indent=1, default=str), encoding="ascii")
        np.save(out_dir / "arm_A_pmf.npy", np.array(pA_all))
        np.save(out_dir / "arm_B_pmf.npy", np.array(pB_all))
        if args.dump_intermediates:
            (out_dir / "intermediates_dump.json").write_text(
                json.dumps(out_rows, indent=1, default=str),
                encoding="ascii")
        (out_dir / "row_keys.json").write_text(json.dumps(
            [{k: x[k] for k in ("game_pk", "pitcher", "forecast_cutoff",
                                "arm_B_status", "arm_B_equals_A")}
             for x in out_rows], indent=1, default=str), encoding="ascii")
        print(json.dumps({k: rep[k] for k in (
            "n_captured_team_games", "n_probable_rows",
            "n_matched_feature_rows", "n_forecast_rows",
            "arm_B_status_counts", "n_A_fallback",
            "fallback_mask_verified", "counts_reconciliation")}, indent=1))
        print("WROTE %s" % out_dir)
        return 0
    except Exception as exc:
        print("BLOCKER %s: %s" % (type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
