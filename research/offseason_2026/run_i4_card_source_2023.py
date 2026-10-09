"""I4 prior-starting-card source scored runner (ONE run, 2023).

Implements `research/offseason_2026/i4-card-source-experiment.md`
(frozen 2026-10-08, sha recorded in the manifest). LABELED: a
CHRONOLOGICAL FALLBACK DIAGNOSTIC; no verified-8am or announced-
lineup claim.

Question: does the previous game's ACTUAL starting batting order
(Retrosheet start records, slots 1..9, substitutes and non-batting
pitcher excluded) improve on the FIRST-NINE-OBSERVED-BATTER PROXY?

Arms on identical rows (the 4,446 eval pitcher-games):
  I3b  frozen benchmark (saved PMFs from the canonical I3 run;
       reproduction asserted)
  I4   same structure (survival-weighted p*, homogeneous count) with
       the card source swapped to Retrosheet previous-game starters

Primary: paired count-RPS I4 - I3b, date-clustered bootstrap 2000 /
seed 20261001, CI entirely below 0 = pass. Any mapping/coverage
failure -> frozen fallback to the proxy card + flag (never silent,
never outcome-based). No BF refit; no tuning; no market inputs; no
2024+ access. 2023 DEVELOPMENTAL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import kcount_combiner as kc  # noqa: E402
import lineup_opportunity as lo  # noqa: E402
import pa_k_baseline as pak  # noqa: E402
import retrosheet_cards as rc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_i3_opportunity_2023 as r3  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import run_pa_k_baseline_2023 as rpt  # noqa: E402

K_MAX = 24
SEED = 20261001
N_BOOT = 2000
ORIGINS = (date(2023, 4, 15), date(2023, 7, 1), date(2023, 8, 1),
           date(2023, 9, 1))
ALIGN_TOL = 1e-8
MILESTONES = (6, 7, 8, 9, 10, 12)
SENS_CAP = 120


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def season_digest(path: Path) -> str:
    """Deterministic sha256 over a season directory's files (sorted by
    name); falls back to the season zip when present."""
    h = hashlib.sha256()
    if (path / ("%s.zip" % path.name)).is_file():
        return sha256_file(path / ("%s.zip" % path.name))
    for f in sorted(path.rglob("*")):
        if f.is_file() and f.name != "SHA256SUMS.txt":
            h.update(str(f.relative_to(path)).encode())
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def run_diagnostic(pa23, pa22, keys23, raw23,
                   kc_preds_path: Path, kc_pmfs_path: Path,
                   i3_pmfs_path: Path, bf_preds_path: Path,
                   bf_pmfs_path: Path, rs_raw_root: Path,
                   rs_register_dir: Path,
                   out_dir: Path, contract_path: Path) -> dict:
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        # ---- frozen inputs (identical lineage to I3) ----------------
        kpreds = pl.read_csv(kc_preds_path).with_row_index("kc_row")
        kpk = pl.read_parquet(i3_pmfs_path)
        n = kpreds.height
        pkI3b = kpk.select(["pkI3b_%02d" % i for i in range(K_MAX)]
                           ).to_numpy()
        bf_pmfs = pl.read_parquet(bf_pmfs_path).to_numpy()
        pmB37 = bf_pmfs[:, 37:][kpreds["pred_row_idx"].to_numpy()]

        joined = kpreds.join(
            keys23.select([pl.col("game_pk"),
                           pl.col("forecast_pitcher").alias("pitcher"),
                           pl.col("game_date").alias("spine_date"),
                           "is_home"]),
            on=["game_pk", "pitcher"], how="left")
        if joined["is_home"].null_count() > 0:
            raise RunFailure("eval keys missing from 2023 spine")
        if (joined["game_date"].cast(pl.Utf8)
                != joined["spine_date"].cast(pl.Utf8)).any():
            raise RunFailure("saved game_date does not match spine")
        pa_counts = pa23.group_by(["game_pk", "pitcher"]).agg(
            pl.len().alias("n_pa"), pl.col("y").sum().alias("k_actual"))
        joined = joined.join(pa_counts, on=["game_pk", "pitcher"],
                             how="left")
        if not (joined["PA"] == joined["n_pa"]).all():
            raise RunFailure("BF identity failed")

        # ---- Retrosheet cards ---------------------------------------
        retro22 = rc.load_season(rs_raw_root / "2022")
        retro23 = rc.load_season(rs_raw_root / "2023")
        retro = pl.concat([retro22, retro23], how="vertical")
        register = rc.load_register(rs_register_dir)
        gm23 = raw23.select("game_pk", "game_date", "home_team",
                            "away_team").unique(subset=["game_pk"])
        sched23 = pl.concat([
            gm23.select(pl.col("game_date").cast(pl.Date).alias("d"),
                        pl.col("home_team").alias("home"), "game_pk"),
        ], how="vertical").unique(subset=["home", "d", "game_pk"])
        match = rc.schedule_match(retro, sched23)
        if not match["threshold_match"]:
            return {"status": "BLOCKED",
                    "reason": "Retrosheet/Statcast schedule "
                              "correspondence below frozen threshold",
                    "schedule_match": match}
        prev_cards = rc.previous_game_cards(retro, register)
        proxy_cards_frame, proxy_sched = r3.build_cards(raw23)

        pool = pl.concat([pa22, pa23], how="vertical")
        per_origin = []
        row_frames = []
        pk_store = {"I3b": [], "I4": []}
        for origin in ORIGINS:
            ev = joined.filter(pl.col("origin") == str(origin))
            if ev.height == 0:
                raise RunFailure("no eval rows for %s" % origin)
            as_of = pd.Timestamp(origin)
            pr_rates, lg, _ = pak.prior_rates(pool, as_of, "pitcher",
                                              pak.W_SHRINK)
            br_rates, _, _ = pak.prior_rates(pool, as_of, "batter",
                                             pak.W_SHRINK)
            lg_safe = lg if lg == lg else 0.2

            proxy_cards, proxy_dates, proxy_stale = [], [], []
            rs_cards, rs_flags = [], []
            for row in ev.iter_rows(named=True):
                team_sc = row["batting_team"]
                team_rs = rc.STATCAST_TO_RETRO.get(team_sc)
                if team_rs is None:
                    raise RunFailure("unmapped Statcast team %r"
                                     % team_sc)
                gd = row["spine_date"]
                # proxy card (I3b benchmark source, as in I3)
                pids, pdate, pgap = r3._prior_card(
                    proxy_cards_frame, proxy_sched, team_sc, gd)
                proxy_cards.append(";".join(str(x) for x in pids))
                proxy_dates.append(str(pdate) if pdate is not None
                                   else "B2_FALLBACK")
                proxy_stale.append(pgap)
                # I4 card: Retrosheet previous game strictly before gd
                pc = prev_cards.filter(
                    (pl.col("team") == team_rs)
                    & (pl.col("date") == str(gd)))
                if pc.height != 1:
                    raise RunFailure("previous-game lookup failed for "
                                     "%s %s" % (team_rs, gd))
                r = pc.row(0, named=True)
                if r["rs_card"] is None:
                    rs_cards.append(";".join(str(lg_safe) for _ in
                                             range(9)))
                    rs_flags.append("fallback:"
                                    + ("no_prior" if r["prev_id"] is None
                                       else "invalid_or_unmapped"))
                else:
                    rs_cards.append(";".join(str(x) for x in
                                             r["rs_card"]))
                    rs_flags.append("retrosheet")
            slot_rs = np.empty((ev.height, lo.SLOT_COUNT))
            slot_px = np.empty((ev.height, lo.SLOT_COUNT))
            for r_i, row in enumerate(ev.iter_rows(named=True)):
                p_p = pr_rates.get(row["pitcher"], (lg_safe, 0))[0]
                px_ids = [int(v) if str(v).isdigit() else None
                          for v in proxy_cards[r_i].split(";")]
                if all(v is not None for v in px_ids):
                    slot_px[r_i] = lo.slot_probs(px_ids, p_p, br_rates,
                                                 lg, pak.W_SHRINK)
                else:
                    slot_px[r_i] = np.full(9, lg_safe)
                rs_ids = [int(v) for v in rs_cards[r_i].split(";")]
                if rs_flags[r_i] == "retrosheet":
                    slot_rs[r_i] = lo.slot_probs(rs_ids, p_p, br_rates,
                                                 lg, pak.W_SHRINK)
                else:
                    slot_rs[r_i] = np.full(9, lg_safe)

            pmf37 = pmB37[[r["pred_row_idx"]
                           for r in ev.iter_rows(named=True)]]
            ext60 = np.array([kc.bf_pmf_from_37(pmf37[i])
                              for i in range(ev.height)])
            k_obs = ev["K"].to_numpy()
            pk_rs = np.array([lo.mixture_ordered(ext60[i], slot_rs[i])
                              for i in range(ev.height)])
            p_star_rs = np.array([lo.p_star(ext60[i], slot_rs[i])
                                  for i in range(ev.height)])
            pk_px = np.array([kc.combine_count(ext60[i], p_star_px)
                              for i, p_star_px in enumerate(
                                  np.array([
                                      lo.p_star(ext60[i], slot_px[i])
                                      for i in range(ev.height)]))])
            # benchmark reproduction: saved I3b PMFs must match the
            # recomputed proxy-card I3b on every row
            pk_i3b_saved = pkI3b[[r["kc_row"]
                                  for r in ev.iter_rows(named=True)]]
            rep = float(np.abs(pk_px - pk_i3b_saved).max())
            if rep > ALIGN_TOL:
                raise RunFailure(
                    "I3b benchmark reproduction failed: max diff %g"
                    % rep)
            pk_store["I3b"].append(pk_i3b_saved)
            pk_store["I4"].append(pk_rs)

            e_k = {
                "I3b": np.array([lo.p_star(ext60[i], slot_px[i])
                                 for i in range(ev.height)]) * np.array(
                    [kc.expected_bf(ext60[i]) for i in range(ev.height)]),
                "I4": p_star_rs * np.array(
                    [kc.expected_bf(ext60[i]) for i in range(ev.height)]),
            }
            sc = {"I3b": rkc._row_scores(pk_i3b_saved, k_obs, e_k["I3b"]),
                  "I4": rkc._row_scores(pk_rs, k_obs, e_k["I4"])}

            rows = pd.DataFrame({
                "origin": str(origin),
                "kc_row": ev["kc_row"].to_numpy(),
                "game_pk": ev["game_pk"].to_numpy(),
                "pitcher": ev["pitcher"].to_numpy(),
                "game_date": ev["game_date"].to_numpy().astype(str),
                "batting_team": ev["batting_team"].to_numpy(),
                "K": k_obs,
                "proxy_card": proxy_cards,
                "proxy_card_date": proxy_dates,
                "proxy_staleness_days": proxy_stale,
                "rs_card": rs_cards,
                "rs_card_flag": rs_flags,
            })
            for a in ("I3b", "I4"):
                pk_arm = pk_i3b_saved if a == "I3b" else pk_rs
                rows["rps_" + a] = sc[a]["rps"]
                rows["logscore_" + a] = sc[a]["logscore"]
                rows["floorhit_" + a] = sc[a]["floor_hit"].astype(int)
                rows["mae_" + a] = sc[a]["mae"]
                rows["mean_" + a] = e_k[a]
                for m in MILESTONES:
                    rows["mb%d_" % m + a] = np.array(
                        [kc.milestone_brier(pk_arm[i], int(k_obs[i]),
                                            MILESTONES)["ge%d" % m]
                         for i in range(ev.height)])
            row_frames.append(rows)
            per_origin.append({
                "origin": str(origin),
                "n_eval": int(ev.height),
                "rs_fallbacks": int(sum(
                    1 for f in rs_flags if f != "retrosheet")),
                "arm_means": {a: {
                    "mean_rps": float(sc[a]["rps"].mean()),
                    "mean_logscore": float(sc[a]["logscore"].mean()),
                    "floor_hit_rows": int(sc[a]["floor_hit"].sum()),
                    "mean_milestone_brier": {
                        m: float(rows["mb%d_" % m + a].mean())
                        for m in MILESTONES}} for a in ("I3b", "I4")},
            })

        all_rows = pd.concat(row_frames, ignore_index=True)
        k_all = all_rows["K"].to_numpy()
        dates = all_rows["game_date"].to_numpy().astype(str)
        pk_all = {a: np.vstack(pk_store[a]) for a in ("I3b", "I4")}
        pooled = {"n": int(len(all_rows)),
                  "label": "chronological fallback diagnostic",
                  "parity_note": "both arms homogeneous (p* form); "
                                 "no parity assertion needed beyond "
                                 "structure identity"}
        for a in ("I3b", "I4"):
            pooled[a] = {
                "mean_rps": float(all_rows["rps_" + a].mean()),
                "mean_logscore": float(all_rows["logscore_" + a].mean()),
                "logscore_floor_hit_rows": int(
                    all_rows["floorhit_" + a].sum()),
                "mean_mae_of_mean": float(all_rows["mae_" + a].mean()),
                "mean_milestone_brier": {
                    m: float(all_rows["mb%d_" % m + a].mean())
                    for m in MILESTONES},
            }
        d = (all_rows["rps_I4"].to_numpy()
             - all_rows["rps_I3b"].to_numpy())
        gate = rch.cluster_bootstrap(d, dates, n_boot=N_BOOT, seed=SEED)
        pooled["gate1"] = {
            "definition": "pooled paired count-RPS (I4 - I3b) 95% CI "
                          "entirely below 0",
            "estimate": gate["estimate"], "lo95": gate["lo95"],
            "hi95": gate["hi95"], "pass": bool(gate["hi95"] < 0.0)}
        pooled["paired"] = {
            "I4_vs_I3b_PRIMARY": {
                "comparison_id": "i4_card_source__vs__i3b_proxy",
                "slate_date_primary": gate,
                "mean_rps_I4": pooled["I4"]["mean_rps"],
                "mean_rps_I3b": pooled["I3b"]["mean_rps"]}}
        changed = int(sum(
            1 for px, rr in zip(all_rows["proxy_card"],
                                all_rows["rs_card"]) if px != rr))
        pooled["source"] = {
            "schedule_match": match,
            "changed_card_rows": changed,
            "changed_card_pct": 100.0 * changed / len(all_rows),
            "rs_fallback_rows": int(sum(
                1 for f in all_rows["rs_card_flag"]
                if f != "retrosheet"))}

        keep = list(all_rows.columns)
        all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
        pmf_cols = []
        pmf_data = []
        for a in ("I3b", "I4"):
            pmf_cols += ["pk%s_%02d" % (a, i) for i in range(K_MAX)]
            pmf_data.append(pk_all[a])
        pl.DataFrame(np.hstack(pmf_data),
                     schema=pmf_cols).write_parquet(out_dir
                                                    / "pmfs.parquet")
        key_hash = hashlib.sha256(";".join(sorted(
            "%s:%s" % (g, p) for g, p in zip(
                all_rows["game_pk"].astype(str),
                all_rows["pitcher"].astype(str)))).encode()).hexdigest()
        provenance = {
            "i4_contract": sha256_file(Path(contract_path)),
            "code_run_i4_card_source_2023": sha256_file(
                HERE / "run_i4_card_source_2023.py"),
            "code_retrosheet_cards": sha256_file(
                HERE / "retrosheet_cards.py"),
            "code_run_i3_opportunity_2023": sha256_file(
                HERE / "run_i3_opportunity_2023.py"),
            "kc_artifact_predictions_csv": sha256_file(
                Path(kc_preds_path)),
            "kc_artifact_pmfs_parquet": sha256_file(Path(kc_pmfs_path)),
            "i3_artifact_pmfs_parquet": sha256_file(Path(i3_pmfs_path)),
            "bf_artifact_predictions_csv": sha256_file(
                Path(bf_preds_path)),
            "bf_artifact_pmfs_parquet": sha256_file(Path(bf_pmfs_path)),
            "retrosheet_raw_2022": season_digest(
                rs_raw_root / "2022"),
            "retrosheet_raw_2023": season_digest(
                rs_raw_root / "2023"),
            "retrosheet_register": season_digest(rs_register_dir),
        }
        kc.validate_provenance(provenance)
        manifest = {
            "lane": "i4_card_source_2023",
            "status": "COMPLETE",
            "label": "chronological fallback diagnostic",
            "opportunity_contract": str(contract_path),
            "opportunity_contract_sha256":
                provenance["i4_contract"],
            "card_source": "Retrosheet previous-game starting slots "
                           "1..9 (start records; subs + non-batting "
                           "pitcher excluded); fallback = I3b proxy",
            "row_identity_hash_sha256": key_hash,
            "population": {"n_eval_total": pooled["n"]},
            "per_origin": per_origin,
            "pooled": pooled,
            "provenance": provenance,
            "notes": ("2023 DEVELOPMENTAL; diagnostic only; I3b "
                      "benchmark reproduced from saved artifacts "
                      "before scoring; chronology from Retrosheet "
                      "(date, game_number), never game_pk"),
        }
        (out_dir / "i4_card_source_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str),
            encoding="ascii")
        return manifest
    except RunFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - receipt then re-raise
        import traceback as _tb
        receipt = {"status": "MECHANICAL_FAILURE",
                   "stage": "run_diagnostic",
                   "error": "%s: %s" % (type(exc).__name__, exc),
                   "traceback": _tb.format_exc()}
        (out_dir / "failure_receipt.json").write_text(
            json.dumps(receipt, indent=2, default=str), encoding="ascii")
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--kc-preds", required=True)
    ap.add_argument("--kc-pmfs", required=True)
    ap.add_argument("--i3-pmfs", required=True)
    ap.add_argument("--bf-preds", required=True)
    ap.add_argument("--bf-pmfs", required=True)
    ap.add_argument("--rs-raw-root", required=True)
    ap.add_argument("--rs-register", required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    args = ap.parse_args(argv)

    from run_corrected_history_2023 import (MechanicalFailure,
                                            default_sources,
                                            verify_and_load)
    out_dir = Path(args.out)
    try:
        rch._require_temp_out(out_dir)
        contract = Path(args.contract)
        if not contract.is_file():
            raise RunFailure("missing frozen I4 contract")
        for p in (args.kc_preds, args.kc_pmfs, args.i3_pmfs,
                  args.bf_preds, args.bf_pmfs):
            if not Path(p).is_file():
                raise RunFailure("missing saved artifact: %s" % p)
        if not Path(args.rs_raw_root).is_dir():
            raise RunFailure("missing Retrosheet raw root")
        root = Path(args.data_root) if args.data_root else rch.REPO / "data"
        shas = {}
        for item in args.season_sha or []:
            y, d = item.split(":", 1)
            shas[int(y)] = d.lower()
        sources = default_sources(root, 2023, (2022,), shas)
        raw23 = verify_and_load(sources["savant_2023"])
        raw22 = verify_and_load(sources["savant_2022"])
        if sorted(rch.frame_years(raw23)) != [2023] \
                or sorted(rch.frame_years(raw22)) != [2022]:
            raise RunFailure("period violation")
        unified23 = rch._unified_pitches([raw23])
        unified22 = rch._unified_pitches([raw22])
        keys23, _ = rch.audit_identity(unified23)
        keys22, _ = rch.audit_identity(unified22)
        PA_COLUMNS = ["game_pk", "game_date", "pitcher", "batter",
                      "stand", "p_throws", "events", "at_bat_number"]
        pa23 = pak.build_pa_table(
            raw23.select(PA_COLUMNS),
            keys23.select(["game_pk",
                           pl.col("forecast_pitcher").alias("pitcher")]))
        pa22 = pak.build_pa_table(
            raw22.select(PA_COLUMNS),
            keys22.select(["game_pk",
                           pl.col("forecast_pitcher").alias("pitcher")]))
        manifest = run_diagnostic(
            pa23, pa22, keys23, raw23,
            Path(args.kc_preds), Path(args.kc_pmfs),
            Path(args.i3_pmfs), Path(args.bf_preds),
            Path(args.bf_pmfs), Path(args.rs_raw_root),
            Path(args.rs_register), out_dir, contract)
        manifest["inputs"] = {
            name: {"path": str(Path(s["path"]).resolve()),
                   "sha256": s["sha256"]}
            for name, s in sources.items()}
        kc.validate_provenance(
            {k: v["sha256"] for k, v in manifest["inputs"].items()})
        (out_dir / "i4_card_source_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps({"status": manifest["status"],
                          "gate1": manifest["pooled"]["gate1"],
                          "n": manifest["pooled"]["n"]}))
        return 0
    except (RunFailure, MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
