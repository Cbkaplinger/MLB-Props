"""Focused tests for the advisory hygiene checker (Chat 3, governance slice).

Builds a synthetic mini-repository per run, proves each check detects its
representative finding, proves adversarial/refusal behaviors (no deletion, no
modification, values redacted, advisory exit codes), and proves the scanned
fixture is byte-unchanged by the checker.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repo_hygiene_check.py"
_spec = importlib.util.spec_from_file_location("repo_hygiene_check", SCRIPT)
rhc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rhc)


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "mini"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "research" / "tool").mkdir(parents=True)
    (repo / "data").mkdir()
    # duplicate-blobs pair
    (repo / "a.txt").write_text("identical content\n", encoding="utf-8")
    (repo / "b.txt").write_text("identical content\n", encoding="utf-8")
    # broken md link
    (repo / "docs" / "guide.md").write_text(
        "# Guide\nsee [missing](missing.md)\n", encoding="utf-8")
    # dead notebook reference
    (repo / "src" / "runner.py").write_text(
        'x = 1\n# see notes: ghost.ipynb\n', encoding="utf-8")
    # secret-shaped literal
    (repo / "src" / "config.py").write_text(
        'API_KEY = "supersecret12345"\n', encoding="utf-8")
    # undeclared third-party import
    (repo / "src" / "mod.py").write_text("import requests\n", encoding="utf-8")
    # pyproject: declares nothing, testpaths pinned to tests/
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "mini"\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8")
    # collected test (inside tests/) and excluded test (outside tests/)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n",
                                               encoding="utf-8")
    (repo / "research" / "tool" / "test_excluded.py").write_text(
        "def test_excluded():\n    assert True\n", encoding="utf-8")
    # ignored-but-tracked
    (repo / ".gitignore").write_text("data/\n*.log\n", encoding="utf-8")
    (repo / "data" / "keep.md").write_text("intentional\n", encoding="utf-8")
    (repo / "oops.log").write_text("log line\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "add", "-f", "data/keep.md")  # intentional ignored-but-tracked file
    _git(repo, "commit", "-m", "fixture")
    return repo


def _tree_digest(repo: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(repo.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        h.update(str(p.relative_to(repo)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _run(repo: Path, *extra: str):
    return rhc.main(["--repo", str(repo), *extra])


def _findings(repo: Path, *extra: str) -> list[dict]:
    out = tmp_findings(repo, *extra)
    return out["findings"]


def tmp_findings(repo: Path, *extra: str) -> dict:
    outpath = repo.parent / "findings.json"
    code = _run(repo, "--json", str(outpath), *extra)
    assert code == 0
    return json.loads(outpath.read_text(encoding="utf-8"))


def _by_check(repo: Path, *extra: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for f in _findings(repo, *extra):
        groups.setdefault(f["check"], []).append(f)
    return groups


def test_representative_findings_detected(fixture_repo):
    by = _by_check(fixture_repo)
    assert "duplicate-blobs" in by  # a.txt/b.txt pair
    assert "broken-links" in by     # docs/guide.md -> missing.md
    assert "dead-notebook-refs" in by  # ghost.ipynb
    assert "secret-patterns" in by  # config.py API_KEY
    assert "undeclared-imports" in by  # requests in src/mod.py
    assert "ignored-but-tracked" in by  # data/keep.md
    assert "ci-collection-gaps" in by  # research/tool/test_excluded.py
    # untracked-generated is intentionally NOT asserted here: every generated
    # file in the fixture is ignored (porcelain never lists ignored files);
    # its detection is proven by test_untracked_generated_only_for_untracked.


def test_untracked_generated_only_for_untracked(fixture_repo):
    # oops.log was committed in the fixture, so it must NOT be flagged;
    # create a real untracked generated file, check, then remove it.
    (fixture_repo / "scratch.parquet").write_bytes(b"x" * 10)
    by = _by_check(fixture_repo)
    assert "untracked-generated" in by
    (fixture_repo / "scratch.parquet").unlink()
    by2 = _by_check(fixture_repo)
    assert "untracked-generated" not in by2


def test_oversized_files_threshold(fixture_repo):
    big = fixture_repo / "big.bin"
    big.write_bytes(b"\0" * (1024 * 1024 + 10))
    _git(fixture_repo, "add", "-A")
    _git(fixture_repo, "commit", "-m", "big")
    by = _by_check(fixture_repo)
    assert "oversized-files" in by
    (fixture_repo / "big.bin").unlink()
    _git(fixture_repo, "add", "-A")
    _git(fixture_repo, "commit", "-m", "remove big")
    assert "oversized-files" not in _by_check(fixture_repo)


def test_allowlist_suppresses_findings(fixture_repo):
    allow = fixture_repo.parent / "allow.json"
    allow.write_text(json.dumps({
        "duplicate-blobs": ["a.txt", "b.txt"],
        "ignored-but-tracked": ["data/keep.md"],
        "ci-collection-gaps": ["research/tool/test_excluded.py"],
    }), encoding="utf-8")
    by = _by_check(fixture_repo, "--allowlist", str(allow))
    assert "duplicate-blobs" not in by
    assert "ignored-but-tracked" not in by
    assert "ci-collection-gaps" not in by


def test_secret_values_never_printed(fixture_repo, capsys):
    _run(fixture_repo)
    captured = capsys.readouterr()
    assert "supersecret12345" not in captured.out
    assert "supersecret12345" not in captured.err


def test_fixture_unchanged_by_checker(fixture_repo):
    before = _tree_digest(fixture_repo)
    _run(fixture_repo, "--strict")
    _run(fixture_repo)
    assert _tree_digest(fixture_repo) == before


def test_strict_exit_code_and_operational_errors(fixture_repo):
    # advisory finding + --strict => 3
    assert _run(fixture_repo, "--strict") == 3
    # non-repo => operational error 2
    assert _run(fixture_repo.parent, "--repo", str(fixture_repo.parent)) == 2


def test_dynamic_import_caveat_not_claimed_dead(fixture_repo):
    # adversarial: a module loaded ONLY via importlib must not produce a
    # dead-code finding — the checker has no dead-code check at all, and this
    # test pins that refusal into the contract.
    checks = {f["check"] for f in _findings(fixture_repo)}
    assert not any("dead" in c and c != "dead-notebook-refs" for c in checks)


def test_deletion_and_modification_refusal(fixture_repo):
    # the tool must not add, delete, or modify ANY tracked or untracked file
    before = _tree_digest(fixture_repo)
    _run(fixture_repo, "--json", str(fixture_repo / "out.json"))
    # only the explicitly requested --json output may exist
    assert (fixture_repo / "out.json").is_file()
    (fixture_repo / "out.json").unlink()
    assert _tree_digest(fixture_repo) == before


def test_no_network_and_no_module_imports(fixture_repo):
    # structural proof: the tool source contains no network/subprocess-pip/
    # importlib patterns beyond the git subprocess it owns.
    src = SCRIPT.read_text(encoding="utf-8")
    assert "urllib" not in src and "requests" not in src
    assert "pip install" not in src
    assert "import_module" not in src and "__import__" not in src
    assert "subprocess.run" in src  # git only
    calls = re.findall(r'subprocess\.run\(\s*\[([^,\]]+)', src)
    assert set(calls) == {'"git"'}
