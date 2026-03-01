param(
    [string]$TrackerPath = ".\data\gtm\conversation_tracker.csv"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $TrackerPath)) {
    throw "Tracker file not found: $TrackerPath"
}

$rows = Import-Csv -LiteralPath $TrackerPath

$dmSent = ($rows | Where-Object { $_.dm_sent -eq "yes" }).Count
$replied = ($rows | Where-Object { $_.replied -eq "yes" }).Count
$calls = ($rows | Where-Object { $_.call_booked -eq "yes" }).Count
$pilotsOffered = ($rows | Where-Object { $_.pilot_offered -eq "yes" }).Count
$pilotsClosed = ($rows | Where-Object { $_.pilot_closed -eq "yes" }).Count
$strongPain = ($rows | Where-Object { $_.pain_signal -eq "strong" }).Count

Write-Host "GTM Signal Summary"
Write-Host "------------------"
Write-Host "contacts_tracked=$($rows.Count)"
Write-Host "dm_sent=$dmSent"
Write-Host "replied=$replied"
Write-Host "calls_booked=$calls"
Write-Host "pilots_offered=$pilotsOffered"
Write-Host "pilots_closed=$pilotsClosed"
Write-Host "strong_pain_signals=$strongPain"
Write-Host ""
Write-Host "Execution Targets"
Write-Host "-----------------"
Write-Host "1) Send 5 DMs today"
Write-Host "2) Book 3 calls"
Write-Host "3) Close 1 paid pilot"
