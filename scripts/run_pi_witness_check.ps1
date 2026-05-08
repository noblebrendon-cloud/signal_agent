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

Set-Location -LiteralPath $RepoRoot
$env:PYTHONDONTWRITEBYTECODE = "1"

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$receiptDir = Join-Path $RepoRoot "data\state\pi_witness_receipts"
$receiptPath = Join-Path $receiptDir "$timestamp.json"

$branch = (& git branch --show-current 2>$null)
$commit = (& git rev-parse --short HEAD 2>$null)
$dirtyCount = @(& git status --short 2>$null).Count

Write-Output "pi_witness_repo_root=$RepoRoot"
Write-Output "pi_witness_branch=$branch"
Write-Output "pi_witness_commit=$commit"
Write-Output "pi_witness_dirty_count=$dirtyCount"
Write-Output "pi_witness_python=$Python"

$testPath = Join-Path $RepoRoot "tests\test_daily_witness_check.py"
if (Test-Path -LiteralPath $testPath) {
    $checkKind = "focused_daily_witness_test"
    $commandText = "$Python -B -m pytest -p no:cacheprovider tests/test_daily_witness_check.py -q"
    & $Python -B -m pytest -p no:cacheprovider tests/test_daily_witness_check.py -q
    $exitCode = $LASTEXITCODE
} else {
    $checkKind = "fallback_environment_check"
    $commandText = "$Python --version; git status --short"
    & $Python --version
    $pythonExit = $LASTEXITCODE
    & git status --short
    $gitExit = $LASTEXITCODE
    if ($pythonExit -eq 0 -and $gitExit -eq 0) {
        $exitCode = 0
    } else {
        $exitCode = 1
    }
}

New-Item -ItemType Directory -Force -Path $receiptDir | Out-Null
$receipt = [ordered]@{
    timestamp_utc = $timestamp
    repo_root = $RepoRoot
    branch = $branch
    commit = $commit
    dirty_count = $dirtyCount
    check_kind = $checkKind
    command = $commandText
    exit_code = $exitCode
    authority = [ordered]@{
        network_actions = @()
        git_writes = @()
        production_mutations = @()
        receipt_root = "data/state/pi_witness_receipts"
    }
}

$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding UTF8

Write-Output "pi_witness_exit_code=$exitCode"
Write-Output "pi_witness_receipt=$receiptPath"
exit $exitCode
