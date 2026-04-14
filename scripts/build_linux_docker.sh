#!/usr/bin/env bash
# Build KDM for Linux inside Docker (works from Mac or Windows with Docker Desktop).
# Output: dist/release/KDM-<version>-Linux-x86_64.tar.gz
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! command -v docker >/dev/null 2>&1; then
  echo "Install Docker Desktop, then run this again."
  exit 1
fi
docker build -f packaging/Dockerfile.linux-release -t kdm-linux-build "$ROOT"
mkdir -p dist/release
CID=$(docker create kdm-linux-build)
docker cp "$CID:/out/." dist/release/
docker rm "$CID"
echo "Copied to dist/release/:"
ls -la dist/release/
