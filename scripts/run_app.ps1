param(
    [ValidateSet("local", "client", "server")]
    [string]$Mode = "client",
    [string]$VenvPath = ".venv",
    [string]$ListenHost = "",
    [int]$Port = 0,
    [switch]$Share
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
switch ($Mode) {
    "local" {
        & (Join-Path $projectRoot "scripts\run_in_windows_by_localMode.ps1") -VenvPath $VenvPath -ListenHost $ListenHost -Port $Port -Share:$Share
    }
    "client" {
        & (Join-Path $projectRoot "scripts\run_in_windows_by_clientMode.ps1") -VenvPath $VenvPath -ListenHost $ListenHost -Port $Port
    }
    "server" {
        & (Join-Path $projectRoot "scripts\run_in_windows_by_serverMode.ps1") -VenvPath $VenvPath -ListenHost $ListenHost -Port $Port
    }
}
