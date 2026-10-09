"""I5 deep-tail challenger scored runner (ONE run, 2023).

Implements `research/offseason_2026/i5-tail-challenger.md` (frozen
2026-10-08, sha in the manifest). Chronological fallback diagnostic;
audit-informed developmental selection; no production claim.

Arm I5-tail: per row, take the saved 37-category arm-B BF PMF and
reassign the overflow mass P(N>=37) into the FIXED receiving interval
[30, 33] with the frozen per-origin strictly-pre-origin empirical
weights; extend (no mass beyond 33); combine with the row's CANONICAL
I3b p_star (HELD FIXED - only the BF PMF changes). Benchmark I3b
reproduced from saved PMFs.

Primary: paired count-RPS (I5 - I3b), date-clustered bootstrap 2000 /
seed 20261001, CI entirely below 0 = pass.
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

import bf_distribution as bfd  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402

K_MAX = 24
SEED = 20261001
N_BOOT = 2000
ORIGINS = (date(2023, 4, 15), date(2023, 7, 1), date(2023, 8, 1),
           date(2023, 9, 1))
ALIGN_TOL = 1e-8
MILESTONES = (6, 7, 8, 9, 10, 12)
RECEIVE_LO, RECEIVE_HI = 30, 33
# frozen per-origin weights (strictly pre-origin training counts,
# normalized at use time): N=30,31,32,33
WEIGHTS = {
    "2023-04-15": [4, 0, 0, 0],
    "2023-07-01": [12, 9, 7, 2],
    "2023-08-01": [19, 10, 9, 2],
    "2023-09-01": [30, 13, 10, 4],
}


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_diagnostic(kpreds_path: Path, i3_preds_path: Path,
                   i3_pmfs_path: Path, bf_preds_path: Path,
                   bf_pmfs_path: Path, out_dir: Path,
                   contract_path: Path) -> dict:
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        i3 = pl.read_csv(i3_preds_path).with_row_index("i3_row")
        kpreds = pl.read_csv(kpreds_path)
        # canonical identity: I3 preds keys == K-count preds keys
        k1 = set(zip(kpreds["game_pk"].to_list(),
                     kpreds["pitcher"].to_list()))
        k2 = set(zip(i3["game_pk"].to_list(), i3["pitcher"].to_list()))
        if k1 != k2 or len(kpreds) != len(i3):
            raise RunFailure("canonical row identity mismatch "
                             "(K-count vs I3 artifacts)")
        n = i3.height
        pkI3b = pl.read_parquet(i3_pmfs_path).select(
            ["pkI3b_%02d" % i for i in range(K_MAX)]).to_numpy()
        p_star = i3["p_star"].to_numpy()
        bf_pmfs = pl.read_parquet(bf_pmfs_path).to_numpy()
        pmB37 = bf_pmfs[:, 37:][i3["kc_row"].to_numpy()]

        # benchmark reproduction: saved I3b == combine(ext60, p_star)
        ext60 = np.array([kc.bf_pmf_from_37(pmB37[i]) for i in range(n)])
        reps = np.array([kc.combine_count(ext60[i], p_star[i])
                         for i in range(n)])
        rep = float(np.abs(reps - pkI3b).max())
        if rep > ALIGN_TOL:
            raise RunFailure("I3b reproduction failed: %g" % rep)

        N = i3["PA"].to_numpy()
        K = i3["K"].to_numpy()
        dates = i3["game_date"].to_numpy().astype(str)
        O = i3["origin"].to_numpy().astype(str)

        pk_store = {"I3b": [], "I5": []}
        row_frames = []
        per_origin = []
        for origin in ORIGINS:
            m = O == str(origin)
            if not m.any():
                raise RunFailure("no eval rows for %s" % origin)
            w = np.asarray(WEIGHTS[str(origin)], dtype=float)
            i5_37 = np.array([kc.reassign_overflow(pmB37[i],
                                                   RECEIVE_LO,
                                                   RECEIVE_HI, w)
                              for i in np.where(m)[0]])
            ext60_i5 = np.array([kc.bf_pmf_from_37(i5_37[j])
                                 for j in range(int(m.sum()))])
            pk_i5 = np.array([kc.combine_count(ext60_i5[j], p_star[m][j])
                              for j in range(int(m.sum()))])
            pk_i3b = pkI3b[m]
            pk_store["I3b"].append(pk_i3b)
            pk_store["I5"].append(pk_i5)
            en_i5 = np.array([kc.expected_bf(ext60_i5[j])
                              for j in range(int(m.sum()))])
            en_i3 = np.array([kc.expected_bf(ext60[j])
                              for j in np.where(m)[0]])
            e_k = {"I3b": p_star[m] * en_i3,
                   "I5": p_star[m] * en_i5}
            sc = {"I3b": rkc._row_scores(pk_i3b, K[m], e_k["I3b"]),
                  "I5": rkc._row_scores(pk_i5, K[m], e_k["I5"])}
            # BF-side secondaries (37-category support)
            bf_rps_i5 = np.array([bfd.rps_score(i5_37[j], int(N[m][j]))
                                  for j in range(int(m.sum()))])
            rows = pd.DataFrame({
                "origin": str(origin),
                "kc_row": i3["kc_row"].to_numpy()[m],
                "i3_row": i3["i3_row"].to_numpy()[m],
                "game_pk": i3["game_pk"].to_numpy()[m],
                "pitcher": i3["pitcher"].to_numpy()[m],
                "game_date": dates[m],
                "PA": N[m],
                "K": K[m],
                "p_star": p_star[m],
                "EN60_I5": en_i5,
            })
            for a in ("I3b", "I5"):
                rows["rps_" + a] = sc[a]["rps"]
                rows["logscore_" + a] = sc[a]["logscore"]
                rows["floorhit_" + a] = sc[a]["floor_hit"].astype(int)
                rows["mae_" + a] = sc[a]["mae"]
                rows["mean_" + a] = e_k[a]
                for mm in MILESTONES:
                    pk_arm = pk_i3b if a == "I3b" else pk_i5
                    rows["mb%d_" % mm + a] = np.array(
                        [kc.milestone_brier(pk_arm[j], int(K[m][j]),
                                            MILESTONES)["ge%d" % mm]
                         for j in range(int(m.sum()))])
            rows["bf_rps_I5"] = bf_rps_i5
            rows["bf_p_lt9_I5"] = i5_37[:, :8].sum(axis=1)
            for mm in (10, 12):
                rows["ge%d_I5" % mm] = np.array(
                    [kc.exceedance(pk_i5[j], mm)
                     for j in range(int(m.sum()))])
                rows["ge%d_I3b" % mm] = np.array(
                    [kc.exceedance(pk_i3b[j], mm)
                     for j in range(int(m.sum()))])
            row_frames.append(rows)
            per_origin.append({
                "origin": str(origin),
                "n_eval": int(m.sum()),
                "weights_30_33": WEIGHTS[str(origin)],
                "bf_mean_bias_I3b": float(
                    en_i3.mean() - N[m].mean()),
                "bf_mean_bias_I5": float(en_i5.mean() - N[m].mean()),
                "k_mean_bias_I3b": float(e_k["I3b"].mean() - K[m].mean()),
                "k_mean_bias_I5": float(e_k["I5"].mean() - K[m].mean()),
                "bf_p_lt9_I5": float(i5_37[:, :8].sum(axis=1).mean()),
                "bf_p_lt9_obs": float((N[m] < 9).mean()),
                "arm_means": {a: {
                    "mean_rps": float(sc[a]["rps"].mean()),
                    "mean_logscore": float(sc[a]["logscore"].mean()),
                    "floor_hit_rows": int(sc[a]["floor_hit"].sum()),
                    "mean_milestone_brier": {
                        mm: float(rows["mb%d_" % mm + a].mean())
                        for mm in MILESTONES}} for a in ("I3b", "I5")},
                "bf_rps_I5_mean": float(bf_rps_i5.mean()),
            })

        all_rows = pd.concat(row_frames, ignore_index=True)
        k_all = all_rows["K"].to_numpy()
        pk_all = {a: np.vstack(pk_store[a]) for a in ("I3b", "I5")}
        pooled = {"n": int(len(all_rows)),
                  "label": "chronological fallback diagnostic",
                  "p_star": "canonical I3b p_star HELD FIXED per row"}
        for a in ("I3b", "I5"):
            pooled[a] = {
                "mean_rps": float(all_rows["rps_" + a].mean()),
                "mean_logscore": float(all_rows["logscore_" + a].mean()),
                "logscore_floor_hit_rows": int(
                    all_rows["floorhit_" + a].sum()),
                "mean_mae_of_mean": float(all_rows["mae_" + a].mean()),
                "mean_milestone_brier": {
                    mm: float(all_rows["mb%d_" % mm + a].mean())
                    for mm in MILESTONES},
                "mean_ladder": {mm: float(np.mean(
                    [kc.exceedance(pk_all[a][i], mm)
                     for i in range(len(all_rows))]))
                    for mm in (6, 8, 10, 12)},
            }
        d = (all_rows["rps_I5"].to_numpy()
             - all_rows["rps_I3b"].to_numpy())
        gate = rch.cluster_bootstrap(d, dates, n_boot=N_BOOT, seed=SEED)
        pooled["gate1"] = {
            "definition": "pooled paired count-RPS (I5 - I3b) 95% CI "
                          "entirely below 0",
            "estimate": gate["estimate"], "lo95": gate["lo95"],
            "hi95": gate["hi95"], "pass": bool(gate["hi95"] < 0.0)}
        pooled["paired"] = {
            "I5_vs_I3b_PRIMARY": {
                "comparison_id": "i5_tail__vs__i3b",
                "slate_date_primary": gate,
                "mean_rps_I5": pooled["I5"]["mean_rps"],
                "mean_rps_I3b": pooled["I3b"]["mean_rps"]}}
        # BF-side secondary: bf-rps (I5 37-PMF vs actual N; the I3b
        # bf-side reference is the saved arm-B rps_B via kc_row->row)
        pooled["bf_secondary"] = {
            "bf_rps_I5_pooled": float(all_rows["bf_rps_I5"].mean()),
            "bf_mean_bias_signed": "bias = predicted - actual "
                                   "(positive = overprediction)",
            "bf_mean_bias_pooled": float(
                all_rows["EN60_I5"].mean() - all_rows["PA"].mean()),
            "short_outing_I5_p_lt9": float(
                all_rows["bf_p_lt9_I5"].mean()),
            "short_outing_obs": float((all_rows["PA"] < 9).mean()),
        }
        # K>=10/12 absolute probability changes + reliability
        rel = {}
        for mm in (10, 12):
            pred5 = float(all_rows["ge%d_I5" % mm].mean())
            pred3 = float(all_rows["ge%d_I3b" % mm].mean())
            obs = float((k_all >= mm).mean())
            ev = int((k_all >= mm).sum())
            rel["ge%d" % mm] = {
                "pred_I5": pred5, "pred_I3b": pred3, "observed": obs,
                "events": ev,
                "abs_change_I5_vs_I3b": pred5 - pred3,
                "reliability_I5": pred5 - obs,
                "reliability_I3b": pred3 - obs}
        pooled["tail_secondary"] = rel

        keep = list(all_rows.columns)
        all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
        pmf_cols = []
        pmf_data = []
        for a in ("I3b", "I5"):
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
            "i5_contract": sha256_file(Path(contract_path)),
            "code_run_i5_tail_2023": sha256_file(
                HERE / "run_i5_tail_2023.py"),
            "code_kcount_combiner": sha256_file(
                HERE / "kcount_combiner.py"),
            "i3_artifact_predictions_csv": sha256_file(
                Path(i3_preds_path)),
            "i3_artifact_pmfs_parquet": sha256_file(
                Path(i3_pmfs_path)),
            "kc_artifact_predictions_csv": sha256_file(
                Path(kpreds_path)),
            "bf_artifact_pmfs_parquet": sha256_file(Path(bf_pmfs_path)),
            "bf_artifact_predictions_csv": sha256_file(
                Path(bf_preds_path)),
        }
        kc.validate_provenance(provenance)
        manifest = {
            "lane": "i5_tail_2023",
            "status": "COMPLETE",
            "label": "chronological fallback diagnostic; audit-informed "
                     "developmental selection",
            "opportunity_contract": str(contract_path),
            "opportunity_contract_sha256":
                provenance["i5_contract"],
            "row_identity_hash_sha256": key_hash,
            "population": {"n_eval_total": pooled["n"]},
            "per_origin": per_origin,
            "pooled": pooled,
            "provenance": provenance,
            "notes": ("I3b p_star HELD FIXED per row (only the BF PMF "
                      "changes); receiving interval 30..33 selected "
                      "during development; per-origin weights use only "
                      "strict-pre-origin counts; April has ONE "
                      "qualifying training event; body mass 34..36 "
                      "retained"),
        }
        (out_dir / "i5_tail_manifest.json").write_text(
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
    ap.add_argument("--i3-preds", required=True)
    ap.add_argument("--i3-pmfs", required=True)
    ap.add_argument("--bf-preds", required=True)
    ap.add_argument("--bf-pmfs", required=True)
    args = ap.parse_args(argv)
    try:
        out_dir = Path(args.out)
        rch._require_temp_out(out_dir)
        for p in (args.contract, args.kc_preds, args.i3_preds,
                  args.i3_pmfs, args.bf_preds, args.bf_pmfs):
            if not Path(p).is_file():
                raise RunFailure("missing input: %s" % p)
        manifest = run_diagnostic(
            Path(args.kc_preds), Path(args.i3_preds),
            Path(args.i3_pmfs), Path(args.bf_preds),
            Path(args.bf_pmfs), out_dir, Path(args.contract))
        print(json.dumps({"status": manifest["status"],
                          "gate1": manifest["pooled"]["gate1"],
                          "n": manifest["pooled"]["n"]}))
        return 0
    except RunFailure as exc:
        print("RUN RunFailure: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
