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

$kdmHarvest = (Resolve-Path (Join-Path $Root "dist\KDM")).Path
# Binder / UI assets (e.g. license) — forward slashes for light -b.
$wixBinder = ((Resolve-Path (Join-Path $Root "packaging\wix")).Path -replace '\\', '/').TrimEnd('/')

function Remove-KdmMetadataDirs {
  param([string]$HarvestRoot)
  # Pip metadata dirs — not needed at runtime; LGHT0103 on CI if heat picks them up.
  # Use Name match; -Filter "*.dist-info" alone can miss nested dirs on some hosts.
  Get-ChildItem -LiteralPath $HarvestRoot -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object {
      $n = $_.Name
      $n -like '*.dist-info' -or $n -like '*.egg-info'
    } |
    Sort-Object { $_.FullName.Length } -Descending |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

Remove-KdmMetadataDirs $kdmHarvest

# heat -var emits Source="$(var.KdmHarvestDir)\rel\path". Inlining to a real disk path avoids candle -d
# (CI/local preprocessor edge cases) and light SourceDir / missing bind LGHT0103.
& $heat dir $kdmHarvest -nologo -o $heatOut `
  -cg KdmHarvest -gg -g1 -scom -sreg -ke -dr INSTALLFOLDER -platform x64 `
  -var var.KdmHarvestDir
if ($LASTEXITCODE -ne 0) { throw "heat.exe failed" }

# Belt-and-suspenders: drop any heat <Component> whose <File Source> points at .dist-info / .egg-info,
# and matching <ComponentRef> rows (otherwise candle fails on dangling refs).
function Remove-HeatWxsMetadataComponents {
  param([string]$WxsPath)
  $t = [System.IO.File]::ReadAllText($WxsPath)
  if ($t.IndexOf('.dist-info', [System.StringComparison]::OrdinalIgnoreCase) -lt 0 -and
      $t.IndexOf('.egg-info', [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
    return
  }
  $cmpRx = New-Object System.Text.RegularExpressions.Regex(
    '(?s)<Component\b[^>]*\bId="([^"]+)"[^>]*>.*?</Component>\s*',
    [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
  )
  $removed = New-Object System.Collections.Generic.List[string]
  $t = $cmpRx.Replace($t, [System.Text.RegularExpressions.MatchEvaluator] {
      param($m)
      $block = $m.Groups[0].Value
      if ($block -match '(?i)\.(dist-info|egg-info)') {
        [void]$removed.Add($m.Groups[1].Value)
        return ''
      }
      $block
    })
  foreach ($id in $removed) {
    $esc = [regex]::Escape($id)
    $refRx = New-Object System.Text.RegularExpressions.Regex(
      '<ComponentRef\b[^>]+\bId="' + $esc + '"\s*/>\s*',
      [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $t = $refRx.Replace($t, '')
  }
  $u8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($WxsPath, $t, $u8)
}

Remove-HeatWxsMetadataComponents $heatOut

$heatUtf8 = New-Object System.Text.UTF8Encoding $false
$heatText = [System.IO.File]::ReadAllText($heatOut)
$harvestAbs = $kdmHarvest.TrimEnd('\') + '\'
$heatVarPrefix = '$(var.KdmHarvestDir)' + '\'
$heatVarFwd = '$(var.KdmHarvestDir)' + '/'
if ($heatText.IndexOf('$(var.KdmHarvestDir)', [System.StringComparison]::Ordinal) -ge 0) {
  $heatText = $heatText.Replace($heatVarPrefix, $harvestAbs)
  $heatText = $heatText.Replace($heatVarFwd, ($harvestAbs -replace '\\', '/'))
  [System.IO.File]::WriteAllText($heatOut, $heatText, $heatUtf8)
  $heatText = [System.IO.File]::ReadAllText($heatOut)
}
# If heat did not emit $(var...) (older tool), paths may still be Source="SourceDir\...
$heatSdPrefix = 'Source="SourceDir' + '\'
if ($heatText.IndexOf($heatSdPrefix, [System.StringComparison]::Ordinal) -ge 0) {
  $heatText = $heatText.Replace($heatSdPrefix, ('Source="' + $harvestAbs))
  [System.IO.File]::WriteAllText($heatOut, $heatText, $heatUtf8)
}

$heatVerifyText = [System.IO.File]::ReadAllText($heatOut)
if ($heatVerifyText.IndexOf('$(var.KdmHarvestDir)', [System.StringComparison]::Ordinal) -ge 0) {
  throw 'HeatKdm.wxs still contains $(var.KdmHarvestDir) after inlining; heat format may have changed.'
}
if ($heatVerifyText.IndexOf($heatSdPrefix, [System.StringComparison]::Ordinal) -ge 0) {
  throw 'HeatKdm.wxs still has SourceDir paths after rewrite; check heat.exe and dist\KDM content.'
}

$sampleFileLine = Select-String -LiteralPath $heatOut -Pattern '<File ' | Select-Object -First 1
if ($sampleFileLine) {
  Write-Host "--- Heat harvest sample (after inline disk root) ---"
  Write-Host $sampleFileLine.Line.Trim()
}

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

$utf8NoBomMain = New-Object System.Text.UTF8Encoding $false
$licenseRtfAbs = (Resolve-Path (Join-Path $Root "packaging\wix\License.rtf")).Path
$mainPatch = [System.IO.File]::ReadAllText($mainWxsBuilt)
if ($mainPatch.IndexOf('Value="License.rtf"', [System.StringComparison]::Ordinal) -ge 0) {
  $mainPatch = $mainPatch.Replace('Value="License.rtf"', ('Value="' + $licenseRtfAbs + '"'))
  [System.IO.File]::WriteAllText($mainWxsBuilt, $mainPatch, $utf8NoBomMain)
}

Write-Host "--- $mainWxsBuilt head (verify Product Version) ---"
Get-Content -LiteralPath $mainWxsBuilt -TotalCount 12

& $candle -nologo -arch x64 -o $candleOutDir $mainWxsBuilt $heatOut
if ($LASTEXITCODE -ne 0) { throw "candle failed" }

$wixobjs = Get-ChildItem -Path $Obj -Filter *.wixobj
if (-not $wixobjs) { throw "No .wixobj from candle" }
# -b wix: any remaining relative assets under packaging\wix; harvested File/@Source is absolute after candle.
& $light -nologo -o $msiOut -b $wixBinder -ext WixUIExtension -sw1076 -cultures:en-us @($wixobjs | ForEach-Object { $_.FullName })
if ($LASTEXITCODE -ne 0) { throw "light failed" }

Write-Host "MSI: $msiOut"
Get-Item $msiOut
