# Build native Windows x64 JobHuntAI.exe from source. Run in PowerShell on Windows RDP.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python launcher not found. Install Python 3.12 (x64).' }
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python venv' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependencies failed to install' }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; refusing to package' }
& $python -m PyInstaller --noconfirm --clean --onefile --name JobHuntAI --collect-all docx --collect-all pypdf app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$env:JOBHUNTAI_HOME = Join-Path $env:TEMP 'JobHuntAI-Smoke'
& '.\dist\JobHuntAI.exe' health
if ($LASTEXITCODE -ne 0) { throw 'EXE smoke test failed' }
New-Item -ItemType Directory -Force package | Out-Null
Copy-Item dist\JobHuntAI.exe package\ -Force
Copy-Item README.md,install-windows.ps1,uninstall-windows.ps1,start-server.cmd,start-server.ps1 package\ -Force
if (Test-Path '.\opencode.exe') { Copy-Item '.\opencode.exe' package\ -Force }
Compress-Archive -Path package\* -DestinationPath JobHuntAI-Windows-x64.zip -Force
Get-FileHash '.\dist\JobHuntAI.exe' -Algorithm SHA256 | Format-List
Write-Host "EXE: $PSScriptRoot\dist\JobHuntAI.exe"
Write-Host "Package: $PSScriptRoot\JobHuntAI-Windows-x64.zip"