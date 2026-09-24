"""Entry point cho bản đóng gói (PyInstaller) — luôn mở chế độ desktop app.

Khi build ở chế độ --windowed, sys.stdout/stderr là None; ta chuyển hướng log
vào file để print() không lỗi.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_stdio() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".cache"
    log_dir = base / "emu-sync"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "emu-sync-app.log", "a", buffering=1, encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


_ensure_stdio()

from emu_sync.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["app", *sys.argv[1:]]))
