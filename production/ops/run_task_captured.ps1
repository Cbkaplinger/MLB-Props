param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$TargetArgs = "",
    [Parameter(Mandatory = $true)][string]$TaskName,
    [string]$LogDir = ""
)

<#
  Wrapper for scheduled tasks: run a target command while capturing ALL output
  (stdout + stderr) to a dated log under artifacts/ops_log/, then exit with the
  target's real exit code so Task Scheduler's "Last Result" is honest.

  Usage examples (as the task Action's command + arguments):
    powershell -NoProfile -ExecutionPolicy Bypass -File .\run_task_captured.ps1 `
        -Target "C:\...\production\ops\run_morning_workflow.ps1" `
        -TaskName "MLBProps_MorningWorkflow"

    powershell -NoProfile -ExecutionPolicy Bypass -File .\run_task_captured.ps1 `
        -Target "C:\...\.venv\Scripts\python.exe" `
        -TargetArgs "C:\...\production\ops\build_automation_self_check.py --notify-on-red" `
        -TaskName "MLBProps_AutomationSelfCheck"
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $LogDir) {
    $LogDir = Join-Path $repoRoot "artifacts\ops_log"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$safe = $TaskName -replace '[^A-Za-z0-9_\-]', '_'
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $LogDir "$($safe)_$($stamp).log"
$env:MLBPROPS_TASK_LOG = $logFile
Write-Host "run_task_captured: task=$TaskName output => $logFile"

# Keep the machine awake (no Modern Standby idle-sleep) for the duration of
# the run. The 2026-09-06..08 morning failures died inside step 1a with a
# 412-byte log right after wake-from-sleep triggers — the box re-entered
# standby mid-fetch with no keep-alive held. 5.1-compatible kernel32 P/Invoke.
$keepAwake = $null
try {
    Add-Type -Namespace MLBProps -Name PowerKeepAlive -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern int SetThreadExecutionState(int esFlags);
"@ -ErrorAction Stop
    # ES_CONTINUOUS|ES_SYSTEM_REQUIRED|ES_AWAYMODE_REQUIRED (0x80000041).
    # Declared as int (not uint) because PowerShell 5.1 wraps 0x80000041 into
    # Int32 overflow; the bit pattern is identical so Win32 is unaffected.
    [void][MLBProps.PowerKeepAlive]::SetThreadExecutionState(-2147483583)
    $keepAwake = $true
    Write-Host "run_task_captured: keep-awake held for task=$TaskName"
} catch {
    Write-Warning "run_task_captured: keep-awake unavailable: $($_.Exception.Message)"
}

# Tokenize TargetArgs (a flat command-line string) into an argv array, honoring
# double quotes so paths/args containing spaces survive.
$argv = New-Object System.Collections.Generic.List[string]
if ($TargetArgs) {
    $cur = ''
    $inQ = $false
    for ($i = 0; $i -lt $TargetArgs.Length; $i++) {
        $c = $TargetArgs[$i]
        if ($inQ) {
            if ($c -eq '"') { $inQ = $false } else { $cur += $c }
        } else {
            if ($c -eq '"') { $inQ = $true }
            elseif ($c -eq ' ') {
                if ($cur.Length -gt 0) { $argv.Add($cur); $cur = '' }
            } else { $cur += $c }
        }
    }
    if ($cur.Length -gt 0) { $argv.Add($cur) }
}

& $Target @argv *>&1 | Tee-Object -FilePath $logFile
$code = $LASTEXITCODE
if ($null -eq $code) { $code = if ($?) { 0 } else { 1 } }
if ($keepAwake) {
    try { [void][MLBProps.PowerKeepAlive]::SetThreadExecutionState(-2147483648) } catch { } # ES_CONTINUOUS (0x80000000): clear request
    Write-Host "run_task_captured: keep-awake released"
}
Write-Host "run_task_captured: task=$TaskName exit=$code (see $logFile)"
exit $code