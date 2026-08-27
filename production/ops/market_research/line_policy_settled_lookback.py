"""Settled-ledger lookback against the frozen line-edge-floor policy.

Read-only diagnostic: reports how the *actually-placed* settled tickets performed
at each line against the currently frozen ``line_edge_floors`` map (does NOT
change any floor — floors are pre-registered and require retest per
``docs/reference/market_clv_gates.md``).

This is intentionally diagnostic output the operator can act on (e.g. propose a
pre-registered retest), not a policy mutation.

Reads:
  - artifacts/odds_log/ledger.parquet
  - production/ops/market_research/line_floor_policy.json

Writes:
  - artifacts/odds_log/line_policy_settled_lookback.json
  - artifacts/odds_log/line_policy_settled_lookback.parquet

Run (from repo root):
  .\\.venv\\Scripts\\python.exe production/ops/market_research/line_policy_settled_lookback.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
LINE_FLOOR_PATH = (
    ROOT / "production" / "ops" / "market_research" / "line_floor_policy.json"
)
JSON_OUT = ODDS_DIR / "line_policy_settled_lookback.json"
PARQUET_OUT = ODDS_DIR / "line_policy_settled_lookback.parquet"


def _load_floor_map() -> dict[float, float]:
    if not LINE_FLOOR_PATH.exists():
        return {}
    try:
        payload = json.loads(LINE_FLOOR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = payload.get("line_edge_floors", {}) if isinstance(payload, dict) else {}
    out: dict[float, float] = {}
    for k, v in raw.items():
        try:
            out[float(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _line_metrics(frame: pl.DataFrame) -> dict:
    n = frame.height
    stake = float(frame["stake"].sum()) if n else 0.0
    pnl = float(frame["pnl"].sum()) if n else 0.0
    wr = (
        float(
            (frame.filter(pl.col("result") == "win").height) / n
        )
        if n
        else 0.0
    )
    clv = frame["clv_pp"]
    clv_nonnull = clv.filter(clv.is_not_null())
    clv_mean = float(clv_nonnull.mean()) if clv_nonnull.len() else None
    beat = (
        float((clv_nonnull > 0).mean()) if clv_nonnull.len() else None
    )
    edge = frame["edge"]
    return {
        "n": n,
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": round(pnl / stake, 6) if stake else 0.0,
        "win_rate": round(wr, 6),
        "mean_clv_pp": round(clv_mean, 6) if clv_mean is not None else None,
        "beat_close_rate": round(beat, 6) if beat is not None else None,
        "mean_edge": round(float(edge.mean()), 6) if n else None,
    }


def _load_ledger() -> pl.DataFrame:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"ledger not found: {LEDGER_PATH}")
    df = pl.read_parquet(LEDGER_PATH)
    settled = df.filter(pl.col("status") == "settled")
    # One row per (date, player, line, side): keep best-edge book so DK+FD
    # pairs are not double-counted in line/ROI/side statistics.
    return dedupe_ledger_props(settled) if not settled.is_empty() else settled

def _risk_flag(roi: float, n: int, floor: float | None) -> str:
    """Diagnostic-only PASS/WARN; never a policy mutation."""
    if n < 20:
        return "PASS_LOW_N"
    # A settled line clearing its frozen floor but realizing strongly negative
    # ROI is a WARN signal worth a pre-registered retest — not a floor change.
    if roi < -0.08 and floor is not None:
        return "WARN_NEGATIVE_ROI"
    return "PASS"


def main() -> None:
    from Python.clv_basis import window_beat_rates

    settled = _load_ledger()
    floor_map = _load_floor_map()
    if settled.is_empty():
        raise SystemExit("no settled rows")

    lines = sorted({float(v) for v in settled["line"].to_list()})
    per_line: list[dict] = []
    active_flag_rows: list[dict] = []

    for L in lines:
        sub = settled.filter(pl.col("line") == L)
        all_ = _line_metrics(sub)
        all_["line"] = L
        all_["frozen_floor"] = floor_map.get(L)
        per_line.append(all_)
        # Active conservative profile: bets at or above the frozen line floor.
        floor = floor_map.get(L, 0.12)
        prof = sub.filter(pl.col("edge") >= floor)
        if prof.height:
            m = _line_metrics(prof)
            m["line"] = L
            m["frozen_floor"] = floor
            m["flag"] = _risk_flag(m["roi"], m["n"], floor)
            active_flag_rows.append(m)
        # Stratify the profile by side for the underperforming lines.
        for side in ("over", "under"):
            ss = prof.filter(pl.col("side") == side)
            if ss.height:
                m = _line_metrics(ss)
                m.update({"line": L, "side": side, "frozen_floor": floor})
                active_flag_rows.append(m)

    # Sodium-free, human sortable by ROI within line for the console.
    active_flag_rows.sort(key=lambda r: (r["line"], r.get("side", "")))

    JSON_OUT.write_text(
        json.dumps(
            {
                "generated_utc": datetime.now(timezone.utc).isoformat(),
                "n_settled": int(settled.height),
                "frozen_line_floors": {str(k): v for k, v in sorted(floor_map.items())},
                "per_line_all": per_line,
                "per_profile": active_flag_rows,
                "note": (
                    "Diagnostic only. Frozen line-edge floors are NOT changed "
                    "here; a pre-registered retest (docs/reference/market_clv_gates.md) "
                    "is required before any floor move. WARN flags indicate a "
                    "settled line that cleared its frozen floor but realized "
                    "negative ROI — a candidate for review, not an automatic change."
                ),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    out_rows = []
    for r in per_line:
        out_rows.append({"scope": "line_all", **r})
    for r in active_flag_rows:
        out_rows.append({"scope": "profile", **r})
    pl.DataFrame(out_rows).write_parquet(PARQUET_OUT)

    print(f"settled n={settled.height}")
    print(f"{'line':<6}{'floor':<7}{'scope':<8}{'n':<6}{'roi':>9}  {'pnl':>9}  {'wr':>7}  {'clv_pp':>8}")
    for r in per_line:
        fl = r["frozen_floor"]
        print(
            f"{r['line']:<6}{(str(fl) if fl is not None else '-'):<7}{'all':<8}"
            f"{r['n']:<6}{100*r['roi']:>8.1f}%  {r['pnl']:>9.0f}  {100*r['win_rate']:>6.1f}%  "
            f"{(str(round(100*r['mean_clv_pp'],1)) if r['mean_clv_pp'] is not None else '-'):>8}"
        )
    print("--- active profile (edge >= frozen floor) by line / side ---")
    for r in active_flag_rows:
        side_lbl = f"{r['line']}:{r.get('side','-')}"
        print(
            f"{r['line']:<6}{str(r['frozen_floor']):<7}{side_lbl:<13}"
            f"{r['n']:<6}{100*r['roi']:>8.1f}%  {r['pnl']:>9.0f}  "
            f"{r.get('flag','')}"
        )
    warns = [r for r in active_flag_rows if str(r.get("flag", "")).startswith("WARN")]
    print()
    if warns:
        print("DIAGNOSTIC WARN (review for pre-registered retest, no auto-change):")
        for w in warns:
            print(f"  line {w['line']} {w.get('side','-')}: roi={100*w['roi']:.1f}% n={w['n']}")
    else:
        print("No negative-ROI profile flags.")
    print(f"wrote {JSON_OUT.name} / {PARQUET_OUT.name}")


if __name__ == "__main__":
    main()

