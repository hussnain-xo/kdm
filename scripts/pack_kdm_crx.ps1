# Build KDM-extension.crx for Windows policy install (no Chrome Web Store).
# Uses Chromium-based browser (Edge preferred on CI runners, then Chrome).
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
    if ($env:GITHUB_ACTIONS -eq "true") {
        Write-Warning "No Edge/Chrome found to pack CRX; skipping (Inno uses skipifsourcedoesntexist for .crx)."
        exit 0
    }
    Write-Error "Neither Microsoft Edge nor Google Chrome found. Install one, then re-run."
}

$ciExtras = @()
if ($env:GITHUB_ACTIONS -eq "true") {
    $ciExtras = @("--no-sandbox", "--disable-gpu")
}

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
        if ($env:GITHUB_ACTIONS -eq "true") {
            Write-Warning "CRX not produced on runner (pack-extension often flaky in CI). Skipping; installer still builds without policy .crx."
            exit 0
        }
        Write-Error "Expected CRX not found after pack-extension. Tried: $($candidates -join ', '). Intermediate path was: $intermediate"
    }

    Move-Item -Force -LiteralPath $intermediate -Destination $OutCrx
}
finally {
    Pop-Location
}

Write-Host "Wrote: $OutCrx"
