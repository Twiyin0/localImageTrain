param(
    [string]$VenvPath = ".venv",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 7861
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot "scripts\run_in_windows_by_localMode.ps1") -VenvPath $VenvPath -ListenHost $ListenHost -Port $Port
