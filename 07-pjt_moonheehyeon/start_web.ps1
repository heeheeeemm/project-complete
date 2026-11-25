$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$managePath = Join-Path $PSScriptRoot 'server\web\manage.py'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the .venv environment and install server/requirements.txt first.'
}
& $pythonPath $managePath migrate
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
& $pythonPath $managePath runserver 127.0.0.1:8080
