param(
    [string]$MorningTime = "08:30",
    [string]$MiddayRefreshTime = "11:00",
    [string]$SecondRefreshTime = "13:45",
    [string]$WatcherStartTime = "11:30",
    [string]$WatcherWatchdogTime = "12:15",
    [string]$SettleTime = "03:00",
    [string]$AutomationSelfCheckTime = "08:50",
    [switch]$RunWhetherLoggedOn,
    [string]$TaskUser = "",
    [string]$TaskPassword = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$morningScript = Join-Path $repoRoot "production\ops\run_morning_workflow.ps1"
$middayScript = Join-Path $repoRoot "production\ops\run_market_refresh.ps1"
$watcherScript = Join-Path $repoRoot "production\ops\start_close_watcher_background.ps1"
$settleScript = Join-Path $repoRoot "production\ops\run_end_of_day_settle.ps1"
$selfCheckScript = Join-Path $repoRoot "production\ops\build_automation_self_check.py"

foreach ($p in @($morningScript, $middayScript, $watcherScript, $settleScript, $selfCheckScript)) {
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
        if (-not $TaskUser -or -not $TaskPassword) {
            throw "RunWhetherLoggedOn requires -TaskUser and -TaskPassword."
        }
        $baseArgs += @("/RU", $TaskUser, "/RP", $TaskPassword, "/RL", "HIGHEST")
    }
    Write-Host "Scheduling $TaskName at $StartTime"
    schtasks @baseArgs | Out-Null
}

function New-Or-UpdateRepeatingTask {
    param(
        [string]$TaskName,
        [string]$StartTime,
        [string]$ScriptPath,
        [int]$RepeatMinutes = 60,
        [string]$Duration = "12:00"
    )
    $runCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    $baseArgs = @(
        "/Create",
        "/TN", $TaskName,
        "/SC", "DAILY",
        "/ST", $StartTime,
        "/TR", $runCmd,
        "/RI", "$RepeatMinutes",
        "/DU", $Duration,
        "/F"
    )
    if ($RunWhetherLoggedOn) {
        if (-not $TaskUser -or -not $TaskPassword) {
            throw "RunWhetherLoggedOn requires -TaskUser and -TaskPassword."
        }
        $baseArgs += @("/RU", $TaskUser, "/RP", $TaskPassword, "/RL", "HIGHEST")
    }
    Write-Host "Scheduling $TaskName at $StartTime (every ${RepeatMinutes}m for $Duration)"
    schtasks @baseArgs | Out-Null
}

function New-Or-UpdatePythonTask {
    param(
        [string]$TaskName,
        [string]$StartTime,
        [string]$ScriptPath
    )
    $python = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { throw "Missing python: $python" }
    $runCmd = "`"$python`" `"$ScriptPath`""
    $baseArgs = @(
        "/Create",
        "/TN", $TaskName,
        "/SC", "DAILY",
        "/ST", $StartTime,
        "/TR", $runCmd,
        "/F"
    )
    if ($RunWhetherLoggedOn) {
        if (-not $TaskUser -or -not $TaskPassword) {
            throw "RunWhetherLoggedOn requires -TaskUser and -TaskPassword."
        }
        $baseArgs += @("/RU", $TaskUser, "/RP", $TaskPassword, "/RL", "HIGHEST")
    }
    Write-Host "Scheduling $TaskName at $StartTime"
    schtasks @baseArgs | Out-Null
}

# Make every MLBProps task run "no matter what": wake the sleeping lid-closed
# PC (WakeToRun), allow start while on battery, and don't stop if it goes on
# battery mid-run. Preserves all other settings (logon, execution, restart)
# by toggling only these elements in each task's XML.
function Enable-MLBPropsReliableRun {
    $tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "MLBProps*" }
    foreach ($t in $tasks) {
        $xml = Export-ScheduledTask -TaskName $t.TaskName
        if ($xml -match "<WakeToRun>false</WakeToRun>") {
            $xml = $xml -replace "<WakeToRun>false</WakeToRun>", "<WakeToRun>true</WakeToRun>"
        } elseif ($xml -notmatch "<WakeToRun>true</WakeToRun>") {
            $xml = $xml -replace "<Settings>", "<Settings><WakeToRun>true</WakeToRun>"
        }
        $xml = $xml -replace "<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>", "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        $xml = $xml -replace "<StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>", "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        # Run a missed schedule as soon as the machine is next available. Without
        # StartWhenAvailable, Task Scheduler silently drops an overnight/early-morning
        # trigger whose time passed while the PC was asleep (Event 153 + 0x80070E20).
        if ($xml -match "<StartWhenAvailable>false</StartWhenAvailable>") {
            $xml = $xml -replace "<StartWhenAvailable>false</StartWhenAvailable>", "<StartWhenAvailable>true</StartWhenAvailable>"
        } elseif ($xml -notmatch "<StartWhenAvailable>true</StartWhenAvailable>") {
            $xml = $xml -replace "<Settings>", "<Settings><StartWhenAvailable>true</StartWhenAvailable>"
        }
        Register-ScheduledTask -TaskName $t.TaskName -Xml $xml -Force | Out-Null
    }
    Write-Host "Enabled WakeToRun + battery-run + run-missed-when-available on all MLBProps tasks (runs regardless of power state/sleep)."
}

New-Or-UpdateTask -TaskName "MLBProps_MorningWorkflow" -StartTime $MorningTime -ScriptPath $morningScript
New-Or-UpdateTask -TaskName "MLBProps_MiddayRefresh" -StartTime $MiddayRefreshTime -ScriptPath $middayScript
New-Or-UpdateTask -TaskName "MLBProps_SecondRefresh" -StartTime $SecondRefreshTime -ScriptPath $middayScript
New-Or-UpdateTask -TaskName "MLBProps_CloseWatcherStart" -StartTime $WatcherStartTime -ScriptPath $watcherScript
New-Or-UpdateRepeatingTask -TaskName "MLBProps_CloseWatcherWatchdog" -StartTime $WatcherWatchdogTime -ScriptPath (Join-Path $repoRoot "production\ops\watch_close_watcher_health.ps1") -RepeatMinutes 60 -Duration "12:00"
New-Or-UpdateTask -TaskName "MLBProps_EndOfDaySettle" -StartTime $SettleTime -ScriptPath $settleScript
New-Or-UpdatePythonTask -TaskName "MLBProps_AutomationSelfCheck" -StartTime $AutomationSelfCheckTime -ScriptPath $selfCheckScript

# Apply reliable-run settings now that the tasks exist (so the running/scheduled
# copies and any future re-run all get wake-from-sleep + battery allowance).
Enable-MLBPropsReliableRun

Write-Host ""
Write-Host "Scheduled tasks created/updated:"
Write-Host " - MLBProps_MorningWorkflow @ $MorningTime"
Write-Host " - MLBProps_MiddayRefresh @ $MiddayRefreshTime"
Write-Host " - MLBProps_SecondRefresh @ $SecondRefreshTime"
Write-Host " - MLBProps_CloseWatcherStart @ $WatcherStartTime"
Write-Host " - MLBProps_CloseWatcherWatchdog @ $WatcherWatchdogTime"
Write-Host " - MLBProps_EndOfDaySettle @ $SettleTime"
Write-Host " - MLBProps_AutomationSelfCheck @ $AutomationSelfCheckTime"
Write-Host ""
Write-Host "Run-no-matter-what configured: wake-from-sleep + allow-on-battery + don't-stop-on-battery."
Write-Host "These run regardless of sleep state or AC power."
Write-Host "Only hard limit: Windows cannot wake a fully POWERED-OFF (shut down/hibernated) machine."
Write-Host "  -> If that matters, re-run with -RunWhetherLoggedOn -TaskUser ... -TaskPassword ..."
Write-Host "  -> Or keep the machine in Sleep (not Shut Down) when closing the lid."
Write-Host ""
Write-Host "Recommended companion (run once, outside this script):"
Write-Host "  powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE 0   # disable battery hibernate-after"
Write-Host "  powercfg /setactive SCHEME_CURRENT                                  # (also set AC to 0 for full coverage)"
Write-Host "Hibernation kills WakeToRun, so disabling it is what lets battery/sleep wake-ups actually fire."
Write-Host "Power note: allowing battery runs + no hibernate means a fully-drained battery = hard power-off."
