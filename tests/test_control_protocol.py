"""Test byte-exact cho control protocol.

Các vector lấy nguyên từ `app/tests/test_control_msg_serialize.c` của scrcpy
(nguồn chuẩn duy nhất cho layout) — nếu test này đỏ thì client của ta sai.
"""

from emu_sync.scrcpy import const as C
from emu_sync.scrcpy import control


def test_inject_keycode_enter():
    buf = control.inject_keycode(
        action=C.KEY_ACTION_UP,
        keycode=C.AKEYCODE_ENTER,
        repeat=5,
        metastate=0x41,  # AMETA_SHIFT_ON | AMETA_SHIFT_LEFT_ON
    )
    assert buf == bytes(
        [
            0,
            0x01,
            0x00, 0x00, 0x00, 0x42,
            0x00, 0x00, 0x00, 0x05,
            0x00, 0x00, 0x00, 0x41,
        ]
    )
    assert len(buf) == 14


def test_inject_text():
    buf = control.inject_text("hello, world!")
    assert buf == bytes([1, 0x00, 0x00, 0x00, 0x0D]) + b"hello, world!"
    assert len(buf) == 18


def test_inject_touch_down():
    buf = control.inject_touch(
        action=C.ACTION_DOWN,
        pointer_id=0x1234567887654321,
        x=100,
        y=200,
        screen_w=1080,
        screen_h=1920,
        pressure=1.0,
        action_button=C.BUTTON_PRIMARY,
        buttons=C.BUTTON_PRIMARY,
    )
    assert buf == bytes(
        [
            2,
            0x00,
            0x12, 0x34, 0x56, 0x78, 0x87, 0x65, 0x43, 0x21,
            0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0xC8,
            0x04, 0x38, 0x07, 0x80,
            0xFF, 0xFF,
            0x00, 0x00, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x01,
        ]
    )
    assert len(buf) == 32


def test_inject_scroll():
    buf = control.inject_scroll(
        x=260,
        y=1026,
        screen_w=1080,
        screen_h=1920,
        hscroll=16,
        vscroll=-16,
        buttons=1,
    )
    assert buf == bytes(
        [
            3,
            0x00, 0x00, 0x01, 0x04, 0x00, 0x00, 0x04, 0x02,
            0x04, 0x38, 0x07, 0x80,
            0x7F, 0xFF,
            0x80, 0x00,
            0x00, 0x00, 0x00, 0x01,
        ]
    )
    assert len(buf) == 21


def test_back_or_screen_on():
    assert control.back_or_screen_on(C.KEY_ACTION_UP) == bytes([4, 0x01])


def test_empty_messages():
    assert control.empty(C.TYPE_ROTATE_DEVICE) == bytes([11])
    assert control.empty(C.TYPE_COLLAPSE_PANELS) == bytes([7])


def test_set_display_power():
    assert control.set_display_power(True) == bytes([10, 1])
    assert control.set_display_power(False) == bytes([10, 0])
