#!/usr/bin/env bash
# Tải scrcpy-server v4.1 (Apache-2.0) vào src/emu_sync/assets/ + verify SHA-256.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="4.1"
URL="https://github.com/Genymobile/scrcpy/releases/download/v${VERSION}/scrcpy-server-v${VERSION}"
OUT="src/emu_sync/assets/scrcpy-server-v${VERSION}.jar"
SHA256="deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae"

if [[ -f "$OUT" ]] && echo "$SHA256  $OUT" | shasum -a 256 -c --status 2>/dev/null; then
  echo "OK: $OUT đã có và đúng checksum"
  exit 0
fi

echo "Đang tải $URL ..."
curl -fL --retry 2 -o "$OUT" "$URL"
echo "$SHA256  $OUT" | shasum -a 256 -c
echo "OK: $OUT"
