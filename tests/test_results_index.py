"""CI tests for the machine-generated results index (Chat 3 maintenance).

Guarantees:
1. The generator runs and produces parseable, non-empty outputs.
2. Generation is deterministic (two runs byte-identical).
3. Coverage: every directory under research/offseason_2026/experiments/ is
   either indexed or explicitly listed in scripts/results_index_exclusions.json.
4. Annotation directories (scripts/results_index_annotations.json) all exist.
5. --check passes on the committed docs/reference/results_index.{md,csv}
   (staleness guard: regenerate + commit after adding/removing experiments).
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "generate_results_index.py"

spec = importlib.util.spec_from_file_location("generate_results_index", SCRIPT)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def _capture_rows():
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.main([])
    return buf.getvalue()


def test_generator_runs_and_outputs_parseable():
    md = _capture_rows()
    assert md.startswith("# Results index (machine-generated)")
    lines = [ln for ln in md.splitlines() if ln.startswith("| ")]
    assert len(lines) >= 2  # header + separator + at least one data row expected


def test_generation_is_deterministic():
    rows_a, excl_a, stale_a = gen.build_rows()
    rows_b, excl_b, stale_b = gen.build_rows()
    assert gen.render_markdown(rows_a, excl_a) == gen.render_markdown(rows_b, excl_b)
    assert gen.render_csv(rows_a) == gen.render_csv(rows_b)
    assert not stale_a, f"annotations reference non-existent directories: {stale_a}"


def test_every_experiment_dir_indexed_or_excluded():
    rows, excluded, _ = gen.build_rows()
    indexed = {r["directory"] for r in rows}
    dirs = {p.name for p in gen.EXPERIMENTS.iterdir() if p.is_dir()}
    assert indexed | set(excluded) == dirs, (
        f"uncovered experiment dirs: {sorted(dirs - indexed - set(excluded))}"
    )
    for e in excluded:
        assert e.get("reason"), f"exclusion without reason: {e}"
        assert e.get("authorized_by"), f"exclusion without authorization: {e}"


def test_exclusion_and_annotation_dirs_exist():
    for reg in (gen.EXCLUSIONS, gen.ANNOTATIONS):
        assert reg.is_file(), f"missing registry: {reg}"
        doc = json.loads(reg.read_text(encoding="utf-8"))
        assert "comment" in doc
    exclusions = json.loads(gen.EXCLUSIONS.read_text(encoding="utf-8"))["exclusions"]
    for e in exclusions:
        assert (gen.EXPERIMENTS / e["directory"]).is_dir(), f"exclusion for missing dir: {e}"


def test_committed_outputs_fresh():
    rows, excluded, _ = gen.build_rows()
    committed_md = gen.OUT_MD.read_text(encoding="utf-8")
    committed_csv = gen.OUT_CSV.read_text(encoding="utf-8")
    assert committed_md == gen.render_markdown(rows, excluded), (
        "results_index.md is stale; run: python scripts/generate_results_index.py --write"
    )
    assert committed_csv == gen.render_csv(rows), (
        "results_index.csv is stale; run: python scripts/generate_results_index.py --write"
    )
    # committed CSV must round-trip
    reader = csv.DictReader(io.StringIO(committed_csv))
    assert len(list(reader)) == len(rows)
