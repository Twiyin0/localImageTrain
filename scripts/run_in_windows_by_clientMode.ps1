param(
    [string]$VenvPath = ".venv",
    [string]$ListenHost = "",
    [int]$Port = 0,
    [switch]$Share
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$resolvedHost = if ($ListenHost) { $ListenHost } elseif ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$resolvedPort = if ($Port -gt 0) { $Port } elseif ($env:PORT) { [int]$env:PORT } else { 7860 }
$python = Join-Path (Join-Path $projectRoot $VenvPath) "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python executable not found: $python. Run scripts\app_setup.ps1 first."
}

$argsList = @("app.py", "--host", $resolvedHost, "--port", $resolvedPort)
if ($Share) {
    $argsList += "--share"
}

Push-Location $projectRoot
try {
    & $python @argsList
}
finally {
    Pop-Location
}
