"""Workspace boundary guards (audit §AF). Import-safe: stdlib only."""

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parents[1]

# Modules that must never be imported from workspace code (writers/pagers/scheduler).
FORBIDDEN_MODULES = frozenset({
    "poll_odds",
    "grade_odds_ledger",
    "grade_projections",
    "log_projections",
    "send_morning_alert",
    "check_nightly_drift",
    "frozen_edge_watch",
    "close_watcher",
    "run_close_sweep",
    "modal_app",
    "score_slate",
    "run_daily",
})

# Import-safe canonical modules (read-only use).
ALLOWED_CANONICAL = frozenset({
    "market",
    "count_layer",
    "prob_calibration",
    "odds_ledger",
    "likelihoods",
    "training",
})

# Only writable roots (absolute, resolved).
ALLOWED_WRITE_ROOTS = (
    WORKSPACE_ROOT / "specs",
    WORKSPACE_ROOT / "manifests",
    WORKSPACE_ROOT / "datasets",
    WORKSPACE_ROOT / "experiments",
    WORKSPACE_ROOT / "reports",
    WORKSPACE_ROOT / "artifacts",
)


class BoundaryError(RuntimeError):
    pass


def assert_workspace_path(path) -> Path:
    """Raise unless path resolves beneath an allowed workspace write root."""
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    rp = p.resolve()
    for root in ALLOWED_WRITE_ROOTS:
        try:
            rp.relative_to(root.resolve())
            return rp
        except ValueError:
            continue
    raise BoundaryError(f"Write outside workspace roots refused: {rp}")


def assert_not_forbidden(module_name: str) -> None:
    base = module_name.split(".")[0]
    if base in FORBIDDEN_MODULES:
        raise BoundaryError(f"Import of never-import module refused: {module_name}")
