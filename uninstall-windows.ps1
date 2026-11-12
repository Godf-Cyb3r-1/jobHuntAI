# Run as Administrator. Personal data is deliberately retained.
schtasks.exe /End /TN JobHuntAI 2>$null | Out-Null
schtasks.exe /Delete /TN JobHuntAI /F 2>$null | Out-Null
Remove-Item 'C:\Program Files\JobHuntAI' -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Application removed. Data retained in C:\ProgramData\JobHuntAI.'