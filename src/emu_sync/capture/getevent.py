"""Đọc & parse `getevent` trên thiết bị master.

- `discover_devices()`: parse `getevent -pl` → capabilities (touch / wheel / keyboard).
- `MtParser`: state machine cho MT protocol B → InputEvent chuẩn hoá 0..1.
- `GeteventSource`: chạy `adb shell -t getevent -t <dev...>` và đẩy event qua callback.

Dòng output (raw, không -l) có dạng:
    [   842.585818] /dev/input/event2: 0003 0035 00000230
(timestamp + device path là tuỳ chọn — parser chấp nhận cả khi thiếu)
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable

from adbutils import AdbDevice

from .. import adb as adbmod
from .events import InputEvent, KeyEvent, ScrollEvent, TouchEvent

log = logging.getLogger(__name__)

# Linux input event codes (include/uapi/linux/input-event-codes.h)
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

SYN_REPORT = 0x00

ABS_MT_SLOT = 0x2F
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39

REL_HWHEEL = 0x06
REL_WHEEL = 0x08

_KEYCODE_A = 30  # KEY_A — dùng làm heuristic nhận diện bàn phím

# Linux keycode của các phím bổ trợ (theo dõi để tính metastate)
_LINUX_MODIFIERS = {
    29: "ctrl",   # KEY_LEFTCTRL
    97: "ctrl",   # KEY_RIGHTCTRL
    42: "shift",  # KEY_LEFTSHIFT
    54: "shift",  # KEY_RIGHTSHIFT
    56: "alt",    # KEY_LEFTALT
    100: "alt",   # KEY_RIGHTALT
    125: "meta",  # KEY_LEFTMETA
    126: "meta",  # KEY_RIGHTMETA
    58: "caps",   # KEY_CAPSLOCK
}


# --------------------------------------------------------------------------
# Parsing dòng output
# --------------------------------------------------------------------------

_DEV_RE = re.compile(r"/dev/input/event(\d+)")
_TS_PREFIX_RE = re.compile(r"^\[[^\]]*\]\s*")
_TRIPLE_RE = re.compile(r"^([0-9a-fA-F]{4})\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]{8})$")


def _to_signed32(value: int) -> int:
    return value - 0x100000000 if value >= 0x80000000 else value


def parse_line(line: str) -> tuple[int | None, int, int, int] | None:
    """Parse 1 dòng getevent raw → (device_number, type, code, value) hoặc None.

    Chấp nhận: `[ts] /dev/input/eventN: TTTT CCCC VVVVVVVV` (device/timestamp tuỳ chọn).
    """
    s = line.rstrip("\r\n")
    if not s:
        return None
    m = _TS_PREFIX_RE.match(s)
    if m:
        s = s[m.end():]
    dev = None
    m = _DEV_RE.match(s)
    if m:
        dev = int(m.group(1))
        s = s[m.end():]
    s = s.lstrip(": ").strip()
    m = _TRIPLE_RE.match(s)
    if not m:
        return None
    type_code = int(m.group(1), 16)
    code = int(m.group(2), 16)
    value = _to_signed32(int(m.group(3), 16))
    return dev, type_code, code, value


# --------------------------------------------------------------------------
# Capabilities (getevent -pl)
# --------------------------------------------------------------------------

_DEV_BLOCK_RE = re.compile(r"add device \d+:\s+(/dev/input/event\d+)")
_NAME_RE = re.compile(r'name:\s*"([^"]*)"')
_SECTION_RE = re.compile(r"^\s+([A-Z]+)\s+\((\w+)\):\s*(.*)$")
# mỗi entry ABS có dạng "0035  : value 0, min 0, max 32767, ..." (numeric)
# hoặc "ABS_MT_POSITION_X : value ..." (khi chạy với -l)
_ABS_RANGE_RE = re.compile(
    r"((?:[0-9a-fA-F]{4}|[A-Z][A-Z0-9_]*))\s*:\s*value -?\d+,\s*min (-?\d+),\s*max (-?\d+)"
)
_TOKEN_RE = re.compile(r"[0-9a-fA-F]{4}|[A-Z][A-Z0-9_]+")

# Map tên → mã cho các code ta quan tâm (dùng khi output ở dạng label, vd `getevent -pl`)
_ABS_NAMES = {
    "ABS_X": 0x00,
    "ABS_Y": 0x01,
    "ABS_MT_SLOT": 0x2F,
    "ABS_MT_POSITION_X": 0x35,
    "ABS_MT_POSITION_Y": 0x36,
    "ABS_MT_TRACKING_ID": 0x39,
}
_REL_NAMES = {"REL_HWHEEL": 0x06, "REL_WHEEL": 0x08}
_KEY_NAMES = {"KEY_A": 30}


@dataclass
class InputDeviceCaps:
    path: str
    name: str = ""
    abs_ranges: dict[int, tuple[int, int]] = field(default_factory=dict)
    rel: set[int] = field(default_factory=set)
    keys: set[int] = field(default_factory=set)

    @property
    def device_number(self) -> int:
        return int(self.path.rsplit("event", 1)[1])

    @property
    def is_touch(self) -> bool:
        return ABS_MT_POSITION_X in self.abs_ranges and ABS_MT_POSITION_Y in self.abs_ranges

    @property
    def has_wheel(self) -> bool:
        return REL_WHEEL in self.rel or REL_HWHEEL in self.rel

    @property
    def is_keyboard(self) -> bool:
        return _KEYCODE_A in self.keys


def _resolve_code(token: str, names: dict[str, int]) -> int | None:
    stripped = token.strip()
    if re.fullmatch(r"[0-9a-fA-F]{4}", stripped):
        return int(stripped, 16)
    return names.get(stripped)


def _feed_cap_section(device: InputDeviceCaps, kind: str, payload: str) -> None:
    if kind == "ABS":
        for code_token, vmin, vmax in _ABS_RANGE_RE.findall(payload):
            code = _resolve_code(code_token, _ABS_NAMES)
            if code is not None:
                device.abs_ranges[code] = (int(vmin), int(vmax))
    elif kind == "REL":
        for token in _TOKEN_RE.findall(payload):
            code = _resolve_code(token, _REL_NAMES)
            if code is not None:
                device.rel.add(code)
    elif kind == "KEY":
        for token in _TOKEN_RE.findall(payload):
            code = _resolve_code(token, _KEY_NAMES)
            if code is not None:
                device.keys.add(code)


def parse_capabilities(text: str) -> list[InputDeviceCaps]:
    """Parse output của `getevent -pl` (kể cả các dòng continuation của ABS/REL/KEY)."""
    devices: list[InputDeviceCaps] = []
    current: InputDeviceCaps | None = None
    section: str | None = None
    for line in text.splitlines():
        m = _DEV_BLOCK_RE.search(line)
        if m:
            current = InputDeviceCaps(path=m.group(1))
            devices.append(current)
            section = None
            continue
        if current is None:
            continue
        m = _NAME_RE.search(line)
        if m:
            current.name = m.group(1)
            continue
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1)
            _feed_cap_section(current, section, m.group(3))
            continue
        if section is not None:
            # dòng continuation: chỉ chứa mã hex (ABS còn kèm range)
            _feed_cap_section(current, section, line)
    return devices


def discover_devices(device: AdbDevice) -> list[InputDeviceCaps]:
    # Dùng `-p` (không `-l`) để nhận mã hex dạng số; parser vẫn hiểu cả dạng label.
    text = device.shell("getevent -p")
    return parse_capabilities(text)


# --------------------------------------------------------------------------
# MT protocol B state machine
# --------------------------------------------------------------------------


@dataclass
class _Slot:
    tracking_id: int | None = None
    x: int | None = None  # None = chưa từng nhận POSITION trong session này
    y: int | None = None
    active: bool = False  # đã phát "down" chưa
    lifted: bool = False
    emitted_x: float = -1.0
    emitted_y: float = -1.0


class MtParser:
    """Feed từng (type, code, value) → danh sách InputEvent đã chuẩn hoá."""

    def __init__(self, x_range: tuple[int, int], y_range: tuple[int, int]):
        self.x_min, self.x_max = x_range
        self.y_min, self.y_max = y_range
        self._cur_slot = 0
        self._slots: dict[int, _Slot] = {}
        self._wheel_h = 0.0
        self._wheel_v = 0.0
        self._cursor: tuple[float, float] = (0.5, 0.5)  # vị trí con trỏ gần nhất (0..1)
        # Vị trí raw cuối cùng từng thấy — emulator BỎ QUA POSITION events khi con trỏ
        # không di chuyển, nên khi có TRACKING_ID mới ta phải kế thừa vị trí này.
        self._last_x: int | None = None
        self._last_y: int | None = None
        # Trạng thái phím bổ trợ (để gắn metastate cho key event)
        self._mods = {"shift": False, "ctrl": False, "alt": False, "meta": False, "caps": False}

    # -- helpers --
    def _metastate(self) -> int:
        from ..scrcpy import const as SC

        state = 0
        if self._mods["shift"]:
            state |= SC.AMETA_SHIFT_ON
        if self._mods["alt"]:
            state |= SC.AMETA_ALT_ON
        if self._mods["ctrl"]:
            state |= SC.AMETA_CTRL_ON
        if self._mods["meta"]:
            state |= SC.AMETA_META_ON
        if self._mods["caps"]:
            state |= SC.AMETA_CAPS_LOCK_ON
        return state

    def _norm_x(self, raw: int) -> float:
        span = self.x_max - self.x_min
        return 0.0 if span <= 0 else min(1.0, max(0.0, (raw - self.x_min) / span))

    def _norm_y(self, raw: int) -> float:
        span = self.y_max - self.y_min
        return 0.0 if span <= 0 else min(1.0, max(0.0, (raw - self.y_min) / span))

    # -- main --
    def feed(self, type_code: int, code: int, value: int) -> list[InputEvent]:
        out: list[InputEvent] = []

        if type_code == EV_ABS:
            if code == ABS_MT_SLOT:
                self._cur_slot = value
                return out
            slot = self._slots.setdefault(self._cur_slot, _Slot())
            if code == ABS_MT_TRACKING_ID:
                if value in (-1, 0xFFFFFFFF):
                    slot.lifted = True
                else:
                    slot.tracking_id = value
                    slot.active = False
                    slot.lifted = False
            elif code == ABS_MT_POSITION_X:
                slot.x = value
                self._last_x = value
                self._cursor = (self._norm_x(value), self._cursor[1])
            elif code == ABS_MT_POSITION_Y:
                slot.y = value
                self._last_y = value
                self._cursor = (self._cursor[0], self._norm_y(value))
        elif type_code == EV_REL:
            if code == REL_WHEEL:
                self._wheel_v += value
            elif code == REL_HWHEEL:
                self._wheel_h += value
        elif type_code == EV_KEY:
            if code < 0x100:  # KEY_* (bàn phím); BTN_* (>= 0x100) bỏ qua
                mod = _LINUX_MODIFIERS.get(code)
                if mod == "caps":
                    if value == 1:
                        self._mods["caps"] = not self._mods["caps"]
                elif mod is not None:
                    if value in (1, 2):
                        self._mods[mod] = True
                    elif value == 0:
                        self._mods[mod] = False

                if value == 1:
                    out.append(KeyEvent(action="down", keycode=code, metastate=self._metastate()))
                elif value == 0:
                    out.append(KeyEvent(action="up", keycode=code, metastate=self._metastate()))
                elif value == 2:
                    out.append(KeyEvent(action="down", keycode=code, metastate=self._metastate()))
        elif type_code == EV_SYN and code == SYN_REPORT:
            out.extend(self._flush())

        return out

    def _flush(self) -> list[InputEvent]:
        out: list[InputEvent] = []
        for slot_id in sorted(self._slots):
            slot = self._slots[slot_id]
            # Kế thừa vị trí cuối khi emulator không gửi POSITION (con trỏ đứng yên).
            raw_x = slot.x if slot.x is not None else (self._last_x if self._last_x is not None else 0)
            raw_y = slot.y if slot.y is not None else (self._last_y if self._last_y is not None else 0)
            nx, ny = self._norm_x(raw_x), self._norm_y(raw_y)
            if slot.lifted:
                if slot.active:
                    out.append(TouchEvent(action="up", slot=slot_id, nx=nx, ny=ny))
                del self._slots[slot_id]
            elif slot.tracking_id is not None and not slot.active:
                slot.active = True
                slot.emitted_x, slot.emitted_y = nx, ny
                out.append(TouchEvent(action="down", slot=slot_id, nx=nx, ny=ny))
            elif slot.active and (nx != slot.emitted_x or ny != slot.emitted_y):
                slot.emitted_x, slot.emitted_y = nx, ny
                out.append(TouchEvent(action="move", slot=slot_id, nx=nx, ny=ny))

        if self._wheel_v or self._wheel_h:
            out.append(
                ScrollEvent(
                    nx=self._cursor[0],
                    ny=self._cursor[1],
                    hscroll=self._wheel_h,
                    vscroll=self._wheel_v,
                )
            )
            self._wheel_h = 0.0
            self._wheel_v = 0.0
        return out


# --------------------------------------------------------------------------
# Nguồn streaming
# --------------------------------------------------------------------------


class GeteventSource:
    """Chạy `adb shell -t getevent -t <devices>` và phát event qua callback."""

    def __init__(self, device: AdbDevice, on_event: Callable[[InputEvent], None]):
        self.device = device
        self.serial = device.serial
        self._on_event = on_event
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._watched: set[int] = set()
        self.parser: MtParser | None = None
        self.touch_device: InputDeviceCaps | None = None
        self.wheel_device: InputDeviceCaps | None = None
        self.keyboard_device: InputDeviceCaps | None = None

    def start(self) -> None:
        caps = discover_devices(self.device)
        if not caps:
            raise RuntimeError(f"{self.serial}: không đọc được capabilities từ `getevent -pl`")

        touch = next((c for c in caps if c.is_touch), None)
        if touch is None:
            raise RuntimeError(f"{self.serial}: không tìm thấy thiết bị cảm ứng (ABS_MT_POSITION_X/Y)")
        wheel = next((c for c in caps if c.has_wheel), None)
        keyboard = next((c for c in caps if c.is_keyboard), None)

        self.touch_device = touch
        self.wheel_device = wheel
        self.keyboard_device = keyboard

        x_range = touch.abs_ranges[ABS_MT_POSITION_X]
        y_range = touch.abs_ranges[ABS_MT_POSITION_Y]
        self.parser = MtParser(x_range, y_range)

        paths = [touch.path]
        if wheel is not None and wheel.path not in paths:
            paths.append(wheel.path)
        if keyboard is not None and keyboard.path not in paths:
            paths.append(keyboard.path)
        self._watched = {int(p.rsplit("event", 1)[1]) for p in paths}

        # getevent chỉ nhận 1 device → chạy KHÔNG tham số (nghe tất cả) và lọc theo
        # device number trong _read_loop. Output qua pipe vẫn là live (đã kiểm chứng
        # trên AVD) nên không cần PTY.
        cmd = [adbmod.adb_binary(), "-s", self.serial, "shell", "getevent", "-t"]
        log.info(
            "watch %s: touch=%s(%s) wheel=%s keyboard=%s",
            self.serial,
            touch.path,
            touch.name,
            wheel.path if wheel else "-",
            keyboard.path if keyboard else "-",
        )
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **adbmod.no_window_kwargs()
        )
        self._thread = threading.Thread(target=self._read_loop, name=f"getevent-{self.serial}", daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        assert self.parser is not None
        for raw in self._proc.stdout:
            line = raw.decode("utf-8", "replace")
            parsed = parse_line(line)
            if parsed is None:
                low = line.strip().lower()
                if low and not low.startswith("["):
                    log.debug("getevent: %s", line.strip())
                continue
            dev, type_code, code, value = parsed
            if dev is not None and dev not in self._watched:
                continue
            for event in self.parser.feed(type_code, code, value):
                try:
                    self._on_event(event)
                except Exception:
                    log.exception("lỗi khi xử lý event")

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
