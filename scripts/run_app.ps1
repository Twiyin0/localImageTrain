param(
    [string]$VenvPath = ".venv",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 7860
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$python = Join-Path $projectRoot $VenvPath
$python = Join-Path $python "Scripts\python.exe"

Push-Location $projectRoot
try {
    & $python app.py --host $ListenHost --port $Port
}
finally {
    Pop-Location
}
