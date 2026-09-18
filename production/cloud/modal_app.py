"""Modal cloud scaffold (STAGED — not deployed; needs owner `modal token new`).

Hosts the daily chain on Modal Starter ($0): image carries code + deps,
a Volume carries state, Secrets carry keys. No policy logic lives here —
each job shells to the same scripts the laptop runs, so laptop and cloud
execute identical code during the >=7 parallel days.

State on the volume (one-time upload, then incremental):
  hot state (~350 MB): data/processed/*.parquet (L3/rolling, biggest),
    artifacts/live_scores, artifacts/odds_log, artifacts/projection_log,
    artifacts/models, data/dimensions, production/ops/*.json policies.
  NOT shipped: Savant raw (GBs, re-pulled incrementally from network),
    Odds-Historical lake (research-only, stays on laptop),
    data/Open-Command (research-only).
Daily refresh (same as wake-recovery): statcast incremental pull over the
network -> L2/L3 rebuild on volume -> projections append -> board -> poll
-> ntfy alert. Single-writer parquet appends; no DB needed (see README:
SQL buys nothing at 18k rows with one writer).

Secrets (modal secret create): SHARPAPI_KEY, THEODDSAPI_KEY, NTFY_TOPIC.
State layout on the volume mirrors the repo tree (data/, artifacts/) so
config's MLB_PROPS_DATA_DIR / MLB_PROPS_OUTPUT_DIR overrides point at it.
One-time upload: modal volume put mlb-props-state data/ data + artifacts/
artifacts (hot state ~350 MB; Savant raw + Odds-Historical lake stay local).
Deploy: modal deploy production/cloud/modal_app.py (after token + upload).
Close-sweep cron (watcher replacement) is the `close_sweep` function below:
fetches latest quotes in game windows via run_close_sweep.py, writes close
rows, exits (ET-window-gated, idempotent).
"""

from __future__ import annotations

APP_NAME = "mlb-props"
VOLUME_NAME = "mlb-props-state"
SECRET_NAME = "mlb-props-keys"
# All wall-clock jobs run on New York local time (OPS-1A 2026-09-17: explicit
# IANA timezone so EST no longer fires 1h early; expressions below are LOCAL,
# not UTC.
SCHEDULE_TZ = "America/New_York"
CRON_MORNING = "0 8 * * *"  # 08:00 NY daily
CRON_HOURLY = "0 9-22 * * *"  # hourly board 09:00-22:00 ET (EDT); 08:00 is morning's
CRON_SWEEP = "*/20 12-22 * * *"  # close sweeps q20min 12:00-22:07 ET
CRON_SETTLE = "0 3 * * *"  # 03:00 NY daily
CRON_DRIFT = "30 5 * * *"  # 05:30 NY daily

ENV = {"PYTHONIOENCODING": "utf-8",
       "MLB_PROPS_DATA_DIR": "/state/data",
       "MLB_PROPS_OUTPUT_DIR": "/state/artifacts",
       "MLB_PROPS_SAVANT_DATA_DIR": "/state/data/Savant-Data/regular"}

# OPS-1A 2026-09-17: image e ships the tz deploy (heartbeat marker).
IMAGE_VERSION = "2026-09-17f"


def _beat(job: str, ok: bool, note: str = "") -> None:
    """Append one heartbeat line to the volume (proves firing, no alerts).

    Read it locally any time: it shows every cloud run with UTC time and
    pass/fail. Silent by design — ntfy stays for boards and failures.
    """
    import datetime
    import json
    import os
    try:
        line = json.dumps({"job": job, "utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
            "ok": bool(ok), "note": note})
        with open("/state/artifacts/odds_log/cloud_heartbeat.jsonl", "a",
                  encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _link_state() -> None:
    """Point repo-tree state dirs at the volume (single place, robust).

    Several scripts resolve artifact paths from the repo root instead of
    config (edge-watch state, alert records). Symlinking makes BOTH styles
    land on the volume: config-aware code uses /state directly, repo-root
    code follows the link. Without this, records split-brain between volume
    (ledger) and ephemeral container (alerts) — caught 2026-09-14.
    """
    import os
    repo = "/root/mlb-props"
    for name in ("artifacts", "data"):
        link = os.path.join(repo, name)
        target = os.path.join("/state", name)
        os.makedirs(target, exist_ok=True)
        if os.path.islink(link) or os.path.exists(link):
            if os.path.islink(link):
                os.unlink(link)
            else:
                import shutil
                shutil.rmtree(link) if os.path.isdir(link) else os.unlink(link)
        os.symlink(target, link)

try:
    import modal

    app = modal.App(APP_NAME)
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install("polars", "lightgbm", "numpy", "scipy",
                     "scikit-learn", "pybaseball", "joblib", "requests")
        .add_local_dir("src", "/root/mlb-props/src")
        .add_local_dir("production", "/root/mlb-props/production")
    )
    volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
    secrets = modal.Secret.from_name(SECRET_NAME)

    @app.function(image=image, volumes={"/state": volume}, secrets=[secrets],
                  schedule=modal.Cron(CRON_MORNING, timezone=SCHEDULE_TZ), timeout=3600)
    def morning_workflow() -> None:
        import os
        import subprocess
        os.environ.update(ENV)
        os.environ["MLB_PROPS_NO_ALERT"] = "1"  # laptop is primary alerter
        _link_state()
        for step in (
            ["python", "-u", "production/ops/refresh_statcast.py", "--retries", "3"],
            ["python", "-u", "production/ops/refresh_features.py", "--skip-training"],
            ["python", "-u", "production/projections/log_projections.py", "--allow-stale"],
            ["python", "-u", "production/odds/odds_board.py", "--unit", "50",
             "--roi-mode", "conservative"],
            ["python", "-u", "production/odds/poll_odds.py", "--snapshot", "open",
             "--unit", "50", "--roi-mode", "conservative", "--from-recommendations"],
            ["python", "-u", "production/ops/send_morning_alert.py"],
        ):
            subprocess.run(step, cwd="/root/mlb-props", check=False)
        _beat("morning_workflow", True)

    @app.function(image=image, volumes={"/state": volume}, secrets=[secrets],
                  schedule=modal.Cron(CRON_HOURLY, timezone=SCHEDULE_TZ), timeout=1800)
    def hourly_refresh() -> None:
        """Hourly board + poll + edge-watch + alert, 08:00-22:00 ET.

        Mirrors run_market_refresh.ps1: projections re-log (dynamic lineups),
        then board/poll/watch/alert on fresh numbers. ~15 runs/day x ~2 min:
        still inside free-tier margin.
        """
        import os
        import subprocess
        os.environ.update(ENV)
        os.environ["MLB_PROPS_NO_ALERT"] = "1"  # laptop is primary alerter
        _link_state()
        for step in (
            ["python", "-u", "production/projections/log_projections.py", "--allow-stale"],
            ["python", "-u", "production/odds/odds_board.py", "--unit", "50",
             "--roi-mode", "conservative", "--write-quotes",
             "artifacts/odds_log/sharp_quotes_latest.parquet"],
            ["python", "-u", "production/odds/poll_odds.py", "--snapshot", "open",
             "--unit", "50", "--roi-mode", "conservative", "--from-recommendations",
             "--quotes-file", "artifacts/odds_log/sharp_quotes_latest.parquet"],
            ["python", "-u", "production/ops/frozen_edge_watch.py"],
            ["python", "-u", "production/ops/send_morning_alert.py", "--flips-only"],
        ):
            subprocess.run(step, cwd="/root/mlb-props", check=False)
        _beat("hourly_refresh", True)

    @app.function(image=image, volumes={"/state": volume}, secrets=[secrets],
                  schedule=modal.Cron(CRON_SWEEP, timezone=SCHEDULE_TZ), timeout=900)
    def close_sweep() -> None:
        """Close fills q20min in game windows (watcher-daemon replacement).

        Mirrors run_close_sweep.py: ET-window-gated, idempotent, exits clean
        outside windows. ~25 runs/day x ~1 min: pennies.
        """
        import os
        import subprocess
        os.environ.update(ENV)
        _link_state()
        subprocess.run(["python", "-u", "production/ops/run_close_sweep.py"],
                       cwd="/root/mlb-props", check=False)
        _beat("close_sweep", True)

    @app.function(image=image, volumes={"/state": volume}, secrets=[secrets],
                  schedule=modal.Cron(CRON_SETTLE, timezone=SCHEDULE_TZ), timeout=1800)
    def end_of_day_settle() -> None:
        import os
        import subprocess
        os.environ.update(ENV)
        _link_state()
        for step in (
            ["python", "-u", "production/odds/grade_odds_ledger.py",
             "--auto-settle-api", "--void-scratches", "--status", "--curve"],
            ["python", "-u", "production/ops/build_validation_ops_report.py"],
            ["python", "-u", "production/ops/build_daily_operator_summary.py"],
            ["python", "-u", "production/ops/build_policy_governance_report.py"],
        ):
            subprocess.run(step, cwd="/root/mlb-props", check=False)
        _beat("end_of_day_settle", True)

    @app.function(image=image, volumes={"/state": volume}, secrets=[secrets],
                  schedule=modal.Cron(CRON_DRIFT, timezone=SCHEDULE_TZ), timeout=1800)
    def nightly_drift() -> None:
        import os
        import subprocess
        os.environ.update(ENV)
        _link_state()
        for step in (
            ["python", "-u", "production/odds/grade_odds_ledger.py",
             "--auto-settle-api", "--void-scratches", "--status", "--curve"],
            ["python", "-u", "production/projections/grade_projections.py",
             "--all-logged", "--preferred-only"],
            ["python", "-u", "production/ops/check_nightly_drift.py"],
            ["python", "-u", "production/ops/build_automation_self_check.py", "--notify-on-red"],
        ):
            subprocess.run(step, cwd="/root/mlb-props", check=False)
        _beat("nightly_drift", True)

except ImportError:  # modal not installed locally: file still parses, deploy needs it
    app = None  # noqa: F841
