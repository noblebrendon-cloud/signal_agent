param(
    [string]$RepoRoot = "",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $Python) {
    $candidate = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $candidate) {
        $Python = $candidate
    } else {
        $Python = "python"
    }
}

$env:PYTHONDONTWRITEBYTECODE = "1"

Write-Output "daily_witness_repo_root=$RepoRoot"
Write-Output "daily_witness_python=$Python"
& $Python -B -m signal_agent.health.daily_check --repo-root $RepoRoot
$exitCode = $LASTEXITCODE
Write-Output "daily_witness_exit_code=$exitCode"
Write-Output "daily_witness_reports=data/state/witness/reports/"
exit $exitCode
