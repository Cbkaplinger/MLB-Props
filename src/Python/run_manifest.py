"""Shared run manifests (OBS-1): one small provenance record per pipeline run.

Every scheduled and simulation run emits the same manifest so a downstream
consumer can tell whether its inputs are fresh, compatible, and complete —
without a central orchestrator. Manifests are display/provenance only: they
never gate selection, staking, paging, or settlement (gates arrive with
DATA-1A/OPS-1B under separate named orders).

Run statuses (owner 2026-09-17):
- ``SUCCESS_FRESH`` — ran on current inputs, outputs trustworthy.
- ``SUCCESS_NO_BETS`` — valid zero-bet run (a zero-bet day is valid).
- ``DEGRADED_NO_PAGE`` — ran degraded; nothing paged on stale output.
- ``FAILED`` — run or inputs untrustworthy.
- ``SKIPPED_OFFSEASON`` — season guard skipped execution.

No-bet reason codes (recorded when known; the board owns detection):
``NO_SLATE / NO_ELIGIBLE / MISSING_DATA / NO_QUOTES / STALE_QUOTES /
BELOW_FLOOR / VETOED / ALREADY_PAGED / OPS_FAILURE``.

``notification_key()`` builds the shared idempotency key groundwork for
OPS-1B (slate + prop + versions + ticket-set hash). Recording, not
enforcement, in this pass.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_STATUSES = (
    "SUCCESS_FRESH",
    "SUCCESS_NO_BETS",
    "DEGRADED_NO_PAGE",
    "FAILED",
    "SKIPPED_OFFSEASON",
)

NO_BET_REASONS = (
    "NO_SLATE",
    "NO_ELIGIBLE",
    "MISSING_DATA",
    "NO_QUOTES",
    "STALE_QUOTES",
    "BELOW_FLOOR",
    "VETOED",
    "ALREADY_PAGED",
    "OPS_FAILURE",
)

_REASON_STATUSES = ("SUCCESS_NO_BETS", "DEGRADED_NO_PAGE")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run(
    pipeline_id: str,
    *,
    prop_id: str = "pitcher_strikeouts",
    mode: str = "live",
    slate_date: str | None = None,
    policy_version: str | None = None,
    model_version: str | None = None,
    calibration_version: str | None = None,
    feature_version: str | None = None,
) -> dict[str, Any]:
    """Open a manifest. Call :func:`finish_run` before writing."""
    return {
        "run_id": uuid.uuid4().hex,
        "pipeline_id": str(pipeline_id),
        "prop_id": str(prop_id),
        "mode": str(mode),
        "status": "RUNNING",
        "started_at_utc": utcnow_iso(),
        "finished_at_utc": None,
        "slate_date": slate_date,
        "as_of_utc": None,
        "input_cutoff_utc": None,
        "model_version": model_version,
        "calibration_version": calibration_version,
        "policy_version": policy_version,
        "feature_version": feature_version,
        "input_artifacts": [],
        "output_artifacts": [],
        "input_rows": {},
        "output_rows": {},
        "population_funnel": {},
        "data_quality": {},
        "warnings": [],
        "errors": [],
        "duration_seconds": None,
        "notification_key": None,
        "no_bet_reason": None,
    }


def finish_run(
    manifest: dict[str, Any],
    status: str,
    *,
    no_bet_reason: str | None = None,
    notification_key: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    input_rows: dict[str, int] | None = None,
    output_rows: dict[str, int] | None = None,
    input_artifacts: list[str] | None = None,
    output_artifacts: list[str] | None = None,
    population_funnel: dict[str, int] | None = None,
    data_quality: dict[str, Any] | None = None,
    as_of_utc: str | None = None,
    input_cutoff_utc: str | None = None,
    policy_version: str | None = None,
    model_version: str | None = None,
    calibration_version: str | None = None,
    feature_version: str | None = None,
) -> dict[str, Any]:
    """Close a manifest with a terminal status. Validates status + reason."""
    if status not in RUN_STATUSES:
        raise ValueError(f"unknown run status: {status!r}")
    if no_bet_reason is not None:
        if no_bet_reason not in NO_BET_REASONS:
            raise ValueError(f"unknown no-bet reason: {no_bet_reason!r}")
        if status not in _REASON_STATUSES:
            raise ValueError(
                f"no-bet reason requires status in {_REASON_STATUSES}, got {status!r}"
            )
    finished = utcnow_iso()
    try:
        started = datetime.fromisoformat(str(manifest.get("started_at_utc") or finished))
        duration = max(0.0, (datetime.fromisoformat(finished) - started).total_seconds())
    except ValueError:
        duration = 0.0
    manifest.update({
        "status": status,
        "finished_at_utc": finished,
        "duration_seconds": round(duration, 3),
        "no_bet_reason": no_bet_reason,
        "notification_key": notification_key,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "input_rows": dict(input_rows or {}),
        "output_rows": dict(output_rows or {}),
        "input_artifacts": list(input_artifacts or []),
        "output_artifacts": list(output_artifacts or []),
        "population_funnel": dict(population_funnel or {}),
        "data_quality": dict(data_quality or {}),
        "as_of_utc": as_of_utc,
        "input_cutoff_utc": input_cutoff_utc,
        "policy_version": policy_version,
        "model_version": model_version,
        "calibration_version": calibration_version,
        "feature_version": feature_version,
    })
    return manifest


def notification_key(
    *,
    slate_date: str,
    prop_id: str,
    policy_version: str,
    model_version: str,
    calibration_version: str,
    selection_window: str,
    ticket_hash: str,
) -> str:
    """Deterministic shared idempotency key (OPS-1B groundwork).

    ``ticket_hash`` is a hex digest over the normalized ticket set, computed
    by the caller (e.g. sha256 of sorted stable_ticket_ids). Same batch in,
    same key out; any ticket difference flips the key.
    """
    basis = "|".join([
        str(slate_date), str(prop_id), str(policy_version), str(model_version),
        str(calibration_version), str(selection_window), str(ticket_hash),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def ticket_set_hash(ticket_ids: list[str]) -> str:
    """Order-invariant digest over a ticket-id set."""
    basis = "\n".join(sorted(str(t) for t in ticket_ids))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def manifest_path(odds_dir: str | Path, pipeline_id: str) -> Path:
    stem = str(pipeline_id).lower().replace("-", "_")
    return Path(odds_dir) / f"run_manifest_{stem}_latest.json"


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    """Atomically write a manifest. Raises on failure (use emit helper in jobs)."""
    from Python.odds_ledger import atomic_write_text

    out = Path(path)
    atomic_write_text(out, json.dumps(manifest, indent=2, default=str))
    return out


def emit_manifest_safely(manifest: dict[str, Any], path: str | Path) -> bool:
    """Write a manifest without ever breaking the calling job. Returns ok."""
    try:
        write_manifest(manifest, path)
        return True
    except Exception:
        return False


def artifact_version(path: str | Path, prefix: str) -> str | None:
    """Content-hash version stamp (`prefix:sha12`) for a pin/policy file.

    Versions are hashes, not semantic numbers: any byte change flips the
    stamp, which is exactly what compatibility checks need. Missing file =
    None (unknown, never fabricated).
    """
    try:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None
    return f"{prefix}:{digest}"


def manifest_from_alert(
    *,
    any_sent: bool,
    failure_message: str = "",
    warnings: list[str] | None = None,
    slate_date: str | None = None,
    input_rows: dict[str, int] | None = None,
    output_rows: dict[str, int] | None = None,
    as_of_utc: str | None = None,
    input_cutoff_utc: str | None = None,
    policy_version: str | None = None,
    model_version: str | None = None,
    calibration_version: str | None = None,
    feature_version: str | None = None,
) -> dict[str, Any]:
    """Build the serve-pipeline manifest for one alert run (pure)."""
    manifest = new_run("P4-SERVE", slate_date=slate_date)
    extra = dict(
        input_rows=input_rows,
        output_rows=output_rows,
        as_of_utc=as_of_utc,
        input_cutoff_utc=input_cutoff_utc,
        policy_version=policy_version,
        model_version=model_version,
        calibration_version=calibration_version,
        feature_version=feature_version,
    )
    if str(failure_message or "").strip():
        return finish_run(
            manifest, "FAILED",
            errors=[str(failure_message).strip()[:300]], **extra,
        )
    warn = [str(w)[:300] for w in (warnings or []) if str(w).strip()]
    if bool(any_sent):
        return finish_run(manifest, "SUCCESS_FRESH", warnings=warn or None, **extra)
    return finish_run(
        manifest,
        "DEGRADED_NO_PAGE",
        warnings=["alert produced no send; board state unknown at this layer"],
        **extra,
    )


def manifest_from_drift(
    *,
    verdict: str,
    today: str,
    failing_checks: list[str] | None = None,
    n_settled: int | None = None,
    policy_version: str | None = None,
    model_version: str | None = None,
    calibration_version: str | None = None,
    feature_version: str | None = None,
    as_of_utc: str | None = None,
) -> dict[str, Any]:
    """Build the settle/monitor-pipeline manifest for one drift run (pure).

    Drift GREEN means fresh inputs + all gates held; YELLOW/RED degrade.
    """
    manifest = new_run("P6-SETTLE", slate_date=today)
    checks = list(failing_checks or [])
    rows = {"settled": int(n_settled)} if n_settled is not None else None
    extra = dict(
        input_rows=rows,
        policy_version=policy_version,
        model_version=model_version,
        calibration_version=calibration_version,
        feature_version=feature_version,
        as_of_utc=as_of_utc,
    )
    if verdict == "GREEN":
        return finish_run(manifest, "SUCCESS_FRESH", **extra)
    if verdict == "YELLOW":
        return finish_run(manifest, "DEGRADED_NO_PAGE", warnings=checks, **extra)
    return finish_run(manifest, "FAILED",
                      errors=checks or [f"verdict={verdict}"], **extra)
