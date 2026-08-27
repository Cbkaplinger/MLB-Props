param(
    [int]$StaleMinutes = 90,
    [switch]$ForceRestart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$logPath = Join-Path $repoRoot "artifacts\odds_log\close_watcher.log"
$launcher = Join-Path $repoRoot "production\ops\start_close_watcher_background.ps1"

if (-not (Test-Path $launcher)) {
    throw "Missing launcher script: $launcher"
}

function Get-WatcherProcesses {
    # Scope the health scan to the canonical .venv launcher process ONLY.
    # The launcher (start_close_watcher_background.ps1) runs close_watcher.py under
    # the repo .venv interpreter. It in turn spawns a short-lived system-Python
    # worker child (also with close_watcher.py in its command line) as part of the
    # SAME logical watcher. Matching *any* interpreter here makes the watchdog count
    # parent+child as two watchers and, on restart, Stop-Process both PIDs - which
    # kills the single logical watcher and triggers a needless re-spawn cascade.
    # Keying on the .venv interpreter keeps the count to one logical watcher (the
    # parent that owns the pid-file / run lock); the child is covered by it.
    $venvMarker = "\.venv\Scripts\python.exe"
    return Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -ieq "python.exe" -and
            $_.ExecutablePath -and
            $_.ExecutablePath -like "*$venvMarker" -and
            $_.CommandLine -and
            $_.CommandLine -like "*production/odds/close_watcher.py*"
        }
}

function Get-HeartbeatAgeMinutes {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $lines = Get-Content -Path $Path -Tail 80 -ErrorAction SilentlyContinue
    if (-not $lines) { return $null }
    $arr = @($lines)
    [array]::Reverse($arr)
    foreach ($line in $arr) {
        if ($line.Length -lt 20) { continue }
        $ts = $line.Substring(0, 20)
        try {
            $dt = [datetime]::ParseExact($ts, "yyyy-MM-ddTHH:mm:ssZ", [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal)
            $age = (New-TimeSpan -Start $dt.ToUniversalTime() -End (Get-Date).ToUniversalTime()).TotalMinutes
            return [math]::Round($age, 2)
        } catch {
            continue
        }
    }
    return $null
}

$procs = Get-WatcherProcesses
$heartbeatAge = Get-HeartbeatAgeMinutes -Path $logPath
$shouldRestart = $ForceRestart.IsPresent -or (-not $procs) -or ($heartbeatAge -ne $null -and $heartbeatAge -gt $StaleMinutes)

if (-not $shouldRestart) {
    $pidList = ($procs | Select-Object -ExpandProperty ProcessId) -join ", "
    Write-Host "Close watcher healthy. PID(s): $pidList | heartbeat_age_min=$heartbeatAge"
    exit 0
}

if ($procs) {
    $pids = $procs | Select-Object -ExpandProperty ProcessId
    foreach ($pid in $pids) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "Stopped stale watcher PID $pid"
        } catch {
            Write-Warning "Failed to stop PID ${pid}: $($_.Exception.Message)"
        }
    }
}

Write-Host "Restarting close watcher..."
powershell -NoProfile -ExecutionPolicy Bypass -File $launcher | Out-Host
Write-Host "Watchdog completed."

