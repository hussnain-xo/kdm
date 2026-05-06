# Build KDM-x64.msi (WiX 3) after PyInstaller: dist\KDM\ must exist.
# Run from repo root on Windows. CI or local with WiX Toolset 3.11+.
# Usage:  powershell -File scripts\build_windows_msi.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

if (-not (Test-Path "dist\KDM\KDM.exe")) { Write-Error "dist\KDM\KDM.exe not found. Run PyInstaller first." }

$v = (Get-Content (Join-Path $Root "packaging\VERSION") -Raw).Trim()
if (-not $v) { Write-Error "packaging\VERSION is empty." }
# WiX Product/@Version must be x.x.x.x with each part 0..65534 (not just semver x.y.z).
$verParts = @($v -split '\.' | ForEach-Object { $_ })
while ($verParts.Count -lt 4) { $verParts += '0' }
if ($verParts.Count -gt 4) { $verParts = $verParts[0..3] }
$vWix = ($verParts -join '.')
if ($vWix -notmatch '^\d+(\.\d+){3}$') {
  Write-Error "WiX Product version must be four integers (e.g. 1.0.0.0); got: $vWix"
}
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
$candleOutDir = Join-Path $Obj ""
if (-not $candleOutDir.EndsWith('\')) { $candleOutDir += '\' }

# Clean stale WiX outputs (re-runs / self-hosted runners).
Remove-Item -Path (Join-Path $Obj "*.wixobj") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $heatOut -Force -ErrorAction SilentlyContinue

# Harvest all files from dist\KDM into ComponentGroup KdmHarvest
& $heat dir (Join-Path $Root "dist\KDM") -nologo -o $heatOut `
  -cg KdmHarvest -gg -g1 -scom -sreg -ke -dr INSTALLFOLDER -platform x64
if ($LASTEXITCODE -ne 0) { throw "heat.exe failed" }

# Compile: baked .wxs (CI pre-bakes to avoid runner encoding / old cached trees).
$mainWxs = Join-Path $Root "packaging\wix\KDM.Main.wxs"
$mainWxsBuilt = Join-Path $Root "packaging\wix\KDM.Main.built.wxs"
$token = "__KDM_PRODUCT_VERSION__"

if ($env:KDM_USE_CI_BAKED_WIX -eq "1") {
  $ciBaked = Join-Path $Root "packaging\wix\KDM.Main.ci-baked.wxs"
  if (-not (Test-Path -LiteralPath $ciBaked)) {
    Write-Error "Missing $ciBaked — run the 'Bake WiX KDM.Main (CI)' workflow step first."
  }
  Copy-Item -LiteralPath $ciBaked -Destination $mainWxsBuilt -Force
  Write-Host "Using CI-baked WiX -> $mainWxsBuilt"
} else {
  $wxsText = [System.IO.File]::ReadAllText($mainWxs)
  if ($wxsText.IndexOf($token, [System.StringComparison]::Ordinal) -lt 0) {
    Write-Error "KDM.Main.wxs must contain $token for Product/@Version."
  }
  $wxsBuilt = $wxsText.Replace($token, $vWix)
  $kdmExeAbs = ((Resolve-Path (Join-Path $Root "dist\KDM\KDM.exe")).Path) -replace "\\", "/"
  $wxsBuilt = $wxsBuilt.Replace('SourceFile="dist\KDM\KDM.exe"', ('SourceFile="{0}"' -f $kdmExeAbs))
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($mainWxsBuilt, $wxsBuilt, $utf8NoBom)
}

Write-Host "--- $mainWxsBuilt head (verify Product Version) ---"
Get-Content -LiteralPath $mainWxsBuilt -TotalCount 12

& $candle -nologo -arch x64 -o $candleOutDir $mainWxsBuilt $heatOut
if ($LASTEXITCODE -ne 0) { throw "candle failed" }

$wixobjs = Get-ChildItem -Path $Obj -Filter *.wixobj
if (-not $wixobjs) { throw "No .wixobj from candle" }
& $light -nologo -o $msiOut -ext WixUIExtension -sw1076 -cultures:en-us @($wixobjs | ForEach-Object { $_.FullName })
if ($LASTEXITCODE -ne 0) { throw "light failed" }

Write-Host "MSI: $msiOut"
Get-Item $msiOut
