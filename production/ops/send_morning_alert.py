"""Send morning recommendation/status alert.

Channels (free-first):
- ntfy.sh via NTFY_TOPIC (or NTFY_URL)
- Telegram bot via TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
- ALERT_WEBHOOK_URL (generic JSON webhook; posts {"text": "..."} )
- Twilio SMS (legacy fallback)

Always writes artifacts/odds_log/morning_alert_latest.json with preview + send status.
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request
import os

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
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


def _send_webhook(url: str, text: str) -> tuple[bool, str]:
    data = json.dumps({"text": text}).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"webhook_status={resp.status}"
    except Exception as exc:
        return False, f"webhook_error={exc}"


def _send_ntfy(text: str) -> tuple[bool, str]:
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
            "Title": "MLB Props - Daily Recs",
            "Priority": "default",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"ntfy_status={resp.status}"
    except Exception as exc:
        return False, f"ntfy_error={exc}"


def _send_telegram(text: str) -> tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "telegram_env_missing"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with request.urlopen(req, timeout=20) as resp:
            return True, f"telegram_status={resp.status}"
    except Exception as exc:
        return False, f"telegram_error={exc}"


def _send_twilio(text: str) -> tuple[bool, str]:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_n = os.getenv("TWILIO_FROM_NUMBER", "")
    to_n = os.getenv("ALERT_TO_NUMBER", "")
    if not all([sid, token, from_n, to_n]):
        return False, "twilio_env_missing"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    body = parse.urlencode({"From": from_n, "To": to_n, "Body": text}).encode("utf-8")
    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req = request.Request(
        url,
        data=body,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            return True, f"twilio_status={resp.status}"
    except Exception as exc:
        return False, f"twilio_error={exc}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    msg = _build_message()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    webhook = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    send_results: list[dict[str, object]] = []

    if args.dry_run:
        send_results.append({"channel": "preview", "ok": True, "detail": "dry_run"})
    else:
        ntfy_ok, ntfy_detail = _send_ntfy(msg)
        if ntfy_detail != "ntfy_env_missing":
            send_results.append({"channel": "ntfy", "ok": ntfy_ok, "detail": ntfy_detail})

        tg_ok, tg_detail = _send_telegram(msg)
        if tg_detail != "telegram_env_missing":
            send_results.append({"channel": "telegram", "ok": tg_ok, "detail": tg_detail})

        if webhook:
            ok, detail = _send_webhook(webhook, msg)
            send_results.append({"channel": "webhook", "ok": ok, "detail": detail})

        tw_ok, tw_detail = _send_twilio(msg)
        if tw_detail != "twilio_env_missing":
            send_results.append({"channel": "twilio_sms", "ok": tw_ok, "detail": tw_detail})

        if not send_results:
            send_results.append(
                {
                    "channel": "none",
                    "ok": False,
                    "detail": "No ntfy/Telegram/webhook/Twilio configuration found; preview only.",
                }
            )

    payload = {
        "sent_utc": now,
        "message": msg,
        "results": send_results,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(msg)


if __name__ == "__main__":
    main()

