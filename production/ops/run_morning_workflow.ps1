param(
    [switch]$SkipStatcast,
    [switch]$SkipFeatures,
    [switch]$SkipProjectionLog,
    [switch]$SkipGradeAllLogged,
    [switch]$SkipOddsBoard,
    [switch]$SkipOpenPoll,
    [switch]$SkipLedgerStatus,
    [switch]$QuietBoard
)

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
    # -u = unbuffered python so a killed run still leaves truthful step logs
    # (buffered stdout previously vanished, leaving 412-byte mystery logs).
    & $python -u @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "step [$Label] exited $LASTEXITCODE" }
}

Write-Host "Starting morning workflow in $repoRoot"

# First failing step is recorded but does NOT silently skip the alert: the
# 2026-09-06..08 failures died in step 1a and paged nobody. We run
# best-effort through the chain, then always fire send_morning_alert (with a
# failure banner when degraded) before exiting nonzero.
$failure = ""

try {
if (-not $SkipStatcast) {
    Run-Step "1a refresh_statcast" @("production/ops/refresh_statcast.py", "--retries", "3")
}
} catch { $failure += "statcast FAILED: $($_.Exception.Message)`n" }
try {
if (-not $SkipFeatures) {
    Run-Step "1b refresh_features" @("production/ops/refresh_features.py", "--skip-training")
}
} catch { $failure += "features FAILED: $($_.Exception.Message)`n" }
try {
if (-not $SkipProjectionLog) {
    # --allow-stale matches the RUNBOOK canonical loop: a 2-day Statcast lag
    # must produce a labeled degraded slate (build_meta.stale_days), not abort
    # the whole morning (this abort mode caused the 2026-09-04 zero-bet day).
    Run-Step "1c log_projections" @("production/projections/log_projections.py", "--allow-stale")
}
} catch { $failure += "log_projections FAILED: $($_.Exception.Message)`n" }
try {
if (-not $SkipGradeAllLogged) {
    Run-Step "2 grade_all_logged" @("production/projections/grade_projections.py", "--all-logged", "--preferred-only")
}
} catch { $failure += "grade FAILED: $($_.Exception.Message)`n" }
try {
if (-not $SkipOddsBoard) {
    $boardArgs = @("production/odds/odds_board.py", "--unit", "50", "--roi-mode", "conservative", "--write-quotes", "artifacts/odds_log/sharp_quotes_latest.parquet")
    if ($QuietBoard) { $boardArgs += "--quiet" }
    Run-Step "3 odds_board" $boardArgs
}
if (-not $SkipOpenPoll) {
    Run-Step "4 poll_open" @("production/odds/poll_odds.py", "--snapshot", "open", "--unit", "50", "--roi-mode", "conservative", "--from-recommendations")
}
if (-not $SkipLedgerStatus) {
    Run-Step "5 ledger_status" @("production/odds/grade_odds_ledger.py", "--status")
}
Run-Step "6 reconcile_board_vs_ledger" @("production/ops/build_board_ledger_reconciliation.py")
Run-Step "7 policy_governance_report" @("production/ops/build_policy_governance_report.py")
Run-Step "7b compact_aux_quote_history" @("production/ops/compact_aux_quote_history.py", "--retention-days", "120")
Run-Step "7c aux_market_shadow_score" @("production/ops/build_aux_market_shadow_score.py")
Run-Step "8 runtime_monitoring_snapshot" @("production/ops/build_runtime_monitoring_snapshot.py")
Run-Step "8b weekly_policy_digest" @("production/ops/build_weekly_policy_digest.py")
Run-Step "8c automation_self_check" @("production/ops/build_automation_self_check.py", "--notify-on-red")
} catch { $failure += "board/ledger chain FAILED: $($_.Exception.Message)`n" }
try {
    if ($failure) {
        Run-Step "9 morning_alert (FAILURE banner)" @("production/ops/send_morning_alert.py", "--failure-message", $failure)
    } else {
        Run-Step "9 morning_alert" @("production/ops/send_morning_alert.py")
    }
} catch {
    Write-Warning "Morning alert step failed: $($_.Exception.Message)"
    if (-not $failure) { $failure = "alert FAILED: $($_.Exception.Message)`n" }
}

if ($failure) {
    Write-Warning "Morning workflow DEGRADED:`n$failure"
    Write-Host "`nMorning workflow complete with failures."
    exit 1
}

Write-Host "`nMorning workflow complete."
