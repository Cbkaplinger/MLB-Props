"""BF bundle reconstruction (single frozen fit; development amendment A).

Uses the frozen 2024-transfer builder (build_frames_2024) - no extraction
drift. Fit rows: 2023 + 2024 (exclusive 2025-01-01); 2022 = feature
history (frozen deviation note in the builder). Fallback scalar derived
by the frozen derive_fallback_2022 (option-A amendment, documented).
NO origins, NO scoring, NO pilot outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
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
import run_corrected_history_2023 as rch  # noqa: E402
import run_i3_transfer_2024 as tr  # noqa: E402
import sklearn  # noqa: E402

UPPER = "2025-01-01"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        root = Path(args.data_root) if args.data_root else (
            Path(__file__).resolve().parents[2] / "data")
        raw = {}
        for y, sha in ((2022, rch.SAVANT_2022_SHA),
                       (2023, rch.SAVANT_2023_SHA),
                       (2024, "de78a1893aa21e305153f5594987f85b40e4bc"
                              "0cf572484e995a1416b3c49b33")):
            src = {"path": str(root_path(root, y)), "sha256": sha,
                   "label": "savant_%d" % y}
            rch.verify_and_load(src)  # verify hash before use
            raw[y] = pl.read_parquet(src["path"])
        fb = rch.derive_fallback_2022(raw[2022])
        frame23, frame24, _apps, hist_quar = tr.build_frames_2024(
            raw[2022], raw[2023], raw[2024], fb["mean_bf"])
        pop = {}
        for year, fr in (("2023", frame23), ("2024", frame24)):
            pdfy = fr.to_pandas()
            pa_ok = (pdfy["PA"] >= 1) & pdfy["PA"].notna()
            # CORRECTED (owner 2026-10-12): NO feature-completeness
            # filtering; frozen missingness = training-fitted median
            # imputation inside fit_hazard. Identity/target exclusions
            # only (PA>=1 per the frozen _season_frame).
            pop[year] = {"candidate": int(len(pdfy)),
                         "zero_or_null_bf": int((~pa_ok).sum()),
                         "eligible": int(pa_ok.sum()),
                         "rows_with_missing_features": int(
                             pdfy.loc[pa_ok, rch.CHALLENGER_FEATURES]
                             .isna().any(axis=1).sum()),
                         "missing_cells": int(sum(
                             int(pdfy.loc[pa_ok, c].isna().sum())
                             for c in rch.CHALLENGER_FEATURES)),
                         "entirely_missing_features": [
                             c for c in rch.CHALLENGER_FEATURES
                             if pdfy.loc[pa_ok, c].notna().sum() == 0],
                         "date_min": str(pdfy["game_date"].min()),
                         "date_max": str(pdfy["game_date"].max())}
        pdf = (pl.concat([frame23, frame24], how="diagonal_relaxed")
               .to_pandas())
        pdf["game_date"] = pdf["game_date"].astype(str)
        eligible = pdf[(pdf["game_date"] >= "2022-01-01")
                       & (pdf["game_date"] < UPPER)
                       & (pdf["PA"] >= 1) & pdf["PA"].notna()]
        # all-missing-column guard: SimpleImputer default would drop an
        # entirely empty column and silently change the feature schema.
        empty_cols = [c for c in rch.CHALLENGER_FEATURES
                      if eligible[c].notna().sum() == 0]
        if empty_cols:
            raise rch.MechanicalFailure(
                "entirely missing features (STOP): %s" % empty_cols)
        feats = eligible[rch.CHALLENGER_FEATURES].to_numpy(dtype=float)
        ns = eligible["PA"].to_numpy(dtype=int)
        bundle = bfd_fit(feats, ns)
        risk_rows, y = __import__("bf_distribution").build_risk_rows(ns)
        bundle_path = out_dir / "bf_bundle.pkl"
        with open(bundle_path, "wb") as fh:
            pickle.dump({"model": bundle["model"],
                         "preprocess": bundle["preprocess"],
                         "feature_names": rch.CHALLENGER_FEATURES,
                         "l2_c": bundle["l2_c"]}, fh)
        # fit-to-reload reference probe: scored by the IN-MEMORY fitted
        # object at fit time, persisted for fresh-process comparison.
        probe = np.clip(np.random.default_rng(20261012).normal(
            0.0, 1.0, size=(50, len(rch.CHALLENGER_FEATURES))), -4, 4)
        import bf_distribution as bfd
        std_probe = bfd._apply_preprocess(bundle["preprocess"], probe)
        probe_hazards = []
        for r in range(len(probe)):
            hz = np.empty(36)
            for j in range(36):
                row = np.concatenate([np.eye(36)[j], std_probe[r]])
                hz[j] = bundle["model"].predict_proba(
                    row.reshape(1, -1))[0, 1]
            probe_hazards.append(bfd.hazard_to_pmf(hz))
        probe_hazards = np.array(probe_hazards)
        probe_pmfs = bfd.predict_pmf(bundle, probe)
        np.save(out_dir / "probe_pmfs_inmemory.npy", probe_pmfs)
        np.save(out_dir / "probe_hazards_inmemory.npy", probe_hazards)
        n_risk = int(len(bfd.build_risk_rows(ns)[0]))
        manifest = {
            "amendment": "option-A development reconstruction (owner "
                         "2026-10-12): fallback estimated from authorized "
                         "2022 training data; NOT historical-transfer "
                         "reproduction; 2026 pilot only",
            "eligibility": {
                "authorized_seasons": [2022, 2023, 2024],
                "inclusive_lower": "first eligible 2023 start (2022 rows "
                                   "not constructible per frozen builder "
                                   "deviation note)",
                "exclusive_upper": UPPER,
                "n_fit_starts": int(eligible.shape[0]),
                "n_risk_rows": n_risk,
                "feature_history_floor": "2022 (earliest authorized "
                                         "source; appearance histories "
                                         "only)",
            },
            "fallback": {"mean_bf": fb["mean_bf"], "n": fb["n"],
                         "bf_sum": fb["bf_sum"],
                         "derivation": "derive_fallback_2022 (frozen)",
                         "source": "2022 raw, sha-verified"},
            "frozen_recipe": {
                "features": list(rch.CHALLENGER_FEATURES),
                "target": "start-by-index termination (build_risk_rows)",
                "l2_c": 1.0, "max_iter": 5000,
                "preprocessing": "train-only median impute + standardize",
            },
            "convergence": int(bundle["model"].n_iter_[-1]),
            "hashes": {
                "bundle": sha256_file(bundle_path),
                "savant_2022": rch.SAVANT_2022_SHA,
                "savant_2023": rch.SAVANT_2023_SHA,
                "savant_2024": "de78a1893aa21e305153f5594987f85b40e4bc"
                               "0cf572484e995a1416b3c49b33",
                "runner": sha256_file(HERE / "run_bf_reconstruct_2026.py"),
            },
            "versions": {"python": sys.version.split()[0],
                         "sklearn": sklearn.__version__,
                         "numpy": np.__version__,
                         "polars": pl.__version__},
            "outcome_access": "training labels 2022-2024 only; pilot "
                              "outcomes NOT accessed",
            "population_by_year": pop,
            "tail_convention": "37 categories: P(N=1)..P(N=36) exact + "
                               "P(N>=37) overflow (absorbing bucket 36); "
                               "hazards mapped via hazard_to_pmf",
            "deviation_note": "frozen builder run_i3_transfer_2024.py "
                              "build_frames_2024 docstring: '2022 "
                              "hazard-fit rows are NOT constructible: "
                              "the frozen prior-year team-rate chain "
                              "requires 2021 batting rows (absent)... "
                              "hazard-fit rows = 2023 + 2024-to-origin; "
                              "2022 remains available through "
                              "appearance histories only'",
            "created": str(datetime.now(timezone.utc).isoformat()),
        }
        (out_dir / "bundle_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps({"n_fit_starts": int(eligible.shape[0]),
                          "n_risk_rows": n_risk,
                          "fallback_mean_bf": fb["mean_bf"],
                          "converged_iter": int(
                              bundle["model"].n_iter_[-1])}, indent=1))
        print("WROTE %s" % out_dir)
        return 0
    except (rch.MechanicalFailure, Exception) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc))
        return 1


def root_path(root, y):
    return root / "Savant-Data" / "regular" / str(y) / (
        "statcast_%d_regular.parquet" % y)


def bfd_fit(feats, ns):
    return __import__("bf_distribution").fit_hazard(
        feats, ns, list(__import__("run_corrected_history_2023",
                                    fromlist=["CHALLENGER_FEATURES"])
                        .CHALLENGER_FEATURES))


if __name__ == "__main__":
    raise SystemExit(main())
