param(
    [string]$FreezeTag = "v0.1-legal-freeze",
    [string]$ExpectedCommit = "40486fc39463fdf9d6d85900a6f5eb2e05d36470"
)

function Fail([string]$msg) {
    Write-Host "FAIL: $msg"
    exit 1
}

# Ensure we're in a git repo
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Fail "Not inside a git repository." }

# Verify tag exists and points to expected commit
$tagCommit = (git log -1 --format="%H" $FreezeTag 2>$null).Trim()
if (-not $tagCommit) { Fail "Tag '$FreezeTag' not found." }
if ($tagCommit -ne $ExpectedCommit) { Fail "Tag '$FreezeTag' points to $tagCommit, expected $ExpectedCommit." }

Write-Host "OK: Tag '$FreezeTag' -> $tagCommit"

# Verify stamp exists in key files
$stamp1 = "Legal Freeze Tag: $FreezeTag"
$stamp2 = "Legal Freeze Commit: $ExpectedCommit"

$filesToCheck = @(
    "SYSTEM_FREEZE_v0.1.md",
    "business\legal\copyright_packet\MASTER_SUMMARY.md"
)

foreach ($f in $filesToCheck) {
    if (-not (Test-Path $f)) { Fail "Missing file: $f" }
    $txt = Get-Content -LiteralPath $f -Raw
    if ($txt -notmatch [regex]::Escape($stamp1)) { Fail "Missing stamp tag in $f" }
    if ($txt -notmatch [regex]::Escape($stamp2)) { Fail "Missing stamp commit in $f" }
    Write-Host "OK: Stamps present in $f"
}

# Hash critical files (extend list as needed)
$critical = @(
    "app\audit\coherence_kernel.py",
    "app\governor\activation_governor.py",
    "app\utils\policy_engine.py",
    "app\utils\resilience.py",
    "SYSTEM_FREEZE_v0.1.md",
    "business\legal\copyright_packet\MASTER_SUMMARY.md"
)

Write-Host ""
Write-Host "SHA256 (critical files):"
foreach ($p in $critical) {
    if (Test-Path $p) {
        $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash
        Write-Host " - $p : $h"
    }
    else {
        Fail "Missing critical file: $p"
    }
}

Write-Host ""
Write-Host "PASS: Legal freeze verification succeeded."
exit 0
