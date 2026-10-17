# track_and_verify.py -- SHARED tracking wrapper for count-eval-v1
# (D-1 TRACKING IN EXECUTION, 2026-10-15). One owner for the whole chain:
#
#     compare -> save (canonical outputs finalize) -> log (MLflow)
#            -> verify (fresh retrieve + exact metric + artifact byte hash)
#
# The frozen LightGBM command (run_lgbm_equal_info.py, registered in
# freeze_lgbm_equal_info_v1.json amendment-1) invokes THIS wrapper after its
# canonical outputs finalize; it does not hand-replicate logging calls.
#
# Failure contract (D-1):
#   * an MLflow failure (e.g. unreachable tracking store) SURFACES to the
#     caller: the wrapper raises TrackingFailure (CLI -> exit nonzero);
#   * the computed canonical outputs are preserved untouched on disk;
#   * the wrapper records status "tracking_failed" in tracking_status.json
#     in the run dir, so the batch is never reported fully successful;
#   * logging recovery is SEPARATE from fitting: compare runs exactly once
#     and an upload failure NEVER triggers a refit.
#
# Identity contract (D-2): verify_registered_identities() re-derives every
# registered identity (freeze config hash, input sha256s, adapter file +
# config hashes, builder-worktree harness comparison.py sha, wrapper/runner
# self-hashes) from disk and fails loud BEFORE any fitting.
# Amendment-2 (2026-10-15): registered text-source files (.py/.json/.md)
# verify LF-NORMALIZED (portable across git EOL materializations); binary
# files (.parquet/.pkl/.joblib/.npy) stay byte-exact. See
# TEXT_SOURCE_IDENTITY_CONVENTION below.
#
# ASCII-only (cp1252 consoles).
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULT_EXPERIMENT = "lgbm-equal-info"
DEFAULT_RUN_NAME = "lgbm-equal-info"

CONFIG_HASH_DEFINITION = (
    "sha256 over json.dumps(config, sort_keys=True, separators=(',',':'))"
    ".encode('utf-8') of the 'config' object in this file")

# ---------------------------------------------------------------------------
# TEXT-SOURCE IDENTITY CONVENTION (amendment-2, 2026-10-15)
# ---------------------------------------------------------------------------
# A byte-exact sha256 over a registered .py/.md source file is NOT portable
# across git EOL materializations: the repo blobs are LF, but core.autocrlf
# (or an eol attribute) can materialize CRLF in a fresh checkout, so the
# on-disk bytes differ while the content is identical. The declared
# convention below fixes this: declared text-source files are identified by
# sha256 over their LF-NORMALIZED content; declared binary files (and any
# undeclared extension, as a safe default) stay BYTE-EXACT. The convention
# is declared here (single owner) and mirrored verbatim in
# freeze_lgbm_equal_info_v1.json under config.text_source_identity_convention.

TEXT_SOURCE_EXTENSIONS = frozenset({".py", ".json", ".md"})
BINARY_IDENTITY_EXTENSIONS = frozenset({".parquet", ".pkl", ".joblib", ".npy"})

TEXT_SOURCE_IDENTITY_CONVENTION = (
    "TEXT-SOURCE IDENTITY CONVENTION (amendment-2, 2026-10-15): declared "
    "text-source files (extensions " + ", ".join(sorted(TEXT_SOURCE_EXTENSIONS))
    + ") are identified by sha256 over their LF-NORMALIZED content (every "
    "CRLF and lone CR is normalized to LF before hashing), so a registered "
    "text identity is reproducible across git EOL materializations "
    "(core.autocrlf / eol attributes). Declared binary files (extensions "
    + ", ".join(sorted(BINARY_IDENTITY_EXTENSIONS))
    + ") and any other extension are identified BYTE-EXACT (sha256 over the "
    "raw file bytes). Byte-exact values registered under the prior "
    "amendment-1 convention are preserved as historical records and are not "
    "re-verified against disk; verification uses the normalized value for "
    "text-source files and the byte-exact value for binary files.")

STATUS_FILE = "tracking_status.json"


class TrackingFailure(RuntimeError):
    """MLflow logging/verification failed; canonical outputs preserved."""


class IdentityMismatch(TrackingFailure):
    """A registered identity (config/input/adapter/harness hash) does not
    match what is on disk; raised BEFORE any fitting."""


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_text_bytes(raw: bytes) -> bytes:
    """LF-normalization per the declared convention: CRLF -> LF, then any
    lone CR -> LF."""
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def file_identity_class(path) -> str:
    """"text" or "binary" per TEXT_SOURCE_IDENTITY_CONVENTION (undeclared
    extensions are treated as binary, the safe default)."""
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SOURCE_EXTENSIONS:
        return "text"
    return "binary"


def sha256_file_identity(path) -> dict:
    """Identity of one file per TEXT_SOURCE_IDENTITY_CONVENTION. Returns
    {"class": "text"|"binary", "byte_exact": sha256(raw bytes),
    "lf_normalized": sha256(LF-normalized bytes)} - for a binary file the
    two hashes are identical."""
    raw = Path(path).read_bytes()
    cls = file_identity_class(path)
    norm = normalize_text_bytes(raw) if cls == "text" else raw
    return {
        "class": cls,
        "byte_exact": hashlib.sha256(raw).hexdigest(),
        "lf_normalized": hashlib.sha256(norm).hexdigest(),
    }


def freeze_config_sha256(cfg: dict) -> str:
    """The registered config hash definition (see CONFIG_HASH_DEFINITION)."""
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# SAVE: canonical outputs finalize
# ---------------------------------------------------------------------------

def save_canonical_outputs(result: dict, out_dir) -> dict:
    """Write the canonical outputs of one comparison into out_dir
    (write-once: refuses to overwrite an existing file). Returns the saved
    artifact inventory with sha256 hashes."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    cfg_path = out_dir / "lgbm_equal_info_config.json"
    for p in (metrics_path, cfg_path):
        if p.exists():
            raise TrackingFailure(
                f"write-once violation: {p} already exists "
                "(never overwrite canonical outputs)")
    metrics_path.write_text(json.dumps(result, indent=2))
    cfg_path.write_text(json.dumps(result["config"], indent=2))
    return {
        "metrics_path": str(metrics_path),
        "metrics_sha256": sha256_file(metrics_path),
        "config_artifact_relpath": "config/lgbm_equal_info_config.json",
        "config_artifact_path": str(cfg_path),
        "config_artifact_sha256": sha256_file(cfg_path),
    }


# ---------------------------------------------------------------------------
# DESCRIBE: result -> (params, metrics, artifacts) for MLflow
# ---------------------------------------------------------------------------

def default_describe(result: dict, out_dir=None, saved: dict | None = None,
                     extra_params: dict | None = None):
    """Default mapping for the lgbm_equal_info_adapter result shape."""
    params = {str(k): v for k, v in result["config"].items()}
    if extra_params:
        params.update(extra_params)
    params["features"] = ",".join(result["features"])
    params["candidates"] = ",".join(result["pooled"]["brier_raw"])
    metrics: dict[str, float] = {}
    for lane, key in (("brier_raw", "pooled_brier_raw"),
                      ("log_loss_raw", "pooled_log_loss_raw")):
        for cand, val in result["pooled"][lane].items():
            metrics[f"{key}__{cand}"] = float(val)
    c = result["contrast"]
    metrics["contrast_delta_brier_raw"] = float(c["delta"])
    metrics["contrast_ci_lo"] = float(c["ci95_unadjusted"][0])
    metrics["contrast_ci_hi"] = float(c["ci95_unadjusted"][1])
    artifacts = []
    if saved is not None:
        artifacts = [(saved["config_artifact_path"], "config")]
    return params, metrics, artifacts


# ---------------------------------------------------------------------------
# LOG: MLflow (research-only tracking mirror, ADR-0007)
# ---------------------------------------------------------------------------

def log_run(tracking_uri: str, experiment: str, run_name: str,
            params: dict, metrics: dict, artifacts: list,
            artifact_location: str | None = None) -> str:
    """Log one run; returns the run_id. Raises on any MLflow failure."""
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    if artifact_location is not None:
        client = mlflow.MlflowClient(tracking_uri=tracking_uri)
        try:
            exp_id = client.create_experiment(
                experiment, artifact_location=artifact_location)
        except Exception:
            exp_id = mlflow.set_experiment(experiment).experiment_id
    else:
        exp_id = mlflow.set_experiment(experiment).experiment_id
    with mlflow.start_run(run_name=run_name, experiment_id=exp_id) as run:
        for k, v in params.items():
            mlflow.log_param(k, v)
        for k, v in metrics.items():
            mlflow.log_metric(k, float(v))
        for src, art in artifacts:
            mlflow.log_artifact(str(src), artifact_path=art)
        run_id = run.info.run_id
    return run_id


# ---------------------------------------------------------------------------
# VERIFY: fresh retrieve + exact metric round-trip + artifact byte hash
# ---------------------------------------------------------------------------

def verify_run(tracking_uri: str, run_id: str, expected_metrics: dict,
               artifact_relpath: str, source_sha256: str, retrieve_dir) -> dict:
    """Retrieve the run through the MLflow artifact API and verify every
    expected metric (exact round-trip) plus the artifact byte hash."""
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri)
    run = client.get_run(run_id)
    per_metric = {}
    for key, expected in expected_metrics.items():
        got = run.data.metrics[key]  # KeyError propagates: fail loud
        per_metric[key] = {"expected": expected, "retrieved": got,
                           "exact_match": got == expected}
    metrics_ok = all(m["exact_match"] for m in per_metric.values())
    got_path = client.download_artifacts(
        run_id, artifact_relpath, str(retrieve_dir))
    got_sha = sha256_file(Path(got_path))
    artifact_ok = got_sha == source_sha256
    return {
        "status": ("VERIFIED" if (metrics_ok and artifact_ok)
                   else "MISMATCH"),
        "run_id": run_id,
        "experiment_id": run.info.experiment_id,
        "metrics": per_metric, "metrics_ok": metrics_ok,
        "artifact": artifact_relpath,
        "source_sha256": source_sha256,
        "retrieved_sha256": got_sha, "artifact_ok": artifact_ok,
    }


def _write_status(out_dir: Path, status: str, **fields) -> None:
    rec = {"status": status,
           "written_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    rec.update(fields)
    (out_dir / STATUS_FILE).write_text(json.dumps(rec, indent=2))


# ---------------------------------------------------------------------------
# ORCHESTRATOR: compare -> save -> log -> verify
# ---------------------------------------------------------------------------

def track_and_verify(compare_fn, out_dir, tracking_uri: str, *,
                     experiment: str = DEFAULT_EXPERIMENT,
                     run_name: str = DEFAULT_RUN_NAME,
                     describe=default_describe,
                     artifact_location: str | None = None,
                     verify: bool = True) -> dict:
    """Run the full chain. compare_fn is invoked EXACTLY ONCE; a later
    logging failure never triggers a refit. On MLflow failure the canonical
    outputs stay untouched, tracking_status.json records status
    "tracking_failed", and TrackingFailure is raised to the caller."""
    out_dir = Path(out_dir)
    result = compare_fn()                       # COMPARE (once; never refit)
    saved = save_canonical_outputs(result, out_dir)   # SAVE (finalize)
    params, metrics, artifacts = describe(result, out_dir, saved)
    run_id = None
    phase = "log"
    try:
        run_id = log_run(tracking_uri, experiment, run_name,
                         params, metrics, artifacts,
                         artifact_location=artifact_location)
        if verify:
            phase = "verify"
            verdict = verify_run(tracking_uri, run_id, metrics,
                                 saved["config_artifact_relpath"],
                                 saved["config_artifact_sha256"],
                                 out_dir / "retrieved")
            status = verdict["status"]
        else:
            verdict = None
            status = "LOGGED"
    except Exception as exc:
        _write_status(out_dir, "tracking_failed", run_id=run_id,
                      phase=phase, error=f"{type(exc).__name__}: {exc}",
                      note="canonical outputs preserved untouched; no refit")
        raise TrackingFailure(
            f"tracking failed during {phase} phase; canonical outputs "
            f"preserved untouched in {out_dir}; batch NOT successful"
        ) from exc
    if status == "MISMATCH":
        _write_status(out_dir, "tracking_failed", run_id=run_id,
                      phase="verify", detail=verdict,
                      note="retrieved run mismatched logged content")
        raise TrackingFailure(
            "tracking verification MISMATCH; canonical outputs preserved "
            f"untouched in {out_dir}; batch NOT successful")
    _write_status(out_dir, status, run_id=run_id, phase=phase,
                  tracking_uri=tracking_uri,
                  metrics_sha256=saved["metrics_sha256"],
                  config_artifact_sha256=saved["config_artifact_sha256"])
    return {"status": status, "run_id": run_id,
            "experiment": experiment, "out_dir": str(out_dir), **saved}


# ---------------------------------------------------------------------------
# D-2: registered identity verification (runs BEFORE any fitting)
# ---------------------------------------------------------------------------

def _import_adapter(path) -> object:
    spec = importlib.util.spec_from_file_location(
        "lgbm_equal_info_adapter", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verify_registered_identities(freeze_path, *, adapter_module=None,
                                 runner_path=None) -> dict:
    """Re-derive every registered identity from disk and fail loud on the
    first mismatch, BEFORE any fitting. Checks: freeze config hash (per the
    registered config_hash_definition), the declared text-source identity
    convention (must equal TEXT_SOURCE_IDENTITY_CONVENTION), the three
    registered input sha256s (pa_table, features_v3, start_metrics outcome
    source - path+hash registration only; binary files, byte-exact), the
    adapter file + config hashes and its frozen hyperparameters, the
    builder-worktree harness comparison.py sha, and the wrapper/runner
    self-hashes. Text-source files (.py/.json/.md) are verified against
    their LF-normalized registered value when one is registered
    (TEXT_SOURCE_IDENTITY_CONVENTION); otherwise - and for binary files -
    the byte-exact value is verified. Byte-exact values registered under
    the prior amendment-1 convention are preserved as historical records."""
    freeze = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    cfg = freeze["config"]
    checks: dict[str, dict] = {}

    def _expect(name: str, declared, actual) -> None:
        ok = declared == actual
        checks[name] = {"declared": declared, "actual": actual, "ok": ok}
        if not ok:
            raise IdentityMismatch(
                f"{name}: registered {declared!r} != on-disk {actual!r}; "
                "refusing to fit against unregistered identities")

    def _expect_file(name: str, path, reg: dict, exact_key: str,
                     normalized_key: str | None = None) -> None:
        """Verify one registered file identity per the declared convention:
        LF-normalized for text-source files when a normalized value is
        registered, byte-exact otherwise (binary files, synthetic freezes)."""
        ident = sha256_file_identity(path)
        if (normalized_key is not None and normalized_key in reg
                and ident["class"] == "text"):
            _expect(f"{name}.{normalized_key}", reg[normalized_key],
                    ident["lf_normalized"])
            checks[f"{name}.byte_exact_observed"] = {
                "declared": reg.get(exact_key),
                "actual": ident["byte_exact"],
                "ok": reg.get(exact_key) in (None, ident["byte_exact"]),
                "note": ("informational: byte-exact value is a historical "
                         "record under the prior convention and is not "
                         "re-verified")}
        elif exact_key in reg:
            _expect(f"{name}.{exact_key}", reg[exact_key],
                    ident["byte_exact"])
        else:
            raise IdentityMismatch(
                f"{name}: no registered identity key "
                f"({normalized_key!r} or {exact_key!r})")

    _expect("config_hash_definition", freeze.get("config_hash_definition"),
            CONFIG_HASH_DEFINITION)
    _expect("text_source_identity_convention",
            cfg.get("text_source_identity_convention"),
            TEXT_SOURCE_IDENTITY_CONVENTION)
    _expect("freeze_config_sha256", freeze["config_sha256"],
            freeze_config_sha256(cfg))
    inputs = cfg["registered_inputs"]
    for key in ("pa_table", "features_v3", "start_metrics_outcome_source"):
        _expect_file(f"input.{key}", inputs[key]["path"], inputs[key],
                     "sha256")
    ad_reg = cfg["adapter"]
    _expect_file("adapter", ad_reg["path"], ad_reg,
                 "file_sha256", "file_sha256_normalized")
    adapter = adapter_module or _import_adapter(ad_reg["path"])
    _expect("adapter.config_sha256", ad_reg["config_sha256"],
            adapter.config_sha256())
    _expect("adapter.hyperparameters", cfg["lgbm_hyperparameters"],
            adapter.LGBM_EQUAL_INFO_CONFIG)
    bw = cfg["builder_worktree_harness"]
    _expect_file("harness.comparison", bw["comparison_path"], bw,
                 "comparison_sha256", "comparison_sha256_normalized")
    tw = cfg["tracking_wrapper"]
    _expect_file("wrapper", tw["path"], tw,
                 "file_sha256", "file_sha256_normalized")
    if runner_path is not None:
        _expect_file("runner", runner_path, bw,
                     "runner_sha256", "runner_sha256_normalized")
    return {"ok": True, "checked": sorted(checks), "checks": checks}
