param(
    [switch]$SkipArtifactCheck,
    [switch]$NoStory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python not found at $python"
}

$env:PYTHONIOENCODING = "utf-8"

Write-Host "Repo root: $repoRoot"
Write-Host "Python: $python"

if (-not $SkipArtifactCheck) {
    Write-Host "`n[1/3] Checking notebook artifacts..."
    & $python (Join-Path $repoRoot "scripts\check_notebook_artifacts.py")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "`n[1/3] Artifact check skipped."
}

Write-Host "`n[2/3] Executing production/notebooks/results_dashboard.ipynb ..."
& $python -m nbconvert --to notebook --execute --inplace (Join-Path $repoRoot "production\notebooks\results_dashboard.ipynb")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($NoStory) {
    Write-Host "`n[3/3] model_results_story skipped (--NoStory)."
} else {
    Write-Host "`n[3/3] Executing analysis/model_results/model_results_story.ipynb ..."
    & $python -m nbconvert --to notebook --execute --inplace (Join-Path $repoRoot "analysis\model_results\model_results_story.ipynb")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "`nAnalysis notebook refresh complete."
