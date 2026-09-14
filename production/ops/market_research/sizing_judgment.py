"""Judgment day: sizing bakeoff + September premium + day/night (measurement).

1. Sizing bakeoff nested: pick arm by Sharpe on 2025 (pre-registered rule),
   judge once on 2026 (labeled confirmatory -- 2026 peeked before).
2. September premium: drop September taken with edge < 0.14 (floor + 0.02
   lean machinery); ROI delta vs full.
3. Day/night: commence_time (envelope, ET) < 17:00 = day; ROI/PnL by
   day/night and day/night x snap.

Reads: juiced candidates + book_lines (event map) + snapshot_envelope.
Writes: artifacts/odds_log/sizing_judgment_report.json. No live change.
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import math
import sys
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src" / "Python"))

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT = REPO / "artifacts" / "odds_log" / "sizing_judgment_report.json"
ANN = 162.0 ** 0.5


def arm_stats(rows: list[dict], arm: str) -> dict:
    st = sum(float(r["stake_" + arm] or 0.0) for r in rows)
    pn = sum(float(r["pnl_" + arm] or 0.0) for r in rows)
    by = {}
    for r in rows:
        by[str(r["gd"])] = by.get(str(r["gd"]), 0.0) + float(r["pnl_" + arm] or 0.0)
    d = [by[k] for k in sorted(by)]
    m = sum(d) / len(d) if d else 0.0
    sd = (sum((x - m) ** 2 for x in d) / len(d)) ** 0.5 if d else 0.0
    eq = peak = dd = 0.0
    for x in d:
        eq += x / 50.0
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {"n": len(rows), "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
            "sharpe": round(m / sd * ANN, 2) if sd else None, "max_dd_u": round(dd, 1)}


def flat_stats(rows: list[dict]) -> dict:
    st = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pn = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    return {"n": len(rows), "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
            "wr": round(sum(1 for r in rows if r["won"]) / len(rows), 3) if rows else None}


def main() -> None:
    taken = (pl.read_parquet(CAND)
             .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"])).to_dicts())
    y25 = [r for r in taken if str(r.get("yr")) == "2025"]
    y26 = [r for r in taken if str(r.get("yr")) == "2026"]
    rep: dict = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "rule": "pick by Sharpe on 2025; judge once on 2026 (confirmatory)"}
    arms = ["flat1u", "kelly", "band", "robust"]
    rep["bakeoff_2025"] = {a: arm_stats(y25, a) for a in arms}
    rep["bakeoff_2026"] = {a: arm_stats(y26, a) for a in arms}
    pick = max(arms, key=lambda a: (rep["bakeoff_2025"][a]["sharpe"] is not None, rep["bakeoff_2025"][a]["sharpe"] or -99))
    rep["picked_on_2025_sharpe"] = pick
    rep["judge_note"] = "2026 peeked before -- confirmatory -- not a clean judge"

    # September premium: require edge >= 0.14 on September tickets
    sep = [r for r in taken if str(r.get("gd", ""))[5:7] == "09"]
    keep = [r for r in taken if not (str(r.get("gd", ""))[5:7] == "09" and float(r.get("edge") or 0.0) < 0.14)]
    rep["september_premium"] = {"sep_n": len(sep), "dropped_n": len(taken) - len(keep),
        "full": flat_stats(taken), "premium": flat_stats(keep),
        "roi_delta": round(flat_stats(keep)["roi"] - flat_stats(taken)["roi"], 4)}

    # Day/night via envelope commence_time (ET)
    env = {}
    for r in pl.read_parquet(REPO / "data" / "Odds-Historical" / "theoddsapi" / "snapshot_envelope.parquet").to_dicts():
        ct = str(r.get("commence_time") or "")
        if len(ct) >= 13 and r.get("event_id"):
            env[str(r["event_id"])] = ct
    bl = (pl.read_parquet(REPO / "data" / "Odds-Historical" / "theoddsapi" / "book_lines_pitcher.parquet")
          .filter(pl.col("market") == "pitcher_strikeouts").select(["event_id", "player", "line"]).to_dicts())
    evdate = _jk.load_event_date_map()
    idx = {}
    for r in bl:
        idx[(_jk.sorted_key(r["player"]), float(r["line"]), evdate.get(str(r["event_id"]), ""))] = str(r["event_id"])
    day, night, unmapped = [], [], 0
    for r in taken:
        ev = idx.get((_jk.sorted_key(r["player_name"]), float(r["line"]), str(r["gd"])))
        ct = env.get(ev or "")
        if not ct:
            unmapped += 1
            continue
        try:
            utc_h = int(ct[11:13])
            month = int(ct[5:7])
            et_h = (utc_h - (4 if 3 <= month <= 11 else 5)) % 24
        except (ValueError, IndexError):
            unmapped += 1
            continue
        (day if et_h < 17 else night).append(r)
    rep["day_night"] = {"day": flat_stats(day), "night": flat_stats(night), "unmapped": unmapped,
        "note": "day = commence before 17:00 ET"}
    rep["day_night_by_snap"] = {}
    for name, grp in (("day", day), ("night", night)):
        rep["day_night_by_snap"][name] = {s: flat_stats([r for r in grp if r.get("snap") == s]) for s in ("open", "morning")}
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
