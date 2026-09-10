"""Send morning recommendation/status alert via ntfy.sh.

Single channel (2026-09-08 decision): ntfy.sh via NTFY_TOPIC (or NTFY_URL).
Telegram / generic-webhook / Twilio senders were deleted — nothing else is
configured and unconfigured dead code only invites silent-alert bugs.

Always writes artifacts/odds_log/morning_alert_latest.json with preview + send status
(unless --record-name overrides the record file, e.g. the nightly drift banner).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from Python.env_load import load_project_dotenv  # noqa: E402

# Load repo .env so NTFY_TOPIC / NTFY_URL is available even when run from Task
# Scheduler, which does NOT inherit the interactive shell's environment.
load_project_dotenv()

ODDS_DIR = ROOT / "artifacts" / "odds_log"
OUT_PATH = ODDS_DIR / "morning_alert_latest.json"


def _safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_message() -> str:
    rec_path = ODDS_DIR / "recommendations.parquet"
    pick_lines: list[str] = []
    raw_max = os.getenv("ALERT_MAX_BETS", "").strip()
    max_bets = int(raw_max) if raw_max else 0
    if rec_path.exists():
        rec = pl.read_parquet(rec_path)
        if not rec.is_empty() and "recommendation" in rec.columns:
            bets = rec.filter(pl.col("recommendation").cast(pl.Utf8).str.to_uppercase() == "BET")
            if not bets.is_empty():
                ordered_cols = [
                    c
                    for c in [
                        "pitcher_team",
                        "player_name",
                        "away_team",
                        "home_team",
                        "expected_K",
                        "book",
                        "line",
                        "best_side",
                        "best_price",
                        "edge",
                        "stake",
                        "units",
                    ]
                    if c in bets.columns
                ]
                ordered = bets.sort("edge", descending=True).select(ordered_cols)
                top = ordered.head(max_bets).to_dicts() if max_bets > 0 else ordered.to_dicts()
                for row in top:
                    side_raw = str(row.get("best_side") or "").strip().lower()
                    side = "Over" if side_raw == "over" else "Under" if side_raw == "under" else side_raw.title()
                    line = row.get("line")
                    price = row.get("best_price")
                    xk = float(row.get("expected_K") or 0.0)
                    units = float(row.get("units") or 0.0)
                    stake = float(row.get("stake") or 0.0)
                    edge_pct = float(row.get("edge") or 0.0) * 100.0
                    name = str(row.get("player_name") or "")
                    team = str(row.get("pitcher_team") or "")
                    away = str(row.get("away_team") or "")
                    home = str(row.get("home_team") or "")
                    pick_lines.append(
                        f"({away} @ {home}) {name} ({team})\n"
                        f"{side} {line} @ {price}, xK {xk:.2f}\n"
                        f"Stake ${stake:.2f} ({units:.2f}u), Edge {edge_pct:.1f}%\n"
                    )
    now_local = datetime.now()
    today_hdr = f"{now_local.month}/{now_local.day}/{now_local.strftime('%y')}"
    lines = [f"{today_hdr} MLB Props - Daily Recs K.", ""]
    shadow = _safe_json(ODDS_DIR / "aux_market_shadow_summary.json")
    if shadow:
        status = str(shadow.get("status") or "n/a")
        rows_scored = shadow.get("rows_scored")
        if status != "ok":
            lines.append(f"ALERT: shadow lane status={status}, rows_scored={rows_scored}")
            lines.append("")
    if pick_lines:
        lines.extend(pick_lines)
    else:
        lines.append("No BET recommendations.")
    return "\n".join(lines)


def _send_ntfy(text: str, *, title: str = "MLB Props - Daily Recs") -> tuple[bool, str]:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    ntfy_url = os.getenv("NTFY_URL", "").strip()
    if not ntfy_url and topic:
        ntfy_url = f"https://ntfy.sh/{topic}"
    if not ntfy_url:
        return False, "ntfy_env_missing"
    req = request.Request(
        ntfy_url,
        data=text.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "high" if title != "MLB Props - Daily Recs" else "default",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"ntfy_status={resp.status}"
    except Exception as exc:
        return False, f"ntfy_error={exc}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--failure-message",
        default="",
        help=(
            "When the morning workflow died before the board was built, pass a "
            "short failure summary. It is prepended as a RED banner so a broken "
            "automation run still pages you instead of staying silent."
        ),
    )
    p.add_argument(
        "--record-name",
        default="morning_alert_latest.json",
        help=(
            "Send-record filename under artifacts/odds_log/ (basename only). "
            "The nightly drift banner passes its own name so a 5am failure "
            "record never overwrites the morning picks record."
        ),
    )
    args = p.parse_args()

    msg = _build_message()
    if args.failure_message.strip():
        msg = f"AUTOMATION FAILURE\n{args.failure_message.strip()}\n\n{msg}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    send_results: list[dict[str, object]] = []

    if args.dry_run:
        send_results.append({"channel": "preview", "ok": True, "detail": "dry_run"})
    else:
        title = "MLBProps AUTOMATION FAILURE" if args.failure_message.strip() else "MLB Props - Daily Recs"
        ntfy_ok, ntfy_detail = _send_ntfy(msg, title=title)
        send_results.append({"channel": "ntfy", "ok": ntfy_ok, "detail": ntfy_detail})

        if not send_results or not any(r.get("ok") for r in send_results):
            send_results.append(
                {
                    "channel": "none",
                    "ok": False,
                    "detail": "ntfy not configured (NTFY_TOPIC/NTFY_URL) or send failed; preview only.",
                }
            )

    payload = {
        "sent_utc": now,
        "message": msg,
        "results": send_results,
        "any_sent": any(r.get("ok") for r in send_results),
    }
    # Dry-run previews must NOT clobber the last real send record: the
    # automation self-check and the operator both read morning_alert_latest.json
    # as "last actually-sent alert". (A --dry-run test on 2026-09-08 overwrote
    # the live record with a preview payload.)
    out_path = OUT_PATH.parent / "morning_alert_preview.json" if args.dry_run else OUT_PATH.parent / Path(args.record_name).name
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(msg)

    # Fail loudly (non-zero) when no alert channel is configured or every
    # channel failed, so the morning workflow / automation self-check catches a
    # silent alert failure instead of reporting success. Dry-run previews don't
    # exit non-zero.
    if not args.dry_run and (not send_results or not payload["any_sent"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

