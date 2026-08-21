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
$env:PYTHONUNBUFFERED = "1"

$logDir = Join-Path $repoRoot "artifacts\odds_log"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logPath = Join-Path $logDir "close_watcher.log"

$argList = @(
    "-u",
    "production/odds/close_watcher.py",
    "--interval", "$IntervalSec",
    "--minutes-before", "$MinutesBefore",
    "--minutes-after", "$MinutesAfter"
)

$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -ieq "python.exe" -and
        $_.CommandLine -and
        $_.CommandLine -like "*production/odds/close_watcher.py*"
    }
if ($existing) {
    $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ", "
    Write-Host "Close watcher already running (PID: $pids). Skipping new launch."
    exit 0
}

Write-Host "Launching close watcher..."
Write-Host "Log file: $logPath"
Write-Host "Task will exit after spawning detached watcher."

$argString = ($argList | ForEach-Object {
    if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
}) -join " "

$proc = Start-Process -FilePath $python `
    -ArgumentList $argString `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError $logPath `
    -WindowStyle Hidden `
    -PassThru

if (-not $proc -or -not $proc.Id) {
    throw "Failed to start close watcher process."
}

Write-Host "Close watcher started (PID: $($proc.Id))."
exit 0
