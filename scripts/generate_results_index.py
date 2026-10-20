"""Machine-generated results index for registered experiments (Chat 3 maintenance).

Scans ONLY declared structured metadata under research/offseason_2026/experiments/:
card.json, metrics.json, bootstrap.json, hashes.json, run_manifest.json.
Never parses prose (card.md) and never infers results. Fields absent from
structured sources are emitted as MISSING.

Outputs (with --write): docs/reference/results_index.md and .csv.
With --check: regenerates in memory and verifies the committed outputs match
byte-for-byte (staleness guard for CI).

Coverage contract: every directory under experiments/ must appear in the index
or in scripts/results_index_exclusions.json. Evidence class / review status /
run status come ONLY from scripts/results_index_annotations.json; unannotated
experiments emit MISSING.

This index links outward to canonical artifacts; it is not itself a source of
truth until independently reviewed. Regenerate and commit after any branch
adds/removes experiment directories (e.g. after PR #3 integrates).
ASCII-only output (cp1252-safe consoles).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO / "research" / "offseason_2026" / "experiments"
OUT_MD = REPO / "docs" / "reference" / "results_index.md"
OUT_CSV = REPO / "docs" / "reference" / "results_index.csv"
EXCLUSIONS = REPO / "scripts" / "results_index_exclusions.json"
ANNOTATIONS = REPO / "scripts" / "results_index_annotations.json"

INVENTORY_FILES = [
    "card.json",
    "metrics.json",
    "bootstrap.json",
    "hashes.json",
    "run_manifest.json",
    "report.json",
]
MISSING = "MISSING"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def short(s, n=18):
    if not isinstance(s, str) or not s:
        return MISSING
    return s[:n] + ("..." if len(s) > n else "")


def populations_summary(card) -> str:
    """Summarize card.json:populations WITHOUT interpreting values."""
    pops = card.get("populations") if isinstance(card, dict) else None
    if isinstance(pops, dict) and pops:
        return "; ".join(sorted(str(k) for k in pops))
    if isinstance(pops, list) and pops:
        return "; ".join(sorted(str(p) for p in pops))
    return MISSING


def inputs_summary(hashes_doc) -> str:
    """Declared input identities from hashes.json; count + first path/hash."""
    inputs = hashes_doc.get("inputs") if isinstance(hashes_doc, dict) else None
    if not isinstance(inputs, list) or not inputs:
        return MISSING
    first = inputs[0]
    if not isinstance(first, dict):
        return MISSING
    return f"{len(inputs)} input(s); first: {first.get('path', MISSING)} sha256 {short(str(first.get('sha256')))}"


def build_rows():
    if not EXPERIMENTS.is_dir():
        raise SystemExit(f"experiments root not found: {EXPERIMENTS}")
    exclusions_doc = load_json(EXCLUSIONS) or {}
    excluded_entries = [e for e in exclusions_doc.get("exclusions", []) if isinstance(e, dict) and "directory" in e]
    excluded = {e["directory"]: e for e in excluded_entries}
    annotations = {}
    ann_doc = load_json(ANNOTATIONS) or {}
    for a in ann_doc.get("experiments", []):
        if isinstance(a, dict) and "directory" in a:
            annotations[a["directory"]] = a

    rows = []
    dirs = sorted(p for p in EXPERIMENTS.iterdir() if p.is_dir())
    for d in dirs:
        if d.name in excluded:
            continue
        card = load_json(d / "card.json")
        hashes_doc = load_json(d / "hashes.json")
        ann = annotations.get(d.name, {})
        artifacts = [f for f in INVENTORY_FILES if (d / f).is_file()]
        rows.append({
            "directory": d.name,
            "experiment_id": str(card.get("experiment_id")) if isinstance(card, dict) and card.get("experiment_id") is not None else MISSING,
            "timestamp_utc": str(card.get("timestamp_utc")) if isinstance(card, dict) and card.get("timestamp_utc") is not None else MISSING,
            "label": short(str(card.get("label")), 60) if isinstance(card, dict) and card.get("label") is not None else MISSING,
            "population_keys": populations_summary(card),
            "owner_auth_recorded": "yes" if isinstance(card, dict) and "owner_authorization" in card else MISSING,
            "artifacts": ", ".join(artifacts) if artifacts else MISSING,
            "card_sha256": str(hashes_doc.get("card_sha256")) if isinstance(hashes_doc, dict) and hashes_doc.get("card_sha256") is not None else MISSING,
            "declared_inputs": inputs_summary(hashes_doc),
            "run_status": ann.get("run_status", MISSING),
            "evidence_class": ann.get("evidence_class", MISSING),
            "review_status": ann.get("review_status", MISSING),
            "annotation_source": ann.get("annotation_note", MISSING),
        })
    return rows, excluded_entries, sorted(set(annotations) - {d.name for d in dirs})


def render_markdown(rows, excluded) -> str:
    buf = io.StringIO()
    buf.write("# Results index (machine-generated)\n\n")
    buf.write("Generated by `scripts/generate_results_index.py` from declared structured")
    buf.write(" metadata only (`card.json`, `metrics.json`, `bootstrap.json`, `hashes.json`,")
    buf.write(" `run_manifest.json`). Prose files are never parsed; missing fields are MISSING;")
    buf.write(" evidence class / review status come only from")
    buf.write(" `scripts/results_index_annotations.json`. This index links outward to canonical")
    buf.write(" artifacts and is not a source of truth until independently reviewed.\n\n")
    buf.write("Regenerate with `python scripts/generate_results_index.py --write` after any")
    buf.write(" change to `research/offseason_2026/experiments/`; CI guards staleness via")
    buf.write(" `--check` in `tests/test_results_index.py`.\n\n")
    cols = ["directory", "experiment_id", "timestamp_utc", "label", "population_keys",
            "owner_auth_recorded", "artifacts", "card_sha256", "declared_inputs",
            "run_status", "evidence_class", "review_status", "annotation_source"]
    buf.write("| " + " | ".join(cols) + " |\n")
    buf.write("|" + "|".join(["---"] * len(cols)) + "|\n")
    for r in rows:
        buf.write("| " + " | ".join(str(r[c]).replace("|", "\\|") for c in cols) + " |\n")
    if excluded:
        buf.write("\n## Excluded directories (authorized)\n\n")
        buf.write("| directory | reason | authorized_by |\n|---|---|---|\n")
        for e in excluded:
            reason = str(e.get("reason", MISSING)).replace("|", "\\|")
            auth = str(e.get("authorized_by", MISSING)).replace("|", "\\|")
            buf.write(f"| {e['directory']} | {reason} | {auth} |\n")
    return buf.getvalue()


def render_csv(rows) -> str:
    buf = io.StringIO()
    if not rows:
        return ""
    cols = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the registered-experiments results index.")
    ap.add_argument("--write", action="store_true", help="write docs/reference/results_index.{md,csv}")
    ap.add_argument("--check", action="store_true", help="verify committed outputs match regeneration")
    args = ap.parse_args(argv)

    rows, excluded, stale_annotations = build_rows()
    md = render_markdown(rows, excluded)
    csv_text = render_csv(rows)

    if stale_annotations:
        print(f"WARNING: annotations reference non-existent directories: {stale_annotations}", file=sys.stderr)

    if args.check:
        committed_md = OUT_MD.read_text(encoding="utf-8") if OUT_MD.is_file() else None
        committed_csv = OUT_CSV.read_text(encoding="utf-8") if OUT_CSV.is_file() else None
        ok_md = committed_md == md
        ok_csv = committed_csv == csv_text
        if not (ok_md and ok_csv):
            print("STALE: committed results index does not match regeneration.", file=sys.stderr)
            print(f"  markdown match: {ok_md}; csv match: {ok_csv}", file=sys.stderr)
            print("  run: python scripts/generate_results_index.py --write", file=sys.stderr)
            return 1
        print(f"results index up to date ({len(rows)} indexed, {len(excluded)} excluded)")
        return 0

    if args.write:
        OUT_MD.write_text(md, encoding="utf-8", newline="\n")
        OUT_CSV.write_text(csv_text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT_MD.name} and {OUT_CSV.name} ({len(rows)} indexed, {len(excluded)} excluded)")
        return 0

    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
