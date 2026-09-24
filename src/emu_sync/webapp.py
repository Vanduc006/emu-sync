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
