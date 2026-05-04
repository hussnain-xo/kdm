#!/bin/bash
# Double-click after opening the DMG (same wizard as Windows .pkg / post-install).
DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -d "$DIR/KDM.app" ]]; then
  open -a "$DIR/KDM.app" --args --post-install
else
  osascript -e 'display dialog "KDM.app not found next to this script. Keep KDM.app in the same folder as this file, or install using the .pkg installer." buttons {"OK"} default button "OK"' 2>/dev/null || true
fi
