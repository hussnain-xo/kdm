# Build KDM.exe (PyInstaller) then compile the Windows setup EXE with Inno Setup 6.
# Prerequisite: Inno Setup 6 — https://jrsoftware.org/isinfo.php
# Typical ISCC path:  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
#
# Usage (repo root):  powershell -ExecutionPolicy Bypass -File scripts\build_windows_installer.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

if (-not (Test-Path "kdm.py")) {
    Write-Error "Run from the KDM repository root."
}

$Version = (Get-Content (Join-Path $RepoRoot "packaging\VERSION") -Raw).Trim()
python -m pip install -r requirements-build.txt
python -m PyInstaller packaging\kdm.spec --noconfirm --clean

if (-not (Test-Path "dist\KDM\KDM.exe")) {
    Write-Error "dist\KDM\KDM.exe not found after PyInstaller."
}
if (-not (Test-Path "dist\KDM\browser-extension\manifest.json")) {
    Write-Warning "browser-extension folder missing in dist\KDM — rebuild after extension-for-users/KDM-Browser-Extension exists."
}

$Rel = Join-Path $RepoRoot "dist\release"
New-Item -ItemType Directory -Force $Rel | Out-Null
$readmeDest = Join-Path $Rel "KDM-$Version-README.txt"
(Get-Content (Join-Path $RepoRoot "packaging\INSTALL.template.txt") -Raw) `
    -replace "__VERSION__", $Version | Set-Content -Path $readmeDest -Encoding utf8
Copy-Item $readmeDest (Join-Path $RepoRoot "dist\KDM\README-KDM.txt") -Force
$userQuick = Join-Path $Rel "USER_QUICK_START.txt"
(Get-Content (Join-Path $RepoRoot "packaging\USER_QUICK_START.txt") -Raw) `
    -replace "__VERSION__", $Version | Set-Content -Path $userQuick -Encoding utf8
Copy-Item $userQuick (Join-Path $RepoRoot "dist\KDM\USER_QUICK_START.txt") -Force

$iscc = $null
foreach ($c in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )) {
    if (Test-Path $c) { $iscc = $c; break }
}
if (-not $iscc) {
    Write-Warning "Inno Setup 6 (ISCC.exe) not found. ZIP-only release:"
    $zipPath = Join-Path $Rel "KDM-$Version-Windows-x64.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $RepoRoot "dist\KDM") -DestinationPath $zipPath -Force
    Write-Host "Built: $zipPath"
    Write-Host "Install Inno Setup 6 and re-run to produce KDM-Setup-$Version-x64.exe"
    exit 0
}

& $iscc (Join-Path $RepoRoot "packaging\windows\KDM-Setup.iss") "/DMyAppVersion=$Version"
$setupExe = Join-Path $Rel "KDM-Setup-$Version-x64.exe"
if (-not (Test-Path $setupExe)) {
    Write-Error "Expected installer not found: $setupExe"
}

$zipPath = Join-Path $Rel "KDM-$Version-Windows-x64.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $RepoRoot "dist\KDM") -DestinationPath $zipPath -Force

Write-Host "Built: $setupExe"
Write-Host "Built: $zipPath"
Get-ChildItem $Rel | Sort-Object Name
