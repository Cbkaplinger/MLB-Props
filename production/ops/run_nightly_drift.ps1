# Scheduled-task entry point for MLBProps_NightlyDrift.
#
# Takes NO arguments on purpose (same lesson as run_self_check_task.ps1:
# flags through the Scheduler command line break under powershell.exe 5.1
# -File parsing, and the CIM layer strips the quotes that fix it).
#
# Best-effort chain (the 2026-09-06..08 lesson: fail-fast chains page nobody):
#   1. settle (idempotent grade/settle over what exists)
#   2. grade all logged projection dates
#   3. nightly drift check (exit 0 GREEN / 1 YELLOW / 2 RED)
#   4. automation self-check --notify-on-red (task health still pages there)
#   5. alert ONLY on degradation (RED, or any step failure) via ntfy banner;
#      GREEN/YELLOW nights stay quiet — the morning board covers them.
#
# Register with:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\production\ops\run_nightly_drift.ps1"
# or re-run production/ops/setup_automation_tasks.ps1 (it registers this file).

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$logDir = Join-Path $repoRoot "artifacts\ops_log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "MLBProps_NightlyDrift_$($stamp).log"

# Keep-awake (same rationale as run_task_captured.ps1: the box re-enters
# Modern Standby mid-run with no keep-alive held). Int, not uint: 5.1 wraps
# 0x80000041 into Int32 overflow; bits are identical.
try {
    Add-Type -Namespace MLBProps -Name PowerKeepAliveNightly -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern int SetThreadExecutionState(int esFlags);
"@ -ErrorAction Stop
    [void][MLBProps.PowerKeepAliveNightly]::SetThreadExecutionState(-2147483583) # 0x80000041
    Write-Host "nightly_drift: keep-awake held (log => $logFile)"
} catch {
    Write-Warning "nightly_drift: keep-awake unavailable: $($_.Exception.Message)"
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"

function Run-Step {
    param([string]$Label, [string]$Script, [string[]]$ExtraArgs = @())
    Write-Host "`n[$Label] $Script $($ExtraArgs -join ' ')"
    $out = & $python -u $Script @ExtraArgs *>&1 | Tee-Object -FilePath $logFile -Append
    $out | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "step [$Label] exited $LASTEXITCODE" }
}

$failure = ""
try { Run-Step "1 settle" "production/odds/grade_odds_ledger.py" @("--auto-settle-api", "--void-scratches", "--status", "--curve") }
catch { $failure += "settle FAILED: $($_.Exception.Message)`n" }
try { Run-Step "2 grade_all_logged" "production/projections/grade_projections.py" @("--all-logged", "--preferred-only") }
catch { $failure += "grade FAILED: $($_.Exception.Message)`n" }
$driftRed = $false
# Drift check has its own exit contract (0 GREEN / 1 YELLOW / 2 RED / 3 crash):
# a YELLOW night is filed quietly, never thrown — only RED (or a crash)
# degrades. Exit 3 exists so a crash can never masquerade as a quiet night.
Write-Host "`n[3 drift_check] production/ops/check_nightly_drift.py"
$out = & $python -u "production/ops/check_nightly_drift.py" *>&1 | Tee-Object -FilePath $logFile -Append
$out | Out-Host
$driftCode = $LASTEXITCODE
if ($null -eq $driftCode) { $driftCode = if ($?) { 0 } else { 3 } }
if ($driftCode -eq 2) { $driftRed = $true }
elseif ($driftCode -ne 0 -and $driftCode -ne 1) { $failure += "drift_check FAILED: exit $driftCode`n" }
try { Run-Step "4 automation_self_check" "production/ops/build_automation_self_check.py" @("--notify-on-red") }
catch { $failure += "self_check FAILED: $($_.Exception.Message)`n" }
# Shadow evidence (never pages: warn-only by design — research scripts must
# not degrade a night or wake the owner).
try { Run-Step "4b policy_freshness" "production/ops/policy_freshness_audit.py" @() }
catch { Write-Warning "policy_freshness warn-only: $($_.Exception.Message)" }
try { Run-Step "4c stacker_gate" "production/ops/market_research/ledger_gate_stacker.py" @() }
catch { Write-Warning "stacker_gate warn-only: $($_.Exception.Message)" }

# Alert only on degradation: step failures or a RED drift verdict.
# A YELLOW drift (warnings / thin-n) stays quiet by design — it is filed in
# nightly_drift_latest.json and reviewed with the morning board, not paged.
try {
    if ($failure -or $driftRed) {
        $msg = "Nightly drift issues:`n$failure"
        if ($driftRed -and -not $failure) { $msg = "Nightly drift RED (see nightly_drift_latest.json).`n" }
        Run-Step "5 alert (FAILURE banner)" "production/ops/send_morning_alert.py" @("--failure-message", $msg, "--record-name", "nightly_drift_alert_latest.json")
    } else {
        Write-Host "`n[5 alert] skipped (no degradation; see nightly_drift_latest.json)"
    }
} catch {
    Write-Warning "Alert step failed: $($_.Exception.Message)"
    if (-not $failure) { $failure = "alert FAILED: $($_.Exception.Message)`n" }
}

try { [void][MLBProps.PowerKeepAliveNightly]::SetThreadExecutionState(-2147483648) } catch { } # ES_CONTINUOUS: clear
if ($failure) {
    Write-Warning "Nightly drift DEGRADED:`n$failure"
    exit 1
}
Write-Host "`nNightly drift complete."
