"""Model event chuẩn hoá (toạ độ 0..1 — độc lập resolution giữa các máy)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Union


@dataclass(frozen=True)
class TouchEvent:
    action: str  # "down" | "move" | "up"
    slot: int  # slot của MT protocol B → dùng làm pointer id
    nx: float  # 0..1
    ny: float
    ts: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class ScrollEvent:
    nx: float
    ny: float
    hscroll: float  # số tick (REL_HWHEEL)
    vscroll: float  # số tick (REL_WHEEL)
    ts: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class KeyEvent:
    action: str  # "down" | "up"
    keycode: int  # linux keycode
    metastate: int = 0  # AMETA_* (shift/ctrl/alt/meta/caps đang giữ)
    ts: float = field(default_factory=time.monotonic)


InputEvent = Union[TouchEvent, ScrollEvent, KeyEvent]
