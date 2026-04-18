$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
1..10 | ForEach-Object {
  Write-Host "=== run $_/10 ==="
  $env:PYTHONPATH = "src"
  python -m pytest tests/test_regression.py --regression -x --tb=short
  if ($LASTEXITCODE -ne 0) { throw "Run $_ faalde" }
}
Write-Host "All 10 runs green."
