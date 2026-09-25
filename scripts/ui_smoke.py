#!/usr/bin/env python3
"""Smoke test UI (Chrome headless qua CDP, stdlib only) — kiểm tra bố cục lưới + editor màn hình.

Cách chạy (app phải đang mở ở http://127.0.0.1:8899):

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
        --remote-debugging-port=9333 --user-data-dir=/tmp/emu-sync-chrome \
        --no-first-run --disable-gpu --window-size=1600,1000 http://127.0.0.1:8899/ &
    uv run python scripts/ui_smoke.py            # SHOT=/tmp/ui.png để đổi chỗ lưu ảnh

Kiểm tra: popover "Bố cục" + vẽ grid (cột × hàng), ô xem trước theo tỉ lệ màn hình thật,
editor "🖥 Màn hình" (preset tỉ lệ, khớp tỉ lệ 1×/0.75×/0.5×, dp). In PASS/FAIL từng mục.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import sys
import urllib.request
from urllib.parse import urlparse

PORT = int(os.environ.get("CDP_PORT", "9333"))


def ws_connect(url: str) -> socket.socket:
    u = urlparse(url)
    sock = socket.create_connection((u.hostname, u.port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall(
        (
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
    )
    data = b""
    while b"\r\n\r\n" not in data:
        data += sock.recv(4096)
    if b"101" not in data.split(b"\r\n")[0]:
        raise RuntimeError(f"bắt tay WS thất bại: {data[:200]!r}")
    return sock


def send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    header += mask
    sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def recv_text(sock: socket.socket) -> str | None:
    def read(n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise EOFError("socket đóng")
            buf += chunk
        return buf

    while True:
        b0, b1 = read(2)
        opcode = b0 & 0x0F
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack(">H", read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", read(8))[0]
        payload = read(length)
        if opcode == 0x1:
            return payload.decode()
        if opcode == 0x8:
            return None


class Client:
    def __init__(self, url: str) -> None:
        self.sock = ws_connect(url)
        self._id = 0

    def cmd(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        send_text(self.sock, json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            msg = recv_text(self.sock)
            if msg is None:
                raise RuntimeError("WS đóng giữa chừng")
            data = json.loads(msg)
            if data.get("id") == self._id:
                return data

    def eval(self, expression: str) -> object:
        res = self.cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        result = res.get("result", {})
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS lỗi: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")


def main() -> int:
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=10))
    page = next((t for t in targets if t["type"] == "page" and "8899" in t.get("url", "")), None)
    if page is None:
        print("Không thấy tab app (cần mở http://127.0.0.1:8899/)", file=sys.stderr)
        return 2
    client = Client(page["webSocketDebuggerUrl"])
    print("URL:", client.eval("location.href"))

    checks: list[tuple[str, object, object]] = []

    # 1) popover "Bố cục" mở ra + lưới vẽ có 24 ô (6×4)
    client.eval("localStorage.clear(); document.getElementById('layout-btn').click()")
    checks.append(("popover mở", client.eval("document.getElementById('layout-pop').className"), "layout-pop open"))
    checks.append(("số ô vẽ lưới", client.eval("document.querySelectorAll('#grid-pick div').length"), 24))

    # 2) click ô (cột 1, hàng 2) như người dùng — "2 máy ở hai hàng dọc"
    client.eval("[...document.querySelectorAll('#grid-pick div')].find(d=>d.dataset.c==='1'&&d.dataset.r==='2').onclick()")
    cols = client.eval("document.getElementById('grid').style.getPropertyValue('--cols')")
    maxh = client.eval("document.getElementById('grid').style.getPropertyValue('--preview-max-h')")
    cls = client.eval("document.getElementById('grid').className")
    computed = client.eval("getComputedStyle(document.getElementById('grid')).gridTemplateColumns")
    checks.append(("class lưới cố định", cls, "grid-fixed"))
    checks.append(("số cột = 1", cols, "1"))
    checks.append(("chiều cao mỗi hàng (2 hàng)", maxh, "calc((100vh - 330px) / 2)"))
    checks.append(("số cột thực tế trong CSS", len(str(computed).split()), 1))
    checks.append(("popover tự đóng sau khi chọn", client.eval("document.getElementById('layout-pop').className"), "layout-pop"))
    checks.append(
        ("đã lưu vào localStorage", client.eval("localStorage.getItem('emu-sync-layout2')"), '{"mode":"grid","cols":1,"rows":2}')
    )

    # 3) ô xem trước theo tỉ lệ màn hình thật của máy ảo
    checks.append(("số máy trên lưới", client.eval("document.querySelectorAll('.tile').length"), 2))
    checks.append(
        (
            "tỉ lệ ô theo máy ảo (1080×2400)",
            client.eval("document.querySelector('.tile img, .tile .prev-off').getAttribute('style')"),
            "aspect-ratio:1080/2400",
        )
    )

    # 4) vẽ lưới 2×2 rồi 6×4
    client.eval("[...document.querySelectorAll('#grid-pick div')].find(d=>d.dataset.c==='2'&&d.dataset.r==='2').onclick()")
    checks.append(("lưới 2 cột", len(str(client.eval("getComputedStyle(document.getElementById('grid')).gridTemplateColumns")).split()), 2))
    client.eval("[...document.querySelectorAll('#grid-pick div')].find(d=>d.dataset.c==='6'&&d.dataset.r==='4').onclick()")
    checks.append(("lưới 6 cột", len(str(client.eval("getComputedStyle(document.getElementById('grid')).gridTemplateColumns")).split()), 6))

    # 5) editor màn hình AVD: mở, đổi preset, khớp tỉ lệ 0.75×
    client.eval("if (avdEditor) avdScreen(avdEditor.name); avdScreen('emu2')")
    checks.append(("editor màn hình mở", client.eval("!!document.querySelector('.avd-editor')"), True))
    checks.append(("có nút khớp tỉ lệ", client.eval("!!document.querySelector('.avd-editor select[onchange*=\"avdEditor.ref\"]')"), True))
    client.eval("avdEditor.ref='emu1'; editorScale(0.75)")
    checks.append(("khớp 0.75× → rộng", client.eval("avdEditor.w"), 810))
    checks.append(("khớp 0.75× → cao", client.eval("avdEditor.h"), 1800))
    checks.append(("khớp 0.75× → dpi (cùng dp)", client.eval("avdEditor.dpi"), 315))
    checks.append(("hiển thị dp trên hàng AVD", client.eval("screenLabel({width:810,height:1800,dpi:315})"), "810×1800 @315 (411×914dp)"))
    client.eval("editorPreset(9)")
    checks.append(("preset 4:3 dọc 1200×1600", client.eval("JSON.stringify([avdEditor.w,avdEditor.h,avdEditor.dpi])"), "[1200,1600,240]"))

    # 6) trả về layout tự động + chụp ảnh
    client.eval("setLayout('auto')")
    checks.append(("về tự động (bỏ grid-fixed)", client.eval("document.getElementById('grid').className"), ""))
    checks.append(
        (
            "tự động = auto-fill (nhiều cột ở 1600px)",
            len(str(client.eval("getComputedStyle(document.getElementById('grid')).gridTemplateColumns")).split()) >= 2,
            True,
        )
    )
    client.eval(
        "[...document.querySelectorAll('#grid-pick div')].find(d=>d.dataset.c==='1'&&d.dataset.r==='2').onclick();"
        "if (!avdEditor) avdScreen('emu2'); avdEditor.ref='emu1'; editorScale(0.75);"
        "document.getElementById('avd-panel').open = true;"
        "document.getElementById('avd-list').scrollIntoView();"
    )
    shot = client.cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    out = os.environ.get("SHOT", "/tmp/emu_sync_ui.png")
    with open(out, "wb") as f:
        f.write(base64.b64decode(shot["result"]["data"]))
    print("ảnh chụp:", out)

    ok = True
    for name, got, want in checks:
        good = got == want
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}: {got!r}" + ("" if good else f" (mong đợi {want!r})"))
    print("KẾT QUẢ:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
