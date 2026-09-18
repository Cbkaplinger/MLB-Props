"""Repo inventory: tracked/untracked files by type, sizes, hashes. Polars-first."""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                ".ruff_cache", ".mypy_cache", "node_modules"}

def sha256(path: Path, limit: int = 5_000_000) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(limit))
    return h.hexdigest()[:16]

def main(root: str, out: str) -> None:
    import polars as pl
    root_p = Path(root)
    rows = []
    for p in root_p.rglob("*"):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        rel = p.relative_to(root_p).as_posix()
        try:
            size = p.stat().st_size
            mtime = p.stat().st_mtime
        except OSError:
            continue
        suffix = p.suffix.lower()
        kind = "other"
        if suffix in {".md", ".mdc", ".rst", ".txt"}:
            kind = "doc"
        elif suffix == ".py":
            kind = "python"
        elif suffix == ".ipynb":
            kind = "notebook"
        elif suffix in {".parquet", ".csv", ".json", ".pkl", ".pickle", ".pdf",
                        ".html", ".png", ".svg", ".log", ".db", ".duckdb"}:
            kind = "artifact"
        elif suffix in {".ps1", ".sh", ".bat", ".yml", ".yaml", ".toml", ".cfg", ".ini"}:
            kind = "config"
        rows.append({"path": rel, "kind": kind, "suffix": suffix,
                     "size": size, "mtime": mtime,
                     "hash": sha256(p) if size < 5_000_000 else "large"})
    df = pl.DataFrame(rows) if rows else pl.DataFrame(
        {"path": [], "kind": [], "suffix": [], "size": [], "mtime": [], "hash": []})
    df.write_csv(out)
    print(f"rows={len(df)} -> {out}")
    if len(df):
        print(df.group_by("kind").agg(pl.len().alias("n"),
              pl.sum("size").alias("bytes")).sort("n", descending=True))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".",
         sys.argv[2] if len(sys.argv) > 2 else "gc_inventory.csv")
