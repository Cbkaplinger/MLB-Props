param(
    [switch]$SkipCurve
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

$args = @(
    "production/odds/grade_odds_ledger.py",
    "--auto-settle-api",
    "--void-scratches",
    "--status"
)
if (-not $SkipCurve) {
    $args += "--curve"
}

Write-Host "Running end-of-day settle..."
& $python @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "End-of-day settle complete."
