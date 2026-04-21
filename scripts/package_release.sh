#!/usr/bin/env bash
# Build KDM with PyInstaller and write distributables to dist/release/
# Naming matches IDM-style releases: KDM-<VERSION>-<Platform>.<ext>
# Usage (macOS or Linux): ./scripts/package_release.sh
# Windows: use scripts/build_windows.ps1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(tr -d ' \t\r\n' < "$ROOT/packaging/VERSION")"
python3 -m pip install -r requirements-build.txt
if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! python3 -m PyInstaller packaging/kdm.spec --noconfirm --clean --target-arch universal2; then
    echo "Universal2 failed; building default arch for this Mac."
    python3 -m PyInstaller packaging/kdm.spec --noconfirm --clean
  fi
  "$ROOT/scripts/sign_mac_app.sh" "$ROOT/dist/KDM.app"
else
  python3 -m PyInstaller packaging/kdm.spec --noconfirm --clean
fi

REL="$ROOT/dist/release"
rm -rf "$REL"
mkdir -p "$REL"

sed "s/__VERSION__/${VERSION}/g" "$ROOT/packaging/INSTALL.template.txt" > "$REL/KDM-${VERSION}-README.txt"
sed "s/__VERSION__/${VERSION}/g" "$ROOT/packaging/USER_QUICK_START.txt" > "$REL/USER_QUICK_START.txt"

OS_UNAME="$(uname -s)"
case "$OS_UNAME" in
  Darwin)
    APP="$ROOT/dist/KDM.app"
    if [[ ! -d "$APP" ]]; then
      echo "ERROR: $APP not found after PyInstaller."
      exit 1
    fi
    STAGE="$ROOT/dist/dmg_staging"
    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    cp -R "$APP" "$STAGE/KDM.app"
    cp "$REL/KDM-${VERSION}-README.txt" "$STAGE/README-KDM.txt"
    cp "$REL/USER_QUICK_START.txt" "$STAGE/USER_QUICK_START.txt"
    cp "$ROOT/packaging/MAC_FIRST_LAUNCH.txt" "$STAGE/MAC_FIRST_LAUNCH.txt"
    if [[ ! -e "$STAGE/Applications" ]]; then
      ln -sf /Applications "$STAGE/Applications"
    fi
    DMG="$REL/KDM-${VERSION}-macOS.dmg"
    rm -f "$DMG"
    hdiutil create -volname "Kalupura Download Manager" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
    ZIP="$REL/KDM-${VERSION}-macOS.zip"
    ditto -c -k --sequesterRsrc --keepParent "$STAGE" "$ZIP"
    rm -rf "$STAGE"
    echo "Built: $DMG"
    echo "Built: $ZIP"
    chmod +x "$ROOT/scripts/build_macos_pkg.sh" "$ROOT/packaging/mac_pkg_scripts/postinstall" 2>/dev/null || true
    if "$ROOT/scripts/build_macos_pkg.sh"; then
      echo "Also built macOS .pkg (if pkgbuild succeeded)."
    fi
    ;;
  Linux)
    if [[ ! -d "$ROOT/dist/KDM" ]]; then
      echo "ERROR: $ROOT/dist/KDM not found after PyInstaller."
      exit 1
    fi
    cp "$REL/KDM-${VERSION}-README.txt" "$ROOT/dist/KDM/README-KDM.txt"
    cp "$REL/USER_QUICK_START.txt" "$ROOT/dist/KDM/USER_QUICK_START.txt"
    ARCHIVE="$REL/KDM-${VERSION}-Linux-x86_64.tar.gz"
    tar -czvf "$ARCHIVE" -C "$ROOT/dist" KDM
    echo "Built: $ARCHIVE"
    chmod +x "$ROOT/scripts/build_linux_deb.sh" 2>/dev/null || true
    if command -v dpkg-deb >/dev/null 2>&1 && "$ROOT/scripts/build_linux_deb.sh"; then
      echo "Also built .deb (if dpkg-deb succeeded)."
    fi
    ;;
  *)
    echo "This script supports macOS and Linux only."
    echo "On Windows run:  powershell -File scripts/build_windows.ps1"
    exit 1
    ;;
esac

echo "Release files in: $REL"
ls -la "$REL"
