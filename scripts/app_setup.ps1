param(
    [ValidateSet("full", "local", "client", "server")]
    [string]$Mode = "full",
    [string]$VenvPath = ".venv",
    [string]$Python = "python",
    [string]$TorchIndexUrl = "",
    [switch]$WithTraining,
    [switch]$CpuOnly
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$venvRoot = Join-Path $projectRoot $VenvPath
$pythonInVenv = if ($IsWindows -or -not (Test-Path "variable:IsWindows")) {
    Join-Path $venvRoot "Scripts\python.exe"
} else {
    Join-Path $venvRoot "bin/python"
}

if (-not (Test-Path -LiteralPath $venvRoot)) {
    & $Python -m venv $venvRoot
}

if (-not (Test-Path -LiteralPath $pythonInVenv)) {
    throw "Python executable not found: $pythonInVenv"
}

Push-Location $projectRoot
try {
    & $pythonInVenv -m pip install --upgrade pip

    $requirements = "requirements-api.txt"
    if (($Mode -ne "server") -and ($IsWindows -or -not (Test-Path "variable:IsWindows")) -and -not $CpuOnly) {
        $requirements = "requirements.txt"
    }
    & $pythonInVenv -m pip install -r $requirements

    if ($WithTraining) {
        if ($TorchIndexUrl) {
            & $pythonInVenv -m pip install torch torchvision torchaudio --index-url $TorchIndexUrl
        } else {
            & $pythonInVenv -m pip install torch torchvision torchaudio
        }
        & $pythonInVenv -m pip install -r requirements-train.txt
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Environment ready: $venvRoot"
Write-Host "Windows local:  powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_localMode.ps1"
Write-Host "Windows client: powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_clientMode.ps1"
Write-Host "Windows server: powershell -ExecutionPolicy Bypass -File scripts\run_in_windows_by_serverMode.ps1"
