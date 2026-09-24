"""Điều phối runtime cho web UI: devices, master, sync flags, sessions, preview.

- Mỗi máy (trừ master) có 1 ControlSession để nhận event bơm vào.
- Master là máy đang được "nghe" (getevent) — đổi master sẽ swap session + sniff.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from collections import deque

from . import adb as adbmod
from . import config
from .capture.getevent import GeteventSource
from .scrcpy import const as C
from .scrcpy import control
from .scrcpy.session import ControlSession
from .sync_engine import SyncEngine

log = logging.getLogger(__name__)

PREVIEW_TTL = 1.5  # giây — cache ảnh preview


class SyncController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.devices: dict[str, dict] = {}
        self._sessions: dict[str, ControlSession] = {}
        self._sizes: dict[str, tuple[int, int]] = {}
        self.engine = SyncEngine({})
        self.source: GeteventSource | None = None
        self.master: str | None = None
        self.running = False
        self.paused = False  # tạm dừng đồng bộ (thao tác riêng từng máy) — phím tắt
        self.hotkey_label = ""
        self.last_error: str | None = None
        self._preview_cache: dict[str, tuple[float, bytes]] = {}
        self._preview_locks: dict[str, threading.Lock] = {}
        self._action_locks: dict[str, threading.Lock] = {}
        self._sniffs: dict[str, GeteventSource] = {}
        self._events: deque[dict] = deque(maxlen=400)
        self._event_seq = 0
        self._last_session_attempt: dict[str, float] = {}

    # ---------------- devices ----------------
    def refresh_devices(self, update_meta: bool = False) -> None:
        with self._lock:
            current = {d.serial: d for d in adbmod.list_devices()}
            for serial in list(self.devices):
                if serial not in current:
                    self._stop_session(serial)
                    self.devices.pop(serial, None)
                    self._sizes.pop(serial, None)
                    self._preview_cache.pop(serial, None)
                    if self.master == serial:
                        self.master = None
            new_serials = [serial for serial in current if serial not in self.devices]
            for serial, device in current.items():
                entry = self.devices.setdefault(
                    serial,
                    {"name": "", "sync_enabled": True, "session_state": "off", "sent": 0},
                )
                if update_meta or not entry["name"]:
                    try:
                        entry["name"] = adbmod.instance_name(device)
                    except Exception as e:
                        entry["name"] = serial
                        self.last_error = f"{serial}: {e}"
                if update_meta or serial not in self._sizes:
                    try:
                        self._sizes[serial] = adbmod.display_size(device)
                    except Exception as e:
                        self.last_error = f"{serial}: không đọc được wm size: {e}"

            if self.running:
                if self.master is None and self.devices:
                    # máy chính mất kết nối → tự chọn máy khác làm máy chính
                    self.master = next(iter(sorted(self.devices)))
                    self._stop_session(self.master)
                    self._stop_source()
                    self._start_source()
                elif self.master is None:
                    self._stop_source()
                    self.last_error = "Máy chính đã mất kết nối"
                else:
                    for serial in new_serials:
                        if serial != self.master:
                            self._start_session(serial)
                    # tự thử lại các session đang lỗi (throttle 10s) — tự chữa lành
                    now = time.monotonic()
                    for serial, entry in self.devices.items():
                        if serial == self.master or serial in self._sessions:
                            continue
                        if entry["session_state"] != "error":
                            continue
                        if now - self._last_session_attempt.get(serial, 0.0) > 10.0:
                            self._start_session(serial)
            self._recompute_targets()

    def _recompute_targets(self) -> None:
        if self.paused:
            self.engine.set_targets({})
            return
        targets = {}
        for serial, session in self._sessions.items():
            entry = self.devices.get(serial)
            if serial == self.master or entry is None or not entry["sync_enabled"]:
                continue
            if session.alive:
                targets[serial] = (session, self._sizes.get(serial, (0, 0)))
        self.engine.set_targets(targets)

    # ---------------- sessions ----------------
    def _start_session(self, serial: str) -> None:
        with self._lock:
            if serial in self._sessions:
                return
            entry = self.devices.get(serial)
            if entry is None:
                return
            session = ControlSession(adbmod.get_device(serial))
            self._last_session_attempt[serial] = time.monotonic()
            entry["session_state"] = "starting"
            try:
                session.start()
            except Exception as e:
                entry["session_state"] = "error"
                self.last_error = f"session {serial}: {e}"
                return
            self._sessions[serial] = session
            entry["session_state"] = "running"
            self._recompute_targets()

    def _stop_session(self, serial: str) -> None:
        with self._lock:
            session = self._sessions.pop(serial, None)
            if session is not None:
                session.stop()
            entry = self.devices.get(serial)
            if entry is not None:
                entry["session_state"] = "off"
            self._recompute_targets()

    def restart_session(self, serial: str) -> None:
        self._stop_session(serial)
        if self.running and serial != self.master:
            self._start_session(serial)

    # ---------------- run / master / sync ----------------
    def start(self, master: str | None = None) -> None:
        with self._lock:
            if not self.devices:
                self.refresh_devices(update_meta=True)
            if master is None:
                master = self.master or (next(iter(self.devices), None))
            if master is None or master not in self.devices:
                self.last_error = "Không có thiết bị nào để bắt đầu"
                return
            self.master = master
            for serial in self.devices:
                if serial != master:
                    self._start_session(serial)
            self._start_source()
            self.running = True

    def stop(self) -> None:
        with self._lock:
            self._stop_source()
            for serial in list(self._sniffs):
                self.set_sniff(serial, False)
            for serial in list(self._sessions):
                self._stop_session(serial)
            self.running = False

    def set_master(self, serial: str) -> None:
        with self._lock:
            if serial not in self.devices:
                raise ValueError(f"Không thấy thiết bị {serial}")
            if serial == self.master:
                return
            old_master = self.master
            self._stop_source()
            # master mới không nhận injection nữa; master cũ chuyển thành target
            self._stop_session(serial)
            self.master = serial
            if self.running and old_master is not None:
                self._start_session(old_master)
            if self.running:
                self._start_source()
            self._recompute_targets()

    def set_sync(self, serial: str, enabled: bool) -> None:
        with self._lock:
            entry = self.devices.get(serial)
            if entry is None:
                raise ValueError(f"Không thấy thiết bị {serial}")
            entry["sync_enabled"] = bool(enabled)
            self._recompute_targets()

    # ---------------- tạm dừng nhanh (phím tắt) ----------------
    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = bool(paused)
            self._recompute_targets()
            log.info("Đồng bộ %s", "TẠM DỪNG" if self.paused else "tiếp tục")

    def toggle_paused(self) -> bool:
        with self._lock:
            self.set_paused(not self.paused)
            return self.paused

    # ---------------- connect / quét cổng ----------------
    def connect(self, address: str) -> str:
        out = adbmod.connect(address)
        self.refresh_devices(update_meta=True)
        return out

    def scan_ports(self) -> list[str]:
        found = adbmod.scan_and_connect(config.EMULATOR_PORT_RANGES)
        self.refresh_devices(update_meta=True)
        return found

    # ---------------- thao tác trực tiếp trên 1 máy (CLI parity) ----------------
    def _action_lock(self, serial: str) -> threading.Lock:
        return self._action_locks.setdefault(serial, threading.Lock())

    def perform_action(self, serial: str, action: str, params: dict) -> None:
        """tap/scroll/key/back/swipe trên 1 máy — dùng session sẵn có hoặc tạo tạm."""
        device = adbmod.get_device(serial)
        size = self._sizes.get(serial)
        if size is None:
            size = self._sizes[serial] = adbmod.display_size(device)
        w, h = size
        with self._action_lock(serial):
            session = self._sessions.get(serial)
            transient = session is None
            if transient:
                session = ControlSession(device)
                session.start()
            try:
                self._dispatch_action(session, action, params, w, h)
                time.sleep(0.15)  # đợi writer gửi hết trước khi đóng session tạm
            finally:
                if transient:
                    session.stop()

    @staticmethod
    def _dispatch_action(session: ControlSession, action: str, p: dict, w: int, h: int) -> None:
        if action == "tap":
            x, y = int(p["x"]), int(p["y"])
            session.send(control.inject_touch(C.ACTION_DOWN, x, y, w, h))
            time.sleep(0.05)
            session.send(control.inject_touch(C.ACTION_UP, x, y, w, h))
        elif action == "scroll":
            x, y = int(p["x"]), int(p["y"])
            dy = float(p.get("dy", -3))
            for _ in range(max(1, int(p.get("repeat", 1)))):
                session.send(control.inject_scroll(x, y, w, h, vscroll=dy))
                time.sleep(0.05)
        elif action == "key":
            code = int(p["keycode"])
            session.send(control.inject_keycode(C.KEY_ACTION_DOWN, code))
            time.sleep(0.02)
            session.send(control.inject_keycode(C.KEY_ACTION_UP, code))
        elif action == "back":
            session.send(control.back_or_screen_on(C.KEY_ACTION_DOWN))
            time.sleep(0.02)
            session.send(control.back_or_screen_on(C.KEY_ACTION_UP))
        elif action == "text":
            session.send(control.inject_text(str(p.get("text", ""))))
        elif action == "swipe":
            x1, y1 = int(p["x1"]), int(p["y1"])
            x2, y2 = int(p["x2"]), int(p["y2"])
            steps = max(2, int(p.get("steps", 12)))
            duration = float(p.get("duration", 0.25))
            session.send(control.inject_touch(C.ACTION_DOWN, x1, y1, w, h))
            for i in range(1, steps + 1):
                mx = x1 + (x2 - x1) * i // steps
                my = y1 + (y2 - y1) * i // steps
                session.send(control.inject_touch(C.ACTION_MOVE, mx, my, w, h))
                time.sleep(duration / steps)
            session.send(control.inject_touch(C.ACTION_UP, x2, y2, w, h))
        else:
            raise ValueError(f"Hành động không hỗ trợ: {action}")

    # ---------------- nghe input (sniff) ----------------
    def set_sniff(self, serial: str, enabled: bool) -> None:
        if enabled:
            if serial in self._sniffs:
                return
            device = adbmod.get_device(serial)
            source = GeteventSource(device, lambda ev, s=serial: self._record_event(s, ev))
            source.start()
            self._sniffs[serial] = source
        else:
            source = self._sniffs.pop(serial, None)
            if source is not None:
                source.stop()

    def _record_event(self, serial: str, event) -> None:
        with self._lock:
            self._event_seq += 1
            self._events.append(
                {
                    "id": self._event_seq,
                    "t": time.strftime("%H:%M:%S"),
                    "serial": serial,
                    "text": repr(event),
                }
            )

    def events(self, after: int = 0, serial: str | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            items = [
                e for e in self._events if e["id"] > after and (serial is None or e["serial"] == serial)
            ]
        return items[-limit:]

    @property
    def sniffing(self) -> list[str]:
        return list(self._sniffs)

    # ---------------- getevent source ----------------
    def _start_source(self) -> None:
        assert self.master is not None
        device = adbmod.get_device(self.master)
        self.source = GeteventSource(device, self.engine.handle)
        try:
            self.source.start()
        except Exception as e:
            self.last_error = f"getevent {self.master}: {e}"
            self.source = None

    def _stop_source(self) -> None:
        if self.source is not None:
            self.source.stop()
            self.source = None

    # ---------------- trạng thái / preview ----------------
    def state(self) -> dict:
        with self._lock:
            devices = []
            for serial, entry in sorted(self.devices.items()):
                session = self._sessions.get(serial)
                size = self._sizes.get(serial)
                devices.append(
                    {
                        "serial": serial,
                        "name": entry["name"],
                        "width": size[0] if size else None,
                        "height": size[1] if size else None,
                        "sync_enabled": entry["sync_enabled"],
                        "is_master": serial == self.master,
                        "session_state": entry["session_state"],
                        "sent": session.stats_sent if session else 0,
                        "sniffing": serial in self._sniffs,
                    }
                )
            count, p50, p95 = self.engine.latency_stats()
            return {
                "running": self.running,
                "paused": self.paused,
                "hotkey": self.hotkey_label,
                "master": self.master,
                "last_error": self.last_error,
                "stats": {"count": count, "p50_ms": p50, "p95_ms": p95},
                "devices": devices,
            }

    def preview_jpeg(self, serial: str, width: int = 360, quality: int = 70) -> bytes:
        now = time.monotonic()
        cached = self._preview_cache.get(serial)
        if cached and now - cached[0] < PREVIEW_TTL:
            return cached[1]
        lock = self._preview_locks.setdefault(serial, threading.Lock())
        with lock:
            cached = self._preview_cache.get(serial)
            now = time.monotonic()
            if cached and now - cached[0] < PREVIEW_TTL:
                return cached[1]
            image = adbmod.get_device(serial).screenshot()
            w, h = image.size
            target_h = max(1, round(h * width / w))
            image = image.convert("RGB").resize((width, target_h))
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality)
            data = buf.getvalue()
            self._preview_cache[serial] = (time.monotonic(), data)
            return data
