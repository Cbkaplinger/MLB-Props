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
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request
from zoneinfo import ZoneInfo

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from Python.env_load import load_project_dotenv  # noqa: E402
# Load repo .env so NTFY_TOPIC / NTFY_URL is available even when run from Task
# Scheduler, which does NOT inherit the interactive shell's environment.
load_project_dotenv()

ODDS_DIR = ROOT / "artifacts" / "odds_log"
OUT_PATH = ODDS_DIR / "morning_alert_latest.json"
ET = ZoneInfo("America/New_York")


def _load_edge_watch_today(path: Path | None = None) -> dict | None:
    """Today's edge-watch report (newest existing candidate), or None.

    The producer names files with the canonical ET slate date
    (``odds_ledger.et_today`` since OPS-1B 2026-09-23; before that it was
    system-local `date.today()`, UTC on Modal containers vs ET on the laptop).
    Candidates are ET-today then UTC-today; the most recently modified
    parseable file wins (kept as belt-and-suspenders for pre-fix files).
    Unknown (nothing parseable)
    means fail-OPEN: a flips-only caller must page rather than assume quiet.
    """
    if path is not None:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None
    utc_today = datetime.now(timezone.utc).date().isoformat()
    et_today = datetime.now(ET).date().isoformat()
    best: dict | None = None
    best_mtime = -1.0
    for day in (et_today, utc_today):
        candidate = ODDS_DIR / f"edge_watch_report_{day}.json"
        try:
            mtime = candidate.stat().st_mtime
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and mtime > best_mtime:
            best, best_mtime = payload, mtime
    return best


def _flips_fire(state: dict | None, *, failure_message: str = "") -> tuple[bool, str]:
    """Flips-only gate: page on failure, unknown state, or non-empty flips.

    Returns (fire, reason). Quiet ONLY when the watch explicitly reports
    zero flips for today.
    """
    if str(failure_message or "").strip():
        return True, "failure-banner"
    if state is None:
        return True, "unknown-watch-state-fail-open"
    flips = state.get("flips") or []
    if len(flips) > 0:
        return True, f"{len(flips)}-flips"
    return False, "no-flips-quiet"


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
    slip_line = ""
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
            pick = _slip_pick(bets)
            if pick is not None:
                slip_line = (
                    f"Slip pick: {pick.get('player_name')} "
                    f"{str(pick.get('best_side') or '').title()} {pick.get('line')} @ "
                    f"{pick.get('best_price')} ({pick.get('book')}) — "
                    f"top in-band edge (0.12-0.18 rule)"
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
    if slip_line:
        lines.append("")
        lines.append(slip_line)
    return "\n".join(lines)


def _slip_pick(bets: pl.DataFrame) -> dict | None:
    """Single-slip pick for an owner who fires one ticket/day (display-only).

    Measured 2026-09-14 on the juiced taken set: top-edge-per-day = -$1,082
    (-6.9%, monster edge = we are wrong); top edge WITHIN 0.12-0.18 =
    +$3,008 (+20.7%, 291 days). So: max edge inside the band, fallback to
    max edge under the 0.24 cap. Never changes BETs — stars one line.
    """
    rows = bets.to_dicts()
    in_band = [r for r in rows if 0.12 <= float(r.get("edge") or 0.0) < 0.18]
    pool = in_band or [r for r in rows if float(r.get("edge") or 0.0) < 0.24] or rows
    if not pool:
        return None
    return max(pool, key=lambda r: float(r.get("edge") or 0.0))


def _send_ntfy(text: str, *, title: str = "MLB Props - Daily Recs",
               retries: int = 3) -> tuple[bool, str]:
    """POST with retries: a single transient (ntfy/vendor blip) must never
    silently eat a recommendation (owner 2026-09-17: belt-and-suspenders so a
    sent board always pages). Backoff 2s/4s; returns the last outcome."""
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
    last: tuple[bool, str] = (False, "ntfy_error=unknown")
    for attempt in range(max(1, retries)):
        try:
            with request.urlopen(req, timeout=15) as resp:
                return True, f"ntfy_status={resp.status}"
        except Exception as exc:  # noqa: BLE001
            last = (False, f"ntfy_error={exc}")
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    return last


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
            "Send-record filename under artifacts/odds_log/ "
            "(basename only). The nightly drift banner passes its own name so a 5am failure "
            "record never overwrites the morning picks record."
        ),
    )
    p.add_argument(
        "--flips-only",
        action="store_true",
        help=(
            "Hourly mode: page only when today's edge-watch reports flips "
            "(or on failure / unknown watch state, which fail open). "
            "Quiet hours write a preview record and exit 0. "
            "The morning chain never passes this flag - it always fires."
        ),
    )
    args = p.parse_args()

    # DATA-1A serving gates (owner 2026-09-23, fail-LOUD): warnings banner the
    # message, force flips-only pages, and land in the run manifest. Nothing
    # here suppresses a ledger write or a page — a human reads and decides.
    try:
        from Python.serving_gates import check_serving  # noqa: E402

        _gate = check_serving(
            ODDS_DIR, datetime.now(ET).date().isoformat())
        gate_warnings: list[str] = list(_gate.get("warnings") or [])
    except Exception:  # noqa: BLE001 — the gate must never break the alert
        gate_warnings = ["serving-gate import failed (fail-open)"]
    gate_banner = "; ".join(gate_warnings)
    failure_message = "; ".join(
        s for s in (args.failure_message.strip(), gate_banner) if s)

    # Parallel-proofing: the laptop runs the same chain as fallback while the
    # cloud is primary (cutover 2026-09-16; laptop tasks disabled).
    # MLB_PROPS_NO_ALERT=1 turns this into a preview-only
    # run (exit 0) so two machines never double-ping. Set it on whichever
    # host is secondary; removed from the cloud chain at cutover.
    if os.getenv("MLB_PROPS_NO_ALERT", "").strip() == "1" and not args.dry_run:
        msg = _build_message()
        out_path = OUT_PATH.parent / "morning_alert_preview.json"
        out_path.write_text(json.dumps({
            "sent_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "message": msg,
            "results": [{"channel": "preview", "ok": True, "detail": "MLB_PROPS_NO_ALERT=1"}],
            "any_sent": False,
        }, indent=2), encoding="utf-8")
        print(f"NO_ALERT=1: wrote {out_path}")
        print(msg)
        return

    if args.flips_only and not args.dry_run:
        _fire, _why = _flips_fire(
            _load_edge_watch_today(), failure_message=failure_message)
        if not _fire:
            out_path = OUT_PATH.parent / "morning_alert_preview.json"
            out_path.write_text(json.dumps({
                "sent_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": f"flips-only quiet ({_why}); no page sent.",
                "results": [{"channel": "suppressed", "ok": True,
                             "detail": f"flips-only:{_why}"}],
                "any_sent": False,
            }, indent=2), encoding="utf-8")
            print(f"flips-only quiet ({_why}): wrote {out_path}")
            return

    msg = _build_message()
    if args.failure_message.strip():
        msg = f"AUTOMATION FAILURE\n{args.failure_message.strip()}\n\n{msg}"
    elif gate_warnings:
        msg = f"SERVING-GATE\n{gate_banner}\n\n{msg}"
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
    # OBS-1 run manifest (provenance only — never gates paging, never raises).
    # Slate/rows come from the board's own meta file; versions are content
    # hashes of the live pins. Anything unreadable stays null (unknown).
    try:
        from Python.run_manifest import (  # noqa: E402
            artifact_version,
            emit_manifest_safely,
            manifest_from_alert,
            manifest_path,
        )
        _meta = _safe_json(OUT_PATH.parent / "recommendations_meta.json")
        _man = manifest_from_alert(
            any_sent=bool(payload["any_sent"]),
            failure_message=args.failure_message,
            warnings=gate_warnings or None,
            slate_date=_meta.get("slate_date"),
            input_rows={
                k: int(_meta[k]) for k in ("n_board", "n_quotes", "n_matched")
                if isinstance(_meta.get(k), (int, float))
            } or None,
            output_rows={
                k: int(_meta[k]) for k in ("n_bet", "n_hold")
                if isinstance(_meta.get(k), (int, float))
            } or None,
            as_of_utc=_meta.get("built_at_utc"),
            input_cutoff_utc=_meta.get("built_at_utc"),
            policy_version=artifact_version(
                ROOT / "production" / "ops" / "kpi_policy.json", "kpi"),
            model_version=artifact_version(
                ROOT / "production" / "ops" / "live_krate_ensemble.json", "krate"),
            calibration_version=artifact_version(
                ROOT / "artifacts" / "models" / "prob_calibration_production.json",
                "ws1c"),
        )
        emit_manifest_safely(_man, manifest_path(OUT_PATH.parent, "P4-SERVE"))
    except Exception:
        pass
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

