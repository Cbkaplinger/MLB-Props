param(
    [switch]$SkipArtifactCheck,
    [switch]$IncludeCalibration,
    [switch]$IncludeGatePolicy,
    [switch]$IncludeDeepDive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python not found at $python"
}

$env:PYTHONIOENCODING = "utf-8"

function Run-Notebook {
    param([string]$NotebookPath, [string]$StepLabel)
    Write-Host "`n$StepLabel Executing $NotebookPath ..."
    & $python -m nbconvert --to notebook --execute --inplace (Join-Path $repoRoot $NotebookPath)
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Repo root: $repoRoot"
Write-Host "Python: $python"

if (-not $SkipArtifactCheck) {
    Write-Host "`n[0] Checking notebook artifacts..."
    & $python (Join-Path $repoRoot "scripts\check_notebook_artifacts.py")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "`n[0] Artifact check skipped."
}

Write-Host "`n[1/7] Refreshing exit anomaly overrides..."
& $python (Join-Path $repoRoot "scripts\build_exit_anomaly_overrides.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[2/7] Rebuilding exit anomaly training mask..."
& $python (Join-Path $repoRoot "scripts\build_exit_anomaly_training_mask.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Core operator flow: future slate + health + performance + profile decision + weakness scan.
Run-Notebook "production\notebooks\daily_projections.ipynb" "[3/7]"
Run-Notebook "production\notebooks\results_kpi_monitor.ipynb" "[4/7]"
Run-Notebook "production\notebooks\results_pnl_clv.ipynb" "[5/7]"
Run-Notebook "production\notebooks\results_bettable_cohort.ipynb" "[6/7]"
Run-Notebook "production\notebooks\results_recommendation_audit.ipynb" "[7/7]"

if ($IncludeCalibration) {
    Run-Notebook "production\notebooks\results_calibration_lab.ipynb" "[extra]"
}

if ($IncludeGatePolicy) {
    Run-Notebook "production\notebooks\results_gate_policy.ipynb" "[extra]"
}

if ($IncludeDeepDive) {
    Run-Notebook "production\notebooks\results_dashboard.ipynb" "[extra]"
}

Write-Host "`nDaily operator notebook flow complete."
