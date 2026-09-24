"""Lớp mỏng quanh adbutils: discovery, connect/scan, wm size, push scrcpy-server."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from adbutils import AdbDevice, adb

from . import config
from .scrcpy import const as C

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_SIZE_RE = re.compile(r"(Physical|Override) size:\s*(\d+)x(\d+)")


def no_window_kwargs() -> dict:
    """Kwargs cho subprocess.Popen để không hiện cửa sổ console trên Windows."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def adb_binary() -> str:
    """Đường dẫn adb: ưu tiên PATH, fallback binary do adbutils cung cấp."""
    path = shutil.which("adb")
    if path:
        return path
    from adbutils import adb_path  # adbutils tự tải/cung cấp adb binary

    return adb_path()


def list_devices() -> list[AdbDevice]:
    return list(adb.device_list())


def get_device(serial: str) -> AdbDevice:
    return adb.device(serial=serial)


def connect(address: str, timeout: float = 3.0) -> str:
    """`adb connect <address>` (vd "127.0.0.1:5555" cho BlueStacks)."""
    return adb.connect(address, timeout=timeout)


def scan_and_connect(port_ranges=None, host: str = "127.0.0.1") -> list[str]:
    """Thử `adb connect` vào các cổng nghi là giả lập; trả về địa chỉ kết nối được.

    - Bỏ qua port console + port adb của các emulator đã đăng ký (tránh kết nối
      nhầm vào console port → sinh thiết bị "offline").
    - Sau khi connect, chỉ giữ địa chỉ thực sự lên "device"; địa chỉ offline bị
      disconnect ngay (dọn rác).
    """
    ranges = port_ranges if port_ranges is not None else config.EMULATOR_PORT_RANGES

    skip: set[int] = set()
    for device in list_devices():
        serial = device.serial
        if serial.startswith("emulator-"):
            try:
                base = int(serial.rsplit("-", 1)[1])
                skip.update({base, base + 1})  # console port + adb bridge
            except ValueError:
                pass
        elif ":" in serial:
            try:
                skip.add(int(serial.rsplit(":", 1)[1]))
            except ValueError:
                pass

    targets = [f"{host}:{port}" for r in ranges for port in r if port not in skip]

    def attempt(address: str) -> str | None:
        try:
            adb.connect(address, timeout=config.SCAN_CONNECT_TIMEOUT)
        except Exception:
            return None
        return address

    candidates: list[str] = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        for address in pool.map(attempt, targets):
            if address is not None:
                candidates.append(address)

    device_serials = {d.serial for d in list_devices()}
    found: list[str] = []
    for address in candidates:
        if address in device_serials:
            found.append(address)
        else:
            try:
                adb.disconnect(address)
            except Exception:
                pass
    return found


def display_size(device: AdbDevice) -> tuple[int, int]:
    """Kích thước hiển thị hiện tại (ưu tiên Override size của `wm size`)."""
    out = device.shell("wm size")
    override = physical = None
    for kind, w, h in _SIZE_RE.findall(out):
        if kind == "Override":
            override = (int(w), int(h))
        else:
            physical = (int(w), int(h))
    size = override or physical
    if size is None:
        raise RuntimeError(f"Không đọc được `wm size` từ {device.serial}: {out!r}")
    return size


def getprop(device: AdbDevice, key: str) -> str:
    try:
        return device.shell(f"getprop {key}").strip()
    except Exception:
        return ""


def instance_name(device: AdbDevice) -> str:
    """Tên instance hiển thị: AVD name nếu có, không thì model."""
    avd = getprop(device, "ro.boot.qemu.avd_name")
    if avd:
        return avd
    return getprop(device, "ro.product.model") or device.serial


def push_server(device: AdbDevice, jar_path: Path | None = None) -> Path:
    jar = jar_path or (ASSETS_DIR / C.SERVER_JAR_NAME)
    if not jar.is_file():
        raise FileNotFoundError(
            f"Không thấy scrcpy-server jar: {jar} — chạy scripts/fetch_scrcpy_server.sh"
        )
    device.sync.push(str(jar), C.SERVER_DEVICE_PATH)
    return jar


def cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".cache"
    d = base / "emu-sync"
    d.mkdir(parents=True, exist_ok=True)
    return d


def server_log_file(serial: str):
    """File log stdout/stderr của scrcpy-server (để chẩn đoán khi start lỗi)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", serial)
    return open(cache_dir() / f"server-{safe}.log", "wb")


def read_log_tail(logfile, max_bytes: int = 4000) -> str:
    if logfile is None:
        return "(không có log)"
    try:
        logfile.flush()
        with open(logfile.name, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return "(không đọc được log)"
