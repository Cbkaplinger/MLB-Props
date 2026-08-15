param(
    [int]$IntervalSec = 60,
    [double]$MinutesBefore = 2,
    [double]$MinutesAfter = 5
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

$logDir = Join-Path $repoRoot "artifacts\odds_log"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logPath = Join-Path $logDir "close_watcher.log"
$errPath = Join-Path $logDir "close_watcher.err.log"

$argList = @(
    "production/odds/close_watcher.py",
    "--interval", "$IntervalSec",
    "--minutes-before", "$MinutesBefore",
    "--minutes-after", "$MinutesAfter"
)

Write-Host "Launching close watcher in background..."
Write-Host "Log file: $logPath"
Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError $errPath
Write-Host "Close watcher started."
