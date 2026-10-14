"""Artifact-root declaration for the P1 harness test suite.

The executed P1 harness artifacts (data/*.parquet, reports/*.json) live in
the private external lake and are NEVER committed. This conftest declares
the artifact root explicitly, with the expected files and their sha256
hashes as recorded in the executed run's reports/manifest.json
(p1-harness-v2, run 2026-10-13T04:23:45+00:00).

Artifact root resolution (single switch, no path fallbacks):

    P1_HARNESS_ARTIFACT_ROOT  -- absolute path of the executed run
                                 directory (the one that contains data/
                                 and reports/), e.g.
                                 <external lake>\\p1-harness-v2

Lane policy (enforced by `require_artifact`):

- Default portable lane (env var unset): artifact-dependent tests SKIP
  with a precise reason naming the missing file. Parsing, schema, and
  assertion failures NEVER become skips -- the skip decision is made
  solely on file existence, before any bytes are read.
- Required-artifact INTEGRATION lane (`pytest -m integration`), or any
  run with the env var set: a missing or hash-mismatched input FAILS.
  Hash mismatch FAILS in every lane (wrong bytes are never silently
  tolerated).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent
REPO_ROOT = HARNESS.parents[2]

ARTIFACT_ROOT_ENV = "P1_HARNESS_ARTIFACT_ROOT"

# Declared executed-artifact manifest (p1-harness-v2 reports/manifest.json
# "data_sha256", verified byte-for-byte against the private lake on
# 2026-10-13). Relative to the artifact root.
EXPECTED_ARTIFACTS: dict[str, str] = {
    "data/pa_table.parquet": (
        "e30d8561d8d0fbb9ab0eae562076312a29eeb1476172d533c3d93570959a85f0"
    ),
    "data/features.parquet": (
        "b2ec8c908159a6089c5b73a4ca7fbca2ded81aa67cd87db908d2c50f457e9b98"
    ),
    "data/dev_predictions.parquet": (
        "d848f6770e637db7790911e8a12be7b6a9fdf9669a04a420e11a31ef4a73d4ba"
    ),
    "data/eval_predictions.parquet": (
        "19c0693ad252aa9f3e16f1f0ca90dea05ccebf2e01565f18375706fcabfa24e9"
    ),
}


def _integration_mode(config: pytest.Config) -> bool:
    """True when the required-artifact lane was requested (-m integration)."""
    try:
        marker = config.getoption("-m", default="") or ""
    except (ValueError, KeyError):
        marker = getattr(config.option, "markexpr", "") or ""
    return marker.strip() == "integration"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact_root() -> Path | None:
    raw = os.environ.get(ARTIFACT_ROOT_ENV, "").strip()
    return Path(raw) if raw else None


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Fail fast in the required-artifact lane when the declared root is
    unusable, so integration tests fail on configuration, not mid-read."""
    if not _integration_mode(config):
        return
    root = _artifact_root()
    if root is None:
        pytest.fail(
            f"INTEGRATION lane requires the artifact root: set "
            f"{ARTIFACT_ROOT_ENV} to the executed p1-harness-v2 run directory "
            f"(expected files: {sorted(EXPECTED_ARTIFACTS)})"
        )
        return
    if not root.is_dir():
        pytest.fail(
            f"{ARTIFACT_ROOT_ENV}={root} is not an existing directory "
            f"(INTEGRATION lane requires the executed run directory)"
        )


@pytest.fixture(scope="session")
def require_artifact(pytestconfig: pytest.Config):
    """Return the absolute path of a declared artifact, enforcing lane rules.

    - env unset + portable lane: SKIP naming the missing file (existence
      check only; nothing is read before this decision).
    - INTEGRATION lane or env set: missing file FAILS (named).
    - present: sha256 must match the declared manifest -- a mismatch FAILS
      in every lane. Any read/parse/assert error downstream stays a test
      failure, never a skip.
    """

    def _require(rel_path: str) -> Path:
        expected = EXPECTED_ARTIFACTS.get(rel_path)
        if expected is None:
            pytest.fail(
                f"artifact {rel_path!r} is not declared in conftest.py "
                f"EXPECTED_ARTIFACTS; add it with its sha256 or fix the path"
            )
        root = _artifact_root()
        if root is None:
            if _integration_mode(pytestconfig):
                pytest.fail(
                    f"required artifact {rel_path} is absent: "
                    f"{ARTIFACT_ROOT_ENV} is not set (INTEGRATION lane; "
                    f"private lake, never committed)"
                )
            pytest.skip(
                f"external artifact <{ARTIFACT_ROOT_ENV}>/{rel_path} is absent: "
                f"{ARTIFACT_ROOT_ENV} not set and default is the portable "
                f"lane (private lake, never committed; run "
                f"`pytest -m integration` with {ARTIFACT_ROOT_ENV} pointing "
                f"at the executed run directory to require it)"
            )
        path = root / rel_path
        if not path.exists():
            if _integration_mode(pytestconfig):
                pytest.fail(
                    f"required artifact file is missing: {path} "
                    f"(declared under {ARTIFACT_ROOT_ENV}; INTEGRATION lane)"
                )
            pytest.skip(
                f"external artifact file is missing: {path} "
                f"(declared under {ARTIFACT_ROOT_ENV}; portable lane)"
            )
        actual = _sha256(path)
        if actual != expected:
            pytest.fail(
                f"artifact hash mismatch: {path} sha256 {actual} != declared "
                f"{expected} (wrong or stale bytes; failing in every lane)"
            )
        return path

    return _require
