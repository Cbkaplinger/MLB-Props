# Catch-up run for after the box was off / automation missed a day or two.
#
# Reports ledger status, grades all logged projection dates, then
# self-checks and alerts. It does NOT settle (#113 step 1: only post-game
# tasks pass --auto-settle-api; intraday settling fabricated K=0 finals in
# #83) and does NOT fabricate paper slates for days with no morning run
# (no projections were logged, no lines captured) — those stay a
# documented gap; this only closes out what actually exists.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File production\ops\run_catchup.ps1

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
    & $python -u @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "step [$Label] exited $LASTEXITCODE" }
}

Write-Host "Starting catch-up in $repoRoot"

$failure = ""
try {
    Run-Step "1 ledger_status" @("production/odds/grade_odds_ledger.py", "--status", "--curve")
} catch { $failure += "settle FAILED: $($_.Exception.Message)`n" }
try {
    Run-Step "2 grade_all_logged" @("production/projections/grade_projections.py", "--all-logged", "--preferred-only")
} catch { $failure += "grade FAILED: $($_.Exception.Message)`n" }
try {
    Run-Step "3 ledger_status" @("production/odds/grade_odds_ledger.py", "--status")
} catch { $failure += "ledger_status FAILED: $($_.Exception.Message)`n" }
try {
    Run-Step "4 automation_self_check" @("production/ops/build_automation_self_check.py", "--notify-on-red")
} catch { $failure += "self_check FAILED: $($_.Exception.Message)`n" }
try {
    if ($failure) {
        Run-Step "5 alert (FAILURE banner)" @("production/ops/send_morning_alert.py", "--failure-message", "Catch-up run issues:`n$failure")
    } else {
        Run-Step "5 alert" @("production/ops/send_morning_alert.py")
    }
} catch {
    Write-Warning "Alert step failed: $($_.Exception.Message)"
    if (-not $failure) { $failure = "alert FAILED: $($_.Exception.Message)`n" }
}

if ($failure) {
    Write-Warning "Catch-up DEGRADED:`n$failure"
    exit 1
}
Write-Host "`nCatch-up complete."
