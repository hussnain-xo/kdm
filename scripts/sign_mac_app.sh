#!/usr/bin/env bash
# Ad-hoc sign KDM.app so Gatekeeper is less likely to reject the bundle.
# Usage: ./scripts/sign_mac_app.sh [path/to/KDM.app]
set -euo pipefail
APP="${1:-dist/KDM.app}"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Only for macOS."
  exit 0
fi
if [[ ! -d "$APP" ]]; then
  echo "Not found: $APP"
  exit 1
fi
codesign --force --sign - --deep "$APP"
echo "Signed: $APP"
codesign -dv --verbose=4 "$APP" 2>&1 | head -5
