$repoRoot = $PSScriptRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $repoRoot ".pycache"

& (Join-Path $repoRoot ".venv\Scripts\Activate.ps1")

Write-Host "Virtual environment active."
Write-Host "Python cache: $env:PYTHONPYCACHEPREFIX"
