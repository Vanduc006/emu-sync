#!/usr/bin/env python3
"""E2E: kiểm tra đồng bộ thao tác (dựa trên foreground activity + screenshot).

Kịch bản:
  1. Đưa tất cả máy về Settings homepage; đợi màn hình ổn định (poll đến khi
     focus + screenshot không đổi giữa 2 lần liên tiếp).
  2. Ghi nhận baseline (focus + hash ảnh + similarity giữa các máy).
  3. Bơm gesture (tap / swipe) vào MASTER bằng **emulator console** (`adb emu event
     mouse`) — đúng đường input như chuột thật trên cửa sổ, và `getevent` nhìn
     thấy được (khác `adb shell input`). Hỗ trợ `sendevent` cho máy không phải emulator.
  4. Đợi ổn định trên tất cả máy.
  5. Assert chính: **foreground activity của mọi máy GIỐNG NHAU** sau gesture
     (cùng UI element được kích hoạt) — mạnh hơn và ổn định hơn so sánh ảnh.
     Assert phụ: master đổi activity; similarity ảnh >= ngưỡng (informational).

Chạy trong lúc `emu-sync run --master <serial>` đang chạy:

    uv run python scripts/e2e_sync_check.py --master emulator-5554
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from collections.abc import Callable

from emu_sync import adb as adbmod
from emu_sync.capture.getevent import ABS_MT_POSITION_X, ABS_MT_POSITION_Y, discover_devices

HASH_BITS = 64

# Toạ độ (0..1): (0.5, 0.28) rơi vào thanh search của Settings → mở SearchActivity.
TAP_POINT = (0.5, 0.28)
SWIPE_FROM = (0.5, 0.72)
SWIPE_TO = (0.5, 0.34)

_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s(u\d+)\s+([\w.$]+/[\w.$]+)[^}]*\}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def dhash(image) -> int:
    small = image.convert("L").resize((9, 8))
    px = list(small.getdata())
    value = 0
    for row in range(8):
        for col in range(8):
            value = (value << 1) | int(px[row * 9 + col] < px[row * 9 + col + 1])
    return value


def similarity(a: int, b: int) -> float:
    return 1.0 - bin(a ^ b).count("1") / HASH_BITS


def screenshot_hash(device) -> int:
    return dhash(device.screenshot())


def get_focus(device) -> str | None:
    out = device.shell("dumpsys window | grep mCurrentFocus")
    m = _FOCUS_RE.search(out)
    return m.group(2) if m else None


def wait_stable(device, timeout: float = 8.0, interval: float = 0.35) -> tuple[str | None, int]:
    """Đợi đến khi (focus, screenshot-hash) không đổi giữa 2 lần poll liên tiếp."""
    last: tuple[str | None, int] | None = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = (get_focus(device), screenshot_hash(device))
        if current == last:
            return current
        last = current
        time.sleep(interval)
    assert last is not None
    return last


def touch_device(device):
    caps = discover_devices(device)
    touch = next((c for c in caps if c.is_touch), None)
    if touch is None:
        raise RuntimeError(f"{device.serial}: không thấy thiết bị cảm ứng")
    return touch


def open_settings(device) -> None:
    device.shell("am force-stop com.android.settings")
    device.shell("am force-stop com.google.android.settings.intelligence")
    time.sleep(0.4)
    device.shell("am start -a android.settings.SETTINGS")


# ---------------------------------------------------------------------------
# Injectors
# ---------------------------------------------------------------------------
def make_console_injector(device) -> Callable[[str], None]:
    w, h = adbmod.display_size(device)

    def mouse(nx: float, ny: float, button: int) -> None:
        x, y = round(nx * w), round(ny * h)
        subprocess.run(
            [adbmod.adb_binary(), "-s", device.serial, "emu", "event", "mouse", str(x), str(y), "0", str(button)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def inject(action: str) -> None:
        if action == "tap":
            mouse(*TAP_POINT, 1)
            time.sleep(0.06)
            mouse(*TAP_POINT, 0)
        elif action == "swipe":
            (x0, y0), (x1, y1) = SWIPE_FROM, SWIPE_TO
            mouse(x0, y0, 1)
            time.sleep(0.02)
            steps = 12
            for i in range(1, steps + 1):
                mouse(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, 1)
                time.sleep(0.012)
            mouse(x1, y1, 0)
        else:
            raise ValueError(action)

    return inject


def make_sendevent_injector(device) -> Callable[[str], None]:
    touch = touch_device(device)
    xr = touch.abs_ranges[ABS_MT_POSITION_X]
    yr = touch.abs_ranges[ABS_MT_POSITION_Y]

    def scale(nx: float, ny: float) -> tuple[int, int]:
        return int(xr[0] + nx * (xr[1] - xr[0])), int(yr[0] + ny * (yr[1] - yr[0]))

    def build(action: str, hold: float = 0.06, steps: int = 12) -> str:
        cmds: list[str] = []

        def ev(t: int, c: int, v: int) -> None:
            cmds.append(f"sendevent {touch.path} {t} {c} {v}")

        def nap(sec: float) -> None:
            cmds.append(f"sleep {sec}")

        if action == "tap":
            x, y = scale(*TAP_POINT)
            ev(3, 0x2F, 0)
            ev(3, 0x39, 1)
            ev(3, 0x35, x)
            ev(3, 0x36, y)
            ev(0, 0, 0)
            nap(hold)
            ev(3, 0x39, -1)
            ev(0, 0, 0)
        elif action == "swipe":
            x0, y0 = scale(*SWIPE_FROM)
            x1, y1 = scale(*SWIPE_TO)
            ev(3, 0x2F, 0)
            ev(3, 0x39, 1)
            ev(3, 0x35, x0)
            ev(3, 0x36, y0)
            ev(0, 0, 0)
            nap(0.02)
            for i in range(1, steps + 1):
                xx = int(x0 + (x1 - x0) * i / steps)
                yy = int(y0 + (y1 - y0) * i / steps)
                ev(3, 0x35, xx)
                ev(3, 0x36, yy)
                ev(0, 0, 0)
                nap(0.012)
            ev(3, 0x39, -1)
            ev(0, 0, 0)
        else:
            raise ValueError(action)
        return "; ".join(cmds)

    def inject(action: str) -> None:
        ret = device.shell2(build(action))
        combined = f"{ret.output or ''}{ret.stderr or ''}"
        if "denied" in combined or "not permitted" in combined:
            raise RuntimeError(f"Không ghi được {touch.path} — cần quyền (thử `adb root`)")

    return inject


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="E2E kiểm tra đồng bộ thao tác")
    parser.add_argument("--master", required=True)
    parser.add_argument("--targets", help="cách nhau bởi dấu phẩy (mặc định: mọi máy còn lại)")
    parser.add_argument("--action", choices=["tap", "swipe"], default="tap")
    parser.add_argument("--inject", choices=["auto", "console", "sendevent"], default="auto")
    parser.add_argument("--threshold", type=float, default=0.90, help="ngưỡng similarity ảnh (assert phụ)")
    parser.add_argument("--settle-timeout", type=float, default=8.0)
    args = parser.parse_args()

    devices = {d.serial: d for d in adbmod.list_devices()}
    if args.master not in devices:
        print(f"Không thấy master {args.master}", file=sys.stderr)
        return 2
    all_serials = [args.master, *(
        [s.strip() for s in args.targets.split(",") if s.strip()]
        if args.targets
        else [s for s in devices if s != args.master]
    )]
    if len(all_serials) < 2:
        print("Cần ít nhất 1 target", file=sys.stderr)
        return 2

    master = devices[args.master]
    mode = args.inject if args.inject != "auto" else (
        "console" if args.master.startswith("emulator-") else "sendevent"
    )
    injector = make_console_injector(master) if mode == "console" else make_sendevent_injector(master)
    print(f"master={args.master}  inject={mode}  devices={all_serials}")

    print("Đưa các máy về Settings homepage...")
    for serial in all_serials:
        open_settings(devices[serial])

    before: dict[str, tuple[str | None, int]] = {}
    for serial in all_serials:
        before[serial] = wait_stable(devices[serial], timeout=args.settle_timeout)
        print(f"  before {serial}: focus={before[serial][0]}")
    for serial in all_serials[1:]:
        print(f"  baseline sim({args.master},{serial}) = {similarity(before[args.master][1], before[serial][1]):.3f}")

    print(f"Bơm gesture '{args.action}' vào master {args.master} ...")
    injector(args.action)

    after: dict[str, tuple[str | None, int]] = {}
    for serial in all_serials:
        after[serial] = wait_stable(devices[serial], timeout=args.settle_timeout)
        print(f"  after  {serial}: focus={after[serial][0]}")

    master_focus_before, master_focus_after = before[args.master][0], after[args.master][0]
    focus_equal = all(after[s][0] == master_focus_after for s in all_serials)
    focus_changed = master_focus_after != master_focus_before
    screen_changed = similarity(before[args.master][1], after[args.master][1]) < 0.99
    sims = {s: similarity(after[args.master][1], after[s][1]) for s in all_serials[1:]}
    sim_ok = all(v >= args.threshold for v in sims.values())

    print(f"master focus: {master_focus_before} → {master_focus_after}")
    print(f"master screen changed: {screen_changed}")
    print(f"focus các máy giống nhau: {focus_equal}")
    for serial, sim in sims.items():
        print(f"  sim(after) {args.master} ↔ {serial} = {sim:.3f}")

    if args.action == "tap":
        # tap: master phải chuyển activity (mở element), tất cả máy cùng activity.
        ok = focus_equal and focus_changed
    else:
        # swipe/scroll: activity không đổi, nhưng màn hình phải đổi (cuộn) và
        # mọi máy phải ở cùng trạng thái sau đó.
        ok = focus_equal and screen_changed and sim_ok
    if not sim_ok:
        print(f"  (cảnh báo: similarity ảnh dưới ngưỡng {args.threshold} — animation/đồng hồ?)")
    print("KẾT QUẢ:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
