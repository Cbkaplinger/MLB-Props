"""Load local ``.env`` into ``os.environ`` (no-op if missing)."""

from __future__ import annotations

import os
from pathlib import Path

# Keep this free of ``Python.config`` imports: config freezes paths at import
# time, so dotenv must be loadable before config is first imported.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_PATH_ENV_KEYS = (
    "MLB_PROPS_DATA_DIR",
    "MLB_PROPS_OUTPUT_DIR",
    "MLB_PROPS_SAVANT_DATA_DIR",
)


def _scrub_placeholder_paths() -> None:
    """Drop example ``/path/to/...`` values left in process env or ``.env``."""
    for name in _PATH_ENV_KEYS:
        val = (os.environ.get(name) or "").strip().strip("\"'")
        norm = val.replace("\\", "/").lower()
        if not val:
            continue
        if "/path/to/" in norm or val.lower() in {"your_key_here", "changeme"}:
            os.environ.pop(name, None)


def load_project_dotenv(*, override: bool = False) -> Path | None:
    """Load ``PROJECT_ROOT/.env`` if present. Returns the path loaded or None.

    ``override=False`` (default): existing process env wins (shell exports).
    ``override=True``: ``.env`` wins — use in long-lived kernels / notebook
    workers where a stale ``MLB_PROPS_*`` may linger after editing ``.env``.
    """
    path = _PROJECT_ROOT / ".env"
    if not path.exists():
        _scrub_placeholder_paths()
        return None
    try:
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "python-dotenv is required to load .env. "
            "Run: pip install python-dotenv"
        ) from exc
    load_dotenv(path, override=override)
    _scrub_placeholder_paths()
    return path
