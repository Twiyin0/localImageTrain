param(
    [string]$VenvPath = ".venv",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu121",
    [switch]$Training = $true
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $VenvPath)) {
    python -m venv $VenvPath
}

$python = Join-Path $VenvPath "Scripts\python.exe"

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt

if ($Training) {
    & $python -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url $TorchIndexUrl
    & $python -m pip install -r requirements-train.txt
}

Write-Host ""
Write-Host "Environment ready."
Write-Host "Start UI with:"
Write-Host "$VenvPath\Scripts\python.exe app.py --host 127.0.0.1 --port 7860"
