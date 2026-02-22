$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Ensure we are in the repo root
Set-Location $ScriptDir

# Set PYTHONPATH to include the current directory
$env:PYTHONPATH = "$ScriptDir;$env:PYTHONPATH"

# Parse command
if ($args.Count -eq 0) {
    Write-Host "Usage: .\daily_ops.ps1 [command] [args...]"
    Write-Host "Examples:"
    Write-Host "  .\daily_ops.ps1 status"
    Write-Host "  .\daily_ops.ps1 decay --days 14"
    exit 1
}

$pyscript = "app.agent"
$cmd = $args[0]
$pass_args = $args[1..($args.Count-1)]

# Run python module
Write-Host "Running: python -m $pyscript capture.$cmd $pass_args"
python -m $pyscript "capture.$cmd" @pass_args
