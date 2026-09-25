"""FastAPI app cho panel quản lý emu-sync (preview ảnh + master + toggle sync)."""

from __future__ import annotations

from importlib import resources

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from .controller import SyncController


def _index_html() -> str:
    return resources.files("emu_sync").joinpath("static/index.html").read_text(encoding="utf-8")


def create_app(controller: SyncController) -> FastAPI:
    app = FastAPI(title="emu-sync", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _index_html()

    @app.get("/api/state")
    def state() -> dict:
        return controller.state()

    @app.post("/api/refresh")
    def refresh() -> dict:
        controller.refresh_devices(update_meta=True)
        return controller.state()

    @app.post("/api/run")
    def run(payload: dict) -> dict:
        enabled = bool(payload.get("enabled", True))
        if enabled:
            controller.start(payload.get("master"))
        else:
            controller.stop()
        return controller.state()

    @app.post("/api/master")
    def set_master(payload: dict) -> dict:
        serial = payload.get("serial")
        if not serial:
            raise HTTPException(400, "thiếu serial")
        try:
            controller.set_master(serial)
        except ValueError as e:
            raise HTTPException(404, str(e))
        return controller.state()

    @app.post("/api/sync")
    def set_sync(payload: dict) -> dict:
        serial = payload.get("serial")
        if not serial:
            raise HTTPException(400, "thiếu serial")
        try:
            controller.set_sync(serial, bool(payload.get("enabled", True)))
        except ValueError as e:
            raise HTTPException(404, str(e))
        return controller.state()

    @app.post("/api/session/restart")
    def restart_session(payload: dict) -> dict:
        serial = payload.get("serial")
        if not serial:
            raise HTTPException(400, "thiếu serial")
        controller.restart_session(serial)
        return controller.state()

    @app.post("/api/pause")
    def pause(payload: dict) -> dict:
        controller.set_paused(bool(payload.get("enabled", True)))
        return controller.state()

    @app.get("/api/avd/list")
    def avd_list() -> dict:
        return {"avds": controller.avds(), "images": controller.avd_images()}

    @app.post("/api/avd/create")
    def avd_create(payload: dict) -> dict:
        name = (payload.get("name") or "").strip()
        image = (payload.get("image") or "").strip()
        if not name or not image:
            raise HTTPException(400, "thiếu name/image")

        def _int(key: str) -> int | None:
            value = payload.get(key)
            return int(value) if value else None

        try:
            info = controller.avd_create(
                name=name,
                image=image,
                device=payload.get("device") or "pixel_6",
                ram_mb=_int("ram_mb"),
                cores=_int("cores"),
                width=_int("width"),
                height=_int("height"),
                dpi=_int("dpi"),
                keyboard=bool(payload.get("keyboard", True)),
            )
        except Exception as e:
            raise HTTPException(502, f"tạo AVD lỗi: {e}")
        return {"avd": info, **controller.state()}

    @app.post("/api/avd/start")
    def avd_start(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")
        try:
            pid = controller.avd_start(
                name,
                headless=bool(payload.get("headless", False)),
                cold=bool(payload.get("cold", False)),
            )
        except Exception as e:
            raise HTTPException(502, f"chạy AVD lỗi: {e}")
        return {"pid": pid}

    @app.post("/api/avd/stop")
    def avd_stop(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")
        try:
            controller.avd_stop(name)
        except Exception as e:
            raise HTTPException(502, f"tắt AVD lỗi: {e}")
        return controller.state()

    @app.post("/api/avd/delete")
    def avd_delete(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")
        try:
            controller.avd_delete(name)
        except Exception as e:
            raise HTTPException(502, f"xoá AVD lỗi: {e}")
        return controller.state()

    @app.post("/api/avd/snapshot")
    def avd_snapshot(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")
        try:
            output = controller.avd_save_state(name)
        except Exception as e:
            raise HTTPException(502, f"lưu state lỗi: {e}")
        return {"output": output}

    @app.post("/api/avd/config")
    def avd_config(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")

        def _int(key: str) -> int | None:
            value = payload.get(key)
            return int(value) if value else None

        keyboard = payload.get("keyboard")
        try:
            info = controller.avd_set_config(
                name,
                ram_mb=_int("ram_mb"),
                cores=_int("cores"),
                width=_int("width"),
                height=_int("height"),
                dpi=_int("dpi"),
                keyboard=bool(keyboard) if keyboard is not None else None,
            )
        except Exception as e:
            raise HTTPException(502, f"sửa cấu hình lỗi: {e}")
        return {"avd": info}

    @app.post("/api/avd/screen")
    def avd_screen(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")
        try:
            width = int(payload.get("width") or 0)
            height = int(payload.get("height") or 0)
            dpi = int(payload["dpi"]) if payload.get("dpi") else None
            result = controller.avd_apply_screen(
                name, width, height, dpi=dpi, persist=bool(payload.get("persist", True))
            )
        except Exception as e:
            raise HTTPException(502, f"đổi độ phân giải lỗi: {e}")
        return {"result": result, **controller.state()}

    @app.post("/api/avd/screen/reset")
    def avd_screen_reset(payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            raise HTTPException(400, "thiếu name")
        try:
            result = controller.avd_reset_screen(name, reset_density=bool(payload.get("reset_density", True)))
        except Exception as e:
            raise HTTPException(502, f"reset màn hình lỗi: {e}")
        return {"result": result, **controller.state()}

    @app.post("/api/connect")
    def connect(payload: dict) -> dict:
        address = (payload.get("address") or "").strip()
        if not address:
            raise HTTPException(400, "thiếu địa chỉ (vd 127.0.0.1:5555)")
        try:
            out = controller.connect(address)
        except Exception as e:
            raise HTTPException(502, f"adb connect lỗi: {e}")
        return {"output": out, **controller.state()}

    @app.post("/api/scan")
    def scan() -> dict:
        try:
            found = controller.scan_ports()
        except Exception as e:
            raise HTTPException(502, f"quét cổng lỗi: {e}")
        return {"found": found, **controller.state()}

    @app.post("/api/action")
    def action(payload: dict) -> dict:
        serial = payload.get("serial")
        act = payload.get("action")
        if not serial or not act:
            raise HTTPException(400, "thiếu serial/action")
        try:
            controller.perform_action(serial, act, payload.get("params") or {})
        except Exception as e:
            raise HTTPException(502, f"{act} lỗi: {e}")
        return {"ok": True}

    @app.post("/api/sniff")
    def sniff(payload: dict) -> dict:
        serial = payload.get("serial")
        if not serial:
            raise HTTPException(400, "thiếu serial")
        try:
            controller.set_sniff(serial, bool(payload.get("enabled", True)))
        except Exception as e:
            raise HTTPException(502, f"nghe input lỗi: {e}")
        return controller.state()

    @app.get("/api/events")
    def events(after: int = 0, serial: str | None = None) -> dict:
        return {"events": controller.events(after, serial)}

    @app.get("/api/preview/{serial}")
    def preview(serial: str) -> Response:
        try:
            data = controller.preview_jpeg(serial)
        except Exception as e:
            raise HTTPException(502, f"không chụp được {serial}: {e}")
        return Response(
            content=data,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    return app
