#!/usr/bin/env bash
# Builds extension-for-users/KDM-Browser-Extension.zip for sharing with end users.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
EXT="$ROOT/extension-for-users/KDM-Browser-Extension"
if [[ ! -f "$EXT/manifest.json" ]]; then
  echo "Missing $EXT — run from repo after extension-for-users is populated."
  exit 1
fi
OUT="$ROOT/extension-for-users/KDM-Browser-Extension.zip"
rm -f "$OUT"
( cd "$ROOT/extension-for-users" && zip -r "$OUT" KDM-Browser-Extension -x "*.DS_Store" )
echo "Created: $OUT"
ls -la "$OUT"
