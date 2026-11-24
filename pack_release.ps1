param(
    [string]$Version = "1.0"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path "dist\BambuSmartTuner.exe")) {
    throw "dist\BambuSmartTuner.exe 不存在，先跑 .\build_exe.ps1 -SkipDeps"
}

$name = "BambuSmartTuner-v$Version-win64"
$stage = Join-Path $root "release\$name"
$zip = Join-Path $root "release\$name.zip"

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage "rules") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage "data") | Out-Null

Copy-Item "dist\BambuSmartTuner.exe" $stage
Copy-Item "rules\BambuRules.json" (Join-Path $stage "rules")
Copy-Item "data\studio_ui.json" (Join-Path $stage "data")
Copy-Item "README.md" $stage
Copy-Item "docs\收件人须知.txt" $stage
# 收款码：放进去收件人也能换（不换就用 EXE 内置那张）
if (Test-Path "assets\donate.png") {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "assets") | Out-Null
    Copy-Item "assets\donate.png" (Join-Path $stage "assets")
}

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal

$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host "  发布包：$zip（$size MB）" -ForegroundColor Green
Write-Host "  目录：  $stage" -ForegroundColor Green
Write-Host ""
Get-ChildItem $stage -Recurse -File | ForEach-Object {
    Write-Host ("    {0,-30} {1,10:N0}" -f $_.Name, $_.Length)
}
