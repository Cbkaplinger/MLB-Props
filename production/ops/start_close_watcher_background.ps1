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
$errPath = Join-Path $logDir "close_watcher.err.log"

$argList = @(
    "-u",
    "production/odds/close_watcher.py",
    "--interval", "$IntervalSec",
    "--minutes-before", "$MinutesBefore",
    "--minutes-after", "$MinutesAfter"
)

# Pid-file guard so exactly ONE watcher runs even if the scheduled task and
# the watchdog launch concurrently/race. If the recorded PID is still alive we
# skip; otherwise (stale) we reclaim the slot.
$pidFile = Join-Path $logDir "close_watcher.pid"
function Test-WatcherAlive([string]$PidPath) {
    if (-not (Test-Path $PidPath)) { return $false }
    $Recorded = (Get-Content $PidPath -Raw).Trim()
    if (-not ($Recorded -match '^\d+$')) { return $false }
    $Proc = Get-Process -Id ([int]$Recorded) -ErrorAction SilentlyContinue
    return ($null -ne $Proc)
}

if (Test-WatcherAlive $pidFile) {
    $p = Get-Content $pidFile -Raw
    Write-Host "Close watcher already running (PID file: $p). Skipping new launch."
    exit 0
}
# Also honor a live process scan as a fallback guard.
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

Start-Sleep -Milliseconds 300
if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }

Write-Host "Launching close watcher..."
Write-Host "Log file: $logPath"
Write-Host "Task will exit after spawning detached watcher."

$proc = Start-Process -FilePath $python `
    -ArgumentList $argList `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -PassThru

if (-not $proc -or -not $proc.Id) {
    throw "Failed to start close watcher process."
}

# Record the spawned PID. The spawned child may re-exec on some systems, so
# also accept the first process we find matching the watcher command line.
$proc.Id | Out-File -FilePath $pidFile -Encoding ascii
Start-Sleep -Milliseconds 500
if (-not (Test-WatcherAlive $pidFile)) {
    $child = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -ieq "python.exe" -and
            $_.CommandLine -and
            $_.CommandLine -like "*production/odds/close_watcher.py*"
        } | Select-Object -First 1
    if ($child) {
        $child.ProcessId | Out-File -FilePath $pidFile -Encoding ascii
    }
}

Write-Host "Close watcher started (PID: $($proc.Id))."
exit 0
