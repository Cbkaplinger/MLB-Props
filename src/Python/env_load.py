"""Load local ``.env`` into ``os.environ`` (no-op if missing)."""

from __future__ import annotations

from pathlib import Path

from Python import config


def load_project_dotenv() -> Path | None:
    """Load ``PROJECT_ROOT/.env`` if present. Returns the path loaded or None."""
    path = config.PROJECT_ROOT / ".env"
    if not path.exists():
        return None
    try:
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "python-dotenv is required to load .env. "
            "Run: pip install python-dotenv"
        ) from exc
    load_dotenv(path, override=False)
    return path
