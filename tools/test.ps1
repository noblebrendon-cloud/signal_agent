param(
  [string[]]$Args
)
& .\.venv\Scripts\python.exe -m pytest -vv @Args
exit $LASTEXITCODE
