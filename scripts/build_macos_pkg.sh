#!/usr/bin/env bash
# Build a .pkg that installs KDM.app into /Applications (requires built dist/KDM.app).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d ' \t\r\n' < "$ROOT/packaging/VERSION")"

APP="$ROOT/dist/KDM.app"
if [[ ! -d "$APP" ]]; then
  echo "dist/KDM.app not found. Run: ./scripts/build_macos.sh or PyInstaller packaging/kdm.spec"
  exit 1
fi

PKGROOT="$ROOT/dist/pkgroot"
rm -rf "$PKGROOT"
mkdir -p "$PKGROOT/Applications"
cp -R "$APP" "$PKGROOT/Applications/KDM.app"

mkdir -p "$ROOT/dist/release"
PKG="$ROOT/dist/release/KDM-Setup-${VERSION}-macOS.pkg"
rm -f "$PKG"
chmod +x "$ROOT/packaging/mac_pkg_scripts/postinstall" 2>/dev/null || true

pkgbuild \
  --root "$PKGROOT" \
  --identifier com.kalupura.kdm \
  --version "$VERSION" \
  --install-location / \
  --scripts "$ROOT/packaging/mac_pkg_scripts" \
  "$PKG"

rm -rf "$PKGROOT"
echo "Built: $PKG"
