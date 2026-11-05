"""Dawn probe: is there a bettable K market before the morning workflow?

Runs at ~05:00-06:00 ET on day-game slates (owner minutes). Two halves:

  RG half  - fetch + parse RotoGrinders lineups; per game record
             confirmed-vs-projected status, starters, game time (ET),
             minutes-to-first-pitch, and RG-vs-MLB-probable agreement.
  Book half - SharpAPI dry-run open poll (preview only, never the ledger,
             never an alert); record per-book K-prop coverage.

Writes: artifacts/odds_log/dawn_probe_YYYYMMDD_HHMMSS.json (one per run)
        artifacts/odds_log/dawn_probe_log.jsonl (appended; the week curve)

GO criterion (pre-registered): DK+FD K props visible at -6h or earlier on
day games AND RG lineups confirmed (not projected) -> build the dawn poll.
NO-GO -> day-game policy gate instead. Exit 0 always; this is a probe,
never a gate. No live change.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

ET = ZoneInfo("America/New_York")
OUT_DIR = REPO / "artifacts" / "odds_log"
LOG = OUT_DIR / "dawn_probe_log.jsonl"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def rg_half() -> dict:
    """Fetch + parse RG; summarize per game. Best-effort, never raises."""
    rec: dict = {"ok": False, "fetch_utc": _utcnow(), "games": []}
    try:
        import Python.daily_lineups as dl

        html = dl.fetch_rotogrinders_html()
        today_et = dt.datetime.now(ET).date()
        slate = dl.parse_rotogrinders_html(html, game_date=today_et)
        now_utc = dt.datetime.now(dt.timezone.utc)
        try:
            sched = dl.fetch_mlb_schedule(dt.date.today())
            probables = {str(r.get("game_pk")): r for r in sched}
        except Exception as exc:  # schedule is a nice-to-have, not load-bearing
            probables = {}
            rec["mlb_schedule_error"] = str(exc)[:200]
        starters = slate.starters.to_dicts() if hasattr(slate, "starters") else []
        lineups = slate.lineups.to_dicts() if hasattr(slate, "lineups") else []
        status_by_game: dict = {}
        for r in lineups:
            g = status_by_game.setdefault(str(r.get("slate_game_key")), {
                "statuses": set(), "n_batters": 0,
                "away": r.get("away_team"), "home": r.get("home_team"),
            })
            g["statuses"].add(str(r.get("lineup_status")))
            g["n_batters"] += 1
        sp_by_game: dict = {}
        for r in starters:
            sp_by_game.setdefault(str(r.get("slate_game_key")), []).append({
                "team": r.get("team"), "sp": r.get("player_name"),
                "status": str(r.get("lineup_status")),
                "game_time_utc": str(r.get("rg_game_time")),
            })
        for key, g in status_by_game.items():
            try:
                gt = dt.datetime.fromisoformat(
                    sp_by_game.get(key, [{}])[0].get("game_time_utc") or "")
                if gt.tzinfo is None:
                    gt = gt.replace(tzinfo=dt.timezone.utc)
                mins = (gt - now_utc).total_seconds() / 60.0
                gt_et = gt.astimezone(ET).strftime("%H:%M ET")
            except Exception:
                mins, gt_et = None, None
            rec["games"].append({
                "away": g["away"], "home": g["home"],
                "game_time_et": gt_et, "mins_to_first_pitch": round(mins, 1) if mins is not None else None,
                "lineup_status": sorted(g["statuses"]),
                "confirmed": g["statuses"] == {"confirmed"},
                "n_batters": g["n_batters"],
                "starters": sp_by_game.get(key, []),
            })
        rec["ok"] = True
        rec["n_games"] = len(rec["games"])
        rec["n_confirmed"] = sum(1 for g in rec["games"] if g["confirmed"])
    except Exception as exc:
        rec["error"] = str(exc)[:300]
    return rec


def book_half() -> dict:
    """SharpAPI dry-run open poll. Preview only; never the ledger/alerts."""
    rec: dict = {"ok": False, "run_utc": _utcnow()}
    cmd = [sys.executable, "production/odds/poll_odds.py",
           "--snapshot", "open", "--unit", "50",
           "--quality-gate", "--dry-run", "--allow-live-open-poll"]
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                              text=True, timeout=600)
        rec["exit"] = proc.returncode
        tail = (proc.stdout or "")[-1500:] + (proc.stderr or "")[-500:]
        rec["tail"] = tail
        rec["ok"] = proc.returncode == 0
    except Exception as exc:
        rec["error"] = str(exc)[:300]
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="",
                    help="Optional label appended to the report filename.")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rg = rg_half()
    books = book_half()
    day_games = [g for g in rg.get("games", [])
                 if g.get("mins_to_first_pitch") is not None
                 and g["mins_to_first_pitch"] < 600]
    rep = {
        "built_utc": _utcnow(),
        "tag": args.tag,
        "rg": rg,
        "books": books,
        "n_day_games": len(day_games),
        "verdict": ("MANUAL-READ (RG side %s, book dry-run %s; owner checks "
                    "preview coverage vs -6h GO rule)"
                    % ("ok" if rg.get("ok") else "FAILED",
                       "ok" if books.get("ok") else "FAILED")),
    }
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"dawn_probe_{stamp}{('_' + args.tag) if args.tag else ''}.json"
    (OUT_DIR / name).write_text(json.dumps(rep, indent=2))
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"built_utc": rep["built_utc"], "tag": args.tag,
                             "rg_ok": rg.get("ok"), "books_ok": books.get("ok"),
                             "n_games": rg.get("n_games"),
                             "n_confirmed": rg.get("n_confirmed"),
                             "n_day_games": len(day_games)}) + "\n")
    print(json.dumps({"report": name, "rg_ok": rg.get("ok"),
                      "books_ok": books.get("ok"),
                      "n_games": rg.get("n_games"),
                      "n_confirmed": rg.get("n_confirmed")}, indent=2))


if __name__ == "__main__":
    main()
