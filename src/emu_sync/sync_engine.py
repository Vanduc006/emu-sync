"""Sync engine: event từ master → serialize riêng cho từng target → bơm qua control socket.

Chuẩn hoá toạ độ: event mang toạ độ 0..1 của master; mỗi target nhân với
kích thước hiển thị riêng của nó (control-only mode → toạ độ raw pixel thiết bị).
"""

from __future__ import annotations

import logging
import time
from collections import deque

from . import config
from .capture.events import InputEvent, KeyEvent, ScrollEvent, TouchEvent
from .keymap import linux_to_android
from .scrcpy import const as C
from .scrcpy import control
from .scrcpy.session import ControlSession

log = logging.getLogger(__name__)

_ACTION = {"down": C.ACTION_DOWN, "move": C.ACTION_MOVE, "up": C.ACTION_UP}
_KEY_ACTION = {"down": C.KEY_ACTION_DOWN, "up": C.KEY_ACTION_UP}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, int(round(pct / 100 * (len(ordered) - 1)))))
    return ordered[k]


class SyncEngine:
    """Nhận event đã chuẩn hoá từ master, bơm cho các target đang bật sync."""

    def __init__(self, targets: dict[str, tuple[ControlSession, tuple[int, int]]]):
        # serial → (session, (width, height))
        self._targets = dict(targets)
        self._latency_ms: deque[float] = deque(maxlen=config.LATENCY_WINDOW)
        self.event_count = 0
        self.dropped_serialize = 0
        # Phím của hotkey (linux keycode) — bỏ qua khi kèm Ctrl+Alt để không gõ vào guest
        self.suppress_keycode: int | None = None

    # ----- target management (M3 sẽ nối vào toggle) --------------------
    def set_targets(self, targets: dict[str, tuple[ControlSession, tuple[int, int]]]) -> None:
        self._targets = dict(targets)

    @property
    def target_serials(self) -> list[str]:
        return list(self._targets)

    def update_size(self, serial: str, size: tuple[int, int]) -> None:
        session, _old = self._targets[serial]
        self._targets[serial] = (session, size)

    # ----- xử lý event ---------------------------------------------------
    def handle(self, event: InputEvent) -> None:
        t0 = time.monotonic()
        produced = False
        for session, (w, h) in self._targets.values():
            message = self.serialize(event, w, h)
            if message is None:
                continue
            try:
                session.send(message)
            except RuntimeError:
                # session vừa bị đóng (đổi master/tắt sync) — bỏ qua event này
                continue
            produced = True
        log.debug("event %r → %d target(s)", event, len(self._targets))
        if not produced:
            self.dropped_serialize += 1
        self._latency_ms.append((time.monotonic() - t0) * 1000.0)
        self.event_count += 1

    def serialize(self, event: InputEvent, w: int, h: int) -> bytes | None:
        """Serialize event cho 1 target có kích thước hiển thị w×h (pixel)."""
        if isinstance(event, TouchEvent):
            x = min(w - 1, max(0, round(event.nx * w)))
            y = min(h - 1, max(0, round(event.ny * h)))
            return control.inject_touch(
                _ACTION[event.action], x, y, w, h, pointer_id=event.slot
            )
        if isinstance(event, ScrollEvent):
            x = min(w - 1, max(0, round(event.nx * w)))
            y = min(h - 1, max(0, round(event.ny * h)))
            k = config.SCROLL_UNITS_PER_TICK * config.SCROLL_VSCROLL_SIGN
            return control.inject_scroll(
                x, y, w, h, hscroll=event.hscroll * config.SCROLL_UNITS_PER_TICK, vscroll=event.vscroll * k
            )
        if isinstance(event, KeyEvent):
            if self._is_hotkey_keystroke(event):
                return None
            akey = linux_to_android(event.keycode)
            if akey is None:
                return None
            return control.inject_keycode(_KEY_ACTION[event.action], akey, metastate=event.metastate)
        return None

    def _is_hotkey_keystroke(self, event: KeyEvent) -> bool:
        """True nếu đây là phím hotkey (Ctrl+Alt+P) — không mirror vào máy nhận."""
        if self.suppress_keycode is None or event.keycode != self.suppress_keycode:
            return False
        combo = C.AMETA_CTRL_ON | C.AMETA_ALT_ON
        return (event.metastate & combo) == combo

    # ----- thống kê ------------------------------------------------------
    def latency_stats(self) -> tuple[int, float, float]:
        """(số event, p50 ms, p95 ms) — đo từ lúc nhận event đến khi enqueue xong."""
        values = list(self._latency_ms)
        return self.event_count, _percentile(values, 50), _percentile(values, 95)
