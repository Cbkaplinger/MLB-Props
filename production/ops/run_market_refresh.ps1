param(
    [switch]$QuietBoard
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

function Run-Step {
    param([string]$Label, [string[]]$ScriptArgs)
    Write-Host "`n[$Label] $($ScriptArgs -join ' ')"
    # -u = unbuffered python so a killed run still leaves truthful step logs.
    & $python -u @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "step [$Label] exited $LASTEXITCODE" }
}

Write-Host "Starting market refresh in $repoRoot"

# Dynamic lineups (owner 2026-09-14): lineups finalize hours before first
# pitch, so every board run re-logs projections first. Doctrine change:
# projections are no longer frozen-AM; quotes AND projections refresh, and
# the edge-watch diffs the combined result (flips still page, losses silent).
$failure = ""
try {
Run-Step "0 refresh_projections" @("production/projections/log_projections.py", "--allow-stale")
} catch { $failure += "projections FAILED: $_`n" }
try {
$boardArgs = @("production/odds/odds_board.py", "--unit", "50", "--roi-mode", "conservative", "--write-quotes", "artifacts/odds_log/sharp_quotes_latest.parquet")
if ($QuietBoard) {
    Write-Warning "QuietBoard requested, but odds_board.py has no --quiet flag; running with normal output."
}
Run-Step "1 odds_board" $boardArgs
Run-Step "2 poll_open" @("production/odds/poll_odds.py", "--snapshot", "open", "--unit", "50", "--roi-mode", "conservative", "--from-recommendations", "--quotes-file", "artifacts/odds_log/sharp_quotes_latest.parquet")
Run-Step "2b frozen_edge_watch" @("production/ops/frozen_edge_watch.py")
# Flips-only alerting (owner 2026-09-14): the watch above already pages
# skip/HOLD->BET flips itself. The full board alert fires on failure or on
# flips; quiet hours stay silent (no 15-pings-a-day). Morning workflow keeps
# its own always-fire alert -- this gate is refresh-only.
$hasFlips = $false
try {
    $watchState = Join-Path $repoRoot ("artifacts\odds_log\edge_watch_state_" + (Get-Date -Format "yyyy-MM-dd") + ".json")
    if (Test-Path $watchState) {
        $flips = (Get-Content $watchState -Raw | ConvertFrom-Json).flips
        $hasFlips = ($null -ne $flips) -and (@($flips).Count -gt 0)
    }
} catch { Write-Warning "Flip-gate read failed (alerting as if flips): $_"; $hasFlips = $true }
Run-Step "3 ledger_status" @("production/odds/grade_odds_ledger.py", "--status")
Run-Step "4 reconcile_board_vs_ledger" @("production/ops/build_board_ledger_reconciliation.py")
Run-Step "5 compact_aux_quote_history" @("production/ops/compact_aux_quote_history.py", "--retention-days", "120")
Run-Step "6 aux_market_shadow_score" @("production/ops/build_aux_market_shadow_score.py")
Run-Step "7 runtime_monitoring_snapshot" @("production/ops/build_runtime_monitoring_snapshot.py")
Run-Step "7b weekly_policy_digest" @("production/ops/build_weekly_policy_digest.py")
Run-Step "7c automation_self_check" @("production/ops/build_automation_self_check.py", "--notify-on-red")
} catch { $failure += "market refresh chain FAILED: $_`n" }
try {
    if ($failure) {
        Run-Step "8 morning_alert (FAILURE banner)" @("production/ops/send_morning_alert.py", "--failure-message", $failure)
    } elseif ($hasFlips) {
        Run-Step "8 morning_alert (flips)" @("production/ops/send_morning_alert.py")
    } else {
        Write-Host "No flips this run -- alert stays silent (board + ledger still updated)."
    }
} catch {
    Write-Warning "Alert step failed: $_"
    if (-not $failure) { $failure = "alert FAILED: $_`n" }
}

if ($failure) {
    Write-Warning "Market refresh DEGRADED:`n$failure"
    exit 1
}

Write-Host "`nMarket refresh complete."

