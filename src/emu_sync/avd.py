"""Quản lý AVD (tạo/xoá/chạy/tắt/snapshot/profile) — chạy được trên macOS & Windows."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import adb as adbmod

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tìm SDK / công cụ
# ---------------------------------------------------------------------------
def sdk_root() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if env:
        candidates.append(Path(env))
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Android" / "Sdk")
    else:
        candidates.append(Path.home() / "Library" / "Android" / "sdk")
        candidates.append(Path.home() / "Android" / "Sdk")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _bin(name: str) -> Path | None:
    suffix = ".exe" if os.name == "nt" and not name.endswith(".bat") else ""
    which = shutil.which(name)
    if which:
        return Path(which)
    sdk = sdk_root()
    if sdk:
        candidate = sdk / "emulator" / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def emulator_binary() -> Path | None:
    return _bin("emulator")


def avdmanager_binary() -> Path | None:
    sdk = sdk_root()
    if sdk:
        bat = "avdmanager.bat" if os.name == "nt" else "avdmanager"
        candidate = sdk / "cmdline-tools" / "latest" / "bin" / bat
        if candidate.is_file():
            return candidate
    which = shutil.which("avdmanager")
    return Path(which) if which else None


def avd_dir() -> Path:
    home = os.environ.get("ANDROID_AVD_HOME")
    return Path(home) if home else Path.home() / ".android" / "avd"


# ---------------------------------------------------------------------------
# config.ini (profile của AVD)
# ---------------------------------------------------------------------------
def read_config(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def write_config(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Thông tin AVD
# ---------------------------------------------------------------------------
@dataclass
class AvdInfo:
    name: str
    path: Path
    image: str = ""
    width: int = 0
    height: int = 0
    dpi: int = 0
    ram_mb: int = 0
    cores: int = 0
    keyboard: bool = False
    running: bool = False
    serial: str = ""
    snapshot: bool = False  # có quickboot snapshot (giữ nguyên state khi mở lại)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "image": self.image,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi or None,
            "ram_mb": self.ram_mb,
            "cores": self.cores,
            "keyboard": self.keyboard,
            "running": self.running,
            "serial": self.serial,
            "snapshot": self.snapshot,
        }


def running_map() -> dict[str, str]:
    """AVD name → serial (các máy ảo đang chạy)."""
    result: dict[str, str] = {}
    for device in adbmod.list_devices():
        serial = device.serial
        if not serial.startswith("emulator-"):
            continue
        try:
            out = subprocess.run(
                [adbmod.adb_binary(), "-s", serial, "emu", "avd", "name"],
                capture_output=True,
                text=True,
                timeout=15,
                **adbmod.no_window_kwargs(),
            ).stdout
        except Exception:
            continue
        for line in out.splitlines():
            line = line.strip()
            if line and line != "OK":
                result[line] = serial
                break
    return result


def list_avds() -> list[AvdInfo]:
    emu = emulator_binary()
    names: list[str] = []
    if emu:
        try:
            out = subprocess.run(
                [str(emu), "-list-avds"],
                capture_output=True,
                text=True,
                timeout=30,
                **adbmod.no_window_kwargs(),
            ).stdout
            names = [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("INFO")]
        except Exception as e:
            log.debug("emulator -list-avds lỗi: %s", e)
    if not names:
        base = avd_dir()
        if base.is_dir():
            names = sorted(p.name[: -len(".avd")] for p in base.glob("*.avd"))

    running = running_map()
    infos: list[AvdInfo] = []
    for name in names:
        folder = avd_dir() / f"{name}.avd"
        cfg = read_config(folder / "config.ini")

        def _int(key: str) -> int:
            try:
                return int(cfg.get(key, "0"))
            except ValueError:
                return 0

        info = AvdInfo(
            name=name,
            path=folder,
            image=cfg.get("image.sysdir.1", ""),
            width=_int("hw.lcd.width"),
            height=_int("hw.lcd.height"),
            dpi=_int("hw.lcd.density"),
            ram_mb=_int("hw.ramSize"),
            cores=_int("hw.cpu.ncore"),
            keyboard=cfg.get("hw.keyboard", "no").lower() == "yes",
            snapshot=(folder / "snapshots" / "default_boot" / "snapshot.pb").is_file(),
        )
        if name in running:
            info.running = True
            info.serial = running[name]
        infos.append(info)
    return infos


def installed_images() -> list[str]:
    """Các system image đã tải (dạng 'system-images;android-35;google_apis;arm64-v8a')."""
    sdk = sdk_root()
    images: list[str] = []
    if not sdk:
        return images
    base = sdk / "system-images"
    if not base.is_dir():
        return images
    for api in sorted(base.iterdir()):
        if not api.is_dir():
            continue
        for tag in sorted(api.iterdir()):
            if not tag.is_dir():
                continue
            for abi in sorted(tag.iterdir()):
                if abi.is_dir():
                    images.append(f"system-images;{api.name};{tag.name};{abi.name}")
    return images


# ---------------------------------------------------------------------------
# Hành động
# ---------------------------------------------------------------------------
def create_avd(
    name: str,
    image: str,
    device: str = "pixel_6",
    ram_mb: int | None = None,
    cores: int | None = None,
    width: int | None = None,
    height: int | None = None,
    dpi: int | None = None,
    keyboard: bool = True,
) -> AvdInfo:
    avdm = avdmanager_binary()
    if avdm is None:
        raise RuntimeError("Không tìm thấy avdmanager (cài Android cmdline-tools)")
    proc = subprocess.run(
        [str(avdm), "create", "avd", "-n", name, "-k", image, "-d", device, "--force"],
        input="no\n",
        capture_output=True,
        text=True,
        timeout=300,
        **adbmod.no_window_kwargs(),
    )
    if proc.returncode != 0:
        tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
        raise RuntimeError(f"avdmanager lỗi: {tail.strip()}")

    updates: dict[str, str] = {
        "hw.keyboard": "yes" if keyboard else "no",
        "avd.ini.displayname": name,
    }
    if ram_mb:
        updates["hw.ramSize"] = str(ram_mb)
    if cores:
        updates["hw.cpu.ncore"] = str(cores)
    if width:
        updates["hw.lcd.width"] = str(width)
    if height:
        updates["hw.lcd.height"] = str(height)
    if dpi:
        updates["hw.lcd.density"] = str(dpi)
    write_config(avd_dir() / f"{name}.avd" / "config.ini", updates)

    for info in list_avds():
        if info.name == name:
            return info
    raise RuntimeError(f"Tạo AVD {name} xong nhưng không đọc lại được thông tin")


def delete_avd(name: str) -> None:
    avdm = avdmanager_binary()
    if avdm is None:
        raise RuntimeError("Không tìm thấy avdmanager")
    proc = subprocess.run(
        [str(avdm), "delete", "avd", "-n", name],
        capture_output=True,
        text=True,
        timeout=120,
        **adbmod.no_window_kwargs(),
    )
    if proc.returncode != 0 and "not found" not in (proc.stderr or "").lower():
        raise RuntimeError(((proc.stdout or "") + (proc.stderr or ""))[-300:].strip())


def start_avd(name: str, headless: bool = False, cold: bool = False) -> int:
    emu = emulator_binary()
    if emu is None:
        raise RuntimeError("Không tìm thấy emulator trong SDK")
    args = [str(emu), "-avd", name, "-no-audio", "-no-boot-anim"]
    if headless:
        args.append("-no-window")
    if cold:
        args += ["-no-snapshot-load", "-no-snapshot-save"]
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    return proc.pid


def stop_avd(name: str) -> None:
    serial = running_map().get(name)
    if serial is None:
        raise RuntimeError(f"{name} không chạy")
    subprocess.run(
        [adbmod.adb_binary(), "-s", serial, "emu", "kill"],
        capture_output=True,
        timeout=30,
        **adbmod.no_window_kwargs(),
    )


def snapshot_save(name: str, snapshot: str = "default_boot") -> str:
    serial = running_map().get(name)
    if serial is None:
        raise RuntimeError(f"{name} không chạy — bật máy ảo trước khi lưu state")
    proc = subprocess.run(
        [adbmod.adb_binary(), "-s", serial, "emu", "avd", "snapshot", "save", snapshot],
        capture_output=True,
        text=True,
        timeout=180,
        **adbmod.no_window_kwargs(),
    )
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def snapshot_list(name: str) -> str:
    serial = running_map().get(name)
    if serial is None:
        raise RuntimeError(f"{name} không chạy")
    proc = subprocess.run(
        [adbmod.adb_binary(), "-s", serial, "emu", "avd", "snapshot", "list"],
        capture_output=True,
        text=True,
        timeout=60,
        **adbmod.no_window_kwargs(),
    )
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def set_config(
    name: str,
    ram_mb: int | None = None,
    cores: int | None = None,
    width: int | None = None,
    height: int | None = None,
    dpi: int | None = None,
    keyboard: bool | None = None,
) -> AvdInfo:
    updates: dict[str, str] = {}
    if ram_mb:
        updates["hw.ramSize"] = str(ram_mb)
    if cores:
        updates["hw.cpu.ncore"] = str(cores)
    if width:
        updates["hw.lcd.width"] = str(width)
    if height:
        updates["hw.lcd.height"] = str(height)
    if dpi:
        updates["hw.lcd.density"] = str(dpi)
    if keyboard is not None:
        updates["hw.keyboard"] = "yes" if keyboard else "no"
    if not updates:
        raise RuntimeError("Không có thay đổi nào")
    write_config(avd_dir() / f"{name}.avd" / "config.ini", updates)
    for info in list_avds():
        if info.name == name:
            return info
    raise RuntimeError(f"Không thấy AVD {name}")


def apply_screen(
    name: str,
    width: int,
    height: int,
    dpi: int | None = None,
    persist: bool = True,
) -> dict:
    """Đổi độ phân giải màn hình máy ảo (đa dạng tỉ lệ).

    - Đang chạy → áp dụng **ngay** bằng `wm size` / `wm density` (không cần khởi động lại).
      Toạ độ sync đọc lại `wm size` nên tự khớp tỉ lệ mới.
    - `persist=True` → lưu vào profile (config.ini) để lần chạy sau đúng luôn.
    """
    if width <= 0 or height <= 0:
        raise RuntimeError("Kích thước không hợp lệ")

    applied = False
    serial = running_map().get(name)
    if serial is not None:
        subprocess.run(
            [adbmod.adb_binary(), "-s", serial, "shell", "wm", "size", f"{width}x{height}"],
            capture_output=True,
            text=True,
            timeout=30,
            **adbmod.no_window_kwargs(),
        )
        if dpi:
            subprocess.run(
                [adbmod.adb_binary(), "-s", serial, "shell", "wm", "density", str(dpi)],
                capture_output=True,
                text=True,
                timeout=30,
                **adbmod.no_window_kwargs(),
            )
        applied = True

    if persist:
        set_config(name, width=width, height=height, dpi=dpi)

    return {"name": name, "width": width, "height": height, "dpi": dpi, "applied_runtime": applied}


def reset_screen(name: str, reset_density: bool = True, persist: bool = True) -> dict:
    """Trả màn hình máy ảo về độ phân giải GỐC (xoá override wm size/density).

    Đồng thời (nếu persist) ghi lại kích thước gốc vào profile để lần chạy sau khớp.
    """
    serial = running_map().get(name)
    if serial is None:
        raise RuntimeError(f"{name} không chạy — bật máy ảo trước")
    subprocess.run(
        [adbmod.adb_binary(), "-s", serial, "shell", "wm", "size", "reset"],
        capture_output=True,
        text=True,
        timeout=30,
        **adbmod.no_window_kwargs(),
    )
    if reset_density:
        subprocess.run(
            [adbmod.adb_binary(), "-s", serial, "shell", "wm", "density", "reset"],
            capture_output=True,
            text=True,
            timeout=30,
            **adbmod.no_window_kwargs(),
        )

    physical_w = physical_h = physical_dpi = None
    out = subprocess.run(
        [adbmod.adb_binary(), "-s", serial, "shell", "wm", "size"],
        capture_output=True,
        text=True,
        timeout=30,
        **adbmod.no_window_kwargs(),
    ).stdout
    m = re.search(r"Physical size:\s*(\d+)x(\d+)", out or "")
    if m:
        physical_w, physical_h = int(m.group(1)), int(m.group(2))
    if reset_density:
        out = subprocess.run(
            [adbmod.adb_binary(), "-s", serial, "shell", "wm", "density"],
            capture_output=True,
            text=True,
            timeout=30,
            **adbmod.no_window_kwargs(),
        ).stdout
        m = re.search(r"Physical density:\s*(\d+)", out or "")
        if m:
            physical_dpi = int(m.group(1))

    if persist and physical_w and physical_h:
        set_config(name, width=physical_w, height=physical_h, dpi=physical_dpi)

    return {"name": name, "reset": True, "width": physical_w, "height": physical_h, "dpi": physical_dpi}
