# Wake-recovery run for after the box was off / asleep for a day or more.
#
# Rebuilds the full chain from scratch: statcast -> features -> projections ->
# board -> poll -> alert. Best-effort throughout: first failure is recorded,
# the chain continues, and the alert always fires (with a failure banner when
# degraded) before exiting nonzero. Never settles intraday (#83) and never
# fabricates paper slates for missed days (those stay a documented gap).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File production\ops\run_wake_recovery.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python not found at $python"
}
Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"

function Run-Step {
    param([string]$Label, [string[]]$ScriptArgs)
    Write-Host "`n[$Label] $($ScriptArgs -join ' ')"
    # -u = unbuffered python so a killed run still leaves truthful step logs.
    & $python -u @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "step [$Label] exited $LASTEXITCODE" }
}

Write-Host "Starting wake-recovery in $repoRoot"

# NOTE: `throw` below raises plain strings, so catch blocks must read `$_`
# (not `$_.Exception.Message`, which is blank for string throws -- the
# 2026-09-11 blank-banner root cause).
$failure = ""
try {
    Run-Step "1a refresh_statcast" @("production/ops/refresh_statcast.py", "--retries", "3")
} catch { $failure += "statcast FAILED: $_`n" }
try {
    Run-Step "1b refresh_features" @("production/ops/refresh_features.py", "--skip-training")
} catch { $failure += "features FAILED: $_`n" }
try {
    Run-Step "1c log_projections" @("production/projections/log_projections.py", "--allow-stale")
} catch { $failure += "log_projections FAILED: $_`n" }
try {
    Run-Step "2 grade_all_logged" @("production/projections/grade_projections.py", "--all-logged", "--preferred-only")
} catch { $failure += "grade FAILED: $_`n" }
try {
    Run-Step "3 odds_board" @("production/odds/odds_board.py", "--unit", "50", "--roi-mode", "conservative")
    Run-Step "4 poll_open" @("production/odds/poll_odds.py", "--snapshot", "open", "--unit", "50", "--roi-mode", "conservative", "--from-recommendations")
    Run-Step "5 ledger_status" @("production/odds/grade_odds_ledger.py", "--status")
} catch { $failure += "board/poll chain FAILED: $_`n" }
try {
    if ($failure) {
        Run-Step "6 alert (FAILURE banner)" @("production/ops/send_morning_alert.py", "--failure-message", $failure)
    } else {
        Run-Step "6 alert" @("production/ops/send_morning_alert.py")
    }
} catch {
    Write-Warning "Alert step failed: $_"
    if (-not $failure) { $failure = "alert FAILED: $_`n" }
}

if ($failure) {
    Write-Warning "Wake-recovery DEGRADED:`n$failure"
    exit 1
}
Write-Host "`nWake-recovery complete."
