"""Bắt input từ giả lập master (qua ADB getevent) và chuẩn hoá thành event 0..1."""

from .events import InputEvent, KeyEvent, ScrollEvent, TouchEvent
from .getevent import GeteventSource, MtParser, discover_devices, parse_line

__all__ = [
    "InputEvent",
    "KeyEvent",
    "ScrollEvent",
    "TouchEvent",
    "GeteventSource",
    "MtParser",
    "discover_devices",
    "parse_line",
]
