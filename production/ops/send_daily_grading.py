"""Daily grading: previous-day report card + ntfy page (owner 2026-09-16).

Grades one slate date on the LIVE ledger: settled + staked + deduped to one
ticket per prop (canonical `settled_bets` + `dedupe_ledger_props` — DK+FD
doubles never count; logging collapses to one slip per signal at the best
edge since 2026-09-23). Surface: N, stake, ROI, CLV
mean + beat_rate, xbook (other-book live close) + beat, WR, plus trailing context and sample-size honesty flags:
THIN (n<5), CALIB (trailing-200 beat<0.50), EXEC (trailing CLV<0).
xROI was removed from notifications 2026-09-21 (owner order); edge-belief
diagnostics live in research (grade_champion xroi_edge), never in pages.

Always writes artifacts/odds_log/daily_grading_YYYY-MM-DD.json. Sends via
ntfy unless --dry-run or MLB_PROPS_NO_ALERT=1 (Modal preview path).

Usage:
  python production/ops/send_daily_grading.py [--date 2026-09-15] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib import request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python.env_load import load_project_dotenv  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    atomic_write_text,
    dedupe_ledger_props,
    load_ledger,
    settled_bets,
)

ODDS_DIR = ROOT / "artifacts" / "odds_log"
ET = ZoneInfo("America/New_York")
TRAIL_N = 200

# Consensus universe: the 9 US-region books pooled (devigged per book, median
# across books) by the paid closeout / consensus_cache. Owner 2026-09-16:
# opens decide on DK/FD; grading references this ensemble.
CONSENSUS_BOOKS = ["draftkings", "fanduel", "betmgm", "bovada", "betonlineag",
                   "fanatics", "betrivers", "williamhill_us", "mybookieag"]


def consensus_depth(frame: pl.DataFrame, cache: pl.DataFrame) -> float | None:
    """Median book depth behind the consensus reference (pure, testable).

    Joins tickets to the close consensus cache on (gd, key, line); key uses
    the canonical join_keys.sorted_key norm so accents/aliases match.
    """
    if frame.is_empty() or cache.is_empty():
        return None
    sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))
    from join_keys import sorted_key  # noqa: E402

    f = frame.with_columns(
        pl.col("game_date").cast(pl.String).str.slice(0, 10).alias("_gd"),
        pl.col("player_name").map_elements(
            sorted_key, return_dtype=pl.String).alias("_key"))
    j = f.join(cache, left_on=["_gd", "_key", "line"],
               right_on=["gd", "key", "line"], how="left")
    depths = j["n_books"].drop_nulls().cast(pl.Float64)
    return round(float(depths.median()), 1) if depths.len() else None


def summarize(frame: pl.DataFrame) -> dict:
    """Grading surface for a settled+dedeuped frame (pure, testable)."""
    n = frame.height
    if n == 0:
        return {"n": 0}
    stake = float(frame["stake"].cast(pl.Float64).fill_null(0.0).sum())
    pnl = float(frame["pnl"].cast(pl.Float64).fill_null(0.0).sum())
    edge = frame["edge"].cast(pl.Float64).fill_null(0.0)
    out: dict = {
        "n": n,
        "stake": round(stake, 2),
        "pnl": round(pnl, 2),
        "roi": round(float(pnl / stake), 4) if stake else None,
        "wr": round(float(frame["result"].eq("win").mean()), 4)
        if "result" in frame.columns else None,
        "ev_dollars": round(float(
            (edge * frame["stake"].cast(pl.Float64).fill_null(0.0)).sum()), 2),
    }
    clv = frame.filter(pl.col("clv_pp").is_not_null()) \
        if "clv_pp" in frame.columns else frame.head(0)
    out["n_clv"] = clv.height
    if clv.height:
        # Ledger clv_pp is fraction scale; report percentage points (x100)
        # to match the paid-consensus convention.
        c = clv["clv_pp"].cast(pl.Float64) * 100.0
        out["mean_clv_pp"] = round(float(c.mean()), 2)
        out["beat_rate"] = round(float((c > 0).mean()), 4)
    else:
        out["mean_clv_pp"] = None
        out["beat_rate"] = None
    # Ensemble-consensus CLV (paid closeout: devigged-median across books,
    # x100 percent scale). Same-book CLV above measures fillable execution;
    # consensus measures beating the market average.
    cons = frame.filter(pl.col("clv_paid_close_pp").is_not_null()) \
        if "clv_paid_close_pp" in frame.columns else frame.head(0)
    out["n_cons"] = cons.height
    if cons.height:
        cc = cons["clv_paid_close_pp"].cast(pl.Float64)
        out["cons_clv_pp"] = round(float(cc.mean()), 2)
        out["cons_beat"] = round(float((cc > 0).mean()), 4)
    else:
        out["cons_clv_pp"] = None
        out["cons_beat"] = None
    # Other-book live CLV (owner 2026-09-23): our best-price line vs the
    # second SharpAPI book's close, on the same single slip. Fills in before
    # paid consensus backfills; same-book above stays the headline.
    xb = frame.filter(pl.col("clv_pp_xbook").is_not_null()) \
        if "clv_pp_xbook" in frame.columns else frame.head(0)
    out["n_xbook"] = xb.height
    if xb.height:
        xc = xb["clv_pp_xbook"].cast(pl.Float64) * 100.0
        out["xbook_clv_pp"] = round(float(xc.mean()), 2)
        out["xbook_beat"] = round(float((xc > 0).mean()), 4)
    else:
        out["xbook_clv_pp"] = None
        out["xbook_beat"] = None
    return out


def send_ntfy(text: str, title: str) -> tuple[bool, str]:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    url = os.getenv("NTFY_URL", "").strip() or (f"https://ntfy.sh/{topic}" if topic else "")
    if not url:
        return False, "ntfy_env_missing"
    req = request.Request(url, data=text.encode("utf-8"),
                          headers={"Title": title, "Priority": "default"}, method="POST")
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"ntfy_status={resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"ntfy_error={exc}"


def pct(v):
    return "n/a" if v is None else f"{v:+.1%}"


def pp(v):
    return "n/a" if v is None else f"{v:+.2f}pp"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default="",
                    help="Slate date YYYY-MM-DD (default: yesterday ET)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_project_dotenv()

    target = args.date or (date.today() - timedelta(days=1)).isoformat()
    day0 = date.fromisoformat(target[:10])
    season_start = f"{day0.year}-01-01"
    bounds = {
        "day": (target[:10], target[:10]),
        "w7": ((day0 - timedelta(days=6)).isoformat(), target[:10]),
        "d30": ((day0 - timedelta(days=29)).isoformat(), target[:10]),
        "ytd": (season_start, target[:10]),
    }

    ledger = load_ledger()
    scoped = settled_bets(ledger)
    if not scoped.is_empty():
        # Stake FIRST, then dedupe: deduping first keeps the highest-edge row
        # per prop even when it is an unstaked skip, and the stake filter then
        # drops the whole key including real BETs (owner 2026-09-16: 36 lost).
        scoped = scoped.filter(pl.col("stake").fill_null(0.0) > 0)
        scoped = dedupe_ledger_props(scoped)
    try:
        cache = pl.scan_parquet(
            ROOT / "data" / "Odds-Historical" / "theoddsapi" / "consensus_cache.parquet"
        ).filter(
            (pl.col("market") == "pitcher_strikeouts") & (pl.col("snapshot") == "close")
        ).select(["gd", "key", "line", "n_books"]).collect()
    except OSError:
        cache = pl.DataFrame(schema={"gd": pl.String, "key": pl.String,
                                     "line": pl.Float64, "n_books": pl.Int64})
    rep: dict = {"date": target[:10], "windows": {},
                 "consensus_books": CONSENSUS_BOOKS}
    for name, (lo, hi) in bounds.items():
        w = scoped.filter(
            (pl.col("game_date").cast(pl.String).str.slice(0, 10) >= lo)
            & (pl.col("game_date").cast(pl.String).str.slice(0, 10) <= hi)) \
            if not scoped.is_empty() else scoped
        s = summarize(w)
        s["cons_depth"] = consensus_depth(w, cache)
        rep["windows"][name] = s
    d = rep["windows"]["day"]

    # Trailing-200 beat rule (spec: <50% over 200 = check calibration).
    trail = scoped.filter(
        pl.col("game_date").cast(pl.String).str.slice(0, 10) <= target[:10]) \
        if not scoped.is_empty() else scoped
    trail_clv = trail.filter(pl.col("clv_pp").is_not_null()).tail(TRAIL_N) \
        if "clv_pp" in trail.columns else trail.head(0)
    flags = []
    if d.get("n", 0) == 0:
        flags.append("NO_SETTLED (nothing graded)")
    elif d["n"] < 5:
        flags.append(f"THIN (n={d['n']})")
    if trail_clv.height >= 50:
        beat = float((trail_clv["clv_pp"].cast(pl.Float64) > 0).mean())
        clv_m = float(trail_clv["clv_pp"].cast(pl.Float64).mean())
        rep["trail_n_clv"] = trail_clv.height
        rep["trail_beat"] = round(beat, 4)
        rep["trail_clv_pp"] = round(clv_m * 100.0, 2)
        if beat < 0.50:
            flags.append(f"CALIB (trail beat {beat:.0%} < 50%)")
        if clv_m < 0:
            flags.append(f"EXEC (trail CLV {clv_m:+.2f}pp < 0)")
    rep["flags"] = flags
    rep["status"] = "check calibration" if any(f.startswith("CALIB") for f in flags) else "on track"

    def row(label: str, s: dict) -> str:
        pnl = f"${s.get('pnl', 0):+.0f}"
        depth = s.get("cons_depth")
        depth_s = f", depth={depth:g}" if depth else ""
        return (f"{label}: n={s.get('n', 0)}, PnL={pnl}, EV=${s.get('ev_dollars', 0):.0f}, "
                f"ROI={pct(s.get('roi'))}, "
                f"CLV={pp(s.get('mean_clv_pp'))} (n={s.get('n_clv', 0)}), "
                f"beat={pct(s.get('beat_rate'))}, "
                f"xbook={pp(s.get('xbook_clv_pp'))} (n={s.get('n_xbook', 0)}), "
                f"cons={pp(s.get('cons_clv_pp'))} (n={s.get('n_cons', 0)}{depth_s}), "
                f"WR={pct(s.get('wr'))}")

    w = rep["windows"]
    lines = [
        f"MLB Props grade {target[:10]} (settled, deduped):",
        row("Yday", w["day"]),
        row("7d  ", w["w7"]),
        row("30d ", w["d30"]),
        row("YTD ", w["ytd"]),
        "cons = devigged-median close, 9 books; xbook = other SharpAPI book live close; depth = median book count.",
        f"Flags: {'; '.join(flags) if flags else 'none'} => {rep['status']}",
    ]
    # Keep each grading window on its own line, with a blank line for ntfy
    # readability. Each row includes its realized dollar PnL.
    body = "\n\n".join(lines)
    out = ODDS_DIR / f"daily_grading_{target[:10]}.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))

    muted = os.getenv("MLB_PROPS_NO_ALERT", "").strip() == "1"
    if args.dry_run or muted:
        print(body + f"\npreview only ({'dry-run' if args.dry_run else 'NO_ALERT'}). wrote {out}")
        return
    ok, info = send_ntfy(body, "MLB Props - Daily Grade")
    print(body + f"\npage: {info}. wrote {out}")


if __name__ == "__main__":
    main()
