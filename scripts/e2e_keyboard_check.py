#!/usr/bin/env python3
"""E2E kiểm tra SYNC BÀN PHÍM: gõ trên master → mọi máy nhận đúng chữ.

Cách làm:
  1. Mở Settings Search trên TẤT CẢ các máy; CHỜ ô nhập được focus (poll dump).
  2. Gõ text vào master qua emulator console (`adb emu event text`) — đường đi
     giống gõ thật trên cửa sổ giả lập (qua thiết bị bàn phím trong nhân).
  3. Chờ master hiện text (xác nhận gõ thành công), rồi kiểm tra mọi máy.

Chạy trong lúc `emu-sync app`/`ui` (hoặc `run --master ...`) đang chạy:

    uv run python scripts/e2e_keyboard_check.py --master emulator-5554 --text hello
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

from emu_sync import adb as adbmod

SEARCH_COMPONENT = "com.google.android.settings.intelligence/.modules.search.SearchActivity"
_TEXT_RE = re.compile(r'text="([^"]*)"')


def open_search(device) -> None:
    device.shell(f"am start -n {SEARCH_COMPONENT}")


def dump_xml(device) -> str:
    device.shell("uiautomator dump /data/local/tmp/w.xml >/dev/null 2>&1")
    return device.shell("cat /data/local/tmp/w.xml")


def texts_of(device) -> list[str]:
    return _TEXT_RE.findall(dump_xml(device))


def wait_until(predicate, timeout: float, interval: float = 1.0):
    """Poll predicate cho tới khi True hoặc hết timeout; trả về giá trị cuối."""
    deadline = time.monotonic() + timeout
    result = None
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    return result


def wait_search_focused(device, timeout: float = 15.0) -> bool:
    def check() -> bool:
        xml = dump_xml(device)
        return 'class="android.widget.EditText"' in xml and 'focused="true"' in xml

    return bool(wait_until(check, timeout=timeout, interval=1.2))


def wait_text(device, text: str, timeout: float = 10.0) -> bool:
    def check() -> bool:
        return any(text.lower() in t.lower() for t in texts_of(device))

    return bool(wait_until(check, timeout=timeout, interval=1.2))


def type_on_master(serial: str, text: str) -> None:
    subprocess.run(
        [adbmod.adb_binary(), "-s", serial, "emu", "event", "text", text],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E sync bàn phím")
    parser.add_argument("--master", required=True)
    parser.add_argument("--targets", help="cách nhau bởi dấu phẩy (mặc định: mọi máy còn lại)")
    parser.add_argument("--text", default="hello", help="text sẽ gõ trên master")
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

    print(f"master={args.master}  devices={all_serials}  text={args.text!r}")
    for serial in all_serials:
        open_search(devices[serial])

    print("Chờ ô nhập được focus...")
    for serial in all_serials:
        ok = wait_search_focused(devices[serial])
        print(f"  {serial}: focus={'OK' if ok else 'TIMEOUT'}")
        if not ok:
            return 3

    print(f"Gõ {args.text!r} trên master...")
    type_on_master(args.master, args.text)

    if not wait_text(devices[args.master], args.text):
        print(f"  master không nhận được text (không gõ được) — dừng", file=sys.stderr)
        return 4
    print(f"  master OK")

    ok = True
    for serial in all_serials[1:]:
        found = wait_text(devices[serial], args.text)
        print(f"  {serial}: {'OK' if found else 'MISSING'}")
        if not found:
            ok = False

    print("KẾT QUẢ:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
