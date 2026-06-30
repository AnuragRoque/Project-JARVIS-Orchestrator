"""Secure localhost API server for browser extensions.

The server binds to 127.0.0.1 only and requires a shared bearer token that is
generated on first run and stored in the data directory. The bundled extension
reads the same token (the user pastes it once into the extension options).

Endpoints
---------
GET  /api/health            -> liveness (no auth)
GET  /api/status            -> tracking flags (auth)
POST /api/visit             -> record one browser visit (auth)
POST /api/visits            -> record a batch of visits (auth)

Runs uvicorn in a background daemon thread so it coexists with the Qt UI.
"""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import DATA_DIR, get_config
from ..logging_setup import get_logger
from ..storage import get_repository

log = get_logger("api.server")

_TOKEN_PATH = DATA_DIR / "api_token.txt"


def get_api_token() -> str:
    """Load the API token, generating and persisting one on first use."""
    if _TOKEN_PATH.exists():
        tok = _TOKEN_PATH.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(24)
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(tok, encoding="utf-8")
    log.info("Generated new API token at %s", _TOKEN_PATH)
    return tok


def _parse_ts(value: str | float | None) -> datetime:
    """Accept ISO strings or epoch millis; return naive UTC."""
    if value is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc) \
            .replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


class Visit(BaseModel):
    url: str
    title: str = ""
    browser: str = ""
    activated: str | float | None = None
    closed: str | float | None = None


class VisitBatch(BaseModel):
    visits: list[Visit]


def create_app(token: str) -> FastAPI:
    app = FastAPI(title="Windows Activity Recall API", version="1.0")
    repo = get_repository()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # extension origins; still token-gated
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def auth(x_recall_token: str = Header(default="")) -> None:
        if not secrets.compare_digest(x_recall_token, token):
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "service": "windows-activity-recall"}

    @app.get("/api/status", dependencies=[Depends(auth)])
    def status() -> dict:
        cfg = get_config()
        return {
            "tracking_enabled": cfg.tracking_enabled,
            "browser_tracking_enabled": cfg.browser_tracking_enabled,
            "private_mode": cfg.private_mode,
        }

    def _record(v: Visit) -> bool:
        cfg = get_config()
        if cfg.private_mode or not cfg.browser_tracking_enabled:
            return False
        vid = repo.record_browser_visit(
            url=v.url, title=v.title, browser=v.browser or "unknown",
            tab_activated=_parse_ts(v.activated),
            tab_closed=_parse_ts(v.closed) if v.closed else None,
            source="extension",
        )
        return vid is not None

    @app.post("/api/visit", dependencies=[Depends(auth)])
    def visit(v: Visit) -> dict:
        return {"recorded": _record(v)}

    @app.post("/api/visits", dependencies=[Depends(auth)])
    def visits(batch: VisitBatch) -> dict:
        n = sum(1 for v in batch.visits if _record(v))
        return {"recorded": n, "received": len(batch.visits)}

    return app


class ApiServer:
    """Runs the FastAPI app via uvicorn in a background thread."""

    def __init__(self):
        self.token = get_api_token()
        self._thread: threading.Thread | None = None
        self._server = None  # uvicorn.Server

    def start(self) -> None:
        import uvicorn

        cfg = get_config()
        app = create_app(self.token)
        config = uvicorn.Config(
            app, host=cfg.api_host, port=cfg.api_port,
            log_level="warning", access_log=False,
        )
        self._server = uvicorn.Server(config)
        # Prevent uvicorn from installing signal handlers off the main thread.
        self._server.install_signal_handlers = False

        self._thread = threading.Thread(
            target=self._server.run, name="api", daemon=True)
        self._thread.start()
        log.info("Browser API listening on http://%s:%d (token in %s)",
                 cfg.api_host, cfg.api_port, _TOKEN_PATH)

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Browser API stopped")
