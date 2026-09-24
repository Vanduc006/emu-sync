#!/usr/bin/env bash
# Double-click file này trong Finder (macOS) để mở emu-sync.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "Chưa có 'uv' (Python package manager)."
  echo "Cài bằng: curl -LsSf https://astral.sh/uv/install.sh | sh"
  read -r -p "Nhấn Enter để đóng..." _
  exit 1
fi

exec uv run emu-sync app "$@"
