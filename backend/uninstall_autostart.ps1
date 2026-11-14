$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'JobHuntAI' -Confirm:$false
Write-Host 'JobHuntAI auto-start task removed.'
