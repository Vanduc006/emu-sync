"""Test parser getevent: parse_line, capabilities, MT protocol B state machine.

Các mẫu dòng/khối capabilities mô phỏng output thật của `getevent -t` / `-pl`
(fixture thật từ AVD sẽ được thêm vào tests/fixtures ở M2).
"""

from pathlib import Path

from emu_sync.capture.events import KeyEvent, ScrollEvent, TouchEvent
from emu_sync.capture.getevent import MtParser, parse_capabilities, parse_line

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_line_with_timestamp_and_device():
    assert parse_line("[   123.456789] /dev/input/event2: 0003 0035 00000230") == (
        2,
        0x03,
        0x35,
        0x230,
    )


def test_parse_line_without_device():
    assert parse_line("0003 0039 ffffffff") == (None, 0x03, 0x39, -1)


def test_parse_line_garbage():
    assert parse_line("could not get driver version for /dev/input/event0") is None
    assert parse_line("") is None


CAPS_SAMPLE = """add device 1: /dev/input/event1
  name:     "qwerty2"
  events:
    KEY (0001): 0001  0002  0003  001e  001f
add device 2: /dev/input/event2
  name:     "multitouch"
  events:
    ABS (0003): 002f  : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                0035  : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
                0036  : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
                0039  : value 0, min 0, max 65535, fuzz 0, flat 0, resolution 0
add device 3: /dev/input/event3
  name:     "mouse"
  events:
    REL (0002): 0000  0001  0006  0008
    KEY (0001): 0110  0111
"""


def test_parse_capabilities():
    devs = parse_capabilities(CAPS_SAMPLE)
    assert [d.path for d in devs] == [
        "/dev/input/event1",
        "/dev/input/event2",
        "/dev/input/event3",
    ]
    assert devs[0].name == "qwerty2" and devs[0].is_keyboard
    assert devs[1].is_touch
    assert devs[1].abs_ranges[0x35] == (0, 32767)
    assert devs[1].abs_ranges[0x2F] == (0, 9)
    assert devs[2].has_wheel
    assert not devs[2].is_keyboard  # chỉ có BTN_*, không có KEY_A


def _seq(parser: MtParser, rows):
    events = []
    for t, c, v in rows:
        events.extend(parser.feed(t, c, v))
    return events


def test_mt_down_move_up():
    p = MtParser((0, 32767), (0, 32767))
    events = _seq(
        p,
        [(3, 0x2F, 0), (3, 0x39, 7), (3, 0x35, 16384), (3, 0x36, 8192), (0, 0, 0)],
    )
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, TouchEvent)
    assert ev.action == "down" and ev.slot == 0
    assert abs(ev.nx - 0.5) < 1e-3
    assert abs(ev.ny - 0.25) < 1e-3

    events = _seq(p, [(3, 0x35, 24576), (0, 0, 0)])
    assert len(events) == 1 and events[0].action == "move"
    assert abs(events[0].nx - 0.75) < 1e-3

    events = _seq(p, [(3, 0x39, -1), (0, 0, 0)])
    assert len(events) == 1 and events[0].action == "up"


def test_mt_two_slots():
    p = MtParser((0, 1000), (0, 1000))
    events = _seq(
        p,
        [
            (3, 0x2F, 0),
            (3, 0x39, 1),
            (3, 0x35, 100),
            (3, 0x36, 100),
            (3, 0x2F, 1),
            (3, 0x39, 2),
            (3, 0x35, 900),
            (3, 0x36, 900),
            (0, 0, 0),
        ],
    )
    assert {e.slot for e in events} == {0, 1}
    assert all(e.action == "down" for e in events)
    by_slot = {e.slot: e for e in events}
    assert abs(by_slot[1].nx - 0.9) < 1e-3


def test_wheel():
    p = MtParser((0, 100), (0, 100))
    events = _seq(p, [(2, 8, -1), (0, 0, 0)])
    assert len(events) == 1
    assert isinstance(events[0], ScrollEvent)
    assert events[0].vscroll == -1


def test_keys():
    p = MtParser((0, 100), (0, 100))
    events = _seq(p, [(1, 28, 1), (0, 0, 0), (1, 28, 0), (0, 0, 0)])
    assert [e.action for e in events] == ["down", "up"]
    assert all(isinstance(e, KeyEvent) and e.keycode == 28 for e in events)


# ---------------------------------------------------------------------------
# Fixtures thật thu từ AVD (xem tests/fixtures/)
# ---------------------------------------------------------------------------


def test_caps_fixture_numeric_avd():
    """`getevent -p` trên AVD (android-35, arm64) — mã hex dạng số."""
    devs = parse_capabilities((FIXTURES / "caps_avd_numeric.txt").read_text())
    touch = next(d for d in devs if d.is_touch)
    assert touch.name == "virtio_input_multi_touch_1"
    assert touch.abs_ranges[0x35] == (0, 32767)
    assert touch.abs_ranges[0x36] == (0, 32767)
    assert touch.abs_ranges[0x2F] == (0, 10)
    assert touch.device_number == 1


def test_caps_fixture_labeled_avd():
    """Cùng AVD nhưng chạy `getevent -pl` — label thay cho mã hex."""
    devs = parse_capabilities((FIXTURES / "caps_avd_labeled.txt").read_text())
    touch = next(d for d in devs if d.is_touch)
    assert touch.name == "virtio_input_multi_touch_1"
    assert touch.abs_ranges[0x35] == (0, 32767)
    assert touch.abs_ranges[0x36] == (0, 32767)


def test_real_event_lines_from_avd():
    """Vài dòng thật thu từ console `event mouse` trên AVD."""
    rows = [
        "[     149.834375] /dev/input/event1: 0003 0039 00000000",
        "[     149.834375] /dev/input/event1: 0003 0035 00003fff",
        "[     149.834375] /dev/input/event1: 0003 0036 00000fff",
        "[     149.834375] /dev/input/event1: 0000 0000 00000000",
        "[     149.985402] /dev/input/event1: 0003 0039 ffffffff",
        "[     149.985402] /dev/input/event1: 0000 0000 00000000",
    ]
    p = MtParser((0, 32767), (0, 32767))
    events = []
    for line in rows:
        parsed = parse_line(line)
        assert parsed is not None
        dev, t, c, v = parsed
        assert dev == 1
        events.extend(p.feed(t, c, v))
    assert [e.action for e in events] == ["down", "up"]
    assert abs(events[0].nx - 0.5) < 1e-3
    assert abs(events[0].ny - 0.125) < 1e-3


def test_position_sticky_when_emulator_omits_position():
    """Emulator bỏ qua POSITION khi con trỏ không di chuyển (bug thực tế trên AVD):
    tap sau đó chỉ có TRACKING_ID + SYN → phải kế thừa vị trí cuối, không được về (0,0).
    """
    p = MtParser((0, 100), (0, 100))
    _seq(p, [(3, 0x39, 1), (3, 0x35, 50), (3, 0x36, 25), (0, 0, 0), (3, 0x39, -1), (0, 0, 0)])
    events = _seq(p, [(3, 0x39, 2), (0, 0, 0)])
    assert len(events) == 1
    assert events[0].action == "down"
    assert abs(events[0].nx - 0.5) < 1e-6
    assert abs(events[0].ny - 0.25) < 1e-6


def test_no_position_at_all_defaults_zero():
    p = MtParser((0, 100), (0, 100))
    events = _seq(p, [(3, 0x39, 1), (0, 0, 0)])
    assert len(events) == 1
    assert events[0].nx == 0.0 and events[0].ny == 0.0


def test_key_modifier_metastate():
    """Shift giữ → metastate của các key sau phải kèm AMETA_SHIFT_ON."""
    from emu_sync.scrcpy import const as C

    p = MtParser((0, 100), (0, 100))
    events = _seq(p, [(1, 42, 1), (0, 0, 0)])  # KEY_LEFTSHIFT down
    assert events[0].keycode == 42
    assert events[0].metastate & C.AMETA_SHIFT_ON

    events = _seq(p, [(1, 30, 1), (0, 0, 0)])  # KEY_A down khi đang giữ shift
    assert events[0].metastate & C.AMETA_SHIFT_ON

    events = _seq(p, [(1, 42, 0), (0, 0, 0)])  # nhả shift
    assert not (events[0].metastate & C.AMETA_SHIFT_ON)
