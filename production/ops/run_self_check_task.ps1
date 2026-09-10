# Scheduled-task entry point for MLBProps_AutomationSelfCheck.
#
# Takes NO arguments on purpose. The generic run_task_captured.ps1 wrapper
# cannot be used here: passing `--notify-on-red` through its -TargetArgs
# string breaks under Task Scheduler + powershell.exe 5.1 `-File` parsing
# (NamedParameterNotFound / exit 1, no log — reproduced 2026-09-08), and the
# Scheduler CIM layer strips the double quotes that would fix it
# interactively. This entry point also does its own stdout capture instead of
# nesting run_task_captured (two nested Tee-Object writers to the same
# timestamped log truncate each other). See setup_automation_tasks.ps1.
#
# Register with:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\production\ops\run_self_check_task.ps1"
# or re-run production/ops/setup_automation_tasks.ps1 (it uses this file).

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$logDir = Join-Path $repoRoot "artifacts\ops_log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "MLBProps_AutomationSelfCheck_$($stamp).log"

# Keep-awake (same rationale as run_task_captured.ps1). Declared as int, not
# uint: PowerShell 5.1 wraps 0x80000041 into Int32 overflow; bits are identical.
try {
    Add-Type -Namespace MLBProps -Name PowerKeepAliveSelfCheck -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern int SetThreadExecutionState(int esFlags);
"@ -ErrorAction Stop
    [void][MLBProps.PowerKeepAliveSelfCheck]::SetThreadExecutionState(-2147483583) # 0x80000041
    Write-Host "self_check_task: keep-awake held (log => $logFile)"
} catch {
    Write-Warning "self_check_task: keep-awake unavailable: $($_.Exception.Message)"
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$script = Join-Path $repoRoot "production\ops\build_automation_self_check.py"
Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"

& $python -u $script --notify-on-red *>&1 | Tee-Object -FilePath $logFile
$code = $LASTEXITCODE
if ($null -eq $code) { $code = if ($?) { 0 } else { 1 } }
try { [void][MLBProps.PowerKeepAliveSelfCheck]::SetThreadExecutionState(-2147483648) } catch { } # ES_CONTINUOUS: clear
Write-Host "self_check_task: exit=$code (see $logFile)"
exit $code
