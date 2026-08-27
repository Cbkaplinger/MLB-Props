param(
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
    & $python @ScriptArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Starting market refresh in $repoRoot"

$boardArgs = @("production/odds/odds_board.py", "--unit", "50", "--roi-mode", "conservative")
if ($QuietBoard) {
    Write-Warning "QuietBoard requested, but odds_board.py has no --quiet flag; running with normal output."
}
Run-Step "1 odds_board" $boardArgs
Run-Step "2 poll_open" @("production/odds/poll_odds.py", "--snapshot", "open", "--unit", "50", "--roi-mode", "conservative", "--from-recommendations")
Run-Step "3 ledger_status" @("production/odds/grade_odds_ledger.py", "--status")
Run-Step "4 reconcile_board_vs_ledger" @("production/ops/build_board_ledger_reconciliation.py")
Run-Step "5 compact_aux_quote_history" @("production/ops/compact_aux_quote_history.py", "--retention-days", "120")
Run-Step "6 aux_market_shadow_score" @("production/ops/build_aux_market_shadow_score.py")
Run-Step "7 runtime_monitoring_snapshot" @("production/ops/build_runtime_monitoring_snapshot.py")
Run-Step "7b weekly_policy_digest" @("production/ops/build_weekly_policy_digest.py")
Run-Step "7c automation_self_check" @("production/ops/build_automation_self_check.py", "--notify-on-red")
Run-Step "8 morning_alert" @("production/ops/send_morning_alert.py")

Write-Host "`nMarket refresh complete."

