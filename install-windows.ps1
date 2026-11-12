# Run as Administrator from an extracted release package
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\JobHuntAI'
New-Item -ItemType Directory -Force $install | Out-Null
Copy-Item "$PSScriptRoot\JobHuntAI.exe" "$install\JobHuntAI.exe" -Force
# Configure one durable data directory, restricting access to Administrators and SYSTEM.
New-Item -ItemType Directory -Force 'C:\ProgramData\JobHuntAI' | Out-Null
icacls 'C:\ProgramData\JobHuntAI' /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
# Task Scheduler starts on boot; host stays localhost until HTTPS proxy is configured.
$cmd = 'cmd.exe /c "set JOBHUNTAI_HOME=C:\ProgramData\JobHuntAI&& ""C:\Program Files\JobHuntAI\JobHuntAI.exe"" serve --host 127.0.0.1 --port 8000"'
schtasks.exe /Create /TN 'JobHuntAI' /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $cmd /F | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Task Scheduler registration failed' }
schtasks.exe /Run /TN 'JobHuntAI' | Out-Host
Write-Host 'Installed. Test locally inside RDP: http://127.0.0.1:8000'
Write-Host 'Do NOT open port 8000 to the public internet. Use an HTTPS reverse proxy.'