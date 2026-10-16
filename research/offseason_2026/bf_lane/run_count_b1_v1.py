"""bf-2026-eval-v1 / count_b1: registered count-layer comparison (one pass).

EXECUTION AMENDMENT V1 RUNNER (2026-10-16). Executes the frozen registration
freeze_count_eval_v1.json + COUNT_REGISTRATION.md
(registration_id bf-2026-eval-v1-count_b1) EXACTLY ONCE into the write-once
run dir C:\\Users\\ckaplinger\\MLB-Props-Research\\bf-2026-eval-v1-outputs\\count_b1\\.

No scientific fields changed; the amendment only pins execution plumbing
(runner bytes, literal command, environment capture, output root, 22-file
inventory schema). Every scientific field (endpoint, bootstrap, Holm family,
row accounting, flag treatment, output path, no-rerun rule) is enforced
verbatim from the frozen registration and its hashes.

Registered procedure (verbatim from the frozen registration):
- Arms differ ONLY in the supplied BF PMF per start:
  B0 = kcount_combiner.bf_pmf_from_37(stored BASE pmf37), cap-60 extension,
       unchanged;
  B1 = persisted b1_ext_* extended PMF from b1_per_row_forecasts.parquet
       (B0 BASE PMF recentered on the Ridge predicted mean by the registered
       deterministic integer shift; career-debut rows pass through
       unchanged, asserted bitwise).
- Everything held identical: cohort/folds (dev-scored block_2024H2 +
  block_2025H1 only; confirm_2025H2 EXCLUDED-NOT-SCORED; block_2024H1
  declared empty; 2026 CLOSED), row eligibility/availability states,
  projected p_bar (persisted per-row column, sha256-gated against the
  registered identity b9148652...; the realized-PA diagnostic p_bar is NOT
  reused), count integration (kcount_combiner.combine_count, k_max 24,
  milestones 6/8/10/12, summed count-RPS convention), calibration +
  aggregation (block-stratified row-weighted pooled dev; resampling unit =
  slate date), observed outcomes (realized BF / realized K cross-checked
  against bf-workload-v1 start_metrics_v2 lineage).
- Primary endpoint: paired count-RPS, B1 - B0
  (C_b1_ridge_vs_b0_empirical). Bootstrap: n_boot 2000, seed 20261001,
  block-stratified by fold, ONE shared draw stream (harness
  comparison.py slate_date_draws, verbatim). Test: null-centered
  approximate bootstrap, two-sided (harness null_centered_contrast_test,
  verbatim); percentile CIs UNADJUSTED; Holm family of 1.
- Row accounting asserted at run time vs the registration table: 4,866 dev
  rows / 186 slate dates (block_2024H2 2,334 + block_2025H1 2,532);
  career_debut pass-through 120; insufficient_history 698; own_distribution
  4,048; 217 flagged recenter records consumed AS-IS (reported, never
  excluded); any mismatch fails loud.
- Fail-closed rules: destination must not exist (write-once; refuse without
  writing); identity gate BEFORE any fitting/scoring (b1 registration sha,
  b1 run manifest + metrics.json hashes, bf_forecasts / start_metrics_v2 /
  pa_table / builder / combiner input hashes, B0 audit PASS verdict,
  b1_per_row_forecasts.parquet sha, p_bar identity -- all re-derived from
  disk); compare executed EXACTLY ONCE via the shared track_and_verify
  chain (compare -> save -> log MLflow -> verify fresh-process); no rerun
  on ANY failure (log-phase-only recovery permitted, recorded); execution
  requires --i-accept-real-data-execution AND owner authorization; no
  promotion, no production change.

Output: exactly the declared 22-file inventory (RUN_FILES_SCHEMA below),
metrics.json with full artifact_inventory_sha256 written inside the single
compare pass, run_manifest.json derived only from that run's final
artifacts (its own sha256 is recorded OUTSIDE the run dir, never edited in
place).

ASCII-only (cp1252 consoles).
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
import traceback
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
HELPERS = HERE.parents[1]
HARNESS = HELPERS / "specs" / "count-eval-v2-spec" / "harness"
sys.path.insert(0, str(HELPERS))
sys.path.insert(0, str(HARNESS))

from kcount_combiner import (  # noqa: E402
    KCOUNT_CAP, bf_pmf_from_37, combine_count, count_logscore, count_rps,
    exceedance,
)
import comparison as cmp  # noqa: E402
from track_and_verify import track_and_verify  # noqa: E402

LAKE = Path(r"C:\Users\ckaplinger\MLB-Props-Research")
BF_DIR = LAKE / "bf-workload-v1"
OUT_DIR = LAKE / "bf-2026-eval-v1-outputs" / "count_b1"
FREEZE_DEFAULT = HERE.parent / "freeze_count_eval_v1.json"
ACCEPT_FLAG = "--i-accept-real-data-execution"

# ---------------------------------------------------------------------------
# Registered identities (frozen registration; hard-coded, fail-closed)
# ---------------------------------------------------------------------------

REGISTRATION_ID = "bf-2026-eval-v1-count_b1"
FREEZE_ID = "count-eval-v1"
AMENDMENT_ID = "execution_amendment_v1"
AMENDMENT_STATEMENT = ("No scientific fields changed; this amendment only "
                       "pins execution plumbing.")
REG_SHA = "e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d"
B1_RUN_MANIFEST_SHA = (
    "37910a98b69177704a8147c2c5e04880a893927c368d598329a674298943b16a")
B1_METRICS_SHA = (
    "0453da67f0c37fdddc37cc66492769014b419c0a0d11bbb46ee1d79da74002f8")
B1_PER_ROW_SHA = (
    "a5f0ad81318c25e34d8837ee56d8728db63df4cd56049d8497d126d6880fcb69")
B0_AUDIT_SHA = (
    "a420dda40317b517dcf7d4cfcafee5d9e8877f52299d1e716db5d70071218a69")
BF_FORECASTS_SHA = (
    "c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679")
BUILDER_SHA = (
    "8893918b3d001f2e3d481eae40e000b32a3968545e37b84f4ba82ba9f7708ef6")
COMBINER_SHA = (
    "94f57a49c0996df5147fb961a085fd229d0ba0e3903c6da0ced9f2d3b670f18f")
START_METRICS_SHA = (
    "af6814ec7ea73b4ac941dd52f185139062b987762d639203b867e15bb4817fde")
PA_TABLE_SHA = (
    "e30d8561d8d0fbb9ab0eae562076312a29eeb1476172d533c3d93570959a85f0")
P_BAR_SHA = (
    "b91486525988da836303d55dab2718164e214bb6679a41225fcc4d79147bf4c4")

INPUT_PATHS = {
    "b1_registration.json": LAKE / "bf-lane-v1" / "b1_registration.json",
    "b1_run_manifest.json": (LAKE / "bf-lane-v1" / "b1_run_v1"
                             / "run_manifest.json"),
    "b1_metrics.json": LAKE / "bf-lane-v1" / "b1_run_v1" / "metrics.json",
    "b1_per_row_forecasts.parquet": (LAKE / "bf-lane-v1" / "b1_run_v1"
                                     / "b1_per_row_forecasts.parquet"),
    "b0_audit.json": LAKE / "bf-lane-v1" / "b0_audit.json",
    "bf_forecasts.parquet": BF_DIR / "data" / "bf_forecasts.parquet",
    "start_metrics_v2.parquet": BF_DIR / "data" / "start_metrics_v2.parquet",
    "build_bf_forecasts.py": BF_DIR / "scripts" / "build_bf_forecasts.py",
    "kcount_combiner.py": HELPERS / "kcount_combiner.py",
    "pa_table.parquet": LAKE / "p1-harness-v2" / "data" / "pa_table.parquet",
}
REGISTERED_SHAS = {
    "b1_registration.json": REG_SHA,
    "b1_run_manifest.json": B1_RUN_MANIFEST_SHA,
    "b1_metrics.json": B1_METRICS_SHA,
    "b1_per_row_forecasts.parquet": B1_PER_ROW_SHA,
    "b0_audit.json": B0_AUDIT_SHA,
    "bf_forecasts.parquet": BF_FORECASTS_SHA,
    "start_metrics_v2.parquet": START_METRICS_SHA,
    "build_bf_forecasts.py": BUILDER_SHA,
    "kcount_combiner.py": COMBINER_SHA,
    "pa_table.parquet": PA_TABLE_SHA,
}

K_MAX = 24
MILESTONES = (6, 8, 10, 12)
N_BOOT_REGISTERED = 2000
SEED_REGISTERED = 20261001
DEbut = "career_debut_league_pool"
DEV_FOLDS = ("block_2024H2", "block_2025H1")

REGISTERED_ROW_ACCOUNTING = {
    "n_dev_rows": 4866,
    "n_slate_dates": 186,
    "fold_rows": {"block_2024H2": 2334, "block_2025H1": 2532},
    "state_counts": {"own_distribution": 4048,
                     "insufficient_history_league_pool": 698,
                     "career_debut_league_pool": 120},
    "recenter_mass_loss_flagged": 217,
    "excluded": {"confirm_2025H2": 2328, "block_2024H1": 0,
                 "2026": "CLOSED"},
}

# Declared 22-file output inventory (immutable schema; enforced at end).
RUN_FILES_SCHEMA = [
    "count_b1_aggregates_block_2024H2.json",
    "count_b1_aggregates_block_2025H1.json",
    "count_b1_aggregates_pooled.json",
    "count_b1_bootstrap_replicates.npy",
    "count_b1_calibration_deciles_block_2024H2.json",
    "count_b1_calibration_deciles_block_2025H1.json",
    "count_b1_calibration_deciles_pooled.json",
    "count_b1_contrast.json",
    "count_b1_coverage_width.json",
    "count_b1_flagged_recenter_records.json",
    "count_b1_identity_gate.json",
    "count_b1_per_date_paired_sums.csv",
    "count_b1_per_row_pmf_b0.parquet",
    "count_b1_per_row_pmf_b1.parquet",
    "count_b1_per_row_scores.parquet",
    "count_b1_p_bar_inventory.json",
    "count_b1_row_count_assertions.json",
    "lgbm_equal_info_config.json",
    "metrics.json",
    "retrieved/lgbm_equal_info_config.json",
    "run_manifest.json",
    "tracking_status.json",
]
assert len(RUN_FILES_SCHEMA) == 22


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_array(a: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(a, dtype=np.float64).tobytes()).hexdigest()


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def py(o):
    """Recursively convert numpy scalars/arrays to plain python for JSON."""
    if isinstance(o, dict):
        return {str(k): py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [py(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return py(o.tolist())
    return o


def fail(msg: str) -> None:
    raise RuntimeError("COUNT_B1 RUN ABORT: " + msg)


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        fail("write-once violation: %s already exists" % path)
    path.write_bytes(data)


def write_once_json(path: Path, obj) -> None:
    write_once(path, json.dumps(py(obj), indent=2).encode("ascii"))


def environment_identity() -> dict:
    return {
        "python": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "polars": pl.__version__,
    }


# ---------------------------------------------------------------------------
# preflight: destination-absent assertion (exit nonzero if it exists)
# ---------------------------------------------------------------------------

def preflight_destination_absent(dest: Path) -> None:
    """Write-once gate: refuse WITHOUT writing anything if the run dir
    already exists (the no-rerun rule; exit nonzero)."""
    if dest.exists():
        fail("write-once destination %s already exists; the no-rerun rule "
             "refuses to re-execute into it (exit nonzero, nothing written)"
             % dest)


# ---------------------------------------------------------------------------
# identity gate (fail loud BEFORE any fitting/scoring)
# ---------------------------------------------------------------------------

def check_freeze_config(freeze_path: Path) -> dict:
    """The freeze JSON must carry the registered scientific contract and the
    amendment; runner verifies it agrees with the hard-coded values."""
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("freeze_id") != FREEZE_ID:
        fail("freeze_id mismatch")
    if freeze.get("registration_id") != REGISTRATION_ID:
        fail("registration_id mismatch")
    am = freeze.get(AMENDMENT_ID)
    if not isinstance(am, dict):
        fail("freeze JSON missing %s amendment" % AMENDMENT_ID)
    if am.get("statement") != AMENDMENT_STATEMENT:
        fail("amendment statement mismatch")
    got_runner = am.get("runner", {}).get("sha256")
    self_sha = sha256_file(HERE)
    if got_runner != self_sha:
        fail("amendment runner sha256 %r != this runner's bytes %r"
             % (got_runner, self_sha))
    ep = freeze["endpoint"]
    if (ep["bootstrap"]["n_boot"] != N_BOOT_REGISTERED
            or ep["bootstrap"]["seed"] != SEED_REGISTERED
            or ep["bootstrap"]["unit"] != "game_date (slate date)"
            or "block-stratified" not in ep["bootstrap"]["method"]
            or ep["primary"] != "paired count-RPS, B1 - B0 "
                                "(C_b1_ridge_vs_b0_empirical)"
            or ep["holm_family"]["size"] != 1):
        fail("freeze endpoint block does not match the registered contract")
    ra = freeze["row_accounting"]
    if ra["dev_scored_expectation"]["n_rows"] != 4866 \
            or ra["dev_scored_expectation"]["n_slate_dates"] != 186 \
            or ra["flagged_recenter_records"]["count"] != 217:
        fail("freeze row accounting does not match the registered table")
    if freeze["output"]["location"] != str(OUT_DIR) + "\\":
        fail("freeze output location mismatch")
    declared = {
        "b1_run_manifest.json": freeze["provenance"]["b1_run_manifest"]["sha256"],
        "b1_metrics.json": freeze["provenance"]["b1_metrics_json"]["sha256"],
        "b1_registration.json": freeze["provenance"]["b1_registration"]["sha256"],
        "b1_per_row_forecasts.parquet":
            freeze["only_varying_input"]["source_artifact"].split()[-1],
        "bf_forecasts.parquet":
            freeze["frozen_baselines"]["bf_pmf_b0"]["bf_forecasts_sha256"],
        "build_bf_forecasts.py":
            freeze["frozen_baselines"]["bf_pmf_b0"]["builder_sha256"],
        "kcount_combiner.py":
            freeze["frozen_baselines"]["bf_pmf_b0"]["kcount_combiner_sha256"],
    }
    for name, h in declared.items():
        if h != REGISTERED_SHAS[name]:
            fail("freeze JSON hash drift for %s: %s != registered %s"
                 % (name, h, REGISTERED_SHAS[name]))
    return {"amendment_sha256": canonical_sha256(am),
            "runner_sha256": self_sha,
            "freeze_sha256": sha256_file(freeze_path)}


def check_identities(freeze_check: dict) -> dict:
    identities = {}
    for name, path in INPUT_PATHS.items():
        if not path.is_file():
            fail("registered input missing from disk: %s" % path)
        h = sha256_file(path)
        if h != REGISTERED_SHAS[name]:
            fail("registered input hash mismatch for %s: %s != %s"
                 % (name, h, REGISTERED_SHAS[name]))
        identities[name] = h
    audit = json.loads(INPUT_PATHS["b0_audit.json"].read_text(
        encoding="ascii"))
    if not str(audit.get("verdict", "")).startswith("PASS"):
        fail("b0_audit verdict is not PASS")
    identities["runner"] = freeze_check["runner_sha256"]
    identities["freeze"] = freeze_check["freeze_sha256"]
    identities["environment"] = environment_identity()
    return {"identities": identities, "amendment_sha256":
            freeze_check["amendment_sha256"], "b0_audit_verdict":
            "PASS"}


# ---------------------------------------------------------------------------
# the compare pass (executed EXACTLY ONCE via track_and_verify)
# ---------------------------------------------------------------------------

_FREEZE_SHA256: str | None = None  # set by main() before the compare pass

def _agg_scope(df: pl.DataFrame) -> dict:
    out = {"n": int(df.height)}
    for arm in ("b0", "b1"):
        a = {}
        a["count_rps"] = float(df["%s_rps" % arm].mean())
        a["count_logscore"] = float(df["%s_logscore" % arm].mean())
        for m in MILESTONES:
            a["brier_ge%d" % m] = float(df["%s_brier_ge%d" % (arm, m)].mean())
        err = df["%s_mean" % arm].to_numpy() - df["realized_bf"].to_numpy()
        a["mean_forecast_bias"] = float(err.mean())
        a["mean_forecast_mae"] = float(np.abs(err).mean())
        a["mean_forecast_rmse"] = float(np.sqrt((err ** 2).mean()))
        cek = df["%s_count_ek" % arm].to_numpy() \
            - df["realized_k"].to_numpy()
        a["count_ek_bias"] = float(cek.mean())
        a["count_ek_mae"] = float(np.abs(cek).mean())
        a["count_ek_rmse"] = float(np.sqrt((cek ** 2).mean()))
        out[arm] = a
    out["paired_delta_b1_minus_b0"] = {
        "count_rps": out["b1"]["count_rps"] - out["b0"]["count_rps"],
        "count_logscore": (out["b1"]["count_logscore"]
                           - out["b0"]["count_logscore"]),
    }
    return out


def _coverage_width(df: pl.DataFrame) -> dict:
    out = {}
    obs = df["realized_bf"].to_numpy()
    for arm in ("b0", "b1"):
        a = {}
        for lo, hi, tag in (("q10", "q90", "P10_P90"),
                            ("q25", "q75", "P25_P75")):
            lo_v = df["%s_%s" % (arm, lo)].to_numpy()
            hi_v = df["%s_%s" % (arm, hi)].to_numpy()
            a["coverage_%s" % tag] = float(
                ((obs >= lo_v) & (obs <= hi_v)).mean())
            a["mean_width_%s" % tag] = float((hi_v - lo_v).mean())
        out[arm] = a
    return out


def _calibration_deciles(df: pl.DataFrame) -> dict:
    out = {}
    obs = df["realized_bf"].to_numpy()
    for arm in ("b0", "b1"):
        pm = df["%s_mean" % arm].to_numpy()
        edges = np.quantile(pm, np.linspace(0.0, 1.0, 11))
        bins = np.clip(np.digitize(pm, edges[1:-1], right=True), 0, 9)
        dec = []
        for b in range(10):
            m = bins == b
            dec.append({
                "bin": b, "n": int(m.sum()),
                "mean_pred": float(pm[m].mean()) if m.any() else None,
                "mean_obs": float(obs[m].mean()) if m.any() else None,
            })
        out[arm] = dec
    return out


def run_compare() -> dict:
    preflight_destination_absent(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    prf = pl.read_parquet(INPUT_PATHS["b1_per_row_forecasts.parquet"])

    # ---- row accounting assertions (fail loud on any mismatch) -----------
    n_rows = prf.height
    if n_rows != 4866:
        fail("row accounting: n_rows %d != 4866" % n_rows)
    fold_counts = {r["fold"]: int(r["len"]) for r in
                   prf.group_by("fold").len().iter_rows(named=True)}
    if fold_counts != REGISTERED_ROW_ACCOUNTING["fold_rows"]:
        fail("row accounting: fold counts %s != registered %s"
             % (fold_counts, REGISTERED_ROW_ACCOUNTING["fold_rows"]))
    state_counts = {r["availability_state"]: int(r["len"]) for r in
                    prf.group_by("availability_state").len()
                    .iter_rows(named=True)}
    if state_counts != REGISTERED_ROW_ACCOUNTING["state_counts"]:
        fail("row accounting: state counts %s != registered %s"
             % (state_counts, REGISTERED_ROW_ACCOUNTING["state_counts"]))
    n_dates = prf["game_date"].n_unique()
    if n_dates != 186:
        fail("row accounting: n_slate_dates %d != 186" % n_dates)
    n_flag = int(prf["recenter_mass_loss_flag"].sum())
    if n_flag != 217:
        fail("row accounting: flagged recenter records %d != 217" % n_flag)

    # ---- p_bar identity gate (persisted column, both arms identical) -----
    p_bar = prf["p_bar"].to_numpy().astype(np.float64)
    p_bar_sha = sha256_array(p_bar)
    if p_bar_sha != P_BAR_SHA:
        fail("p_bar identity mismatch: %s != registered %s"
             % (p_bar_sha, P_BAR_SHA))
    if p_bar.min() < 1e-6 or p_bar.max() > 1 - 1e-6:
        fail("p_bar outside the registered clip range")

    # ---- realized-outcome lineage cross-check (start_metrics_v2) ---------
    sm = pl.read_parquet(INPUT_PATHS["start_metrics_v2.parquet"]).select(
        "game_pk", "side", "pitcher", "realized_bf", "realized_k")
    joined = prf.select("game_pk", "side", "pitcher", "realized_bf",
                        "realized_k").join(
        sm, on=["game_pk", "side", "pitcher"], how="inner",
        suffix="_sm")
    if joined.height != 4866:
        fail("start_metrics_v2 lineage join: %d != 4866 rows" % joined.height)
    if (joined["realized_bf"] != joined["realized_bf_sm"]).any() \
            or (joined["realized_k"] != joined["realized_k_sm"]).any():
        fail("start_metrics_v2 lineage join: realized outcome mismatch")

    # ---- per-row scoring from the SUPPLIED BF PMFs (the only varying
    #      input), cross-checked against the persisted B1-run columns -----
    pmf37_cols = ["b0_pmf37_%d" % j for j in range(37)]
    ext_cols = ["b1_ext_%d" % j for j in range(KCOUNT_CAP)]
    rows = prf.to_dicts()
    b0_pk = np.zeros((n_rows, K_MAX))
    b1_pk = np.zeros((n_rows, K_MAX))
    b0_pmf37_sha = []
    b1_ext_sha = []
    n_debut_checked = 0
    for i, r in enumerate(rows):
        p37 = np.array([r[c] for c in pmf37_cols], dtype=np.float64)
        b0_ext = bf_pmf_from_37(p37)
        b1_ext = np.array([r[c] for c in ext_cols], dtype=np.float64)
        if abs(b1_ext.sum() - 1.0) > 1e-9:
            fail("row %d: persisted b1_ext PMF does not sum to 1" % i)
        if r["availability_state"] == DEbut:
            if not np.array_equal(b1_ext, b0_ext):
                fail("row %d: career-debut pass-through violated "
                     "(B1 PMF != B0 extended PMF)" % i)
            n_debut_checked += 1
        pk0 = combine_count(b0_ext, r["p_bar"], K_MAX)
        pk1 = combine_count(b1_ext, r["p_bar"], K_MAX)
        b0_pk[i] = pk0
        b1_pk[i] = pk1
        b0_pmf37_sha.append(sha256_array(p37))
        b1_ext_sha.append(sha256_array(b1_ext))
        k_real = int(r["realized_k"])
        for arm, pk in (("b0", pk0), ("b1", pk1)):
            persisted_pk = np.array([r["%s_count_%d" % (arm, k)]
                                     for k in range(K_MAX)])
            if np.abs(pk - persisted_pk).max() > 1e-12:
                fail("row %d: recomputed %s count PMF deviates from the "
                     "persisted B1-run PMF" % (i, arm))
            if abs(count_rps(pk, k_real) - r["%s_rps" % arm]) > 1e-12:
                fail("row %d: recomputed %s count-RPS deviates" % (i, arm))
            if abs(count_logscore(pk, k_real)
                   - r["%s_logscore" % arm]) > 1e-12:
                fail("row %d: recomputed %s count-logscore deviates"
                     % (i, arm))
            for m in MILESTONES:
                want = (exceedance(pk, m)
                        - (1.0 if k_real >= m else 0.0)) ** 2
                if abs(want - r["%s_brier_ge%d" % (arm, m)]) > 1e-12:
                    fail("row %d: recomputed %s Brier_ge%d deviates"
                         % (i, arm, m))

    rdf = prf.select("game_pk", "side", "pitcher", "game_date", "fold",
                     "availability_state", "p_bar", "realized_bf",
                     "realized_k", "b0_mean", "b1_mean", "shift_s",
                     "recenter_mass_loss", "recenter_mass_loss_flag",
                     "b0_rps", "b1_rps", "b0_logscore", "b1_logscore",
                     "b0_brier_ge6", "b1_brier_ge6", "b0_brier_ge8",
                     "b1_brier_ge8", "b0_brier_ge10", "b1_brier_ge10",
                     "b0_brier_ge12", "b1_brier_ge12", "b0_q10", "b1_q10",
                     "b0_q25", "b1_q25", "b0_q75", "b1_q75", "b0_q90",
                     "b1_q90")
    rdf = rdf.with_columns([
        pl.Series("b0_count_ek", (b0_pk * np.arange(K_MAX)).sum(axis=1)),
        pl.Series("b1_count_ek", (b1_pk * np.arange(K_MAX)).sum(axis=1)),
        pl.Series("b0_pmf37_sha256", b0_pmf37_sha),
        pl.Series("b1_ext_sha256", b1_ext_sha),
    ])

    # ---- aux artifacts (write-once) ---------------------------------------
    write_once(OUT_DIR / "count_b1_per_row_scores.parquet",
               rdf.write_parquet())
    pmf_df = rdf.select("game_pk", "side", "pitcher")
    b0_pdf = pl.DataFrame(b0_pk, schema=["b0_count_%d" % k
                                         for k in range(K_MAX)])
    b1_pdf = pl.DataFrame(b1_pk, schema=["b1_count_%d" % k
                                         for k in range(K_MAX)])
    write_once(OUT_DIR / "count_b1_per_row_pmf_b0.parquet",
               pl.concat([pmf_df, b0_pdf], how="horizontal")
               .write_parquet())
    write_once(OUT_DIR / "count_b1_per_row_pmf_b1.parquet",
               pl.concat([pmf_df, b1_pdf], how="horizontal")
               .write_parquet())

    per_date = (rdf.group_by("fold", "game_date")
                .agg(pl.len().alias("n"),
                     pl.col("b0_rps").sum().alias("b0_rps_sum"),
                     pl.col("b1_rps").sum().alias("b1_rps_sum"))
                .sort(["fold", "game_date"]))
    write_once(OUT_DIR / "count_b1_per_date_paired_sums.csv",
               per_date.write_csv().encode("ascii"))

    # ---- paired slate-date bootstrap (shared stream) + contrast -----------
    dates = rdf["game_date"].to_list()
    blocks = rdf["fold"].to_list()
    values = {"b0_rps": rdf["b0_rps"].to_numpy(),
              "b1_rps": rdf["b1_rps"].to_numpy()}
    res = cmp.slate_date_draws(values, dates, blocks,
                               n_boot=cmp.N_BOOT,
                               seed=cmp.SEED_BOOTSTRAP)
    if (cmp.N_BOOT, 2) != res.shape:
        fail("bootstrap replicate matrix shape %s != (2000, 2)" % (res.shape,))
    np.save(OUT_DIR / "count_b1_bootstrap_replicates.npy", res)
    contrast = cmp.null_centered_contrast_test(
        values, [("C_b1_ridge_vs_b0_empirical", "b1_rps", "b0_rps")],
        dates, blocks, n_boot=cmp.N_BOOT, seed=cmp.SEED_BOOTSTRAP, res=res)
    c = contrast["contrasts"]["C_b1_ridge_vs_b0_empirical"]
    d_rep = res[:, 1] - res[:, 0]
    c["ci95_unadjusted"] = [float(np.percentile(d_rep, 2.5)),
                            float(np.percentile(d_rep, 97.5))]
    c["note"] = ("primary endpoint C_b1_ridge_vs_b0_empirical on count-RPS; "
                 "Holm family of 1; percentile CIs UNADJUSTED")
    write_once_json(OUT_DIR / "count_b1_contrast.json", contrast)

    # ---- aggregates / calibration / coverage ------------------------------
    scopes = [("pooled", rdf)] + [(f, rdf.filter(pl.col("fold") == f))
                                  for f in DEV_FOLDS]
    agg_by_scope = {}
    cov_by_scope = {}
    cal_by_scope = {}
    for tag, df in scopes:
        agg_by_scope[tag] = _agg_scope(df)
        cov_by_scope[tag] = _coverage_width(df)
        cal_by_scope[tag] = _calibration_deciles(df)
        suffix = "" if tag == "pooled" else "_" + tag
        write_once_json(OUT_DIR
                        / ("count_b1_aggregates%s.json" % suffix),
                        agg_by_scope[tag])
        write_once_json(OUT_DIR
                        / ("count_b1_calibration_deciles%s.json" % suffix),
                        cal_by_scope[tag])
    write_once_json(OUT_DIR / "count_b1_coverage_width.json", cov_by_scope)

    # ---- assertions / inventories / flagged records ------------------------
    row_count_assertions = {
        **REGISTERED_ROW_ACCOUNTING,
        "observed": {"n_dev_rows": n_rows, "n_slate_dates": n_dates,
                     "fold_rows": fold_counts, "state_counts": state_counts,
                     "recenter_mass_loss_flagged": n_flag,
                     "career_debut_pass_through_asserted_bitwise":
                         n_debut_checked},
        "verdict": "PASS" if (
            n_rows == 4866 and n_dates == 186 and fold_counts ==
            REGISTERED_ROW_ACCOUNTING["fold_rows"] and state_counts ==
            REGISTERED_ROW_ACCOUNTING["state_counts"] and n_flag == 217)
            else "FAIL",
    }
    if row_count_assertions["verdict"] != "PASS":
        fail("row-count assertion table verdict FAIL")
    write_once_json(OUT_DIR / "count_b1_row_count_assertions.json",
                    row_count_assertions)

    flagged = rdf.filter(pl.col("recenter_mass_loss_flag")).select(
        "game_pk", "side", "pitcher", "fold", "availability_state",
        "recenter_mass_loss")
    fl = flagged.to_dicts()
    losses = [r["recenter_mass_loss"] for r in fl]
    write_once_json(OUT_DIR / "count_b1_flagged_recenter_records.json", {
        "count": len(fl),
        "share": "%d/%d = %.1f%%" % (len(fl), n_rows, 100.0 * len(fl)
                                     / n_rows),
        "max_mass_loss": max(losses),
        "median_mass_loss": float(np.median(losses)),
        "treatment": "consumed AS-IS from the persisted B1 run; "
                     "renormalized valid PMFs carried into every aggregate; "
                     "reported, never silently accepted, never excluded",
        "rows": fl,
    })

    p_bar_inventory = {
        "sha256": p_bar_sha,
        "registered_sha256": P_BAR_SHA,
        "matches_registered": True,
        "n": n_rows,
        "min": float(p_bar.min()), "max": float(p_bar.max()),
        "mean": float(p_bar.mean()),
        "lineage": "persisted per-row projected p_bar from "
                   "b1_per_row_forecasts.parquet (B1 run; identical both "
                   "arms; realized-PA diagnostic p_bar NOT reused)",
    }
    write_once_json(OUT_DIR / "count_b1_p_bar_inventory.json",
                    p_bar_inventory)

    config = {
        "run_id": "bf-2026-eval-v1-count_b1",
        "registration_id": REGISTRATION_ID,
        "freeze_id": FREEZE_ID,
        "amendment_id": AMENDMENT_ID,
        "amendment_statement": AMENDMENT_STATEMENT,
        "freeze_sha256": _FREEZE_SHA256,
        "arms": {
            "b0": "kcount_combiner.bf_pmf_from_37(stored BASE pmf37), "
                  "cap-60 extension, unchanged",
            "b1": "persisted b1_ext_* extended PMF from "
                  "b1_per_row_forecasts.parquet (career-debut rows pass "
                  "through unchanged, asserted bitwise)",
        },
        "only_varying_input": "the supplied BF PMF per start",
        "folds_dev_scored": list(DEV_FOLDS),
        "folds_excluded_not_scored": ["confirm_2025H2"],
        "folds_declared_empty": ["block_2024H1"],
        "2026": "CLOSED",
        "count_integration": {"k_max": K_MAX, "milestones": list(MILESTONES),
                              "combiner": "kcount_combiner.combine_count",
                              "rps_convention": "summed"},
        "p_bar_sha256": P_BAR_SHA,
        "paired_uncertainty": {"n_boot": int(cmp.N_BOOT),
                               "seed": int(cmp.SEED_BOOTSTRAP),
                               "unit": "game_date (slate date)",
                               "method": "block-stratified by fold, one "
                                         "shared draw stream "
                                         "(comparison.slate_date_draws)",
                               "predeclared_contrasts":
                                   ["C_b1_ridge_vs_b0_empirical on "
                                    "count-RPS"],
                               "test": "null-centered approximate bootstrap, "
                                       "two-sided ("
                                       "comparison.null_centered_contrast_"
                                       "test); Holm family of 1; percentile "
                                       "CIs UNADJUSTED"},
        "inputs_sha256": {k: REGISTERED_SHAS[k] for k in REGISTERED_SHAS},
        "row_count_assertions": row_count_assertions,
    }

    result = {
        "config": config,
        "aggregate": agg_by_scope,
        "coverage_width": cov_by_scope,
        "calibration_deciles": cal_by_scope,
        "bootstrap": {"_meta": {"method": "slate-date, block-stratified, "
                                          "row-weighted ratio; ONE shared "
                                          "draw stream across arms and "
                                          "contrasts",
                                "n_resamples": int(cmp.N_BOOT),
                                "seed": int(cmp.SEED_BOOTSTRAP),
                                "unit": "game_date",
                                "replicate_matrix":
                                    "count_b1_bootstrap_replicates.npy"},
                      "b0_rps": {"point": float(values["b0_rps"].mean()),
                                 "ci95": [float(np.percentile(res[:, 0],
                                                               2.5)),
                                          float(np.percentile(res[:, 0],
                                                               97.5))]},
                      "b1_rps": {"point": float(values["b1_rps"].mean()),
                                 "ci95": [float(np.percentile(res[:, 1],
                                                               2.5)),
                                          float(np.percentile(res[:, 1],
                                                               97.5))]}},
        "contrast": contrast,
        "p_bar": p_bar_inventory,
        "row_count_assertions": row_count_assertions,
    }
    return py(result)


def describe(result: dict, out_dir, saved=None, extra_params=None):
    cfg = result["config"]
    params = {
        "registration_id": cfg["registration_id"],
        "freeze_id": cfg["freeze_id"],
        "amendment_id": cfg["amendment_id"],
        "primary_endpoint": "C_b1_ridge_vs_b0_empirical on count-RPS",
        "n_boot": cfg["paired_uncertainty"]["n_boot"],
        "seed": cfg["paired_uncertainty"]["seed"],
        "holm_family_size": 1,
        "run_dir": str(OUT_DIR),
    }
    agg = result["aggregate"]["pooled"]
    metrics = {
        "pooled_count_rps_b0": agg["b0"]["count_rps"],
        "pooled_count_rps_b1": agg["b1"]["count_rps"],
        "pooled_count_logscore_b0": agg["b0"]["count_logscore"],
        "pooled_count_logscore_b1": agg["b1"]["count_logscore"],
        "contrast_delta_count_rps": result["contrast"]["contrasts"][
            "C_b1_ridge_vs_b0_empirical"]["delta"],
        "contrast_p_null_centered": result["contrast"]["contrasts"][
            "C_b1_ridge_vs_b0_empirical"]["p_value"],
        "contrast_p_holm": result["contrast"]["contrasts"][
            "C_b1_ridge_vs_b0_empirical"]["p_holm"],
    }
    artifacts = [(saved["config_artifact_path"], "config")]
    return params, metrics, artifacts


def finalize_manifest(identities: dict, amendment_sha256: str,
                      metrics_sha: str) -> None:
    """run_manifest.json derived ONLY from this run's final artifacts; its
    own sha256 is recorded OUTSIDE the run dir (never edited in place)."""
    inventory = {}
    for rel in RUN_FILES_SCHEMA:
        p = OUT_DIR / rel
        if rel == "run_manifest.json":
            continue
        if not p.is_file():
            fail("declared inventory file missing at finalize: %s" % rel)
        inventory[rel] = sha256_file(p)
    on_disk = sorted(str(p.relative_to(OUT_DIR)).replace("\\", "/")
                     for p in OUT_DIR.rglob("*") if p.is_file())
    expected = sorted(set(RUN_FILES_SCHEMA) - {"run_manifest.json"})
    if on_disk != expected:
        fail("output inventory mismatch:\n  on disk: %s\n  expected: %s"
             % (on_disk, expected))
    manifest = {
        "schema": "count_b1_run_manifest_v1",
        "created_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "run_id": "bf-2026-eval-v1-count_b1",
        "registration": {
            "registration_id": REGISTRATION_ID,
            "freeze_id": FREEZE_ID,
            "freeze_json_sha256": identities["freeze"],
            "b1_registration_json_sha256": REG_SHA,
        },
        "amendment": {
            "amendment_id": AMENDMENT_ID,
            "amendment_section_sha256": amendment_sha256,
            "statement": AMENDMENT_STATEMENT,
            "runner": {"file": "run_count_b1_v1.py",
                       "sha256": identities["runner"]},
        },
        "identity_gate": identities,
        "primary_endpoint": "paired count-RPS, B1 - B0 "
                            "(C_b1_ridge_vs_b0_empirical)",
        "metrics_json_sha256": metrics_sha,
        "artifact_inventory_sha256": inventory,
        "declared_inventory_schema": RUN_FILES_SCHEMA,
        "verdict": "count_b1 comparison executed exactly once; primary "
                   "endpoint numbers in metrics.json; no rerun permitted "
                   "into this destination",
        "immutability": {
            "rule": "write-once run dir; never edited in place",
            "manifest_self_note": "the sha256 of this run_manifest.json is "
                                  "recorded OUTSIDE this file "
                                  "(COUNT_REGISTRATION.md amendment section "
                                  "in the repo); it must never be edited "
                                  "in place",
        },
    }
    write_once_json(OUT_DIR / "run_manifest.json", manifest)
    print("run_manifest.json sha256 (record OUTSIDE the run dir):")
    print(sha256_file(OUT_DIR / "run_manifest.json"))


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        description="Registered count_b1 comparison (execution amendment "
                    "v1). Refuses without the execution-acceptance flag; "
                    "refuses if the write-once destination exists.")
    p.add_argument("--freeze", default=str(FREEZE_DEFAULT),
                   help="path to freeze_count_eval_v1.json")
    p.add_argument(ACCEPT_FLAG, dest="accept_real_data_execution",
                   action="store_true",
                   help="acknowledge this command scores realized outcomes "
                        "on the registered dev folds")
    args = p.parse_args(argv)
    if not args.accept_real_data_execution:
        print("REFUSED: real-data execution requires %s. Nothing was read, "
              "fitted, scored, or written." % ACCEPT_FLAG)
        return 2

    # preflight: destination must be absent (exit nonzero otherwise)
    preflight_destination_absent(OUT_DIR)
    freeze_check = check_freeze_config(Path(args.freeze).resolve())
    identities = check_identities(freeze_check)
    global _FREEZE_SHA256
    _FREEZE_SHA256 = freeze_check["freeze_sha256"]
    print("identity gates PASS; registration sha256 verified")

    try:
        t = track_and_verify(
            run_compare, OUT_DIR,
            "sqlite:///" + str(LAKE / "mlflow.db"),
            experiment="bf-2026-eval-v1", run_name="count_b1_v1",
            describe=describe)
    except Exception as exc:
        err = {"status": "FAILED",
               "written_utc": __import__("datetime").datetime.now(
                   __import__("datetime").timezone.utc).isoformat(),
               "error": "%s: %s" % (type(exc).__name__, exc),
               "traceback": traceback.format_exc(),
               "note": "single run; partials preserved; NO silent retry; "
                       "no rerun into this destination"}
        log_dir = OUT_DIR if OUT_DIR.exists() else OUT_DIR.parent
        (log_dir / "count_b1_error_log.json").write_text(
            json.dumps(err, indent=2), encoding="ascii")
        print("RUN FAILED - partials preserved in %s" % log_dir)
        print(err["error"])
        return 1

    # identity gate record (final, includes env + amendment hashes),
    # written exactly once
    gate = {"identities": identities["identities"],
            "amendment_sha256": identities["amendment_sha256"],
            "b0_audit_verdict": identities["b0_audit_verdict"],
            "environment": environment_identity(),
            "python_executable": sys.executable}
    write_once_json(OUT_DIR / "count_b1_identity_gate.json", gate)

    finalize_manifest({**identities["identities"],
                       "freeze": freeze_check["freeze_sha256"]},
                      identities["amendment_sha256"], t["metrics_sha256"])
    print("track_and_verify:", t["status"], "run_id", t["run_id"])
    print("metrics.json sha256:", t["metrics_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
