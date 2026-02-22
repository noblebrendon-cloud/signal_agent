$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$dropRelative = "data/intake/pdf_drop_2026-02-22"
$dropAbsolute = (Resolve-Path $dropRelative).Path

$pythonExe = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $pythonExe = ".\.venv\Scripts\python.exe"
}

& $pythonExe .\app\intake\intake.py --root .\data\intake\pdf_drop_2026-02-22 --only-ext pdf

$ledgerPath = Join-Path $repoRoot "data/intake/intake.jsonl"
if (-not (Test-Path $ledgerPath)) {
    throw "Ledger not found at $ledgerPath"
}

$dropRelativePosix = $dropRelative -replace "\\", "/"
$dropAbsolutePosix = $dropAbsolute -replace "\\", "/"

$dropEntries = Get-Content $ledgerPath | ForEach-Object {
    try {
        $_ | ConvertFrom-Json
    } catch {
        $null
    }
} | Where-Object {
    $_ -and
    $_.source_path -and
    ($_.source_path -match "\.pdf$") -and
    (
        $_.source_path -like "$dropRelativePosix/*" -or
        (($_.source_path -replace "\\", "/") -like "$dropAbsolutePosix/*")
    )
}

$recordsFound = $dropEntries.Count
if ($recordsFound -lt 1) {
    throw "No PDF entries found in intake.jsonl for $dropRelativePosix"
}

$recordsSuccess = ($dropEntries | Where-Object { $_.status -eq "success" }).Count
$recordsError = ($dropEntries | Where-Object { $_.status -eq "error" }).Count

Write-Host "records_found=$recordsFound"
Write-Host "records_success=$recordsSuccess"
Write-Host "records_error=$recordsError"
