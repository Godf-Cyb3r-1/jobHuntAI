# Run by Task Scheduler as LocalSystem. No command-line environment-variable tricks.
$ErrorActionPreference = 'Stop'
$homePath = Join-Path $env:ProgramData 'JobHuntAI'
New-Item -ItemType Directory -Force -Path $homePath | Out-Null
$env:JOBHUNTAI_HOME = $homePath
$env:PYTHONUNBUFFERED = '1'
$exe = Join-Path $PSScriptRoot 'JobHuntAI.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "JobHuntAI.exe not found at $exe"
}
# Keep the task alive for as long as the web server runs; append diagnostics to a log.
& $exe serve --host 127.0.0.1 --port 8000 *>> (Join-Path $homePath 'stdout.log')
exit $LASTEXITCODE
