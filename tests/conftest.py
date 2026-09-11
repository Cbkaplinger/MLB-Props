"""Shared pytest fixtures: artifact-dependent tests skip cleanly in CI.

`artifacts/` and `data/` are gitignored by design (provenance lives on the
ops box, not in the repo). Any test reading them must go through
`artifact_path()` so CI stays green while local runs exercise full data.
Full-suite-local is the source of truth; CI guards shared logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def artifact_path(*parts: str) -> Path:
    """Return repo-rooted path, or skip the test if it is absent (CI)."""
    p = ROOT.joinpath(*parts)
    if not p.exists():
        pytest.skip(f"missing local artifact (CI-safe skip): {p}")
    return p
