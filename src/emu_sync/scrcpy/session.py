"""Control-only scrcpy session — kênh bơm input vào một thiết bị Android.

Protocol (pin scrcpy v4.1, đã verify từ source):
- Host listen TCP; `adb reverse localabstract:scrcpy_%08x tcp:<port>` để server connect về.
- Server chạy qua app_process với `video=false audio=false control=true`.
- Control-only ⇒ control socket là "first socket" ⇒ server gửi **64 byte device meta**
  trước khi nhận message.
- Không có video ⇒ server inject toạ độ RAW theo pixel thiết bị (không map/drop —
  xem Controller.getEventPointAndDisplayId trong source scrcpy).
"""

from __future__ import annotations

import logging
import queue
import random
import socket
import subprocess
import threading
from pathlib import Path

from adbutils import AdbDevice

from .. import adb as adbmod
from . import const as C

log = logging.getLogger(__name__)

_SERVER_CMD = (
    "CLASSPATH={jar} app_process / com.genymobile.scrcpy.Server {version} "
    "scid={scid} log_level=info video=false audio=false control=true "
    "cleanup=true power_on=true clipboard_autosync=false"
)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks: list[bytes] = []
    remaining = n
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError(f"socket đóng khi còn {remaining} byte chưa đọc")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class ControlSession:
    """Một phiên control-only tới 1 thiết bị."""

    def __init__(self, device: AdbDevice, jar_path: Path | None = None, spawn_timeout: float = 25.0):
        self.device = device
        self.serial = device.serial
        self.scid = random.getrandbits(31)
        self.jar_path = jar_path
        self.spawn_timeout = spawn_timeout
        self.device_name = ""
        self.stats_sent = 0
        self._listener: socket.socket | None = None
        self._sock: socket.socket | None = None
        self._proc: subprocess.Popen | None = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=8192)
        self._writer: threading.Thread | None = None
        self._closed = False
        self._logfile = None

    def socket_name(self) -> str:
        return f"{C.SOCKET_NAME_PREFIX}_{self.scid:08x}"

    @property
    def alive(self) -> bool:
        return not self._closed and self._sock is not None

    # ----- lifecycle ---------------------------------------------------
    def start(self) -> None:
        adbmod.push_server(self.device, self.jar_path)

        # QUAN TRỌNG: phải là listener dual-stack (IPv6 + IPv4-mapped). adb reverse
        # kết nối tới localhost theo cách không tới được listener IPv4-only
        # (đã kiểm chứng thực tế trên macOS + adb 37: IPv4-only => không accept).
        try:
            listener = socket.create_server(("::", 0), family=socket.AF_INET6, dualstack_ipv6=True)
        except (OSError, ValueError):
            listener = socket.create_server(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        self.device.reverse(f"localabstract:{self.socket_name()}", f"tcp:{port}")

        cmd = _SERVER_CMD.format(
            jar=C.SERVER_DEVICE_PATH, version=C.SERVER_VERSION, scid=f"{self.scid:08x}"
        )
        self._logfile = adbmod.server_log_file(self.serial)
        self._proc = subprocess.Popen(
            [adbmod.adb_binary(), "-s", self.serial, "shell", cmd],
            stdout=self._logfile,
            stderr=subprocess.STDOUT,
            **adbmod.no_window_kwargs(),
        )

        listener.settimeout(self.spawn_timeout)
        try:
            conn, _ = listener.accept()
        except socket.timeout as e:
            tail = adbmod.read_log_tail(self._logfile)
            self._cleanup()
            raise RuntimeError(
                f"scrcpy-server ({self.serial}) không kết nối về sau {self.spawn_timeout}s.\n"
                f"Log server:\n{tail}"
            ) from e

        conn.settimeout(None)
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        meta = _recv_exact(conn, C.DEVICE_NAME_FIELD_LENGTH)
        self.device_name = meta.split(b"\0", 1)[0].decode("utf-8", "replace")
        self._sock = conn
        self._listener = listener
        self._writer = threading.Thread(
            target=self._writer_loop, name=f"ctl-{self.serial}", daemon=True
        )
        self._writer.start()
        log.info(
            "session %s: started (device=%r, scid=%08x, port=%d)",
            self.serial,
            self.device_name,
            self.scid,
            port,
        )

    def _writer_loop(self) -> None:
        assert self._sock is not None
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                self._sock.sendall(item)
                self.stats_sent += 1
                log.debug("session %s: sent %d bytes (total=%d)", self.serial, len(item), self.stats_sent)
            except OSError as e:
                log.warning("session %s: gửi lỗi (%s) — dừng writer", self.serial, e)
                break

    def send(self, message: bytes) -> None:
        """Đưa message vào hàng đợi FIFO (writer thread gửi, giữ nguyên thứ tự)."""
        if self._closed:
            raise RuntimeError(f"session {self.serial} đã đóng")
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            log.warning("session %s: queue đầy — bỏ message", self.serial)

    def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._writer is not None:
            self._writer.join(timeout=1.0)
        self._cleanup()
        log.info("session %s: stopped (sent=%d)", self.serial, self.stats_sent)

    def _cleanup(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        try:
            self.device.reverse_remove(f"localabstract:{self.socket_name()}")
        except Exception as e:
            log.debug("session %s: reverse_remove lỗi: %s", self.serial, e)
        if self._logfile is not None:
            try:
                self._logfile.close()
            except OSError:
                pass
            self._logfile = None

    def __enter__(self) -> "ControlSession":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
