"""Build automation self-check snapshot and optionally notify on failures."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request
import os

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
OUT_PATH = ODDS_DIR / "automation_self_check_latest.json"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
NOTIFY_STATE_PATH = ODDS_DIR / "automation_self_check_notify_state.json"
# Re-send a still-open RISK at most this often (a daily reminder, not per-run
# spam). A *new* risk fingerprint always notifies immediately.
NOTIFY_REMIND_HOURS = 20.0

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
    "MLBProps_NightlyDrift",
    # Self-watch: last_result here reflects the PREVIOUS scheduled self-check
    # run, so a repeatedly-crashing self-check still pages via the other
    # chains (morning/midday run this script inline with --notify-on-red).
    "MLBProps_AutomationSelfCheck",
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
    # One prop per (date, player, line, side), best-edge book, so the skill-gate
    # n and win-rate are honest (no DK+FD double count of the same prop).
    if not settled.is_empty():
        settled = dedupe_ledger_props(settled)

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


def _risk_fingerprint(
    unhealthy: list[dict[str, str]],
    missing_files: list[str],
    stale_ledger: bool,
) -> str:
    """Stable id for the current risk shape (drives notify dedupe)."""
    parts = sorted(f"{r.get('task')}:{r.get('last_result', '?')}" for r in unhealthy)
    return "|".join([",".join(parts), ",".join(sorted(missing_files)), str(bool(stale_ledger))])


def _load_notify_state() -> dict:
    if not NOTIFY_STATE_PATH.exists():
        return {}
    try:
        return json.loads(NOTIFY_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _should_notify(fingerprint: str, now: datetime) -> tuple[bool, str]:
    """Notify on new risk, or as a daily reminder while risk stays open.

    Before 2026-09-08 every chain run with --notify-on-red paged on every
    RISK, so one stuck condition (e.g. a stale ledger over a quiet weekend)
    spammed 3+ identical notifications a day. Now: first sighting notifies,
    repeats notify at most once per NOTIFY_REMIND_HOURS.
    """
    state = _load_notify_state()
    last_fp = str(state.get("fingerprint") or "")
    last_sent_raw = str(state.get("last_sent_utc") or "")
    if fingerprint != last_fp:
        return True, "new_risk_fingerprint"
    try:
        last_sent = datetime.fromisoformat(last_sent_raw.replace("Z", "+00:00"))
        age_h = (now - last_sent).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        return True, "unparseable_last_sent"
    if age_h >= NOTIFY_REMIND_HOURS:
        return True, f"daily_reminder age_h={age_h:.1f}"
    return False, f"duplicate_suppressed age_h={age_h:.1f}"


def _record_notify(fingerprint: str, now_utc: str) -> None:
    NOTIFY_STATE_PATH.write_text(
        json.dumps(
            {"fingerprint": fingerprint, "last_sent_utc": now_utc},
            indent=2,
        ),
        encoding="utf-8",
    )


def _describe_risk(
    unhealthy: list[dict[str, str]],
    missing_files: list[str],
    ledger_health: dict[str, object],
) -> list[str]:
    """Human-readable risk lines for the notification body."""
    lines: list[str] = []
    for r in unhealthy:
        lines.append(
            f"- task {r.get('task')} last_result={r.get('last_result', '?')} "
            f"(status={r.get('status', '?')}, next={r.get('next_run_time', '?')}). "
            "Non-zero last_result = that run failed; check its log in artifacts/ops_log/."
        )
    for fp in missing_files:
        lines.append(f"- missing expected file: {fp}")
    fresh = ledger_health.get("freshness") or {}
    if ledger_health.get("stale"):
        lines.append(
            f"- ledger stale: last settled game_date={fresh.get('last_game_date')} "
            f"({fresh.get('days_since_last_settled')}d ago, n_settled={fresh.get('n_settled')}). "
            "Usually clears on its own at the next 3am settle once games complete; "
            "if it persists, the settle chain is failing."
        )
    return lines


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
        fingerprint = _risk_fingerprint(unhealthy, missing_files, stale_ledger)
        now_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        send, reason = _should_notify(fingerprint, now)
        detail_lines = _describe_risk(unhealthy, missing_files, ledger_health)
        text = (
            "MLBProps Automation self-check RISK\n"
            + "\n".join(detail_lines)
            + f"\nsee {OUT_PATH}"
        )
        if send:
            nt_ok, _ = _send_ntfy(text)
            payload["notify_sent"] = {"ntfy": nt_ok}
            if nt_ok:
                _record_notify(fingerprint, now_utc)
            payload["notify_reason"] = reason
            print(f"risk notify sent ({reason})")
        else:
            payload["notify_sent"] = {"ntfy": False}
            payload["notify_reason"] = reason
            print(f"risk notify skipped ({reason})")
        OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    elif status == "ok":
        # Risk cleared: drop the dedupe state so the NEXT risk notifies
        # immediately instead of being mistaken for a duplicate.
        if NOTIFY_STATE_PATH.exists():
            NOTIFY_STATE_PATH.unlink()
        print("status ok")


if __name__ == "__main__":
    main()

