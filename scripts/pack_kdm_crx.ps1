# Build KDM-extension.crx for Windows policy install (no Chrome Web Store).
# Uses Chromium --pack-extension (Edge or Chrome). Unreliable on headless CI — skipped there.
#
# Usage (repo root):  powershell -ExecutionPolicy Bypass -File scripts\pack_kdm_crx.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$OutDir = Join-Path $RepoRoot "dist\extensions"
$OutCrx = Join-Path $OutDir "KDM-extension.crx"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# GitHub Actions / Azure Pipelines / etc.: Chromium pack-extension usually produces no .crx on runners.
# Inno Setup uses skipifsourcedoesntexist for the .crx; policy bundling can be done on a real Windows PC.
$skipPack = ($env:GITHUB_ACTIONS -eq "true") -or ($env:CI -eq "true")
if ($skipPack) {
    Write-Host "CI environment: skipping CRX pack (expected). For a policy .crx, run this script on Windows with Edge/Chrome, or use a self-hosted runner."
    exit 0
}

$ExtDir = Join-Path $RepoRoot "extension-for-users\KDM-Browser-Extension"
$Pem = Join-Path $RepoRoot "packaging\windows\kdm-extension.pem"

if (-not (Test-Path (Join-Path $ExtDir "manifest.json"))) {
    Write-Error "Extension folder missing: $ExtDir"
}
if (-not (Test-Path $Pem)) {
    Write-Error "Missing packaging\windows\kdm-extension.pem"
}

$extParent = Split-Path $ExtDir -Parent
$extLeaf = Split-Path $ExtDir -Leaf
$intermediate = Join-Path $extParent "$extLeaf.crx"

$candidates = @(
    "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

if ($candidates.Count -eq 0) {
    Write-Error "Neither Microsoft Edge nor Google Chrome found. Install one, then re-run."
}

$ciExtras = @("--no-sandbox", "--disable-gpu")

function Get-RecentCrxIn($dir) {
    if (-not (Test-Path $dir)) { return $null }
    Get-ChildItem -LiteralPath $dir -Filter "*.crx" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

Remove-Item -LiteralPath $intermediate -ErrorAction SilentlyContinue

Push-Location $RepoRoot
try {
    $packed = $false
    foreach ($browser in $candidates) {
        Write-Host "Trying pack-extension via: $browser"
        $args = $ciExtras + @(
            "--pack-extension=$ExtDir",
            "--pack-extension-key=$Pem"
        )
        $p = Start-Process -FilePath $browser -ArgumentList $args -PassThru -Wait -NoNewWindow
        if ($p.ExitCode -ne 0) {
            Write-Warning "Exit code $($p.ExitCode) from $browser"
        }
        if (Test-Path -LiteralPath $intermediate) {
            $packed = $true
            break
        }
        $alt = Get-RecentCrxIn $extParent
        if ($alt) {
            $intermediate = $alt.FullName
            $packed = $true
            break
        }
        $alt = Get-RecentCrxIn $RepoRoot
        if ($alt -and ($alt.LastWriteTime -gt (Get-Date).AddMinutes(-2))) {
            $intermediate = $alt.FullName
            $packed = $true
            break
        }
    }

    if (-not $packed) {
        Write-Error "CRX not produced. Tried: $($candidates -join ', '). Expected near: $intermediate"
    }

    Move-Item -Force -LiteralPath $intermediate -Destination $OutCrx
}
finally {
    Pop-Location
}

Write-Host "Wrote: $OutCrx"
