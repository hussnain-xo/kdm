# Build KDM-extension.crx for Windows policy install (no Chrome Web Store).
# Requires Google Chrome on the machine (uses chrome.exe --pack-extension).
#
# Usage (repo root):  powershell -ExecutionPolicy Bypass -File scripts\pack_kdm_crx.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$ExtDir = Join-Path $RepoRoot "extension-for-users\KDM-Browser-Extension"
$Pem = Join-Path $RepoRoot "packaging\windows\kdm-extension.pem"
$OutDir = Join-Path $RepoRoot "dist\extensions"
$OutCrx = Join-Path $OutDir "KDM-extension.crx"

if (-not (Test-Path (Join-Path $ExtDir "manifest.json"))) {
    Write-Error "Extension folder missing: $ExtDir"
}
if (-not (Test-Path $Pem)) {
    Write-Error "Missing packaging\windows\kdm-extension.pem"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$chrome = $null
foreach ($c in @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    )) {
    if (Test-Path $c) { $chrome = $c; break }
}
if (-not $chrome) {
    Write-Error "Google Chrome not found. Install Chrome, then re-run."
}

$extParent = Split-Path $ExtDir -Parent
$extLeaf = Split-Path $ExtDir -Leaf
$intermediate = Join-Path $extParent "$extLeaf.crx"
Remove-Item $intermediate -ErrorAction SilentlyContinue
Push-Location $RepoRoot
try {
    & $chrome --pack-extension="$ExtDir" --pack-extension-key="$Pem"
    if (-not (Test-Path $intermediate)) {
        Write-Error "Expected CRX not found: $intermediate"
    }
    Move-Item -Force $intermediate $OutCrx
}
finally {
    Pop-Location
}

Write-Host "Wrote: $OutCrx"
