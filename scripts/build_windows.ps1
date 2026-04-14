# Build KDM for Windows (PyInstaller + zip). Run from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot
if (-not (Test-Path "kdm.py")) {
    Write-Error "Run this script from the KDM repository (kdm.py not found)."
}

$Version = (Get-Content (Join-Path $RepoRoot "packaging\VERSION") -Raw).Trim()
python -m pip install -r requirements-build.txt
python -m PyInstaller packaging/kdm.spec --noconfirm --clean

if (-not (Test-Path "dist\KDM\KDM.exe")) {
    Write-Error "dist\KDM\KDM.exe not found after PyInstaller."
}

$Rel = Join-Path $RepoRoot "dist\release"
New-Item -ItemType Directory -Force $Rel | Out-Null
$readmeDest = Join-Path $Rel "KDM-$Version-README.txt"
(Get-Content (Join-Path $RepoRoot "packaging\INSTALL.template.txt") -Raw) `
 -replace "__VERSION__", $Version | Set-Content -Path $readmeDest -Encoding utf8
Copy-Item $readmeDest (Join-Path $RepoRoot "dist\KDM\README-KDM.txt") -Force

$zipPath = Join-Path $Rel "KDM-$Version-Windows-x64.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $RepoRoot "dist\KDM") -DestinationPath $zipPath -Force
Write-Host "Built: $zipPath"
Get-ChildItem $Rel
