$ErrorActionPreference = "Stop"

param(
    [string]$VenvPath = ".venv",
    [string]$Host = "127.0.0.1",
    [int]$Port = 7860
)

$python = Join-Path $VenvPath "Scripts\python.exe"
& $python app.py --host $Host --port $Port
