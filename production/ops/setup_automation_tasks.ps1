param(
    [string]$MorningTime = "08:30",
    [string]$MiddayRefreshTime = "11:00",
    [string]$SecondRefreshTime = "13:45",
    [string]$WatcherStartTime = "11:30",
    [string]$WatcherWatchdogTime = "12:15",
    [string]$SettleTime = "03:00",
    [string]$SettleBackfillStartTime = "04:00",
    [int]$SettleBackfillRepeatMinutes = 60,
    [string]$SettleBackfillDuration = "08:00",
    [string]$NightlyDriftTime = "05:30",
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
$nightlyDriftScript = Join-Path $repoRoot "production\ops\run_nightly_drift.ps1"
$selfCheckScript = Join-Path $repoRoot "production\ops\build_automation_self_check.py"
# NOTE: the self-check goes through run_self_check_task.ps1 (a no-arg wrapper),
# NOT Invoke-Captured with -TargetArgs. Passing `--notify-on-red` through a
# scheduler command line breaks under powershell.exe 5.1 -File parsing
# (NamedParameterNotFound, exit 1, no log — reproduced 2026-09-08), and the
# Scheduler CIM layer strips the double quotes that fix it interactively.
# See production/ops/run_self_check_task.ps1 for the full story.
$selfCheckEntry = Join-Path $repoRoot "production\ops\run_self_check_task.ps1"
$captureWrapper = Join-Path $repoRoot "production\ops\run_task_captured.ps1"
$opsLogDir = Join-Path $repoRoot "artifacts\ops_log"

foreach ($p in @($morningScript, $middayScript, $watcherScript, $settleScript, $nightlyDriftScript, $selfCheckScript, $selfCheckEntry, $captureWrapper)) {
    if (-not (Test-Path $p)) { throw "Missing script: $p" }
}
New-Item -ItemType Directory -Force -Path $opsLogDir | Out-Null

# Wrapper invoked as a Task action -> logs all output to artifacts/ops_log and
# propagates the real exit code so "Last Result" is truthful instead of 0/1-noise.
function Invoke-Captured {
    param([string]$Target, [string]$TargetArgs = "", [string]$TaskName)
    # NOTE on -TargetArgs quoting (learned 2026-09-08): do NOT pass `--flags`
    # through a scheduler-registered command line at all. History:
    #  - unquoted `--flag` => powershell.exe parses it as a *wrapper* parameter
    #    (NamedParameterNotFound, exit 1, no log);
    #  - double-quoted => the Scheduler CIM layer strips the quotes at
    #    registration time, degrading to the unquoted case;
    #  - single-quoted => survives registration and works interactively, but
    #    STILL fails binding when launched by the Scheduler under 5.1 -File.
    # Single quotes are kept below as the least-bad default, but any scheduled
    # action needing flags must use a dedicated no-arg entry script instead
    # (see run_self_check_task.ps1). Do not "simplify" this quoting.
    if ($TargetArgs) {
        return "powershell -NoProfile -ExecutionPolicy Bypass -File `"$captureWrapper`" -Target `"$Target`" -TargetArgs '$TargetArgs' -TaskName `"$TaskName`""
    }
    return "powershell -NoProfile -ExecutionPolicy Bypass -File `"$captureWrapper`" -Target `"$Target`" -TaskName `"$TaskName`""
}

# Wraps a candidate command string into a "File (Execute) + args" tuple suitable
# for New-ScheduledTaskAction. First whitespace token = execute*, rest = args.
function Split-TaskCommand {
    param([Parameter(Mandatory = $true)][string]$Cmd)
    $tokens = $Cmd -split ' ', 2
    return @($tokens[0], $(if ($tokens.Length -gt 1) { $tokens[1] } else { "" }))
}

# Register (or update) a task via the ScheduledTasks module. Because this API has
# no schtasks 261-char /TR cap, long capture-wrapper commands register cleanly.
function New-Or-UpdateTaskActionModule {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$StartTime,
        [Parameter(Mandatory = $true)][string]$Command,
        [bool]$Repeat = $false,
        [int]$RepeatMinutes = 60,
        [TimeSpan]$RepeatDuration = (New-TimeSpan -Hours 12)
    )
    $exe, $args = Split-TaskCommand -Cmd $Command
    $action = New-ScheduledTaskAction -Execute $exe -Argument $args
    if ($Repeat) {
        $trigger = New-ScheduledTaskTrigger -Daily -At $StartTime -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes) -RepetitionDuration $RepeatDuration
    } else {
        $trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
    }
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun
    if ($RunWhetherLoggedOn) {
        if (-not $TaskUser -or -not $TaskPassword) {
            throw "RunWhetherLoggedOn requires -TaskUser and -TaskPassword."
        }
        $principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Password -RunLevel Highest
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    } else {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    }
    if ($Repeat) {
        Write-Host "Scheduled $TaskName at $StartTime (every ${RepeatMinutes}m for $($RepeatDuration.TotalMinutes)m)"
    } else {
        Write-Host "Scheduled $TaskName at $StartTime"
    }
}

# --- Standard tasks (short command; proven schtasks path, unchanged) ----------
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

# --- Register all tasks -------------------------------------------------------
# Standard short-command tasks keep the proven schtasks helpers.
New-Or-UpdateTask -TaskName "MLBProps_MiddayRefresh" -StartTime $MiddayRefreshTime -ScriptPath $middayScript
New-Or-UpdateTask -TaskName "MLBProps_SecondRefresh" -StartTime $SecondRefreshTime -ScriptPath $middayScript
New-Or-UpdateTask -TaskName "MLBProps_CloseWatcherStart" -StartTime $WatcherStartTime -ScriptPath $watcherScript
New-Or-UpdateRepeatingTask -TaskName "MLBProps_CloseWatcherWatchdog" -StartTime $WatcherWatchdogTime -ScriptPath (Join-Path $repoRoot "production\ops\watch_close_watcher_health.ps1") -RepeatMinutes 60 -Duration "12:00"
New-Or-UpdateTask -TaskName "MLBProps_EndOfDaySettle" -StartTime $SettleTime -ScriptPath $settleScript
New-Or-UpdateRepeatingTask -TaskName "MLBProps_EndOfDaySettleBackfill" -StartTime $SettleBackfillStartTime -ScriptPath $settleScript -RepeatMinutes $SettleBackfillRepeatMinutes -Duration $SettleBackfillDuration
# Nightly drift runs after the settle window (settle 03:00 + hourly backfill
# from 04:00): own log, no scheduler-visible args (no-arg entry script), quiet
# on GREEN/YELLOW, failure-banner alert on RED/step failure.
New-Or-UpdateTask -TaskName "MLBProps_NightlyDrift" -StartTime $NightlyDriftTime -ScriptPath $nightlyDriftScript

# Long-command tasks (MorningWorkflow + AutomationSelfCheck) go through the capture
# wrapper so stdout/stderr is saved to artifacts/ops_log and "Last Result" is the
# real exit code. The AutomationSelfCheck entry (run_self_check_task.ps1, no
# scheduler-visible args) runs build_automation_self_check.py --notify-on-red so
# a RED self-check actually pushes an alert. Registered via the ScheduledTasks
# module to side-step schtasks' 261-char /TR limit.
$morningCmd = Invoke-Captured -Target $morningScript -TaskName "MLBProps_MorningWorkflow"
New-Or-UpdateTaskActionModule -TaskName "MLBProps_MorningWorkflow" -StartTime $MorningTime -Command $morningCmd

$selfCheckCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$selfCheckEntry`""
New-Or-UpdateTaskActionModule -TaskName "MLBProps_AutomationSelfCheck" -StartTime $AutomationSelfCheckTime -Command $selfCheckCmd

# Apply reliable-run settings now that the tasks exist (so the running/scheduled
# copies and any future re-run all get wake-from-sleep + battery allowance).
Enable-MLBPropsReliableRun

Write-Host ""
Write-Host "Scheduled tasks created/updated:"
Write-Host " - MLBProps_MorningWorkflow @ $MorningTime (captured log)"
Write-Host " - MLBProps_MiddayRefresh @ $MiddayRefreshTime"
Write-Host " - MLBProps_SecondRefresh @ $SecondRefreshTime"
Write-Host " - MLBProps_CloseWatcherStart @ $WatcherStartTime"
Write-Host " - MLBProps_CloseWatcherWatchdog @ $WatcherWatchdogTime"
Write-Host " - MLBProps_EndOfDaySettle @ $SettleTime"
Write-Host " - MLBProps_EndOfDaySettleBackfill @ $SettleBackfillStartTime (every ${SettleBackfillRepeatMinutes}m for $SettleBackfillDuration)"
Write-Host " - MLBProps_NightlyDrift @ $NightlyDriftTime (settle+grade+drift+self-check; pages on RED only)"
Write-Host " - MLBProps_AutomationSelfCheck @ $AutomationSelfCheckTime (captured log + --notify-on-red)"
Write-Host ""
Write-Host "Run-no-matter-what configured: wake-from-sleep + allow-on-battery + don't-stop-on-battery."
Write-Host "These run regardless of sleep state or AC power."
Write-Host "Only hard limit: Windows cannot wake a fully POWERED-OFF (shut down/hibernated) machine."
Write-Host "  -> If that matters, re-run with -RunWhetherLoggedOn -TaskUser ... -TaskPassword ..."
Write-Host "  -> Or keep the machine in Sleep (not Shut Down) when closing the lid."
Write-Host ""
Write-Host "Action logs (MorningWorkflow / AutomationSelfCheck) land in artifacts/ops_log/."