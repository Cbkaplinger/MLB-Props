"""Cohort-aware execution mode for the BF A/B scoring path.

Extends the scoring path WITHOUT modifying any frozen file:
  - run_bf_ab_score_v2.py (vendored at b2fef02, blob sha256
    6b8cecf2a2463463d98e94e84b0bdab146d55cb6d29382c4955eb4cdb24bc4a)
    hardcodes the pilot cohort size in
    `assert j.height == n == A.shape[0] == B.shape[0] == 134`;
  - run_bf_ab_score_v3.py (canonical historical pilot scorer) is left
    byte-identical and keeps its exact historical behavior.

This module generalizes the cohort gate: the expected row population is
validated against a PINNED row-key manifest file (n + exact key set +
cutoffs) instead of the hardcoded 134, so a future non-134 cohort (e.g.
the registered full-season cohort) can be scored after the owner pins a
manifest. The metric and bootstrap code below is copied VERBATIM from
the vendored v2 compute_stats (same kc.count_rps, same slate-date
bootstrap, seed 20261001, same secondaries, same keying); the ONLY
semantic change is the cohort gate. All fail-loud checks are preserved
and extended: unique keys, identical arm populations, PMF validity
(24 buckets, nonnegative finite, rows sum to 1 within 1e-9), zero
unmatched label rows, and manifest/payload key-set equality.

Validation mode (no --data-root) touches NO outcomes and works on any
seal-dir payload. Score mode performs the gated realized-K join exactly
as the canonical scorer does; 2026 outcome scoring remains forbidden
until the owner seals the payload.

Lineage: b2fef02 (vendored v2) -> this file (additive).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent

V2_PIN_SHA256 = ("6b8cecf24a2463463d98e94e84b0bdab146d55cb6d29382c4955eb"
                 "4cdb24bc4a")
# NOTE: the b2fef02 commit message and EXECUTION_MANIFEST_2026.json v2
# record this pin as "6b8cecf2a246...b24bc4a" - a 63-character
# transcription (one hex digit dropped after "6b8cecf2"). The true
# sha256 of the vendored file, the executed v2 archive
# (bf-ab-score-2026-v2/runner_executed_v2_archive.py), and the
# archived-scoring-sources copy are all the 64-character hash above
# (three-way byte identity verified 2026-10-14); content provenance is
# intact, only the recorded pin string was mistyped.


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_lf_normalized(path: Path) -> str:
    """sha256 of the file with CRLF normalized to LF (the committed blob
    content under core.autocrlf; documented seal-manifest precedent)."""
    raw = Path(path).read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def verify_vendored_v2() -> dict:
    """Fail loud if the imported v2 module is not the pinned vendored
    blob (LF-normalized content hash)."""
    import run_bf_ab_score_v2 as s2
    got = sha256_lf_normalized(Path(s2.__file__).resolve())
    ok = got == V2_PIN_SHA256
    if not ok:
        raise SystemExit(
            "COHORT-SCORER BLOCKER: vendored v2 hash mismatch: %s vs pin %s"
            % (got, V2_PIN_SHA256))
    return {"run_bf_ab_score_v2_sha256_lf": got, "matches_pin": ok}


def load_manifest(path: Path) -> dict:
    man = json.loads(Path(path).read_text(encoding="ascii"))
    for field in ("manifest_id", "row_keys", "n_rows"):
        if field not in man:
            raise SystemExit("manifest missing field %r: %s" % (field, path))
    if man["n_rows"] != len(man["row_keys"]):
        raise SystemExit("manifest n_rows != len(row_keys): %s" % path)
    return man


def validate_payload(seal_dir: Path, manifest: dict) -> dict:
    """Manifest-pinned cohort validation (outcome-free, fail-loud).

    Checks (extended from the canonical hard-coded checks):
      1. payload n == manifest n_rows (generalizes the vendored
         `== 134` assert);
      2. exact key-set equality payload vs manifest on (game_pk,
         pitcher); forecast_cutoff equality required whenever the
         manifest entries carry it;
      3. unique keys (payload and manifest);
      4. identical arm populations: A.shape == B.shape == (n, 24);
      5. PMF validity: 24 support buckets, nonnegative finite, rows sum
         to 1 within 1e-9.
    NOTE: arm_B_status / arm_B_equals_A stamps are deliberately NOT
    validated against the manifest: the seal payload re-stamps arm
    flags under the new builder's arm identities, and pilot usable-B
    membership (11/123) belongs to the PILOT package (see the seal dir
    CLASSIFICATION.md).
    """
    seal = Path(seal_dir)
    keys = json.loads((seal / "row_keys.json").read_text(encoding="ascii"))
    A = np.load(seal / "arm_A_pmf.npy")
    B = np.load(seal / "arm_B_pmf.npy")
    mkeys = manifest["row_keys"]
    n = len(keys)
    checks = {}

    checks["n_matches_manifest"] = (n == manifest["n_rows"])
    payload_keys = [(int(k["game_pk"]), int(k["pitcher"])) for k in keys]
    manifest_keys = [(int(k["game_pk"]), int(k["pitcher"]))
                     for k in mkeys]
    checks["unique_keys_payload"] = (len(set(payload_keys)) == n)
    checks["unique_keys_manifest"] = (len(set(manifest_keys))
                                      == len(manifest_keys))
    checks["key_set_matches_manifest"] = (set(payload_keys)
                                          == set(manifest_keys))
    missing = set(manifest_keys) - set(payload_keys)
    extra = set(payload_keys) - set(manifest_keys)
    if missing or extra:
        raise SystemExit(
            "COHORT-SCORER BLOCKER: key set != pinned manifest "
            "(missing %d, extra %d; e.g. missing=%s extra=%s)"
            % (len(missing), len(extra), sorted(missing)[:3],
               sorted(extra)[:3]))
    cutoff_mismatch = 0
    mmap = {(int(k["game_pk"]), int(k["pitcher"])): k.get("forecast_cutoff")
            for k in mkeys}
    for k in keys:
        mc = mmap[(int(k["game_pk"]), int(k["pitcher"]))]
        if mc is not None and k.get("forecast_cutoff") != mc:
            cutoff_mismatch += 1
    checks["cutoffs_match_manifest"] = (cutoff_mismatch == 0)
    if cutoff_mismatch:
        raise SystemExit(
            "COHORT-SCORER BLOCKER: %d forecast_cutoff mismatches vs "
            "pinned manifest" % cutoff_mismatch)
    if not (n and checks["n_matches_manifest"]):
        raise SystemExit(
            "COHORT-SCORER BLOCKER: payload n=%d != manifest n_rows=%d"
            % (n, manifest["n_rows"]))
    if A.shape != B.shape or A.shape != (n, 24):
        raise SystemExit(
            "COHORT-SCORER BLOCKER: arm shape mismatch: %r %r vs n=%d"
            % (A.shape, B.shape, n))
    checks["identical_arm_populations"] = True
    checks["pmf_support_buckets"] = int(A.shape[1])
    bad = 0
    for P in (A, B):
        bad += int((~np.isfinite(P)).sum()) + int((P < 0).sum()) + int(
            (np.abs(P.sum(axis=1) - 1.0) > 1e-9).sum())
    if bad:
        raise SystemExit(
            "COHORT-SCORER BLOCKER: %d invalid PMF cells/rows" % bad)
    checks["pmf_valid"] = True

    return {
        "mode": "validate",
        "seal_dir": str(seal),
        "manifest": {
            "manifest_id": manifest["manifest_id"],
            "n_rows": manifest["n_rows"],
            "source": manifest.get("pinned_from"),
            "source_sha256": manifest.get("pinned_source_sha256"),
        },
        "n_rows": n,
        "checks": checks,
        "fail_loud": "all violations raise SystemExit; nothing is "
                     "silently dropped",
        "arm_flags_note": "arm_B_status/arm_B_equals_A not manifest-"
                          "validated (pilot membership lives in the "
                          "pilot package; see CLASSIFICATION.md)",
    }


def compute_stats_cohort(seal_dir: Path, data_root: Path,
                         manifest: dict) -> dict:
    """Verbatim vendored-v2 compute_stats with the cohort gate replaced
    by the pinned manifest (n + key set validated by validate_payload
    before this runs). Metric/bootstrap code UNCHANGED: same
    kc.count_rps, same 2,000-resample slate-date bootstrap, seed
    20261001, same secondaries, same (game_pk, pitcher) keying."""
    import kcount_combiner as kc
    import run_bf_ab_score_v2 as s2

    seal = Path(seal_dir)
    A = np.load(seal / "arm_A_pmf.npy")
    B = np.load(seal / "arm_B_pmf.npy")
    keys = json.loads((seal / "row_keys.json").read_text(encoding="ascii"))
    raw = pl.read_parquet(
        Path(data_root) / "Savant-Data" / "regular" / "2026"
        / "statcast_2026_regular.parquet")
    lab = raw.group_by(["game_pk", "pitcher"]).agg(
        pl.col("events").is_in(["strikeout", "strikeout_double_play"])
        .sum().alias("K"))
    j = pl.DataFrame({"game_pk": [k["game_pk"] for k in keys],
                      "pitcher": [k["pitcher"] for k in keys]}).join(
        lab, on=["game_pk", "pitcher"], how="left")
    unmatched = int(j["K"].is_null().sum())
    assert unmatched == 0, "unmatched rows: %d" % unmatched
    n = len(keys)
    # cohort gate: pinned manifest instead of the vendored literal 134
    assert n == manifest["n_rows"], (
        "cohort gate: payload n=%d != pinned manifest n_rows=%d"
        % (n, manifest["n_rows"]))
    assert j.height == n == A.shape[0] == B.shape[0]
    K = j["K"].to_numpy().astype(int)
    rpsA = np.array([kc.count_rps(A[i], K[i]) for i in range(n)])
    rpsB = np.array([kc.count_rps(B[i], K[i]) for i in range(n)])
    dates = np.array([k["forecast_cutoff"][:10] for k in keys])
    fb = np.array([k["arm_B_status"].startswith("A_fallback") for k in keys])

    def boot(mask):
        d = rpsB[mask] - rpsA[mask]
        ds = dates[mask]
        uds = np.unique(ds)
        rng = np.random.default_rng(20261001)
        boots = np.empty(2000)
        for b in range(2000):
            pick = rng.choice(uds, size=len(uds), replace=True)
            idx = np.concatenate([np.where(ds == u)[0] for u in pick])
            boots[b] = d[idx].mean()
        lo, hi = np.percentile(boots, [2.5, 97.5])
        return {"est": float(d.mean()), "lo95": float(lo), "hi95": float(hi),
                "n": int(mask.sum()), "n_dates": int(len(uds))}

    usable = ~fb
    sec = {}
    for name, P in (("A", A), ("B", B)):
        ks = np.arange(24)
        meanK = (P * ks).sum(axis=1)
        sec[name] = {
            "logscore": float(np.mean([-np.log(max(P[i, K[i]], 1e-12))
                                       for i in range(n)])),
            "meanK_mae": float(np.mean(np.abs(meanK - K))),
            "meanK_bias": float(np.mean(meanK - K))}
    per_pitcher = s2.actual_K_by_pitcher(lab, keys)
    return {
        "population_all": boot(np.ones(n, bool)),
        "population_usable_B": boot(usable),
        "secondary": sec,
        "actual_K": per_pitcher,
        "unmatched": unmatched,
        "n_rows": n,
        "usable_B_n": int(usable.sum()),
        "note": ("usable-B membership from payload arm_B_status flags; "
                 "for the pilot-reproduction payload the registered "
                 "usable-B view (11 rows) comes from the PILOT package "
                 "(see CLASSIFICATION.md)"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal-dir", required=True)
    ap.add_argument("--manifest", required=True,
                    help="pinned row-key manifest JSON (n + exact keys)")
    ap.add_argument("--data-root", default=None,
                    help="required for --mode score; omit for validate")
    ap.add_argument("--mode", choices=("validate", "score"),
                    default="validate")
    ap.add_argument("--label-source-note", default=None,
                    help="mandatory provenance note for score mode "
                         "(e.g. SYNTHETIC labels)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.mode == "score" and not args.data_root:
        ap.error("--mode score requires --data-root")
    vendored = verify_vendored_v2()
    manifest = load_manifest(Path(args.manifest))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    validation = validate_payload(Path(args.seal_dir), manifest)
    rep = {
        "version": "cohort-aware-1",
        "lineage": {
            "vendored_v2_commit": "b2fef02",
            "vendored_v2": vendored,
            "metric_changes": "none (verbatim v2 metric/bootstrap code)",
            "gate_change": "hardcoded 134 -> pinned manifest n + exact "
                           "key set + cutoff equality",
        },
        **validation,
    }
    if args.mode == "score":
        stats = compute_stats_cohort(Path(args.seal_dir),
                                     Path(args.data_root), manifest)
        rep["mode"] = "score"
        rep["label_source_note"] = args.label_source_note
        rep["stats"] = stats
    fname = ("cohort_scoring_report.json" if args.mode == "score"
             else "cohort_validation_report.json")
    (out / fname).write_text(json.dumps(rep, indent=1), encoding="ascii")
    print(json.dumps({"out": str(out / fname),
                      "mode": rep["mode"], "n_rows": rep["n_rows"],
                      "checks": rep["checks"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
