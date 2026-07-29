"""FastAPI application powering the IPMG dashboard.

Everything is served locally: the REST API under /api/v1, a WebSocket for
live scan progress, and the bundled frontend (no CDN assets, fully offline).
"""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException, UploadFile, WebSocket
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from ipmg import __version__
from ipmg.core.diff import DiffOptions
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.exceptions import FileIOError, HistoryError, ReportError
from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database
from ipmg.infrastructure.file_io import (
    SUPPORTED_INPUT_SUFFIXES,
    build_markdown_report,
    load_targets,
    parse_manual_targets,
)
from ipmg.reporting.diff_report import DIFF_FORMATS, render_diff
from ipmg.reporting.frames import results_dataframe
from ipmg.services.history_service import HistoryService
from ipmg.web.manager import ScanManager

STATIC_DIR = Path(__file__).parent / "static"

#: Uploaded target files are small by nature; cap them so a single request
#: cannot exhaust memory on the machine running the dashboard.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

REPORT_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "json": "application/json",
    "md": "text/markdown",
}

DIFF_MEDIA_TYPES = {fmt: REPORT_MEDIA_TYPES[fmt] for fmt in DIFF_FORMATS}

#: Hostnames that count as "this machine" when checking WebSocket origins.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class ScanRequest(BaseModel):
    targets: Optional[str] = Field(default=None, description="Free-form target text")
    ips: Optional[List[str]] = Field(default=None, description="Pre-parsed IP list")
    source: str = "manual"
    timeout: int = 2
    count: int = 1
    threads: int = 50
    resolve: bool = False
    dns_cache_ttl: int = 300


def _targets_from_json(data: Any) -> List[str]:
    if isinstance(data, dict):
        data = data.get("targets") or data.get("ips") or []
    if not isinstance(data, list):
        raise FileIOError("JSON uploads must contain a list of targets.")

    lines = []
    for entry in data:
        if isinstance(entry, str):
            lines.append(entry)
        elif isinstance(entry, dict):
            value = entry.get("IP Address") or entry.get("ip") or entry.get("target")
            if value:
                lines.append(str(value))
    return parse_manual_targets("\n".join(lines))


def _parse_scan_targets(request: ScanRequest) -> List[str]:
    try:
        if request.ips:
            return parse_manual_targets("\n".join(request.ips))
        if request.targets:
            return parse_manual_targets(request.targets)
        raise FileIOError("Provide 'targets' text or an 'ips' list.")
    except FileIOError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _results_dataframe(scan: Dict[str, Any], rows: List[Dict[str, Any]]) -> pd.DataFrame:
    results = [
        HostResult(
            ip=row["ip"],
            status=row["status"],
            latency=row["latency"],
            hostname=row["hostname"] or "",
        )
        for row in rows
    ]
    return results_dataframe(results, scan["started_at"], scan["duration_s"])


def _render_report(df: pd.DataFrame, fmt: str) -> bytes:
    if fmt == "xlsx":
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        return buffer.getvalue()
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8")
    if fmt == "json":
        return df.to_json(orient="records").encode("utf-8")
    return build_markdown_report(df).encode("utf-8")


def _parse_upload(filename: str, payload: bytes) -> List[str]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".json":
        return _targets_from_json(json.loads(payload.decode("utf-8")))

    if suffix in SUPPORTED_INPUT_SUFFIXES:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(payload)
            temp_path = handle.name
        try:
            return load_targets(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    raise FileIOError(
        f"Unsupported file type '{suffix or '<none>'}'. Supported: "
        f"{', '.join(sorted(SUPPORTED_INPUT_SUFFIXES | {'.json'}))}."
    )


def _register_overview_routes(api: APIRouter, database: Database) -> None:
    @api.get("/stats")
    def stats() -> Dict[str, Any]:
        return database.overview()

    @api.get("/assets")
    def assets() -> List[Dict[str, Any]]:
        return database.inventory()

    @api.get("/scans")
    def list_scans(limit: int = 50) -> List[Dict[str, Any]]:
        return database.list_scans(limit=max(1, min(limit, 500)))


def _register_scan_routes(api: APIRouter, database: Database, manager: ScanManager) -> None:
    @api.post("/scans", status_code=201)
    def create_scan(request: ScanRequest) -> Dict[str, Any]:
        ips = _parse_scan_targets(request)
        config = ScanConfig(
            timeout=request.timeout,
            count=request.count,
            threads=request.threads,
            resolve=request.resolve,
            dns_cache_ttl=request.dns_cache_ttl,
        ).clamped()
        scan_id = manager.start_scan(ips, config, source=request.source)
        return {"id": scan_id, "total": len(ips)}

    @api.get("/scans/{scan_id}")
    def get_scan(scan_id: int) -> Dict[str, Any]:
        scan = database.get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return scan

    @api.get("/scans/{scan_id}/results")
    def get_results(
        scan_id: int,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if database.get_scan(scan_id) is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return database.get_results(scan_id, status=status, search=search)

    @api.post("/scans/{scan_id}/cancel")
    def cancel_scan(scan_id: int) -> Dict[str, Any]:
        if not manager.cancel(scan_id):
            raise HTTPException(status_code=409, detail="Scan is not running")
        return {"id": scan_id, "cancelling": True}

    @api.delete("/scans/{scan_id}", status_code=204)
    def delete_scan(scan_id: int) -> Response:
        if not database.delete_scan(scan_id):
            raise HTTPException(status_code=404, detail="Scan not found")
        return Response(status_code=204)


def _register_report_routes(api: APIRouter, database: Database) -> None:
    @api.get("/scans/{scan_id}/report")
    def download_report(scan_id: int, fmt: str = "csv") -> Response:
        if fmt not in REPORT_MEDIA_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

        scan = database.get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")

        df = _results_dataframe(scan, database.get_results(scan_id))
        content = _render_report(df, fmt)

        timestamp = str(scan["started_at"]).replace(" ", "_").replace(":", "")
        filename = f"ipmg_scan_{scan_id}_{timestamp}.{fmt}"
        return Response(
            content=content,
            media_type=REPORT_MEDIA_TYPES[fmt],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload, refusing anything above :data:`MAX_UPLOAD_BYTES`."""
    chunks: List[bytes] = []
    size = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _register_diff_routes(api: APIRouter, history: HistoryService) -> None:
    def _diff(
        scan_id: int,
        baseline: Optional[int],
        latency_threshold: float,
        latency_pct: float,
    ):
        options = DiffOptions(
            latency_abs_ms=max(latency_threshold, 0.0),
            latency_pct=max(latency_pct, 0.0),
        )
        try:
            if baseline is None:
                return history.compare_with_previous(scan_id, options=options)
            return history.compare(baseline, scan_id, options=options)
        except HistoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.get("/scans/{scan_id}/diff")
    def scan_diff(
        scan_id: int,
        baseline: Optional[int] = None,
        latency_threshold: float = 5.0,
        latency_pct: float = 25.0,
    ) -> Dict[str, Any]:
        return _diff(scan_id, baseline, latency_threshold, latency_pct).to_dict()

    @api.get("/scans/{scan_id}/diff/report")
    def scan_diff_report(
        scan_id: int,
        fmt: str = "md",
        baseline: Optional[int] = None,
        latency_threshold: float = 5.0,
        latency_pct: float = 25.0,
    ) -> Response:
        if fmt not in DIFF_MEDIA_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {fmt}. Supported: {', '.join(DIFF_FORMATS)}.",
            )

        diff = _diff(scan_id, baseline, latency_threshold, latency_pct)
        try:
            content = render_diff(diff, fmt)
        except ReportError as exc:  # pragma: no cover - guarded by the check above
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        baseline_id = diff.baseline.id if diff.baseline.id is not None else "baseline"
        filename = f"ipmg_changes_{baseline_id}_to_{scan_id}.{fmt}"
        return Response(
            content=content.encode("utf-8"),
            media_type=DIFF_MEDIA_TYPES[fmt],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def _register_upload_route(api: APIRouter) -> None:
    @api.post("/upload")
    async def upload_targets(file: UploadFile) -> Dict[str, Any]:
        payload = await _read_upload(file)
        try:
            targets = _parse_upload(file.filename or "", payload)
        except FileIOError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            # Corrupt uploads raise parser-specific errors (BadZipFile,
            # ParserError, ...); every one of them is a client error, not a 500.
            raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}") from exc

        return {"filename": file.filename, "count": len(targets), "targets": targets}


def _origin_allowed(websocket: WebSocket) -> bool:
    """Reject cross-site WebSocket connections.

    Browsers do not apply the same-origin policy to WebSockets, so without
    this check any web page could connect to the local dashboard and read
    live scan results. Non-browser clients (no Origin header) are allowed.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    try:
        origin_host = urlsplit(origin).hostname
    except ValueError:
        return False
    server_host = websocket.url.hostname
    if origin_host == server_host:
        return True
    return origin_host in _LOOPBACK_HOSTS and server_host in _LOOPBACK_HOSTS


def _register_websocket(app: FastAPI, manager: ScanManager) -> None:
    @app.websocket("/api/v1/ws")
    async def websocket_events(websocket: WebSocket) -> None:
        if not _origin_allowed(websocket):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        queue = manager.subscribe()

        async def forward_events() -> None:
            while True:
                event = await queue.get()
                await websocket.send_json(event)

        forward_task = asyncio.create_task(forward_events())
        try:
            # Detect client disconnects promptly; the dashboard never sends
            # messages, so this loop only ends when the socket closes.
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            forward_task.cancel()
            manager.unsubscribe(queue)


def create_app(db: Optional[Database] = None) -> FastAPI:
    database = db if db is not None else Database(DEFAULT_DB_PATH)
    manager = ScanManager(database)
    history = HistoryService(database)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        manager.attach_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(title="IPMG Dashboard", version=__version__, lifespan=lifespan)
    app.state.db = database
    app.state.manager = manager
    app.state.history = history

    api = APIRouter(prefix="/api/v1")
    _register_overview_routes(api, database)
    _register_scan_routes(api, database, manager)
    _register_report_routes(api, database)
    _register_diff_routes(api, history)
    _register_upload_route(api)
    app.include_router(api)

    _register_websocket(app, manager)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
