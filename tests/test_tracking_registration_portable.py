"""Portable tracking-registration verification lane (CI-runnable, lake-free).

Verifies that the frozen tracking registrations are verifiable from the REPO
TREE ALONE - fresh clone, no worktrees, no private lake. This is the CI lane
for the registration-integrity defect class found by review in the
amendment-3/4 corrections (registered wrapper identity vs bytes at the
registered path): a fresh clone can now re-derive every repo-portable
registered identity and fail loud on drift.

Verified here (read-only; no frozen registration file is modified):
- freeze_lgbm_equal_info_v1/v2 config_sha256 recomputes exactly from the
  committed top-level config per the shared registered hash definition;
- every registered file identity whose registered path lives under a
  WORKTREE is carried byte-identically (LF-normalized per
  TEXT_SOURCE_IDENTITY_CONVENTION) by the repo-tree file at the same
  repo-relative path (harness wrapper / comparison / runners);
- the amendment-2 portability precondition holds (harness/*.py pinned
  text eol=lf in .gitattributes) so a fresh clone materializes the
  LF-registered bytes;
- freeze_pregame_pa_ext_v2.json parses with a structurally valid
  registered-pin format (null or 64-hex). Its scientific content is PR
  #21's exact-head review lane and is deliberately NOT asserted here.

Explicitly skipped, by design and declared (never silent):
- registered paths under the private lake (MLB-Props-Research: pa_table,
  features_v3, start_metrics_v2, lake adapter config, mlflow.db) - verified
  at execution time by verify_registered_identities(), unverifiable from a
  clone; this lane records their count as declared skips;
- entries under historical_registrations and CRLF-historical keys -
  historical records preserved verbatim, never re-verified.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "research" / "offseason_2026" / "specs" / "count-eval-v2-spec" / "harness"
FREEZE_V1 = HARNESS / "freeze_lgbm_equal_info_v1.json"
FREEZE_V2 = HARNESS / "freeze_lgbm_equal_info_v2.json"
FREEZE_PAEXT = ROOT / "research" / "offseason_2026" / "pregame_pa_ext" / "freeze_pregame_pa_ext_v2.json"

HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Both freezes declare the same hash definition; the lane follows the
# registered definition rather than a paraphrase of it.
CANONICAL_HASH_DEFINITION = (
    "sha256 over json.dumps(config, sort_keys=True, separators=(',',':'))"
    ".encode('utf-8') of the 'config' object in this file"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _lf_norm_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _iter_sha_pairs(obj, path=""):
    """Yield (json_path, registered_path, sha_key, sha_value) for every
    registered worktree-pathed (path, *sha256*) pair. Path keys are 'path'
    or '<name>_path' (e.g. comparison_path / runner_path) with sibling
    '<name>_sha256[...]' identity fields."""
    if isinstance(obj, dict):
        for path_key, reg_path in obj.items():
            if not isinstance(reg_path, str) or "MLB-Props-worktrees" not in reg_path:
                continue
            if path_key != "path" and not path_key.endswith("_path"):
                continue
            prefix = path_key[:-len("path")] if path_key != "path" else ""
            for k, v in obj.items():
                if (k != path_key and isinstance(v, str) and HEX64.match(v)
                        and k.startswith(prefix) and k != "config_sha256"):
                    yield f"{path}/{path_key}", reg_path, k, v
        for k, v in obj.items():
            yield from _iter_sha_pairs(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_sha_pairs(v, f"{path}[{i}]")


def _current_pairs(freeze: dict):
    """Current-registration pairs only: historical_registrations entries,
    CRLF-historical keys, and config_sha256 fields (the lake adapter's
    CONFIG identity - a different artifact than the file at `path`, verified
    at execution time by the runner's config_sha256()) are excluded."""
    for jpath, reg_path, sha_key, sha_val in _iter_sha_pairs(freeze["config"]):
        if "historical_registrations" in jpath or "historical" in sha_key:
            continue
        if sha_key == "config_sha256":
            continue
        yield jpath, reg_path, sha_key, sha_val


def _lake_skip_count() -> int:
    """Count CURRENT registered identities whose registered path is under
    the private lake (declared skips - unverifiable from a clone)."""
    n = 0
    for freeze_path in (FREEZE_V1, FREEZE_V2):
        freeze = _load(freeze_path)
        stack = [("config", freeze["config"])]
        while stack:
            path, obj = stack.pop()
            if isinstance(obj, dict):
                reg_path = obj.get("path")
                if (isinstance(reg_path, str) and "MLB-Props-Research" in reg_path
                        and any(HEX64.match(v) for v in obj.values()
                                if isinstance(v, str))):
                    n += 1
                for k, v in obj.items():
                    stack.append((f"{path}/{k}", v))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    stack.append((f"{path}[{i}]", v))
    return n


def test_freeze_config_sha256_recomputes_from_repo_tree():
    for freeze_path in (FREEZE_V1, FREEZE_V2):
        freeze = _load(freeze_path)
        assert freeze["config_hash_definition"] == CANONICAL_HASH_DEFINITION, (
            f"{freeze_path.name}: registered hash definition changed - "
            f"this lane must be updated to follow it, never to assume it"
        )
        blob = json.dumps(freeze["config"], sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        recomputed = hashlib.sha256(blob).hexdigest()
        assert recomputed == freeze["config_sha256"], (
            f"{freeze_path.name}: registered config_sha256 does not recompute "
            f"from the committed config - registration drift, the exact "
            f"amendment-3/4 defect class"
        )


def test_worktree_registered_text_identities_are_repo_portable():
    verified = []
    for freeze_path in (FREEZE_V1, FREEZE_V2):
        freeze = _load(freeze_path)
        for jpath, reg_path, sha_key, sha_val in _current_pairs(freeze):
            tail = reg_path.split("MLB-Props-worktrees", 1)[1].lstrip("\\/")
            repo_rel = tail.split("\\", 1)[1].replace("\\", "/")
            repo_file = ROOT / repo_rel
            assert repo_file.exists(), (
                f"{freeze_path.name}: registered worktree identity {jpath} "
                f"maps to {repo_rel}, absent from the repo tree - the "
                f"registration is not repo-portable"
            )
            actual = _lf_norm_sha256(repo_file.read_bytes())
            assert actual == sha_val, (
                f"{freeze_path.name}: registered {sha_key} ({sha_val[:12]}...) "
                f"does not match repo-tree bytes at {repo_rel} "
                f"(got {actual[:12]}...) - amendment-3/4 drift class caught"
            )
            verified.append((freeze_path.name, sha_key.split("_normalized")[0],
                             repo_rel))
    # The lane must actually verify the core tracking components: the shared
    # wrapper (identical bytes bound by BOTH freezes) and at least one
    # comparison + runner identity per freeze.
    names = {k for _, k, _ in verified}
    assert {"file_sha256", "comparison_sha256", "runner_sha256"} <= names
    wrapper_rels = {rel for (_, k, rel) in verified if k == "file_sha256"
                    and rel.endswith("track_and_verify.py")}
    assert wrapper_rels == {
        "research/offseason_2026/specs/count-eval-v2-spec/harness/track_and_verify.py"
    }, "both freezes must bind the ONE shared wrapper"


def test_lake_only_registrations_are_declared_skips():
    assert _lake_skip_count() >= 3, (
        "expected the declared lake-only skip set (registered_inputs x2 "
        "freezes + lake-bound components); zero would mean the walker "
        "silently dropped registrations"
    )


def test_amendment2_eol_portability_precondition():
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "count-eval-v2-spec/harness/*.py text eol=lf" in gitattributes


def test_pregame_pa_freeze_structural_and_pin_format():
    freeze = _load(FREEZE_PAEXT)
    assert isinstance(freeze.get("freeze_id"), str) and freeze["freeze_id"]
    pin = freeze.get("checkpoint_sha256_expected")
    assert pin is None or HEX64.match(pin), (
        "registered checkpoint pin must be null (gate disabled) or 64-hex"
    )
    assert isinstance(freeze.get("registration_status"), str)
