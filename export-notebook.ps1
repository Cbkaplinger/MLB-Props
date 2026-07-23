param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Notebook,

    [string]$OutputDir
)

$repoRoot = $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$env:PYTHONPYCACHEPREFIX = Join-Path $repoRoot ".pycache"

if (-not (Test-Path $python)) {
    throw "Project virtual environment not found: $python"
}

$notebookPath = (Resolve-Path $Notebook -ErrorAction Stop).Path
$arguments = @(
    (Join-Path $repoRoot "export_notebook.py"),
    "--to", "webpdf",
    "--allow-chromium-download"
)

if ($OutputDir) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    $arguments += @("--output-dir", (Resolve-Path $OutputDir).Path)
}

$arguments += $notebookPath
& $python @arguments
exit $LASTEXITCODE
