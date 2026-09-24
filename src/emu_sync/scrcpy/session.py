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
import select
import socket
import subprocess
import threading
import time
from pathlib import Path

from adbutils import AdbDevice

from .. import adb as adbmod
from . import const as C

log = logging.getLogger(__name__)

_SERVER_CMD = (
    "CLASSPATH={jar} app_process / com.genymobile.scrcpy.Server {version} "
    "scid={scid} log_level=info video=false audio=false control=true "
    "cleanup=true power_on=true clipboard_autosync=false {extra}"
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
        self._listeners: list[socket.socket] = []
        self._host_port: int | None = None
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
        """Mở session control-only.

        Thử **forward** trước: adb forward cho DEVICE listen, ta connect ra — hoàn toàn
        không có listener trên máy host ⇒ Windows Firewall không hỏi quyền truy cập.
        Nếu thất bại (adbd vendor lạ), fallback sang **reverse** (wildcard listener).
        """
        adbmod.push_server(self.device, self.jar_path)
        errors: list[str] = []
        last_tail = ""
        for mode in ("forward", "reverse"):
            try:
                self._attempt(mode)
                log.info(
                    "session %s: started (mode=%s, device=%r, scid=%08x)",
                    self.serial,
                    mode,
                    self.device_name,
                    self.scid,
                )
                return
            except Exception as e:
                errors.append(f"[{mode}] {e}")
                last_tail = adbmod.read_log_tail(self._logfile)
                self._cleanup()
        raise RuntimeError(
            f"scrcpy-server ({self.serial}) không kết nối được:\n"
            + "\n".join(errors)
            + f"\nLog server:\n{last_tail}\n"
            + f"Gợi ý: chạy `emu-sync doctor {self.serial}` để kiểm tra từng bước."
        )

    def _attempt(self, mode: str) -> None:
        if mode == "forward":
            port = self.device.forward_port(f"localabstract:{self.socket_name()}")
            self._host_port = port
            self._proc = self._spawn_server("tunnel_forward=true send_dummy_byte=false")
            conn, meta = self._connect_forward(port)
        else:
            listener = socket.create_server(("::", 0), family=socket.AF_INET6, dualstack_ipv6=True)
            self._listeners = [listener]
            port = listener.getsockname()[1]
            self.device.reverse(f"localabstract:{self.socket_name()}", f"tcp:{port}")
            self._proc = self._spawn_server("send_dummy_byte=false")
            conn = self._accept_reverse(listener)
            conn.settimeout(2.0)
            try:
                meta = _recv_exact(conn, C.DEVICE_NAME_FIELD_LENGTH)
            finally:
                conn.settimeout(None)
        self._finalize(conn, meta)

    def _spawn_server(self, extra: str):
        cmd = _SERVER_CMD.format(
            jar=C.SERVER_DEVICE_PATH,
            version=C.SERVER_VERSION,
            scid=f"{self.scid:08x}",
            extra=extra,
        )
        self._logfile = adbmod.server_log_file(self.serial)
        return subprocess.Popen(
            [adbmod.adb_binary(), "-s", self.serial, "shell", cmd],
            stdout=self._logfile,
            stderr=subprocess.STDOUT,
            **adbmod.no_window_kwargs(),
        )

    def _connect_forward(self, port: int) -> tuple[socket.socket, bytes]:
        """Connect vào adb forward port, retry tới khi server trên device sẵn sàng.

        Lưu ý: adb accept ngay cả khi phía device chưa listen ⇒ phải đọc thử 64B meta
        để biết đã vào thật chưa (nếu chưa, socket bị đóng ngay).
        """
        deadline = time.monotonic() + self.spawn_timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            for host in ("127.0.0.1", "::1"):
                try:
                    conn = socket.create_connection((host, port), timeout=2.0)
                except OSError as e:
                    last = e
                    continue
                conn.settimeout(2.0)
                try:
                    meta = _recv_exact(conn, C.DEVICE_NAME_FIELD_LENGTH)
                except (OSError, ConnectionError) as e:
                    last = e
                    conn.close()
                    continue
                finally:
                    try:
                        conn.settimeout(None)
                    except OSError:
                        pass
                return conn, meta
            time.sleep(0.25)
        raise RuntimeError(f"adb forward không kết nối được sau {self.spawn_timeout}s ({last})")

    def _accept_reverse(self, listener: socket.socket) -> socket.socket:
        deadline = time.monotonic() + self.spawn_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"server không kết nối về sau {self.spawn_timeout}s")
            ready, _, _ = select.select([listener], [], [], min(remaining, 0.5))
            for sock in ready:
                try:
                    conn, _ = sock.accept()
                    return conn
                except OSError:
                    continue

    def _finalize(self, conn: socket.socket, meta: bytes) -> None:
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.device_name = meta.split(b"\0", 1)[0].decode("utf-8", "replace")
        self._sock = conn
        self._writer = threading.Thread(
            target=self._writer_loop, name=f"ctl-{self.serial}", daemon=True
        )
        self._writer.start()

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
        for listener in self._listeners:
            try:
                listener.close()
            except OSError:
                pass
        self._listeners = []
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
        if self._host_port is not None:
            try:
                self.device.forward_remove(f"tcp:{self._host_port}")
            except Exception as e:
                log.debug("session %s: forward_remove lỗi: %s", self.serial, e)
            self._host_port = None
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
