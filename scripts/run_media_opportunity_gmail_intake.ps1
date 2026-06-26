param(
    [string]$Label = "Media Opportunity"
)

$ErrorActionPreference = "Stop"
$startedAt = (Get-Date).ToString("o")
$scriptPath = $MyInvocation.MyCommand.Path
$scriptDir = Split-Path -Parent $scriptPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

Write-Host "[$startedAt] media-opportunity-gmail-intake starting label=`"$Label`""

Push-Location $repoRoot
try {
    $output = & python -m signal_agent.media_opportunities.cli ingest-gmail-label --label $Label 2>&1
    $exitCode = $LASTEXITCODE
} catch {
    $exitCode = 1
} finally {
    Pop-Location
}

$completedAt = (Get-Date).ToString("o")
if ($exitCode -ne 0) {
    Write-Host "[$completedAt] media-opportunity-gmail-intake failed exit_code=$exitCode"
    exit $exitCode
}

$created = "unknown"
$skipped = "unknown"
$manualReview = "unknown"
$errors = "unknown"
try {
    $jsonLine = ($output | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1)
    if ($jsonLine) {
        $payload = $jsonLine | ConvertFrom-Json
        $created = $payload.created_count
        $skipped = $payload.skipped_count
        $manualReview = $payload.manual_review_count
        $errors = $payload.error_count
    }
} catch {
    $errors = "parse_error"
}

Write-Host "[$completedAt] media-opportunity-gmail-intake completed created=$created skipped=$skipped manual_review=$manualReview errors=$errors"
exit 0
