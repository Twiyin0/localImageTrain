$ErrorActionPreference = "Stop"

param(
    [string]$VenvPath = "..\\.venv",
    [string]$Host = "127.0.0.1",
    [int]$Port = 7860
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvedVenv = Join-Path $scriptDir $VenvPath
$python = Join-Path $resolvedVenv "Scripts\python.exe"

Push-Location $scriptDir
try {
    & $python app.py --host $Host --port $Port
}
finally {
    Pop-Location
}
