param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$py = Join-Path $PWD ".venv\\Scripts\\python.exe"
if (-not (Test-Path $py)) { throw "Missing venv interpreter: $py" }

& $py -m pytest @Args
exit $LASTEXITCODE
