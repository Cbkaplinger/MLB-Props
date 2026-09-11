"""Frozen edge watch: harvest intraday threshold crossings (live ops helper).

Doctrine (#82 backlog): morning projections stay frozen all day; the board
re-scores frozen probs vs fresh SharpAPI quotes on every refresh. This script
diffs the current board against today's last-seen state and pages ONLY skip/HOLD
-> BET flips (a line moved into our threshold). BET -> skip is recorded
silently. First run of the day stores the baseline and stays silent.

Veto/floors are applied by build_recommendations itself (same conservative
flags as the production board), so a paged flip is policy-clean by
construction; an assert fails loud if a veto-tagged row ever pages.

State: artifacts/odds_log/edge_watch_state_YYYY-MM-DD.json (per-day).
Report: artifacts/odds_log/edge_watch_report_YYYY-MM-DD.json.
Pages via ntfy (NTFY_TOPIC/NTFY_URL); --dry-run pages nothing.
No ledger writes, no policy change.

Usage:
  python production/ops/frozen_edge_watch.py --self-test   # pure diff test
  python production/ops/frozen_edge_watch.py --dry-run     # live fetch, no page
  python production/ops/frozen_edge_watch.py              # live fetch + page
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.env_load import load_project_dotenv  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.odds_board import build_recommendations  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
KEY_COLS = ["player_name", "line", "best_side"]


def row_key(r: dict) -> str:
    return f"{r.get('player_name')}|{r.get('line')}|{r.get('best_side')}"


def diff_frames(old: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (harvest_flips, lost_rows). Pure function (self-testable).

    lost = BET that flipped to skip/HOLD (line moved away) PLUS prior BET
    rows absent from the new frame entirely (quote vanished midday — #96:
    Smith 13:30-13:58 ET taught us vanished quotes are the silent case).
    """
    old_rec = {row_key(r): str(r.get("recommendation")) for r in old}
    new_keys = {row_key(r) for r in new}
    flips, lost = [], []
    for r in new:
        k = row_key(r)
        prev = old_rec.get(k)
        cur = str(r.get("recommendation"))
        if prev is not None and prev != "BET" and cur == "BET":
            reason = str(r.get("policy_reason") or "")
            if "veto" in reason.lower():
                raise AssertionError(f"veto-tagged flip paged as BET: {k} ({reason})")
            flips.append(r)
        elif prev == "BET" and cur != "BET":
            lost.append(r)
    for r in old:
        if row_key(r) not in new_keys and old_rec[row_key(r)] == "BET":
            lost.append({**r, "_vanished": True})
    return flips, lost


def send_ntfy(text: str, title: str) -> tuple[bool, str]:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    url = os.getenv("NTFY_URL", "").strip() or (f"https://ntfy.sh/{topic}" if topic else "")
    if not url:
        return False, "ntfy_env_missing"
    req = request.Request(url, data=text.encode("utf-8"),
                          headers={"Title": title, "Priority": "high"}, method="POST")
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"ntfy_status={resp.status}"
    except Exception as exc:
        return False, f"ntfy_error={exc}"


def fmt_flip(r: dict) -> str:
    price = r.get("best_price")
    try:
        price_s = f"{int(float(price)):+d}"
    except Exception:
        price_s = str(price)
    return (f"({r.get('player_name')}) {r.get('best_side')} {r.get('line')} @ {price_s}, "
            f"edge {float(r.get('edge', 0)) * 100:.1f}%, "
            f"stake ${float(r.get('stake', 0)):.2f}")


def self_test() -> None:
    old = [
        {"player_name": "A", "line": 4.5, "best_side": "over",
         "recommendation": "HOLD", "policy_reason": "veto_4_5_over",
         "edge": 0.05, "best_price": -110, "stake": 0.0},
        {"player_name": "B", "line": 6.5, "best_side": "over",
         "recommendation": "skip", "policy_reason": "",
         "edge": 0.10, "best_price": -110, "stake": 0.0},
        {"player_name": "C", "line": 3.5, "best_side": "under",
         "recommendation": "BET", "policy_reason": "",
         "edge": 0.15, "best_price": -110, "stake": 60.0},
    ]
    new = [
        {"player_name": "A", "line": 4.5, "best_side": "over",
         "recommendation": "HOLD", "policy_reason": "veto_4_5_over",
         "edge": 0.06, "best_price": -110, "stake": 0.0},
        {"player_name": "B", "line": 6.5, "best_side": "over",
         "recommendation": "BET", "policy_reason": "",
         "edge": 0.14, "best_price": 105, "stake": 55.0},
        {"player_name": "C", "line": 3.5, "best_side": "under",
         "recommendation": "skip", "policy_reason": "",
         "edge": 0.09, "best_price": -110, "stake": 0.0},
    ]
    flips, lost = diff_frames(old, new)
    assert [row_key(r) for r in flips] == ["B|6.5|over"], flips
    assert [row_key(r) for r in lost] == ["C|3.5|under"], lost
    van = diff_frames(old, [r for r in new if row_key(r) != "C|3.5|under"])[1]
    assert [row_key(r) for r in van] == ["C|3.5|under"] and van[0].get("_vanished"), van
    bad = [dict(new[1], policy_reason="veto_4_5_over")]
    try:
        diff_frames(old, bad)
        raise SystemExit("self-test FAILED: veto flip did not raise")
    except AssertionError:
        pass
    print("self-test OK: 1 harvest flip, 1 silent loss, veto assert fires.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unit", type=float, default=50.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    load_project_dotenv()

    today = date.today().isoformat()
    state_path = ODDS_DIR / f"edge_watch_state_{today}.json"
    report_path = ODDS_DIR / f"edge_watch_report_{today}.json"

    frame, _meta = build_recommendations(
        unit_dollars=args.unit, edge_floor=0.12,
        apply_line_price_correction=True, apply_line_floors=True,
        apply_deploy_matrix_filter=True)
    cols = ["player_name", "line", "best_side", "recommendation", "edge",
            "best_price", "units", "stake", "policy_reason"]
    cur = [dict(r) for r in frame.select([c for c in cols if c in frame.columns]).to_dicts()]

    if not state_path.exists():
        stamp = datetime.now(timezone.utc).isoformat()
        atomic_write_text(state_path, json.dumps(
            {"date": today, "stored_at_utc": stamp, "rows": cur},
            indent=2, default=str))
        atomic_write_text(report_path, json.dumps(
            {"date": today, "baseline": True, "stored_at_utc": stamp,
             "n": len(cur), "flips": [], "lost": [], "paged": False},
            indent=2, default=str))
        print(f"baseline stored ({len(cur)} rows); silent first run. wrote {state_path}")
        return

    old = json.loads(state_path.read_text(encoding="utf-8"))["rows"]
    flips, lost = diff_frames(old, cur)
    paged: bool | str = False
    if flips:
        body = "MLB Props edge harvest (frozen AM probs vs fresh lines):\n" + "\n".join(
            fmt_flip(r) for r in flips)
        if args.dry_run:
            paged = "dry-run (not sent)"
            print(body)
        else:
            ok, info = send_ntfy(body, "MLB Props - Edge Harvest")
            paged = ok if ok else info
            print(f"{body}\npage: {info}")
    else:
        print(f"no flips ({len(cur)} rows watched, {len(lost)} silently lost).")
    atomic_write_text(state_path, json.dumps(
        {"date": today, "stored_at_utc": datetime.now(timezone.utc).isoformat(),
         "rows": cur}, indent=2, default=str))
    atomic_write_text(report_path, json.dumps(
        {"date": today, "baseline": False, "n": len(cur),
         "flips": flips, "lost": lost, "paged": paged}, indent=2, default=str))
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
