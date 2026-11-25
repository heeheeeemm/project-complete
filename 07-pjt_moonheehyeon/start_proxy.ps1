$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$proxyPath = Join-Path $PSScriptRoot 'server\proxy'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the .venv environment and install server/requirements.txt first.'
}
& $pythonPath -m uvicorn main:app --app-dir $proxyPath --host 127.0.0.1 --port 8081 --reload
