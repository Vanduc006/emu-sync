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


def test_touch_maps_to_each_target_size():
    """Máy nhận bị resize (tỉ lệ khác) → toạ độ vẫn được nhân theo kích thước riêng."""
    engine = SyncEngine({})
    event = TouchEvent(action="down", slot=0, nx=0.25, ny=0.5)

    assert engine.serialize(event, 1080, 2400) == control.inject_touch(
        C.ACTION_DOWN, 270, 1200, 1080, 2400, pointer_id=0
    )
    assert engine.serialize(event, 720, 1600) == control.inject_touch(
        C.ACTION_DOWN, 180, 800, 720, 1600, pointer_id=0
    )
    assert engine.serialize(event, 1920, 1080) == control.inject_touch(
        C.ACTION_DOWN, 480, 540, 1920, 1080, pointer_id=0
    )


def test_touch_clamped_at_edges_of_smaller_screen():
    engine = SyncEngine({})
    buf = engine.serialize(TouchEvent(action="up", slot=0, nx=1.0, ny=1.0), 720, 1600)
    assert buf == control.inject_touch(C.ACTION_UP, 719, 1599, 720, 1600, pointer_id=0)


class _FakeSession:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def send(self, message: bytes) -> None:
        self.sent.append(message)


def test_fanout_sends_scaled_coordinates_to_each_machine():
    """1 event → nhiều máy, mỗi máy nhận toạ độ theo size của chính nó (1080×2400 vs 720×1600)."""
    big, small = _FakeSession(), _FakeSession()
    engine = SyncEngine(
        {
            "emulator-5554": (big, (1080, 2400)),
            "emulator-5556": (small, (720, 1600)),
        }
    )
    engine.handle(TouchEvent(action="down", slot=0, nx=0.5, ny=0.5))

    assert big.sent == [control.inject_touch(C.ACTION_DOWN, 540, 1200, 1080, 2400, pointer_id=0)]
    assert small.sent == [control.inject_touch(C.ACTION_DOWN, 360, 800, 720, 1600, pointer_id=0)]
    assert engine.event_count == 1


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
