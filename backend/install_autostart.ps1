# Register a per-user logon task that starts the Windows backend.
# Run in PowerShell as the Windows account that should host JobHuntAI.
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot 'run_windows.bat'
if (-not (Test-Path $launcher)) { throw 'run_windows.bat not found' }
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c "' + $launcher + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'JobHuntAI' -Action $action -Trigger $trigger -Settings $settings -Description 'JobHuntAI auto-start' -Force
Write-Host 'JobHuntAI logon task registered. Check Windows Task Scheduler for its status.'
