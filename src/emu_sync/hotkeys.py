"""Phím tắt toàn cục để bật/tắt nhanh đồng bộ (pynput) — dùng khi đang thao tác
cửa sổ giả lập, không cần chuyển sang app."""

from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)

DEFAULT_HOTKEY = "<ctrl>+<alt>+p"

_MOD_NAMES = {"<ctrl>": "Ctrl", "<alt>": "Alt", "<cmd>": "Cmd", "<shift>": "Shift", "<super>": "Win"}


def label_of(spec: str) -> str:
    """'<ctrl>+<alt>+p' → 'Ctrl+Alt+P' (để hiển thị)."""
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    return "+".join(_MOD_NAMES.get(p.lower(), p.upper()) for p in parts)


# Linux keycode cho các ký tự đơn (dùng để bỏ qua phím hotkey khi sync bàn phím)
_CHAR_TO_LINUX = {
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24, "p": 25,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38,
    "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
}


def keycode_of_spec(spec: str) -> int | None:
    """Linux keycode của phím cuối trong hotkey (vd '<ctrl>+<alt>+p' → 25)."""
    token = spec.split("+")[-1].strip().lower()
    return _CHAR_TO_LINUX.get(token)


class HotkeyManager:
    def __init__(self, spec: str, on_toggle: Callable[[], None]):
        self.spec = spec
        self.on_toggle = on_toggle
        self.ok = False
        self._listener = None

    def start(self) -> bool:
        if self.spec.lower() in ("none", "off", ""):
            return False
        try:
            from pynput import keyboard
        except ImportError:
            log.warning("Chưa cài pynput — phím tắt bị tắt (uv pip install -e '.[desktop]')")
            return False
        try:
            self._listener = keyboard.GlobalHotKeys({self.spec: self._on_trigger})
            self._listener.start()
            self.ok = True
            log.info("Phím tắt %s đã đăng ký", label_of(self.spec))
        except Exception as e:
            log.warning("Không đăng ký được phím tắt %s: %s", self.spec, e)
            self.ok = False
        return self.ok

    def _on_trigger(self) -> None:
        try:
            self.on_toggle()
        except Exception:
            log.exception("lỗi khi xử lý phím tắt")

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
