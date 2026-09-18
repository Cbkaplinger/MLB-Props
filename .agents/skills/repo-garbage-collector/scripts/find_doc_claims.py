"""Find numeric/model claims in Markdown: counts, %, $, dates, versions, paths."""
from __future__ import annotations
import re
import sys
from pathlib import Path

PATTERNS = {
    "ticket_count": re.compile(r"\bn\s*=\s*[\d,]+"),
    "percent": re.compile(r"[+-]?\d+(?:\.\d+)?\s*%"),
    "dollars": re.compile(r"\$[\d,]+(?:\.\d+)?"),
    "date": re.compile(r"\b202[3-7]-\d{2}-\d{2}\b"),
    "lcb": re.compile(r"LCB[^.\n]{0,40}[+-]?\d+(?:\.\d+)?%?", re.IGNORECASE),
    "roi": re.compile(r"ROI[^.\n]{0,40}[+-]?\d+(?:\.\d+)?%?", re.IGNORECASE),
    "clv": re.compile(r"CLV[^.\n]{0,40}[+-]?\d+(?:\.\d+)?p?p?", re.IGNORECASE),
    "abspath": re.compile(r"C:\\[^\s\"']+|/home/[^\s\"']+|/Users/[^\s\"']+"),
}

def main(root: str, out: str) -> None:
    import polars as pl
    rows = []
    for p in Path(root).rglob("*.md"):
        if ".git" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS.items():
                for m in rx.finditer(line):
                    rows.append({"file": p.relative_to(root).as_posix(),
                                 "line": lineno, "claim": name,
                                 "match": m.group(0)[:160]})
    df = pl.DataFrame(rows) if rows else pl.DataFrame(
        {"file": [], "line": [], "claim": [], "match": []})
    df.write_csv(out)
    print(f"claims={len(df)} -> {out}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".",
         sys.argv[2] if len(sys.argv) > 2 else "gc_doc_claims.csv")
