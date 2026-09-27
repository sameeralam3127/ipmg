"""FastAPI application powering the IPMG dashboard.

Everything is served locally: the REST API under /api/v1, a WebSocket for
live scan progress, and the bundled frontend (no CDN assets, fully offline).
The API contract (models, errors, versioning) is described in docs/API.md.
"""

from __future__ import annotations

import asyncio
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Security,
    UploadFile,
    WebSocket,
)
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from ipmg import __version__
from ipmg.core.diff import DiffOptions
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.core.portscan import decode_ports
from ipmg.exceptions import FileIOError, HistoryError, ReportError
from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database
from ipmg.infrastructure.file_io import (
    SUPPORTED_INPUT_SUFFIXES,
    load_targets,
    parse_manual_targets,
    render_report,
)
from ipmg.reporting.diff_report import DIFF_FORMATS, render_diff
from ipmg.reporting.frames import ReportTable, results_table
from ipmg.services.history_service import HistoryService
from ipmg.web.manager import OVERFLOW, ScanManager
from ipmg.web.schemas import (
    Asset,
    ErrorResponse,
    HostResultRow,
    ScanCancelled,
    ScanCreated,
    ScanDiffModel,
    ScanRequest,
    ScanSummary,
    Stats,
    UploadResult,
    websocket_event_schemas,
)

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

AUTH_ERROR = (
    "Missing or invalid access token. Open IPMG Web with the link that "
    "'ipmg web' printed when it started."
)


#: WebSocket subprotocol the server answers with. Browsers cannot set headers
#: on a WebSocket, so the client offers ``ipmg`` plus ``ipmg.token.<token>``.
WS_SUBPROTOCOL = "ipmg"
_WS_AUTH_PREFIX = "ipmg.token."


#: Declares the Bearer scheme in /openapi.json (and the Authorize button in
#: /docs). It never rejects a request itself; :func:`_require_token` does.
_BEARER_SCHEME = HTTPBearer(
    auto_error=False, description="The access token from the link 'ipmg web' prints"
)


def _bearer_token(headers: Mapping[str, str]) -> Optional[str]:
    """The token from an ``Authorization: Bearer`` header.

    Tokens are never read from the URL: query strings end up in access logs,
    proxy logs, and browser history.
    """
    scheme, _, credentials = headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return None


def _websocket_token(websocket: WebSocket) -> Optional[str]:
    """A Bearer header (non-browser clients) or the ``ipmg.token.`` subprotocol."""
    token = _bearer_token(websocket.headers)
    if token is not None:
        return token
    for protocol in websocket.scope.get("subprotocols", []):
        if protocol.startswith(_WS_AUTH_PREFIX):
            return protocol[len(_WS_AUTH_PREFIX) :]
    return None


def _token_valid(supplied: Optional[str], expected: str) -> bool:
    return supplied is not None and secrets.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
    )


def _require_token(expected: str) -> Callable[[Request], None]:
    """FastAPI dependency that rejects API requests without the access token.

    Every API route requires it, on loopback too: it stops other users on the
    machine, web pages attempting CSRF, and DNS-rebinding attacks from driving
    the scanner, and makes a non-loopback --host safe to use.
    """

    def check(
        request: Request,
        _credentials: Optional[HTTPAuthorizationCredentials] = Security(_BEARER_SCHEME),
    ) -> None:
        if not _token_valid(_bearer_token(request.headers), expected):
            raise HTTPException(
                status_code=401, detail=AUTH_ERROR, headers={"WWW-Authenticate": "Bearer"}
            )

    return check


API_DESCRIPTION = """\
The HTTP API behind the IPMG dashboard. See docs/API.md for a guide.

* **Authentication:** every request needs `Authorization: Bearer <token>`, using
  the token from the link `ipmg web` prints when it starts.
* **Errors:** every 4xx/5xx response has an `ErrorResponse` body.
* **Versioning:** `/api/v1` only changes additively; breaking changes go to `/api/v2`.
* **Live events:** `GET /api/v1/ws` (WebSocket) sends `WebSocketEvent` messages;
  their schemas are under `components.schemas`.
"""

#: Error responses shared by every API route.
_COMMON_ERRORS: Dict[Union[int, str], Dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
    422: {"model": ErrorResponse, "description": "Request failed validation"},
}


def _errors(*codes: int) -> Dict[Union[int, str], Dict[str, Any]]:
    descriptions = {
        400: "Invalid request",
        404: "Scan not found",
        409: "Scan is not running",
        413: "Upload too large",
    }
    return {code: {"model": ErrorResponse, "description": descriptions[code]} for code in codes}


def _file_response(media_types: Mapping[str, str], description: str) -> Dict[int, Dict[str, Any]]:
    """OpenAPI entry for a 200 response that is a file download."""
    binary = {"schema": {"type": "string", "format": "binary"}}
    return {200: {"description": description, "content": {m: binary for m in media_types.values()}}}


def _parse_scan_targets(request: ScanRequest) -> List[str]:
    try:
        if request.ips:
            return parse_manual_targets("\n".join(request.ips))
        if request.targets:
            return parse_manual_targets(request.targets)
        raise FileIOError("Provide 'targets' text or an 'ips' list.")
    except FileIOError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _results_table(scan: Dict[str, Any], rows: List[Dict[str, Any]]) -> ReportTable:
    results = [
        HostResult(
            ip=row["ip"],
            status=row["status"],
            latency=row["latency"],
            hostname=row["hostname"] or "",
            open_ports=decode_ports(row.get("open_ports") or ""),
        )
        for row in rows
    ]
    return results_table(results, scan["started_at"], scan["duration_s"])


def _render_report(table: ReportTable, fmt: str) -> bytes:
    # The CLI's own writers, so a download matches the file a scan saves.
    return render_report(table, fmt)


def _parse_upload(filename: str, payload: bytes) -> List[str]:
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_INPUT_SUFFIXES:
        raise FileIOError(
            f"Unsupported file type '{suffix or '<none>'}'. Supported: "
            f"{', '.join(sorted(SUPPORTED_INPUT_SUFFIXES))}."
        )

    # Every supported type, JSON included, goes through the CLI loader, so an
    # upload and an --input file are parsed by exactly the same code.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
        temp_path = handle.name
    try:
        return load_targets(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _register_overview_routes(api: APIRouter, database: Database) -> None:
    @api.get("/stats", response_model=Stats, summary="Dashboard overview")
    def stats() -> Dict[str, Any]:
        return database.overview()

    @api.get("/assets", response_model=List[Asset], summary="Every host ever scanned")
    def assets() -> List[Dict[str, Any]]:
        return database.inventory()

    @api.get("/scans", response_model=List[ScanSummary], summary="Recent scans, newest first")
    def list_scans(
        limit: int = Query(50, description="Maximum scans to return (clamped to 1-500)"),
    ) -> List[Dict[str, Any]]:
        return database.list_scans(limit=max(1, min(limit, 500)))


def _register_scan_routes(api: APIRouter, database: Database, manager: ScanManager) -> None:
    @api.post(
        "/scans",
        status_code=201,
        response_model=ScanCreated,
        responses=_errors(400),
        summary="Start a scan",
    )
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

    @api.get(
        "/scans/{scan_id}", response_model=ScanSummary, responses=_errors(404), summary="One scan"
    )
    def get_scan(scan_id: int) -> Dict[str, Any]:
        scan = database.get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return scan

    @api.get(
        "/scans/{scan_id}/results",
        response_model=List[HostResultRow],
        responses=_errors(404),
        summary="Per-host results of a scan",
    )
    def get_results(
        scan_id: int,
        status: Optional[str] = Query(None, description="Only this status, e.g. 'Active'"),
        search: Optional[str] = Query(None, description="Substring of the IP or hostname"),
    ) -> List[Dict[str, Any]]:
        if database.get_scan(scan_id) is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return database.get_results(scan_id, status=status, search=search)

    @api.post(
        "/scans/{scan_id}/cancel",
        response_model=ScanCancelled,
        responses=_errors(409),
        summary="Stop a running scan",
    )
    def cancel_scan(scan_id: int) -> Dict[str, Any]:
        if not manager.cancel(scan_id):
            raise HTTPException(status_code=409, detail="Scan is not running")
        return {"id": scan_id, "cancelling": True}

    @api.delete(
        "/scans/{scan_id}",
        status_code=204,
        response_class=Response,
        responses=_errors(404),
        summary="Delete a scan and its results",
    )
    def delete_scan(scan_id: int) -> Response:
        if not database.delete_scan(scan_id):
            raise HTTPException(status_code=404, detail="Scan not found")
        return Response(status_code=204)


def _register_report_routes(api: APIRouter, database: Database) -> None:
    @api.get(
        "/scans/{scan_id}/report",
        response_class=Response,
        responses={
            **_file_response(REPORT_MEDIA_TYPES, "The report as a file download"),
            **_errors(400, 404),
        },
        summary="Download a scan report",
    )
    def download_report(
        scan_id: int,
        fmt: str = Query("csv", description="One of: " + ", ".join(REPORT_MEDIA_TYPES)),
    ) -> Response:
        if fmt not in REPORT_MEDIA_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

        scan = database.get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found")

        table = _results_table(scan, database.get_results(scan_id))
        content = _render_report(table, fmt)

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

    baseline_query = Query(
        None, description="Scan to compare against; defaults to the previous comparable scan"
    )
    threshold_query = Query(5.0, description="Minimum latency change to report, in ms")
    pct_query = Query(25.0, description="Minimum latency change to report, in percent")

    @api.get(
        "/scans/{scan_id}/diff",
        response_model=ScanDiffModel,
        responses=_errors(404),
        summary="Compare a scan with a baseline",
    )
    def scan_diff(
        scan_id: int,
        baseline: Optional[int] = baseline_query,
        latency_threshold: float = threshold_query,
        latency_pct: float = pct_query,
    ) -> Dict[str, Any]:
        return _diff(scan_id, baseline, latency_threshold, latency_pct).to_dict()

    @api.get(
        "/scans/{scan_id}/diff/report",
        response_class=Response,
        responses={
            **_file_response(DIFF_MEDIA_TYPES, "The change report as a file download"),
            **_errors(400, 404),
        },
        summary="Download a change report",
    )
    def scan_diff_report(
        scan_id: int,
        fmt: str = Query("md", description="One of: " + ", ".join(DIFF_FORMATS)),
        baseline: Optional[int] = baseline_query,
        latency_threshold: float = threshold_query,
        latency_pct: float = pct_query,
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
    @api.post(
        "/upload",
        response_model=UploadResult,
        responses=_errors(400, 413),
        summary="Parse targets from a file",
    )
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


def _register_websocket(app: FastAPI, manager: ScanManager, token: str) -> None:
    @app.websocket("/api/v1/ws")
    async def websocket_events(websocket: WebSocket) -> None:
        if not _origin_allowed(websocket) or not _token_valid(_websocket_token(websocket), token):
            await websocket.close(code=1008)
            return

        offered = websocket.scope.get("subprotocols", [])
        await websocket.accept(subprotocol=WS_SUBPROTOCOL if WS_SUBPROTOCOL in offered else None)
        queue = manager.subscribe()

        async def forward_events() -> None:
            while True:
                event = await queue.get()
                if event is OVERFLOW:
                    # 1013 "try again later": the client fell too far behind.
                    await websocket.close(code=1013)
                    return
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


def _register_error_handlers(app: FastAPI) -> None:
    """Give every error the one :class:`ErrorResponse` shape."""

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> Response:
        body = ErrorResponse(detail=str(exc.detail))
        return JSONResponse(
            body.model_dump(exclude_none=True),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> Response:
        issues = [
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
            for error in exc.errors()
        ]
        first = issues[0] if issues else None
        summary = "Invalid request"
        if first:
            where = ".".join(str(part) for part in first["loc"])
            summary = f"Invalid request: {where}: {first['msg']}"
        body = ErrorResponse(detail=summary, errors=issues)
        return JSONResponse(body.model_dump(), status_code=422)


def _install_openapi(app: FastAPI) -> None:
    """Add the WebSocket event schemas, which FastAPI cannot infer, to ``/openapi.json``."""

    def openapi() -> Dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            components.update(websocket_event_schemas("#/components/schemas/{model}"))
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(db: Optional[Database] = None, token: Optional[str] = None) -> FastAPI:
    """Build the app. ``token`` guards every API route; a random one is made if omitted."""
    database = db if db is not None else Database(DEFAULT_DB_PATH)
    token = token or secrets.token_urlsafe(32)
    manager = ScanManager(database)
    history = HistoryService(database)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        manager.attach_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(
        title="IPMG Web", version=__version__, description=API_DESCRIPTION, lifespan=lifespan
    )
    app.state.db = database
    app.state.manager = manager
    app.state.history = history
    app.state.token = token

    api = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(_require_token(token))],
        responses=_COMMON_ERRORS,
    )
    _register_overview_routes(api, database)
    _register_scan_routes(api, database, manager)
    _register_report_routes(api, database)
    _register_diff_routes(api, history)
    _register_upload_route(api)
    app.include_router(api)

    _register_websocket(app, manager, token)
    _register_error_handlers(app)
    _install_openapi(app)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
