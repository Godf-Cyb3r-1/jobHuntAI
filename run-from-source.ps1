# No EXE required. Start the same application from source for initial local tests.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
$env:JOBHUNTAI_HOME = Join-Path $PSScriptRoot 'data'
Write-Host 'Open the local dashboard at http://127.0.0.1:8000'
& '.\.venv\Scripts\python.exe' app.py serve --host 127.0.0.1 --port 8000