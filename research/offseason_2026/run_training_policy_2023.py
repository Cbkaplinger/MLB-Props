"""BF training-policy comparison: frozen vs expanding (ONE scored run).

Implements `research/offseason_2026/expanding-training-prereg.md`
(sha af2f4bf29350eca29c3ffdb1c1a1150bd063a5c6be594a1265ef0e511b9c5f00).

Arms (identical eval rows, identical features/support/scoring):
  A: frozen pre-04-15 training (n=414) for every origin - must
     reproduce the original diagnostic PMFs within tolerance.
  B: expanding strictly-pre-origin training (game_date < origin).

April arms use identical inputs -> fitted separately, asserted equal,
reported once. Primary gate: pooled paired RPS (B-A) date-clustered CI
entirely below zero. BF>=9 and q-gap = secondary diagnostics only.

No calibration, interactions, LightGBM, 2024+ inputs, promotion claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
import run_corrected_history_2023 as rch  # noqa: E402
from run_bf_distribution_2023 import (  # noqa: E402
    APRIL_ORIGIN, build_frames, DEFAULT_ORIGINS, DEFAULT_FINAL)


class RunFailure(RuntimeError):
    pass


MIN_TRAIN_ROWS = 50
MIN_TRAIN_SHORT_EVENTS = 1
REPRO_TOL = 1e-8
SEED = 20261001
N_BOOT = 2000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def batch_predict(bundle, feats: np.ndarray) -> np.ndarray:
    """Vectorized PMF prediction (numerically identical to per-row path)."""
    std = bfd._apply_preprocess(bundle["preprocess"], feats)
    model = bundle["model"]
    n_ev = len(std)
    idx = np.repeat(np.arange(n_ev), bfd.N_MAX)
    one_hot = np.tile(np.eye(bfd.N_MAX), (n_ev, 1))
    design = np.hstack([one_hot, std[idx]])
    hazards = model.predict_proba(design)[:, 1].reshape(n_ev, bfd.N_MAX)
    out = np.empty((n_ev, bfd.N_CATEGORIES))
    for r in range(n_ev):
        out[r] = bfd.hazard_to_pmf(hazards[r])
    return out


def train_mask_A(assigned: pd.DataFrame, origin_ts) -> pd.Series:
    """Arm A: frozen pre-04-15 rows only (excludes ALL eval rows)."""
    return (assigned["origin"].isna()) & (assigned["game_date"] < origin_ts)


def train_mask_B(assigned: pd.DataFrame, origin_ts) -> pd.Series:
    """Arm B: expanding, strictly pre-origin (no eval-window exclusion)."""
    return assigned["game_date"] < origin_ts


def fit_arm(train_pdf: pd.DataFrame) -> dict:
    n = len(train_pdf)
    short = int((train_pdf["PA"].to_numpy(dtype=int) < 9).sum())
    if n < MIN_TRAIN_ROWS or short < MIN_TRAIN_SHORT_EVENTS:
        raise RunFailure(
            "training gate failed: n=%d short_events=%d (min %d/%d)"
            % (n, short, MIN_TRAIN_ROWS, MIN_TRAIN_SHORT_EVENTS))
    return bfd.fit_hazard(
        train_pdf[rch.CHALLENGER_FEATURES].to_numpy(dtype=float),
        train_pdf["PA"].to_numpy(dtype=int),
        list(rch.CHALLENGER_FEATURES))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--orig-pmfs", required=True,
                    help="original run pmfs.parquet for arm-A reproduction")
    ap.add_argument("--orig-preds", required=True,
                    help="original run predictions.csv for row identity")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    ap.add_argument("--fallback-mean", type=float, required=True)
    ap.add_argument("--fallback-source", required=True)
    ap.add_argument("--fallback-cutoff", required=True)
    args = ap.parse_args(argv)

    from run_corrected_history_2023 import (MechanicalFailure,
                                            default_sources, verify_and_load)

    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        prereg = Path(args.prereg)
        if not prereg.is_file():
            raise RunFailure("missing preregistration file")
        prereg_sha = sha256_file(prereg)
        root = Path(args.data_root) if args.data_root else rch.REPO / "data"
        shas = {}
        for item in args.season_sha or []:
            y, d = item.split(":", 1)
            shas[int(y)] = d.lower()
        sources = default_sources(root, 2023, (2022,), shas)
        pitches = {}
        for name, spec in sources.items():
            frame = verify_and_load(spec)
            year = int(str(name).split("_")[1])
            if sorted(rch.frame_years(frame)) != [year]:
                raise RunFailure("period violation in %s" % name)
            pitches[year] = rch._unified_pitches([frame])

        frame, appearances, pop = build_frames(
            pitches[2023], pitches[2022], args.fallback_mean)
        pdf = frame.to_pandas()
        assigned = rch.assign_origins(pdf, DEFAULT_ORIGINS, DEFAULT_FINAL)

        orig_pmfs = pl.read_parquet(args.orig_pmfs).to_numpy()
        orig_preds = pl.read_csv(args.orig_preds)
        orig_keys = list(zip(orig_preds["origin"].to_list(),
                             orig_preds["game_pk"].to_list(),
                             orig_preds["pitcher"].to_list(),
                             orig_preds["game_date"].to_list()))
        # within-game row order is NOT deterministic across runs (polars
        # join ordering) -> align by row KEY, not position
        orig_key_to_idx = {k: i for i, k in enumerate(orig_keys)}
        if len(orig_key_to_idx) != len(orig_keys):
            raise RunFailure("duplicate keys in original predictions.csv")

        per_origin = []
        all_rows = []
        all_pmfs = {}
        repro_max = 0.0
        covered = 0
        for origin in DEFAULT_ORIGINS:
            ts = pd.Timestamp(origin)
            ev = assigned[assigned["origin"] == origin]
            if len(ev) == 0:
                raise RunFailure("no eval rows for %s" % origin)
            trainA = assigned[train_mask_A(assigned, ts)]
            trainB = assigned[train_mask_B(assigned, ts)]
            y = ev["PA"].to_numpy(dtype=int)
            feats = ev[rch.CHALLENGER_FEATURES].to_numpy(dtype=float)

            bundleA = fit_arm(trainA)
            pmfsA = batch_predict(bundleA, feats)
            if origin == APRIL_ORIGIN:
                bundleB_apr = fit_arm(trainB)
                pmfsB_apr = batch_predict(bundleB_apr, feats)
                coincide = float(np.abs(pmfsA - pmfsB_apr).max())
                if coincide > 1e-10:
                    raise RunFailure(
                        "April arms do not coincide: max diff %g" % coincide)
                bundleB = bundleB_apr
                pmfsB = pmfsB_apr
            else:
                bundleB = fit_arm(trainB)
                pmfsB = batch_predict(bundleB, feats)

            keys = list(zip([origin] * len(ev),
                            ev["game_pk"].tolist(),
                            ev["pitcher"].tolist(),
                            ev["game_date"].astype(str).tolist()))
            try:
                idxs = [orig_key_to_idx[k] for k in keys]
            except KeyError as missing:
                raise RunFailure(
                    "row-identity mismatch for %s: key %s not in original"
                    % (origin, missing.args[0]))
            block = sorted(idxs)
            if block != list(range(covered, covered + len(ev))):
                raise RunFailure(
                    "row-identity block mismatch for %s" % origin)
            covered += len(ev)
            rep = float(np.abs(
                pmfsA - orig_pmfs[np.asarray(idxs)]).max())
            repro_max = max(repro_max, rep)
            if repro_max > REPRO_TOL:
                raise RunFailure(
                    "arm A reproduction exceeded tolerance: %g > %g"
                    % (repro_max, REPRO_TOL))

            rpsA = np.array([bfd.rps_score(p, int(k))
                             for p, k in zip(pmfsA, y)])
            rpsB = np.array([bfd.rps_score(p, int(k))
                             for p, k in zip(pmfsB, y)])
            nllA = np.array([bfd.count_nll(p, int(k))[0]
                             for p, k in zip(pmfsA, y)])
            nllB = np.array([bfd.count_nll(p, int(k))[0]
                             for p, k in zip(pmfsB, y)])
            qA = pmfsA[:, :8].sum(axis=1)
            qB = pmfsB[:, :8].sum(axis=1)
            all_pmfs[origin] = (pmfsA, pmfsB)
            rows = pd.DataFrame({
                "origin": origin,
                "game_pk": ev["game_pk"].to_numpy(),
                "pitcher": ev["pitcher"].to_numpy(),
                "game_date": ev["game_date"].astype(str).to_numpy(),
                "PA": y,
                "q_A": qA, "q_B": qB,
                "rps_A": rpsA, "rps_B": rpsB,
                "nll_A": nllA, "nll_B": nllB,
                "armA_repro_max_diff": rep,
            })
            for f in rch.CHALLENGER_FEATURES:
                rows["feat_" + f] = ev[f].to_numpy()
            all_rows.append(rows)
            per_origin.append({
                "origin": origin,
                "n_eval": int(len(ev)),
                "n_train_A": int(len(trainA)),
                "n_train_B": int(len(trainB)),
                "train_B_short_events": int(
                    (trainB["PA"].to_numpy(dtype=int) < 9).sum()),
                "train_A_short_events": int(
                    (trainA["PA"].to_numpy(dtype=int) < 9).sum()),
                "armA_repro_max_diff": rep,
            })

        all_rows = pd.concat(all_rows, ignore_index=True)
        if covered != len(orig_keys):
            raise RunFailure("original rows not fully covered: %d/%d"
                             % (covered, len(orig_keys)))
        dates = all_rows["game_date"].to_numpy().astype(str)
        d_rps = all_rows["rps_B"].to_numpy() - all_rows["rps_A"].to_numpy()
        pooled = {
            "n": int(len(all_rows)),
            "mean_rps_A": float(all_rows["rps_A"].mean()),
            "mean_rps_B": float(all_rows["rps_B"].mean()),
            "mean_nll_A": float(all_rows["nll_A"].mean()),
            "mean_nll_B": float(all_rows["nll_B"].mean()),
            "paired": {
                "comparison_id": "bf_expand_v1__vs__bf_frozen_v1",
                "slate_date_primary": rch.cluster_bootstrap(d_rps, dates),
                "pitcher_sensitivity": rch.cluster_bootstrap(
                    d_rps, all_rows["pitcher"].to_numpy().astype(str)),
            },
            "armA_reproduction_max_diff": repro_max,
            "armA_reproduction_tolerance": REPRO_TOL,
        }
        ge9 = all_rows["PA"] >= 9
        d9 = all_rows.loc[ge9, "rps_B"].to_numpy() \
            - all_rows.loc[ge9, "rps_A"].to_numpy()
        pooled["bf_ge9_secondary"] = {
            "n": int(ge9.sum()),
            "mean_rps_A": float(all_rows.loc[ge9, "rps_A"].mean()),
            "mean_rps_B": float(all_rows.loc[ge9, "rps_B"].mean()),
            "paired": rch.cluster_bootstrap(d9, dates[ge9.to_numpy()]),
            "status": "prespecified secondary diagnostic (exploratory)",
        }
        qgaps = []
        for origin in DEFAULT_ORIGINS:
            sub = all_rows[all_rows["origin"] == origin]
            yv = (sub["PA"].to_numpy() < 9).astype(float)
            for arm, qcol in (("A", "q_A"), ("B", "q_B")):
                qgaps.append({
                    "origin": origin, "arm": arm,
                    "mean_q": float(sub[qcol].mean()),
                    "event_freq": float(yv.mean()),
                    "q_gap": float(sub[qcol].mean() - yv.mean()),
                    "n": int(len(sub)), "events": int(yv.sum())})
        pooled["q_gap_secondary"] = {
            "definition": "q_gap(origin) = mean q - observed event freq",
            "status": "prespecified secondary diagnostic (exploratory)",
            "rows": qgaps}
        gate1 = pooled["paired"]["slate_date_primary"]
        pooled["gate1"] = {
            "definition": "pooled paired RPS (B-A) 95% CI entirely below 0",
            "estimate": gate1["estimate"], "lo95": gate1["lo95"],
            "hi95": gate1["hi95"],
            "pass": bool(gate1["hi95"] < 0.0)}

        manifest = {
            "lane": "bf_training_policy_2023",
            "status": "COMPLETE",
            "preregistration": str(prereg),
            "preregistration_sha256": prereg_sha,
            "origins": list(DEFAULT_ORIGINS),
            "final_date": DEFAULT_FINAL,
            "population": pop,
            "per_origin": per_origin,
            "pooled": pooled,
            "code": {p.name: sha256_file(p) for p in [
                HERE / "run_training_policy_2023.py",
                HERE / "bf_distribution.py",
                HERE / "run_corrected_history_2023.py",
                HERE / "run_bf_distribution_2023.py"]},
            "inputs": {name: {"path": str(Path(s["path"]).resolve()),
                              "sha256": s["sha256"]}
                       for name, s in sources.items()},
            "fallback": {"mean_bf": args.fallback_mean,
                         "source": args.fallback_source,
                         "cutoff": args.fallback_cutoff},
        }
        (out_dir / "training_policy_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        keep = list(all_rows.columns)
        all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
        pmf_cols = ["pmfA_%02d" % i for i in range(bfd.N_CATEGORIES)] + \
                   ["pmfB_%02d" % i for i in range(bfd.N_CATEGORIES)]
        pl.DataFrame(np.hstack([np.vstack([all_pmfs[o][0] for o in
                                           DEFAULT_ORIGINS]),
                                np.vstack([all_pmfs[o][1] for o in
                                           DEFAULT_ORIGINS])]),
                     schema=pmf_cols).write_parquet(out_dir / "pmfs.parquet")
        print(json.dumps({"status": "COMPLETE",
                          "gate1": pooled["gate1"],
                          "armA_repro_max_diff": repro_max,
                          "mean_rps_A": pooled["mean_rps_A"],
                          "mean_rps_B": pooled["mean_rps_B"]}))
        return 0
    except (RunFailure, MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
