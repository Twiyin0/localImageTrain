param(
    [string]$VenvPath = ".venv",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu121",
    [switch]$Training
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "app_setup.ps1"
$argsList = @("-VenvPath", $VenvPath)
if ($Training) {
    $argsList += @("-WithTraining", "-TorchIndexUrl", $TorchIndexUrl)
}

& $scriptPath @argsList
