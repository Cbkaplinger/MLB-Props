# Close open ledger tickets whose tip is near (SharpAPI Free tier).
#
# Run after morning open. Leave PowerShell running until today's CLVs are
# filled or you Ctrl+C. Keep the PC awake while the slate is live.
#
#   .\production\run_close_watcher.ps1
#   .\production\run_close_watcher.ps1 -Once
#   .\production\run_close_watcher.ps1 -IntervalSec 90

param(
    [int]$IntervalSec = 120,
    [double]$MinutesBefore = 15,
    [double]$MinutesAfter = 5,
    [switch]$Once,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "production\close_watcher.py"))) {
    $Root = $PSScriptRoot
}
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python"
}

$argList = @(
    "production/close_watcher.py",
    "--interval", "$IntervalSec",
    "--minutes-before", "$MinutesBefore",
    "--minutes-after", "$MinutesAfter"
)
if ($Once) { $argList += "--once" }
if ($DryRun) { $argList += "--dry-run" }

Write-Host "Starting close watcher in $Root"
Write-Host "Keep this window open / PC awake until the slate is done."
& $Py @argList
