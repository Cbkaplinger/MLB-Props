"""CLV flavors: same-book vs cross-book vs consensus (measurement).

Answers whether our CLV is cherrypicked soft-book reads or sharp-anchored:
same-book close (fillable, conservative), cross-book close (soft-book,
inflated), devigged-consensus close (sharp ensemble). Beat rates each.

SCALE WARNING (audited 2026-09-15, do not "fix" by rewriting history):
live ledger clv_pp is FRACTION scale (0.0011 = +0.11pp); paid clv_*_pp and
juiced clv_pp are PERCENT scale (+1.08 = +1.08pp). This report converts
everything to pp exactly once, labeled.

Reads: ledger.parquet (settled). Writes: clv_flavors_report.json.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
LED = REPO / "artifacts" / "odds_log" / "ledger.parquet"
OUT = REPO / "artifacts" / "odds_log" / "clv_flavors_report.json"


def flavor(rows: list[dict], scale: float) -> dict:
    clvs = [float(r["clv_pp"]) * scale for r in rows if r.get("clv_pp") is not None]
    return {"n": len(clvs),
            "mean_pp": round(sum(clvs) / len(clvs), 3) if clvs else None,
            "beat_rate": round(sum(1 for c in clvs if c > 0) / len(clvs), 3) if clvs else None}


def main() -> None:
    led = (pl.read_parquet(LED).filter(pl.col("status") == "settled").to_dicts())
    same = [r for r in led if r.get("close_status") == "ok"]
    cross = [r for r in led if r.get("close_status") == "ok_cross_book"]
    cons_rows = [r for r in led if r.get("clv_paid_close_pp") is not None]
    cons = [{"clv_pp": float(r["clv_paid_close_pp"])} for r in cons_rows]
    rep = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scale_note": "ledger fraction x100 -> pp; paid/juiced already percent (pp)",
        "same_book_fillable": flavor(same, 100.0),
        "cross_book_soft": flavor(cross, 100.0),
        "consensus_sharp": {**flavor(cons, 1.0), "n_tickets": len(cons_rows)},
        "verdict": ("HEADLINE = same-book (fillable, conservative); consensus as sharp reference; "
                    "cross-book labeled soft-read, never headlined. "
                    "Cross-book beat-rate inflation is the cherrypick hazard, measured not rumored."),
    }
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
