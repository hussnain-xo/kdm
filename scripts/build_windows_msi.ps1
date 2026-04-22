# Build KDM-x64.msi (WiX 3) after PyInstaller: dist\KDM\ must exist.
# Run from repo root on Windows. CI or local with WiX Toolset 3.11+.
# Usage:  powershell -File scripts\build_windows_msi.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

if (-not (Test-Path "dist\KDM\KDM.exe")) { Write-Error "dist\KDM\KDM.exe not found. Run PyInstaller first." }

$v = (Get-Content (Join-Path $Root "packaging\VERSION") -Raw).Trim()
$wixRoot = $null
foreach ($c in @(
    "C:\Program Files (x86)\WiX Toolset v3.14\bin",
    "C:\Program Files (x86)\WiX Toolset v3.11\bin"
)) { if (Test-Path (Join-Path $c "candle.exe")) { $wixRoot = $c; break } }
if (-not $wixRoot) {
  Write-Host "WiX 3 not found. Installing with Chocolatey..."
  cmd /c "choco install wixtoolset -y --no-progress 2>nul"
  foreach ($c in @("C:\Program Files (x86)\WiX Toolset v3.14\bin", "C:\Program Files (x86)\WiX Toolset v3.11\bin")) {
    if (Test-Path (Join-Path $c "candle.exe")) { $wixRoot = $c; break }
  }
}
if (-not $wixRoot) { Write-Error "candle.exe not found. Install WiX Toolset 3.11+ from https://wixtoolset.org/" }

$heat   = Join-Path $wixRoot "heat.exe"
$candle = Join-Path $wixRoot "candle.exe"
$light  = Join-Path $wixRoot "light.exe"

$rel = Join-Path $Root "dist\release"
New-Item -ItemType Directory -Force $rel | Out-Null
$Obj = Join-Path $Root "packaging\wix\obj"
New-Item -ItemType Directory -Force $Obj | Out-Null
$heatOut = Join-Path $Obj "HeatKdm.wxs"
$msiOut  = Join-Path $Root "dist\release\KDM-$v-x64.msi"

# Harvest all files from dist\KDM into ComponentGroup KdmHarvest
& $heat dir (Join-Path $Root "dist\KDM") -nologo -o $heatOut `
  -cg KdmHarvest -gg -g1 -scom -sreg -ke -dr INSTALLFOLDER -platform x64
if ($LASTEXITCODE -ne 0) { throw "heat.exe failed" }

# Compile (KdmVersion + arch x64; License.rtf is next to KDM.Main.wxs)
$wxsObj = Join-Path $Obj "KDM.Main.wixobj"
$heatObj = Join-Path $Obj "HeatKdm.wixobj"
$mainWxs = Join-Path $Root "packaging\wix\KDM.Main.wxs"
& $candle -nologo -arch x64 -dKdmVersion=$v -o "$Obj\" $mainWxs $heatOut
if ($LASTEXITCODE -ne 0) { throw "candle failed" }

$wixobjs = Get-ChildItem -Path $Obj -Filter *.wixobj
if (-not $wixobjs) { throw "No .wixobj from candle" }
& $light -nologo -o $msiOut -ext WixUIExtension -sw1076 -cultures:en-us @($wixobjs | ForEach-Object { $_.FullName })
if ($LASTEXITCODE -ne 0) { throw "light failed" }

Write-Host "MSI: $msiOut"
Get-Item $msiOut
