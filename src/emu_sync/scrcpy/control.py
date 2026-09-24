"""Serialize control message gửi tới scrcpy-server — big-endian toàn bộ.

Byte layout khớp `app/tests/test_control_msg_serialize.c` của scrcpy v4.1;
các vector trong tests/test_control_protocol.py lấy nguyên từ file đó.
"""

from __future__ import annotations

import struct

from . import const as C


def _pack(fmt: str, *values) -> bytes:
    return struct.pack(">" + fmt, *values)


def inject_keycode(action: int, keycode: int, repeat: int = 0, metastate: int = 0) -> bytes:
    """14 bytes: type, action, keycode u32, repeat u32, metastate u32."""
    return _pack("BBIII", C.TYPE_INJECT_KEYCODE, action, keycode, repeat, metastate)


def inject_text(text: str) -> bytes:
    """1 + 4 + len(utf-8) bytes; tối đa 300 bytes payload."""
    payload = text.encode("utf-8")[:300]
    return _pack("BI", C.TYPE_INJECT_TEXT, len(payload)) + payload


def _u16fp(pressure: float) -> int:
    """float 0..1 → u16 fixed-point (1.0 → 0xFFFF)."""
    return max(0, min(0xFFFF, int(pressure * 0x10000)))


def _i16fp(value: float) -> int:
    """float -1..1 → i16 fixed-point (1.0 → 0x7FFF)."""
    return max(-0x8000, min(0x7FFF, int(value * 32768)))


def inject_touch(
    action: int,
    x: int,
    y: int,
    screen_w: int,
    screen_h: int,
    pointer_id: int = 0,
    pressure: float = 1.0,
    action_button: int = 0,
    buttons: int = 0,
) -> bytes:
    """32 bytes touch event.

    `x, y` theo hệ toạ độ của `screen_w x screen_h` (control-only mode: pixel
    thiết bị của máy nhận — xem plan §4.4).
    """
    return _pack(
        "BBQIIHHHII",
        C.TYPE_INJECT_TOUCH_EVENT,
        action,
        pointer_id,
        x,
        y,
        screen_w,
        screen_h,
        _u16fp(pressure),
        action_button,
        buttons,
    )


def inject_scroll(
    x: int,
    y: int,
    screen_w: int,
    screen_h: int,
    hscroll: float = 0.0,
    vscroll: float = 0.0,
    buttons: int = 0,
) -> bytes:
    """21 bytes scroll event.

    `hscroll/vscroll` nhận giá trị trong [-16, 16]; serialize = normalize /16,
    clamp [-1, 1], i16 fixed-point (scrcpy quy ước).
    """
    h_norm = max(-1.0, min(1.0, hscroll / 16))
    v_norm = max(-1.0, min(1.0, vscroll / 16))
    return _pack(
        "BIIHHhhI",
        C.TYPE_INJECT_SCROLL_EVENT,
        x,
        y,
        screen_w,
        screen_h,
        _i16fp(h_norm),
        _i16fp(v_norm),
        buttons,
    )


def back_or_screen_on(action: int) -> bytes:
    """2 bytes."""
    return _pack("BB", C.TYPE_BACK_OR_SCREEN_ON, action)


def empty(msg_type: int) -> bytes:
    """Message 1 byte không có payload (collapse_panels, rotate_device, ...)."""
    return _pack("B", msg_type)


def set_display_power(on: bool) -> bytes:
    return _pack("BB", C.TYPE_SET_DISPLAY_POWER, 1 if on else 0)
