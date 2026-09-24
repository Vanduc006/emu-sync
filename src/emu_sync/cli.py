"""CLI emu-sync."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time

from . import adb as adbmod
from .capture.getevent import GeteventSource, discover_devices
from .hotkeys import DEFAULT_HOTKEY, HotkeyManager, keycode_of_spec, label_of
from .scrcpy import const as C
from .scrcpy import control
from .scrcpy.session import ControlSession
from .sync_engine import SyncEngine


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def cmd_devices(args) -> int:
    devices = adbmod.list_devices()
    if not devices:
        print("Không thấy thiết bị nào (adb devices trống).")
        return 1
    for d in devices:
        try:
            w, h = adbmod.display_size(d)
            size = f"{w}x{h}"
        except Exception as e:
            size = f"(lỗi: {e})"
        print(f"{d.serial:22s} {size:11s} {adbmod.instance_name(d)}")
    return 0


def cmd_tap(args) -> int:
    d = adbmod.get_device(args.serial)
    w, h = adbmod.display_size(d)
    if not (0 <= args.x < w and 0 <= args.y < h):
        print(f"Toạ độ ngoài màn hình {w}x{h}: ({args.x}, {args.y})", file=sys.stderr)
        return 2
    with ControlSession(d) as session:
        session.send(control.inject_touch(C.ACTION_DOWN, args.x, args.y, w, h))
        time.sleep(args.hold)
        session.send(control.inject_touch(C.ACTION_UP, args.x, args.y, w, h))
        time.sleep(0.2)
    return 0


def cmd_scroll(args) -> int:
    d = adbmod.get_device(args.serial)
    w, h = adbmod.display_size(d)
    with ControlSession(d) as session:
        for _ in range(args.repeat):
            session.send(control.inject_scroll(args.x, args.y, w, h, vscroll=args.dy))
            time.sleep(0.05)
        time.sleep(0.2)
    return 0


def cmd_key(args) -> int:
    d = adbmod.get_device(args.serial)
    with ControlSession(d) as session:
        session.send(control.inject_keycode(C.KEY_ACTION_DOWN, args.keycode))
        time.sleep(0.02)
        session.send(control.inject_keycode(C.KEY_ACTION_UP, args.keycode))
        time.sleep(0.2)
    return 0


def cmd_back(args) -> int:
    d = adbmod.get_device(args.serial)
    with ControlSession(d) as session:
        session.send(control.back_or_screen_on(C.KEY_ACTION_DOWN))
        time.sleep(0.02)
        session.send(control.back_or_screen_on(C.KEY_ACTION_UP))
        time.sleep(0.2)
    return 0


def cmd_text(args) -> int:
    d = adbmod.get_device(args.serial)
    with ControlSession(d) as session:
        session.send(control.inject_text(args.text))
        time.sleep(0.3)
    return 0


def cmd_sniff(args) -> int:
    """In ra các event input parse được từ 1 thiết bị (debug parser)."""
    d = adbmod.get_device(args.serial)

    def on_event(event) -> None:
        print(event)

    source = GeteventSource(d, on_event)
    source.start()
    print(f"Sniffing {args.serial} — tương tác với giả lập, Ctrl+C để dừng.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDừng sniff.")
    finally:
        source.stop()
    return 0


def cmd_run(args) -> int:
    """Đồng bộ: bắt input từ master (getevent) → bơm sang các target (scrcpy control-only)."""
    master = adbmod.get_device(args.master)
    devices = {d.serial: d for d in adbmod.list_devices()}
    if args.master not in devices:
        print(f"Không thấy master {args.master} trong adb devices", file=sys.stderr)
        return 2
    if args.targets:
        target_serials = [s.strip() for s in args.targets.split(",") if s.strip()]
    else:
        target_serials = [s for s in devices if s != args.master]
    if not target_serials:
        print("Không có target nào để đồng bộ", file=sys.stderr)
        return 2

    sessions: list[ControlSession] = []
    targets: dict[str, tuple[ControlSession, tuple[int, int]]] = {}
    source = None
    try:
        for serial in target_serials:
            d = devices.get(serial) or adbmod.get_device(serial)
            w, h = adbmod.display_size(d)
            session = ControlSession(d)
            session.start()
            sessions.append(session)
            targets[serial] = (session, (w, h))
            print(f"target  {serial:22s} {w}x{h}  {adbmod.instance_name(d)}", flush=True)

        engine = SyncEngine(targets)
        source = GeteventSource(master, engine.handle)
        source.start()
        print(f"master  {args.master:22s} {adbmod.instance_name(master)}", flush=True)
        print("Đang đồng bộ thao tác — Ctrl+C để dừng.", flush=True)

        last_report = time.monotonic()
        last_count = 0
        while True:
            time.sleep(0.5)
            now = time.monotonic()
            if now - last_report >= 5.0:
                count, p50, p95 = engine.latency_stats()
                if count != last_count:
                    print(
                        f"[stats] events={count} fan-out p50={p50:.1f}ms p95={p95:.1f}ms",
                        flush=True,
                    )
                    last_count = count
                last_report = now
    except KeyboardInterrupt:
        print("\nDừng đồng bộ.")
    finally:
        if source is not None:
            source.stop()
        for session in sessions:
            session.stop()
    return 0


def _free_port(preferred: int, attempts: int = 60) -> int:
    """Trả về cổng trống (bắt đầu từ `preferred`, tự tăng nếu bận)."""
    import socket as _socket

    for port in range(preferred, preferred + attempts):
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
            sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Không tìm được cổng trống quanh {preferred}")


def _background_watchdog(controller) -> None:
    """Định kỳ làm mới danh sách thiết bị + tự thử lại session lỗi (không cần bấm nút)."""
    import threading

    def worker() -> None:
        while True:
            time.sleep(5.0)
            try:
                controller.refresh_devices()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True, name="emu-sync-watchdog").start()


def _background_scan(controller) -> None:
    """Quét cổng giả lập ở nền; tự bật đồng bộ nếu tìm thấy máy."""
    import threading

    def worker() -> None:
        try:
            controller.scan_ports()
            if not controller.running and controller.devices:
                controller.start()
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True, name="emu-sync-scan").start()


def _wire_hotkeys(controller, spec: str) -> HotkeyManager:
    """Đăng ký phím tắt bật/tắt đồng bộ; trả về manager để stop khi thoát."""
    controller.hotkey_label = label_of(spec) if spec.lower() not in ("none", "off", "") else ""
    controller.engine.suppress_keycode = keycode_of_spec(spec) if controller.hotkey_label else None
    manager = HotkeyManager(spec, on_toggle=controller.toggle_paused)
    if controller.hotkey_label:
        if manager.start():
            print(f"Phím tắt bật/tắt đồng bộ: {controller.hotkey_label}", flush=True)
        else:
            print(
                "Phím tắt chưa đăng ký được (thiếu pynput hoặc chưa cấp quyền Accessibility/Input Monitoring).",
                flush=True,
            )
    return manager


def cmd_ui(args) -> int:
    """Panel web quản lý: preview từng máy, chọn master, bật/tắt sync."""
    import uvicorn

    from .controller import SyncController
    from .webapp import create_app

    controller = SyncController()
    controller.refresh_devices(update_meta=True)
    if controller.devices:
        controller.start(args.master)
    _background_scan(controller)
    _background_watchdog(controller)
    hotkeys = _wire_hotkeys(controller, args.hotkey)
    port = _free_port(args.port)
    host_shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"emu-sync UI: http://{host_shown}:{port}", flush=True)
    print(f"master: {controller.master or '—'} — Ctrl+C để dừng.", flush=True)
    try:
        uvicorn.run(create_app(controller), host=args.host, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        hotkeys.stop()
        controller.stop()
    return 0


def cmd_app(args) -> int:
    """Desktop app: panel trong cửa sổ native (pywebview; WKWebView/WebView2)."""
    import threading

    import uvicorn

    from .controller import SyncController
    from .webapp import create_app

    try:
        import webview
    except ImportError:
        print(
            "Thiếu pywebview — cài desktop extras:\n  uv pip install -e '.[desktop]'",
            file=sys.stderr,
        )
        return 1

    controller = SyncController()
    controller.refresh_devices(update_meta=True)
    if controller.devices:
        controller.start(args.master)
    _background_scan(controller)
    _background_watchdog(controller)
    hotkeys = _wire_hotkeys(controller, args.hotkey)

    port = _free_port(args.port)
    server = uvicorn.Server(
        uvicorn.Config(create_app(controller), host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True, name="emu-sync-http").start()

    print(
        f"emu-sync app — master: {controller.master or '—'}, UI nội bộ: http://127.0.0.1:{port}",
        flush=True,
    )
    webview.create_window("emu-sync", f"http://127.0.0.1:{port}", width=1280, height=860)
    try:
        webview.start()
    finally:
        server.should_exit = True
        hotkeys.stop()
        controller.stop()
    return 0


def cmd_doctor(args) -> int:
    """Kiểm tra từng bước kết nối tới thiết bị (debug nhanh khi session lỗi)."""
    ok = True

    def step(name: str, fn):
        nonlocal ok
        try:
            print(f"[OK]  {name}: {fn()}")
        except Exception as e:
            ok = False
            print(f"[LỖI] {name}: {e}")
        return ok

    print("== 1) Môi trường ==")
    step("adb binary", lambda: adbmod.adb_binary())

    def adb_version() -> str:
        out = subprocess.run(
            [adbmod.adb_binary(), "version"], capture_output=True, text=True, timeout=15
        ).stdout
        return out.splitlines()[0] if out else "?"

    step("adb version", adb_version)

    devices = adbmod.list_devices()
    if devices:
        print(f"[OK]  adb devices: {', '.join(d.serial for d in devices)}")
    else:
        ok = False
        print("[LỖI] adb devices: (trống) — mở giả lập + bật ADB rồi bấm 'Tìm máy ảo'")
        return 1

    serial = args.serial or (devices[0].serial if len(devices) == 1 else None)
    if serial is None:
        print("→ Có nhiều thiết bị, chạy lại với serial cụ thể: emu-sync doctor <serial>")
        return 0
    if serial not in {d.serial for d in devices}:
        print(f"→ Không thấy {serial} trong adb devices")
        return 1

    print(f"\n== 2) Thiết bị {serial} ==")
    device = adbmod.get_device(serial)

    def shell_echo() -> str:
        out = device.shell("echo ok").strip()
        if "ok" not in out:
            raise RuntimeError(f"phản hồi lạ: {out!r}")
        return "shell phản hồi OK"

    if not step("shell", shell_echo):
        return 1

    def size() -> str:
        w, h = adbmod.display_size(device)
        return f"{w}x{h}"

    step("wm size", size)

    def caps() -> str:
        found = discover_devices(device)
        touch = next((c for c in found if c.is_touch), None)
        if touch is None:
            raise RuntimeError("không thấy thiết bị cảm ứng (ABS_MT_POSITION_X/Y)")
        keyboard = next((c for c in found if c.is_keyboard), None)
        kb = f", bàn phím: {keyboard.path}" if keyboard else " (KHÔNG có bàn phím — AVD cần hw.keyboard=yes)"
        return f"cảm ứng: {touch.path}{kb}"

    step("getevent", caps)

    def push() -> str:
        jar = adbmod.push_server(device)
        return f"đã push {jar.name} → {C.SERVER_DEVICE_PATH}"

    if not step("push scrcpy-server", push):
        return 1

    print("\n== 3) Mở thử session control-only ==")
    try:
        session = ControlSession(device)
        session.start()
        print(f"[OK]  scrcpy-server kết nối ✓ (thiết bị: {session.device_name!r})")
        session.stop()
    except Exception as e:
        print(f"[LỖI] {e}")
        print(
            "\n→ Gợi ý: 1) thử lại (máy ảo có thể đang bận lúc khởi động); "
            "2) kiểm tra version jar khớp (scripts/fetch_scrcpy_server.sh); "
            "3) thử giả lập khác/xem log server ở trên."
        )
        return 1

    print("\nKẾT QUẢ: mọi bước OK ✅")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="emu-sync", description="Đồng bộ thao tác giữa nhiều giả lập Android (giai đoạn M1)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log chi tiết")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("devices", help="liệt kê thiết bị ADB + kích thước màn hình")
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("tap", help="tap vào toạ độ pixel trên 1 thiết bị")
    p.add_argument("serial")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("--hold", type=float, default=0.05, help="thời gian giữ (giây), mặc định 0.05")
    p.set_defaults(func=cmd_tap)

    p = sub.add_parser("scroll", help="scroll tại toạ độ trên 1 thiết bị")
    p.add_argument("serial")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("dy", type=float, help="trong [-16, 16]; thử để chốt dấu")
    p.add_argument("--repeat", type=int, default=1)
    p.set_defaults(func=cmd_scroll)

    p = sub.add_parser("key", help="gửi keycode Android (vd 66=ENTER, 4=BACK)")
    p.add_argument("serial")
    p.add_argument("keycode", type=int)
    p.set_defaults(func=cmd_key)

    p = sub.add_parser("back", help="gửi BACK (back_or_screen_on)")
    p.add_argument("serial")
    p.set_defaults(func=cmd_back)

    p = sub.add_parser("text", help="gõ text vào máy (ASCII; dấu tiếng Việt có thể không vào được)")
    p.add_argument("serial")
    p.add_argument("text")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("sniff", help="in event input parse được từ 1 thiết bị (debug)")
    p.add_argument("serial")
    p.set_defaults(func=cmd_sniff)

    p = sub.add_parser("doctor", help="kiểm tra từng bước kết nối tới thiết bị (debug)")
    p.add_argument("serial", nargs="?")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("run", help="đồng bộ thao tác từ master sang các target")
    p.add_argument("--master", required=True, help="serial máy master (máy bạn thao tác)")
    p.add_argument("--targets", help="các serial cách nhau bởi dấu phẩy (mặc định: mọi máy còn lại)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("ui", help="panel web quản lý (preview, master, toggle sync)")
    p.add_argument("--host", default="127.0.0.1", help="mặc định 127.0.0.1 (dùng 0.0.0.0 để truy cập từ xa)")
    p.add_argument("--port", type=int, default=8899)
    p.add_argument("--master", help="serial master ban đầu (mặc định: máy đầu tiên)")
    p.add_argument("--hotkey", default=DEFAULT_HOTKEY, help="phím tắt bật/tắt đồng bộ; 'none' để tắt")
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("app", help="desktop app (cửa sổ native, cùng panel với `ui`)")
    p.add_argument("--port", type=int, default=8899)
    p.add_argument("--master", help="serial master ban đầu (mặc định: máy đầu tiên)")
    p.add_argument("--hotkey", default=DEFAULT_HOTKEY, help="phím tắt bật/tắt đồng bộ; 'none' để tắt")
    p.set_defaults(func=cmd_app)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
