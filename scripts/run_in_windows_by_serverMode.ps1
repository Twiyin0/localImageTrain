param(
    [string]$VenvPath = ".venv",
    [string]$ListenHost = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$resolvedHost = if ($ListenHost) { $ListenHost } elseif ($env:HOST) { $env:HOST } else { "0.0.0.0" }
$resolvedPort = if ($Port -gt 0) { $Port } elseif ($env:PORT) { [int]$env:PORT } else { 8000 }
$python = Join-Path (Join-Path $projectRoot $VenvPath) "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python executable not found: $python. Run scripts\app_setup.ps1 first."
}

Push-Location $projectRoot
try {
    & $python api.py --host $resolvedHost --port $resolvedPort
}
finally {
    Pop-Location
}
