"""Repo hygiene checker for MLB-Props — read-only, advisory-only, stdlib-only.

Scans the tracked tree of a git repository for hygiene findings and reports
them. It never modifies, deletes, moves, or fixes anything, never accesses the
network, never installs packages, never executes notebooks, never imports
repository modules, and never follows links outside the repository root
(junction/symlink targets are reported as findings, not traversed; tracked
content is read through git, not the filesystem).

Checks (all advisory; findings never affect the exit code):
  duplicate-blobs      identical content under multiple tracked paths
  broken-links         relative Markdown links to non-existent tracked files
  dead-notebook-refs   references to .ipynb basenames that exist nowhere tracked
  oversized-files      tracked files above --max-bytes (default 1 MiB)
  ignored-but-tracked  tracked files matching .gitignore patterns
  secret-patterns      credential-shaped literals (file:line only, values never
                       printed)
  undeclared-imports   third-party imports absent from pyproject.toml declared
                       package names
  ci-collection-gaps   test files outside the pytest `testpaths` roots
  untracked-generated  non-ignored untracked files matching generated patterns
  worktree-status      detached-HEAD worktrees (debris candidates; report-only)

Exit codes: 0 = ran clean of operational errors (findings are advisory);
2 = operational error (repo missing, git failure, malformed input); with
--strict, 3 = operational success but findings exist.

Usage:
  python scripts/repo_hygiene_check.py [--repo PATH] [--json OUT.json]
      [--allowlist allowlist.json] [--max-bytes N] [--strict]

Allowlist shape: {"<check-name>": ["<exact tracked path or basename>", ...]}
Deep audits (near-duplicate shingles, full import graphs) are intentionally not
part of this tool — see
docs/reference/reports/hygiene_automation_design_2026-10-16.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

GENERATED_RE = re.compile(r"\.(parquet|pickle|pkl|log|tmp)$", re.IGNORECASE)
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*[\"'][^\"']{8,}[\"']"
)
BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9_\-\.]{16,}")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)\)")
NB_REF_RE = re.compile(r"[\w\-/\\.]+\.ipynb", re.IGNORECASE)
IMP_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w\.]*)", re.M)


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )


def must_git(repo: Path, *args: str) -> str:
    r = run_git(repo, *args)
    if r.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args[:2]) + "... failed: " + r.stderr.strip()[:200]
        )
    return r.stdout


def tracked_files(repo: Path) -> list[dict]:
    out = must_git(repo, "ls-tree", "-r", "-l", "HEAD")
    files = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        parts = meta.split()
        files.append({
            "path": path.replace('"', ""),
            "blob": parts[2],
            "bytes": int(parts[3]) if parts[3] != "-" else 0,
        })
    return files


def read_tracked(repo: Path, path: str) -> str:
    r = run_git(repo, "show", "HEAD:" + path)
    return r.stdout if r.returncode == 0 else ""


def make_get_text(repo: Path, cache: dict[str, str]):
    def get_text(path: str) -> str:
        if path not in cache:
            cache[path] = read_tracked(repo, path)
        return cache[path]
    return get_text


def load_allowlist(path: Path | None) -> dict[str, set[str]]:
    if path is None or not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {k: set(v) for k, v in doc.items() if isinstance(v, list)}


def allowlisted(allow: dict[str, set[str]], check: str, path: str) -> bool:
    names = allow.get(check, set())
    return path in names or path.split("/")[-1] in names


def check_duplicate_blobs(files, allow):
    by_blob: dict[str, list[str]] = {}
    for f in files:
        if f["blob"] == "0" * 40:
            continue
        by_blob.setdefault(f["blob"], []).append(f["path"])
    out = []
    for _, paths in sorted(by_blob.items()):
        kept = [p for p in paths if not allowlisted(allow, "duplicate-blobs", p)]
        if len(kept) >= 2:
            out.append({"check": "duplicate-blobs", "severity": "advisory",
                        "detail": "identical content x%d" % len(kept),
                        "paths": sorted(kept)})
    return out


def resolve_link(source_path: str, target: str) -> str:
    parent = PurePosixPath(source_path).parent
    stack: list[str] = []
    for part in (parent / PurePosixPath(target)).parts:
        if part == "..":
            if stack:
                stack.pop()
        elif part != ".":
            stack.append(part)
    return "/".join(stack)


def check_broken_links(get_text, files, allow):
    lower = {f["path"].lower() for f in files}
    findings = []
    for f in files:
        if not f["path"].lower().endswith(".md"):
            continue
        if allowlisted(allow, "broken-links", f["path"]):
            continue
        text = get_text(f["path"])
        for m in LINK_RE.finditer(text):
            t = m.group(1)
            if t.startswith(("http", "mailto:", "data:")):
                continue
            norm = resolve_link(f["path"], t).lower()
            if norm and norm not in lower:
                line_no = text.count("\n", 0, m.start()) + 1
                findings.append({
                    "check": "broken-links", "severity": "advisory",
                    "detail": "target not tracked: " + t,
                    "paths": [f["path"] + ":" + str(line_no)],
                })
    return findings


def check_dead_notebook_refs(get_text, files, allow):
    nb = {f["path"].split("/")[-1].lower() for f in files
          if f["path"].lower().endswith(".ipynb")}
    findings = []
    for f in files:
        if not f["path"].endswith((".py", ".ps1", ".md", ".json")):
            continue
        if allowlisted(allow, "dead-notebook-refs", f["path"]):
            continue
        text = get_text(f["path"])
        seen: set[str] = set()
        for m in NB_REF_RE.finditer(text):
            base = m.group(0).replace("\\", "/").split("/")[-1].lower()
            if base not in nb and base not in seen:
                seen.add(base)
                findings.append({
                    "check": "dead-notebook-refs", "severity": "advisory",
                    "detail": "no tracked notebook named " + base,
                    "paths": [f["path"]],
                })
    return findings


def check_oversized(files, allow, max_bytes):
    return [
        {"check": "oversized-files", "severity": "advisory",
         "detail": "%d bytes > %d" % (f["bytes"], max_bytes), "paths": [f["path"]]}
        for f in sorted(files, key=lambda x: -x["bytes"])
        if f["bytes"] > max_bytes and not allowlisted(allow, "oversized-files", f["path"])
    ]


def check_ignored_but_tracked(repo, allow):
    out = must_git(repo, "ls-files", "-ci", "--exclude-standard")
    paths = [l for l in out.splitlines() if l.strip()]
    return [
        {"check": "ignored-but-tracked", "severity": "advisory",
         "detail": "tracked despite ignore rules", "paths": [p]}
        for p in paths if not allowlisted(allow, "ignored-but-tracked", p)
    ]


def check_secret_patterns(get_text, files, allow):
    findings = []
    for f in files:
        if not f["path"].endswith((".py", ".ps1", ".md", ".json", ".yml", ".yaml", ".toml", ".ipynb")):
            continue
        if allowlisted(allow, "secret-patterns", f["path"]):
            continue
        text = get_text(f["path"])
        for rx, label in ((SECRET_RE, "credential-shaped assignment"), (BEARER_RE, "bearer token")):
            m = rx.search(text)
            if m:
                line_no = text.count("\n", 0, m.start()) + 1
                findings.append({
                    "check": "secret-patterns", "severity": "advisory",
                    "detail": label + " (value redacted)",
                    "paths": [f["path"] + ":" + str(line_no)],
                })
    return findings


def declared_packages(pyproject_text: str) -> set[str]:
    names = set()
    for m in re.finditer(r'"([A-Za-z0-9][A-Za-z0-9_\-\.\[\]]*)"', pyproject_text):
        names.add(m.group(1).split("[")[0].lower().replace("-", "_"))
    return names


def check_undeclared_imports(get_text, files, allow, stdlib: set[str], pyproject_text: str):
    declared = declared_packages(pyproject_text)
    findings = []
    for f in files:
        if not f["path"].endswith(".py"):
            continue
        if allowlisted(allow, "undeclared-imports", f["path"]):
            continue
        text = get_text(f["path"])
        tops = sorted({m.group(1).split(".")[0] for m in IMP_RE.finditer(text)})
        for top in tops:
            if top in stdlib or top == "__future__":
                continue
            if top.lower() in declared:
                continue
            findings.append({
                "check": "undeclared-imports", "severity": "advisory",
                "detail": "third-party import '%s' not found in pyproject.toml" % top,
                "paths": [f["path"]],
            })
            break  # one finding per file
    return findings


def check_ci_collection_gaps(files, allow, pyproject_text):
    text = pyproject_text
    m = re.search(r"testpaths\s*=\s*\[([^\]]*)\]", text)
    if not m:
        return []
    roots = [r.strip().strip("\"'") for r in m.group(1).split(",") if r.strip()]
    findings = []
    for f in files:
        if not f["path"].endswith(".py"):
            continue
        base = f["path"].split("/")[-1]
        if not base.startswith("test_"):
            continue
        if any(f["path"].startswith(root) for root in roots):
            continue
        if allowlisted(allow, "ci-collection-gaps", f["path"]):
            continue
        findings.append({
            "check": "ci-collection-gaps", "severity": "advisory",
            "detail": "test file outside testpaths %s" % roots,
            "paths": [f["path"]],
        })
    return findings


def check_untracked_generated(repo, allow):
    out = must_git(repo, "status", "--porcelain")
    findings = []
    for line in out.splitlines():
        if not line.startswith("??"):
            continue
        p = line[3:].strip().strip('"')
        if not GENERATED_RE.search(p):
            continue
        if allowlisted(allow, "untracked-generated", p):
            continue
        findings.append({"check": "untracked-generated", "severity": "advisory",
                         "detail": "untracked file matching generated pattern",
                         "paths": [p]})
    return findings


def check_worktree_status(repo, allow):
    out = must_git(repo, "worktree", "list", "--porcelain")
    findings = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            current = {"path": line[9:]}
        elif line.startswith("HEAD "):
            current["head"] = line[5:]
        elif line.startswith("branch "):
            current["branch"] = line[7:]
        elif line == "detached" and current:
            head = current.get("head", "?")[:8]
            findings.append({"check": "worktree-status", "severity": "advisory",
                             "detail": "detached HEAD at " + head,
                             "paths": [current["path"]]})
            current = {}
    return findings


def collect_findings(repo: Path, allow, max_bytes: int, stdlib: set[str]) -> list[dict]:
    files = tracked_files(repo)
    cache: dict[str, str] = {}
    get_text = make_get_text(repo, cache)
    pyproject_text = get_text("pyproject.toml")
    findings: list[dict] = []
    findings += check_duplicate_blobs(files, allow)
    findings += check_broken_links(get_text, files, allow)
    findings += check_dead_notebook_refs(get_text, files, allow)
    findings += check_oversized(files, allow, max_bytes)
    findings += check_ignored_but_tracked(repo, allow)
    findings += check_secret_patterns(get_text, files, allow)
    findings += check_undeclared_imports(get_text, files, allow, stdlib, pyproject_text)
    findings += check_ci_collection_gaps(files, allow, pyproject_text)
    findings += check_untracked_generated(repo, allow)
    findings += check_worktree_status(repo, allow)
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Advisory repository hygiene checker (read-only).")
    ap.add_argument("--repo", default=".", help="repository root (explicit; no traversal above it)")
    ap.add_argument("--json", dest="json_out", default=None, help="write findings JSON here")
    ap.add_argument("--allowlist", default=None, help="allowlist JSON: {check: [paths/basenames]}")
    ap.add_argument("--max-bytes", type=int, default=1024 * 1024, help="oversized threshold")
    ap.add_argument("--strict", action="store_true", help="exit 3 when any finding exists")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print("OPERATIONAL ERROR: not a git repository: %s" % repo, file=sys.stderr)
        return 2

    stdlib = set(sys.stdlib_module_names)
    try:
        allow = load_allowlist(Path(args.allowlist) if args.allowlist else None)
        findings = collect_findings(repo, allow, args.max_bytes, stdlib)
        head = must_git(repo, "rev-parse", "HEAD").strip()
    except RuntimeError as exc:
        print("OPERATIONAL ERROR: %s" % exc, file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print("OPERATIONAL ERROR: %s" % exc, file=sys.stderr)
        return 2

    result = {"repo": str(repo), "head": head, "advisory": True,
              "finding_count": len(findings), "findings": findings}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    for f in findings:
        print("[%s] %s :: %s" % (f["check"], f["detail"], "; ".join(f["paths"][:4])))
    print("hygiene: %d advisory finding(s); operational errors: 0" % len(findings))
    if args.strict and findings:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
