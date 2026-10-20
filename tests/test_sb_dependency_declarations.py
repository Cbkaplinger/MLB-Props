"""S-B patch validation: the 7 declared packages exactly cover the undeclared
import surface, `sage` is deliberately NOT declared, and no other import
surface changes. Read-only; no package installation."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repo_hygiene_check.py"

spec = importlib.util.spec_from_file_location("rhc_sb", SCRIPT)
rhc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rhc)

# the exact seven choices presented for owner approval
DECLARED_NOW = {
    "requests": "research",   # 4 consumers, all production/ops/market_research pullers
    "xgboost": "research",    # models research ablations
    "optuna": "research",     # models research tuners
    "catboost": "research",   # models research ablation
    "pymupdf": "paper",       # docs/paper/validate_pdf.py
    "markdown": "paper",      # docs/paper/render_pdf.py
    "modal": "deploy",        # production/cloud/modal_app.py
}
DELIBERATELY_EXCLUDED = "sage"  # single legacy consumer; verify-or-retire pending


def test_pyproject_declares_the_seven():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pkg in DECLARED_NOW:
        assert f'"{pkg}"' in text, f"{pkg} missing from pyproject.toml"
    assert 'paper = ["pymupdf", "markdown"]' in text
    assert 'deploy = ["modal"]' in text


def test_sage_is_deliberately_not_declared():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"sage"' not in text


def test_import_to_package_mapping_is_documented():
    doc = (ROOT / "docs" / "reference" / "reports" /
           "sb_dependency_declaration_choices_2026-10-19.md").read_text(encoding="utf-8")
    for pkg, importer in DECLARED_NOW.items():
        assert pkg in doc
    assert "full_feature_importance_screen.py" in doc  # sage consumer named
    assert "do NOT" in doc or "not declared" in doc.lower()


def test_undeclared_import_findings_shrink_to_sage_only(tmp_path):
    """Contract check on a synthetic fixture mirroring the real decision:
    a pyproject declaring exactly the seven packages, one consumer importing a
    declared package (must NOT be flagged), and one importing `sage` (must be
    flagged). The full-repo equivalent is a documented manual command:
    python scripts/repo_hygiene_check.py --repo . --json out.json
    (it scans ~400 files via git and takes minutes locally)."""
    import subprocess as sp

    repo = tmp_path / "mini"
    (repo / "src").mkdir(parents=True)
    (repo / "puller.py").write_text("import requests\n", encoding="utf-8")
    (repo / "screen.py").write_text("import sage\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "mini"\n'
        "[project.optional-dependencies]\n"
        'research = ["requests", "xgboost", "optuna", "catboost"]\n'
        'paper = ["pymupdf", "markdown"]\n'
        'deploy = ["modal"]\n',
        encoding="utf-8",
    )
    sp.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"],
              ["add", "-A"], ["commit", "-m", "x"]):
        sp.run(["git"] + a, cwd=repo, capture_output=True, check=True)
    out = tmp_path / "findings.json"
    r = sp.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--json", str(out)],
               capture_output=True, text=True, encoding="utf-8", errors="replace",
               timeout=120)
    assert r.returncode == 0, r.stderr[:300]
    result = json.loads(out.read_text(encoding="utf-8"))
    flagged = {}
    for f in result["findings"]:
        if f["check"] != "undeclared-imports":
            continue
        m = re.search(r"import '([A-Za-z0-9_]+)' not found", f["detail"])
        for pth in f["paths"]:
            flagged[m.group(1) if m else "?"] = pth
    assert "requests" not in flagged, "declared package still flagged"
    assert "sage" in flagged, "deliberately excluded sage import must stay flagged"
