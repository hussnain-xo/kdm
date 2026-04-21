#!/usr/bin/env bash
# Build .deb after PyInstaller (dist/KDM/). Run from repo root on Debian/Ubuntu.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d ' \t\r\n' < "$ROOT/packaging/VERSION")"

if [[ ! -x "$ROOT/dist/KDM/KDM" ]]; then
  echo "Run PyInstaller first:  python -m PyInstaller packaging/kdm.spec --noconfirm --clean"
  exit 1
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb not found. Install: sudo apt install dpkg-dev"
  exit 1
fi

STAGE="$ROOT/dist/deb_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/opt/kdm"
cp -a "$ROOT/dist/KDM/." "$STAGE/opt/kdm/"

mkdir -p "$STAGE/usr/share/applications"
cp "$ROOT/packaging/linux/kdm.desktop" "$STAGE/usr/share/applications/kdm.desktop"

mkdir -p "$STAGE/usr/bin"
ln -sf /opt/kdm/KDM "$STAGE/usr/bin/kdm"

mkdir -p "$STAGE/DEBIAN"
sed "s/__VERSION__/${VERSION}/g" "$ROOT/packaging/linux/DEBIAN_control.tpl" > "$STAGE/DEBIAN/control"

cat > "$STAGE/DEBIAN/postinst" << 'EOS'
#!/bin/sh
set -e
chmod +x /opt/kdm/KDM 2>/dev/null || true
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications 2>/dev/null || true
fi
exit 0
EOS
chmod 755 "$STAGE/DEBIAN/postinst"

mkdir -p "$ROOT/dist/release"
OUT="$ROOT/dist/release/kdm_${VERSION}_amd64.deb"
rm -f "$OUT"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"
rm -rf "$STAGE"
echo "Built: $OUT"
ls -la "$OUT"
