param(
    [string]$MorningTime = "08:30",
    [string]$WatcherStartTime = "11:30",
    [string]$SettleTime = "03:00",
    [switch]$RunWhetherLoggedOn
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$morningScript = Join-Path $repoRoot "production\ops\run_morning_workflow.ps1"
$watcherScript = Join-Path $repoRoot "production\ops\start_close_watcher_background.ps1"
$settleScript = Join-Path $repoRoot "production\ops\run_end_of_day_settle.ps1"

foreach ($p in @($morningScript, $watcherScript, $settleScript)) {
    if (-not (Test-Path $p)) { throw "Missing script: $p" }
}

function New-Or-UpdateTask {
    param(
        [string]$TaskName,
        [string]$StartTime,
        [string]$ScriptPath
    )
    $runCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    $baseArgs = @(
        "/Create",
        "/TN", $TaskName,
        "/SC", "DAILY",
        "/ST", $StartTime,
        "/TR", $runCmd,
        "/F"
    )
    if ($RunWhetherLoggedOn) {
        # Will prompt for credentials unless preconfigured.
        $baseArgs += @("/RL", "HIGHEST")
    }
    Write-Host "Scheduling $TaskName at $StartTime"
    schtasks @baseArgs | Out-Null
}

New-Or-UpdateTask -TaskName "MLBProps_MorningWorkflow" -StartTime $MorningTime -ScriptPath $morningScript
New-Or-UpdateTask -TaskName "MLBProps_CloseWatcherStart" -StartTime $WatcherStartTime -ScriptPath $watcherScript
New-Or-UpdateTask -TaskName "MLBProps_EndOfDaySettle" -StartTime $SettleTime -ScriptPath $settleScript

Write-Host ""
Write-Host "Scheduled tasks created/updated:"
Write-Host " - MLBProps_MorningWorkflow @ $MorningTime"
Write-Host " - MLBProps_CloseWatcherStart @ $WatcherStartTime"
Write-Host " - MLBProps_EndOfDaySettle @ $SettleTime"
Write-Host ""
Write-Host "Tip: keep PC powered and awake near run windows."
