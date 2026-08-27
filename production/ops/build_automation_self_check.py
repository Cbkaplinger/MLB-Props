"""Build automation self-check snapshot and optionally notify on failures."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request
import os

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
OUT_PATH = ODDS_DIR / "automation_self_check_latest.json"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"

# Pre-registered real-bankroll win-rate bar (see market_clv_gates.md).
BANKROLL_WR_BAR = 0.524
# n_clv at floor >= 12% required before any floor/Kelly move (market_clv_gates).
SKILL_GATE_N = 150
SKILL_GATE_FLOOR = 0.12
# Days without a newly-settled game date before we flag the ledger as stale.
LEDGER_STALE_DAYS = 3

TASKS = [
    "MLBProps_MorningWorkflow",
    "MLBProps_MiddayRefresh",
    "MLBProps_SecondRefresh",
    "MLBProps_CloseWatcherStart",
    "MLBProps_CloseWatcherWatchdog",
    "MLBProps_EndOfDaySettle",
    "MLBProps_EndOfDaySettleBackfill",
]

KEY_FILES = [
    ODDS_DIR / "runtime_monitoring_snapshot.json",
    ODDS_DIR / "daily_kpi_loop_last_run.json",
    ODDS_DIR / "morning_alert_latest.json",
    ODDS_DIR / "aux_market_shadow_summary.json",
]


def _task_status(task_name: str) -> dict[str, str]:
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        return {"task": task_name, "found": "no"}
    row = {"task": task_name, "found": "yes"}
    for line in (proc.stdout or "").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip().lower()
        val = v.strip()
        if key == "status":
            row["status"] = val
        elif key == "last result":
            row["last_result"] = val
        elif key == "next run time":
            row["next_run_time"] = val
    return row


_NOT_RUN_RESULTS = {
    "",
    "0",
    "0x0",
    "267009",  # 0x41301 == task is currently running
    "267011",  # 0x41303 == task has not yet run
    "0x41301",
    "0x41303",
}


def _is_task_healthy(row: dict[str, str]) -> bool:
    if row.get("found") != "yes":
        return False
    status = str(row.get("status", "")).lower()
    if "disabled" in status:
        return False
    # A task whose last run returned a non-zero exit code (other than the
    # "has not yet run" placeholder) actually failed. Status staying "Ready"
    # only means it's scheduled for the next run, not that the last run passed.
    last = str(row.get("last_result", "")).strip()
    if last and last.upper() not in _NOT_RUN_RESULTS:
        return False
    return True


def _ledger_health(now: datetime) -> dict[str, object]:
    """Freshness + skill-gate progress on the settled ledger (read-only)."""
    base: dict[str, object] = {
        "ledger_exists": False,
        "stale": False,
        "skill_gate": None,
        "freshness": None,
    }
    if not LEDGER_PATH.exists():
        return base

    df = pl.read_parquet(LEDGER_PATH)
    if df["game_date"].dtype == pl.String:
        df = df.with_columns(
            pl.col("game_date").str.to_date("%Y-%m-%d").alias("game_date")
        )
    settled = df.filter(pl.col("status") == "settled")

    max_date = settled["game_date"].max()
    stale = max_date is None or (now.date() - max_date).days > LEDGER_STALE_DAYS

    freshness: dict[str, object] = {
        "n_settled": int(settled.height),
        "last_game_date": str(max_date) if max_date is not None else None,
        "days_since_last_settled": (
            None if max_date is None else (now.date() - max_date).days
        ),
        "stale": stale,
    }

    # Skill gate: n_clv at edge>=12%, mean CLV, beat-rate, and WR vs bankroll bar.
    skill: dict[str, object] | None = None
    clv_rows = settled.filter(
        pl.col("clv_pp").is_not_null() & (pl.col("edge") >= SKILL_GATE_FLOOR)
    )
    if clv_rows.height:
        clv = clv_rows["clv_pp"]
        wins = settled.filter(pl.col("result") == "win").height
        losses = settled.filter(pl.col("result") == "loss").height
        wr = wins / (wins + losses) if (wins + losses) else 0.0
        skill = {
            "n_clv_at_floor12": int(clv_rows.height),
            "countdown_to_150": max(SKILL_GATE_N - int(clv_rows.height), 0),
            "gate_met": int(clv_rows.height) >= SKILL_GATE_N,
            "mean_clv_pp": round(float(clv.mean()), 6),
            "beat_close_rate": round(float((clv > 0).mean()), 6),
            "all_time_win_rate": round(wr, 6),
            "win_rate_bar": BANKROLL_WR_BAR,
            "win_rate_passes_bar": wr >= BANKROLL_WR_BAR,
        }

    base["ledger_exists"] = True
    base["stale"] = stale
    base["freshness"] = freshness
    base["skill_gate"] = skill
    return base


def _send_ntfy(text: str) -> tuple[bool, str]:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    url = os.getenv("NTFY_URL", "").strip()
    if not url and topic:
        url = f"https://ntfy.sh/{topic}"
    if not url:
        return False, "ntfy_env_missing"
    req = request.Request(
        url,
        data=text.encode("utf-8"),
        headers={"Title": "MLBProps Automation Check", "Priority": "high"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"ntfy_status={resp.status}"
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        return False, f"telegram_error={exc}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--notify-on-red", action="store_true")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    task_rows = [_task_status(t) for t in TASKS]
    unhealthy = [r for r in task_rows if not _is_task_healthy(r)]

    missing_files = [str(fp) for fp in KEY_FILES if not fp.exists()]
    ledger_health = _ledger_health(now)
    stale_ledger = bool(ledger_health.get("stale"))
    status = (
        "ok"
        if not unhealthy and not missing_files and not stale_ledger
        else "risk"
    )

    payload: dict[str, object] = {
        "snapshot_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "unhealthy_tasks": unhealthy,
        "missing_files": missing_files,
        "stale_ledger": stale_ledger,
        "ledger_health": ledger_health,
        "tasks": task_rows,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")

    if status != "ok" and args.notify_on_red:
        text = (
            "Automation self-check RISK\n"
            f"unhealthy_tasks={len(unhealthy)} "
            f"missing_files={len(missing_files)} "
            f"stale_ledger={stale_ledger}\n"
            f"see {OUT_PATH}"
        )
        nt_ok, _ = _send_ntfy(text)
        tg_ok, _ = _send_telegram(text)
        payload["notify_sent"] = {"ntfy": nt_ok, "telegram": tg_ok}
        OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

