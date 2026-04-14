#!/usr/bin/env bash
# Builds Linux tar.gz. See also: scripts/package_release.sh
set -euo pipefail
exec "$(dirname "$0")/package_release.sh"
