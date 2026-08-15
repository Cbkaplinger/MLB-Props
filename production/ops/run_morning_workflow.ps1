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
    param([string]$Label, [string[]]$Args)
    Write-Host "`n[$Label] $($Args -join ' ')"
    & $python @Args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Starting morning workflow in $repoRoot"

if (-not $SkipStatcast) {
    Run-Step "1a refresh_statcast" @("production/ops/refresh_statcast.py")
}
if (-not $SkipFeatures) {
    Run-Step "1b refresh_features" @("production/ops/refresh_features.py", "--skip-training")
}
if (-not $SkipProjectionLog) {
    Run-Step "1c log_projections" @("production/projections/log_projections.py")
}
if (-not $SkipGradeAllLogged) {
    Run-Step "2 grade_all_logged" @("production/projections/grade_projections.py", "--all-logged", "--preferred-only")
}
if (-not $SkipOddsBoard) {
    $boardArgs = @("production/odds/odds_board.py", "--unit", "50")
    if ($QuietBoard) { $boardArgs += "--quiet" }
    Run-Step "3 odds_board" $boardArgs
}
if (-not $SkipOpenPoll) {
    Run-Step "4 poll_open" @("production/odds/poll_odds.py", "--snapshot", "open", "--unit", "50")
}
if (-not $SkipLedgerStatus) {
    Run-Step "5 ledger_status" @("production/odds/grade_odds_ledger.py", "--status")
}

Write-Host "`nMorning workflow complete."
