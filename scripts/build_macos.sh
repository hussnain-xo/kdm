#!/usr/bin/env bash
# Builds DMG + ZIP for macOS. See also: scripts/package_release.sh
set -euo pipefail
exec "$(dirname "$0")/package_release.sh"
