$ErrorActionPreference = "Stop"

$snapshotRoot = Join-Path (Resolve-Path .).Path ".cache\wd_tagger\models--SmilingWolf--wd-convnext-tagger-v3\snapshots"
$snapshotDir = Get-ChildItem $snapshotRoot -Directory | Select-Object -First 1
if (-not $snapshotDir) {
    throw "No cached wd-convnext-tagger-v3 snapshot found in $snapshotRoot"
}

$targetDir = Join-Path (Resolve-Path .).Path "models\wd-convnext-tagger-v3"
New-Item -ItemType Directory -Force $targetDir | Out-Null

Copy-Item -LiteralPath (Join-Path $snapshotDir.FullName "model.onnx") -Destination (Join-Path $targetDir "model.onnx") -Force
Copy-Item -LiteralPath (Join-Path $snapshotDir.FullName "selected_tags.csv") -Destination (Join-Path $targetDir "selected_tags.csv") -Force

Write-Host "Offline model prepared in $targetDir"
