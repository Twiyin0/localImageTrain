param(
    [ValidateSet("full", "local", "client", "server")]
    [string]$Mode = "full",
    [string]$VenvPath = ".venv",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu121",
    [switch]$Training,
    [switch]$CpuOnly
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "app_setup.ps1"
$argsList = @("-Mode", $Mode, "-VenvPath", $VenvPath)
if ($Training) {
    $argsList += @("-WithTraining", "-TorchIndexUrl", $TorchIndexUrl)
}
if ($CpuOnly) {
    $argsList += "-CpuOnly"
}

& $scriptPath @argsList
