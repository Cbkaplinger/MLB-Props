"""Duplicate finder: exact sha256 + near-dupe heading fingerprints for Markdown."""
from __future__ import annotations
import hashlib
import re
import sys
from pathlib import Path

def norm_heading(line: str) -> str:
    line = line.strip().lower()
    line = re.sub(r"[#>*`_~\-:;,.()\[\]]+", " ", line)
    return re.sub(r"\s+", " ", line).strip()

def main(root: str, out: str) -> None:
    import polars as pl
    rows = []
    for p in Path(root).rglob("*.md"):
        if ".git" in p.parts:
            continue
        try:
            data = p.read_bytes()
            text = data.decode("utf-8", errors="replace")
        except OSError:
            continue
        heads = sorted({norm_heading(l) for l in text.splitlines()
                        if l.strip().startswith("#") and norm_heading(l)})
        rows.append({"path": p.relative_to(root).as_posix(),
                     "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()[:16],
                     "headings": "|".join(heads[:24])})
    df = pl.DataFrame(rows) if rows else pl.DataFrame(
        {"path": [], "bytes": [], "sha256": [], "headings": []})
    df.write_csv(out)
    dupes = 0
    if len(df):
        dupes = int((df.group_by("sha256").agg(pl.len().alias("n"))
                     .filter(pl.col("n") > 1)["n"].sum() or 0))
    print(f"markdown={len(df)} exact-dupe-rows={dupes} -> {out}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".",
         sys.argv[2] if len(sys.argv) > 2 else "gc_duplicates.csv")
