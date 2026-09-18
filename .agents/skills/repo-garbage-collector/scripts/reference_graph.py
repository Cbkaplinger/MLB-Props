"""Reference graph: imports, CLI/config/scheduler/notebook string refs per file."""
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path

ENTRY_HINTS = re.compile(
    r"modal|@app\.function|@stub\.function|cron|schedule|poll_odds|odds_board|"
    r"grade_odds_ledger|send_morning_alert|send_daily_grading|ntfy|"
    r"frozen_edge_watch|close_watcher|run_close_sweep|check_nightly_drift",
    re.IGNORECASE)

def py_imports(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out

def main(root: str, out: str) -> None:
    import polars as pl
    rows = []
    root_p = Path(root)
    for p in root_p.rglob("*.py"):
        if ".git" in p.parts or ".venv" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rows.append({"path": p.relative_to(root_p).as_posix(),
                     "imports": ";".join(sorted(set(py_imports(text)))),
                     "entry_hint": bool(ENTRY_HINTS.search(text)),
                     "lines": len(text.splitlines())})
    df = pl.DataFrame(rows) if rows else pl.DataFrame(
        {"path": [], "imports": [], "entry_hint": [], "lines": []})
    df.write_csv(out)
    print(f"python_files={len(df)} entry_hints={int(df['entry_hint'].sum()) if len(df) else 0} -> {out}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".",
         sys.argv[2] if len(sys.argv) > 2 else "gc_reference_graph.csv")
