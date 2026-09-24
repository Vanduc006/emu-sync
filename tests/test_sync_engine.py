"""Test sync engine: serialize key (metastate), chặn phím hotkey, keymap."""

from emu_sync.capture.events import KeyEvent, TouchEvent
from emu_sync.keymap import linux_to_android
from emu_sync.scrcpy import const as C
from emu_sync.scrcpy import control
from emu_sync.sync_engine import SyncEngine


def test_key_serialize_with_metastate():
    engine = SyncEngine({})
    buf = engine.serialize(KeyEvent(action="down", keycode=30, metastate=C.AMETA_SHIFT_ON), 1080, 2400)
    assert buf == control.inject_keycode(C.KEY_ACTION_DOWN, C.AKEYCODE_A, metastate=C.AMETA_SHIFT_ON)


def test_hotkey_keystroke_suppressed():
    engine = SyncEngine({})
    engine.suppress_keycode = 25  # KEY_P
    combo = C.AMETA_CTRL_ON | C.AMETA_ALT_ON
    assert engine.serialize(KeyEvent("down", 25, metastate=combo), 1080, 2400) is None
    assert engine.serialize(KeyEvent("up", 25, metastate=combo), 1080, 2400) is None
    # chữ p thường vẫn được gửi
    assert engine.serialize(KeyEvent("down", 25, metastate=0), 1080, 2400) is not None


def test_unmapped_key_returns_none():
    engine = SyncEngine({})
    assert engine.serialize(KeyEvent("down", 240, metastate=0), 1080, 2400) is None


def test_touch_serialize_unchanged():
    engine = SyncEngine({})
    buf = engine.serialize(TouchEvent(action="down", slot=0, nx=0.5, ny=0.25), 1080, 2400)
    assert buf == control.inject_touch(C.ACTION_DOWN, 540, 600, 1080, 2400, pointer_id=0)


def test_keymap_samples():
    assert linux_to_android(30) == 29  # KEY_A → AKEYCODE_A
    assert linux_to_android(31) == 47  # KEY_S → AKEYCODE_S (khác thứ tự alphabet)
    assert linux_to_android(16) == 45  # KEY_Q → AKEYCODE_Q
    assert linux_to_android(25) == 44  # KEY_P → AKEYCODE_P
    assert linux_to_android(44) == 54  # KEY_Z → AKEYCODE_Z
    assert linux_to_android(42) == C.AKEYCODE_SHIFT_LEFT
    assert linux_to_android(28) == C.AKEYCODE_ENTER
    assert linux_to_android(14) == C.AKEYCODE_DEL
    assert linux_to_android(52) == 56  # KEY_DOT → PERIOD
    assert linux_to_android(240) is None
