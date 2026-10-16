"""Tests for the machine-generated results index (Chat 3 charter).

The generator must run hermetically: the lake root may be absent (CI), in
which case lake entries are EXCLUDED with a reason rather than failing.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "tools" / "generate_results_index.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_results_index", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _generate(tmp_path: Path):
    mod = _load_module()
    out_dir = tmp_path / "docs"
    rc = mod.main(["--out-dir", str(out_dir)])
    return mod, rc, out_dir


def test_generator_runs(tmp_path):
    mod, rc, out_dir = _generate(tmp_path)
    assert rc == 0
    for name in ("RESULTS_INDEX.md", "RESULTS_INDEX.csv", "RESULTS_INDEX_COVERAGE.md"):
        path = out_dir / name
        assert path.is_file(), f"missing output {name}"
        assert path.stat().st_size > 0, f"empty output {name}"


def test_registry_integrity():
    mod = _load_module()
    entries = mod.registry()
    assert len(entries) >= 10, "registry unexpectedly small"
    ids = [e.entry_id for e in entries]
    assert len(ids) == len(set(ids)), "duplicate entry_id in registry"
    for e in entries:
        assert e.result_class in mod.RESULT_CLASSES, f"{e.entry_id}: bad result_class"
        assert e.files, f"{e.entry_id}: no declared files"
        assert e.required_roles, f"{e.entry_id}: no required roles"
        for role in e.required_roles:
            assert role in e.files, f"{e.entry_id}: required role {role} undeclared"
        if e.review is not None:
            assert e.review.get("kind") in ("json", "marker"), f"{e.entry_id}: bad review kind"


def test_every_registered_experiment_indexed_or_excluded(tmp_path):
    mod, _, out_dir = _generate(tmp_path)
    coverage_text = (out_dir / "RESULTS_INDEX_COVERAGE.md").read_text(encoding="ascii", errors="replace")
    registered = [e.entry_id for e in mod.registry()]
    for entry_id in registered:
        assert entry_id in coverage_text, f"{entry_id} absent from coverage report"
        line = next(l for l in coverage_text.splitlines() if l.startswith(f"| {entry_id} |"))
        assert ("| INDEXED |" in line) or ("| EXCLUDED |" in line), f"{entry_id}: bad disposition"
        if "| EXCLUDED |" in line:
            assert line.strip().rstrip("|").strip() != f"| {entry_id} | EXCLUDED", (
                f"{entry_id}: excluded without reason")


def test_no_missing_principal_metric_for_completed_nonconforming_free_runs(tmp_path):
    """Confirmation / eligible-for-promotion rows that are indexed must carry a
    principal metric; MISSING is only allowed for excluded entries or classes
    that by design carry no metric (frozen / diagnostic-only)."""
    mod, _, out_dir = _generate(tmp_path)
    import polars as pl

    df = pl.read_csv(out_dir / "RESULTS_INDEX.csv")
    gated = df.filter(
        pl.col("result_class").is_in(["confirmation", "eligible-for-promotion"])
        & (pl.col("status") != "EXCLUDED")
    )
    for entry_id, principal in zip(
        gated["entry_id"].to_list(), gated["principal_metric"].to_list()
    ):
        assert principal != "MISSING", (
            f"{entry_id}: confirmation-class indexed row without a principal metric"
        )


def test_index_values_carry_provenance(tmp_path):
    mod, _, out_dir = _generate(tmp_path)
    import polars as pl

    df = pl.read_csv(out_dir / "RESULTS_INDEX.csv")
    indexed = df.filter(pl.col("principal_metric") != "MISSING")
    for entry_id, prov in zip(indexed["entry_id"].to_list(), indexed["provenance"].to_list()):
        assert prov and "principal=" in prov, f"{entry_id}: principal metric lacks provenance"
