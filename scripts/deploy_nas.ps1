param(
    [string]$HostName,
    [int]$SshPort = 22,
    [string]$Username = "root",
    [string]$Password = "",
    [string]$RemoteDir = "/opt/python/huggingface/localImageTrain",
    [string]$LocalDir = ".",
    [string]$VenvPath = ".venv",
    [switch]$NoUpload
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "HostName is required, for example: -HostName 10.10.1.9"
}
if (-not $Password) {
    throw "Password is required. Pass -Password or set it through your own wrapper."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path (Join-Path $projectRoot $VenvPath) "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python executable not found: $python. Run scripts\app_setup.ps1 first."
}

$argsList = @(
    "deploy_nas.py",
    "--host", $HostName,
    "--port", [string]$SshPort,
    "--username", $Username,
    "--password", $Password,
    "--remote-dir", $RemoteDir,
    "--local-dir", $LocalDir
)
if ($NoUpload) {
    $argsList += "--no-upload"
}

Push-Location $projectRoot
try {
    & $python @argsList
}
finally {
    Pop-Location
}
