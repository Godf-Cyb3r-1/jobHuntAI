# JobHuntAI Windows installation. Run elevated as Administrator.
# Reentrant: safe to repeat after a previously failed Task Scheduler registration.
$ErrorActionPreference = 'Stop'
$taskName = 'JobHuntAI'
$install = Join-Path $env:ProgramFiles 'JobHuntAI'
$data = Join-Path $env:ProgramData 'JobHuntAI'
if (-not (Test-Path (Join-Path $PSScriptRoot 'JobHuntAI.exe') -PathType Leaf)) {
    throw "JobHuntAI.exe is missing from $PSScriptRoot. Extract the whole release package first."
}
if (-not (Test-Path (Join-Path $PSScriptRoot 'start-server.ps1') -PathType Leaf)) {
    throw "start-server.ps1 is missing from $PSScriptRoot. Use the fixed release package."
}
# This is checked before side effects; non-admin users cannot register the task.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator."
}
New-Item -ItemType Directory -Force -Path $install,$data | Out-Null
# Restrict personal data, session keys and resume files to SYSTEM and local Administrators.
& icacls.exe $data '/inheritance:r' '/grant:r' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to secure $data" }

# Stop an existing task before replacing application files, if present.
$previous = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($previous) {
    try { Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop } catch {
        Write-Warning "Could not stop previous task: $($_.Exception.Message)"
    }
}
foreach ($name in @('JobHuntAI.exe','opencode.exe','start-server.ps1','start-server.cmd','uninstall-windows.ps1','README.md')) {
    $src = Join-Path $PSScriptRoot $name
    $dst = Join-Path $install $name
    if ((Test-Path -LiteralPath $src -PathType Leaf) -and
        -not ([IO.Path]::GetFullPath($src).Equals([IO.Path]::GetFullPath($dst),[StringComparison]::OrdinalIgnoreCase))) {
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }
}
# Avoid schtasks.exe /TR quoting of inline "set VARIABLE=... && ..." (old installer bug).
# A dedicated -File script sets JOBHUNTAI_HOME and starts the executable.
$psExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $psExe)) { throw "Windows PowerShell executable not found at $psExe" }
$serverScript = Join-Path $install 'start-server.ps1'
$arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $serverScript + '"'
$action = New-ScheduledTaskAction -Execute $psExe -Argument $arguments -WorkingDirectory $install
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName -ErrorAction Stop

# Validate both task registration and the actual application HTTP health endpoint.
$healthy = $false
for ($attempt = 1; $attempt -le 20; $attempt++) {
    Start-Sleep -Seconds 2
    try {
        $answer = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
        if ($null -ne $answer) { $healthy = $true; break }
    } catch { }
}
if (-not $healthy) {
    Write-Warning "HTTP health check failed. Inspect $data\stdout.log and Task Scheduler history."
    throw "JobHuntAI scheduled task started, but web server did not become healthy."
}
Write-Host 'JobHuntAI installed, scheduled task started, and health check passed.'
Write-Host 'Open inside Windows RDP: http://127.0.0.1:8000'
Write-Host 'Public internet access is deliberately disabled until HTTPS is configured.'
