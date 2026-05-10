from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from storage.database import Database, TrackRecord
from utils.config import Settings, get_settings

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = Database(settings.database_path)
    await db.connect()
    app.state.db = db
    app.state.settings = settings
    logger.info("Admin UI connected to %s", settings.database_path)
    yield
    await db.close()


app = FastAPI(title="TG Music bot — Admin", lifespan=lifespan)


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def verify_admin(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> None:
    if not settings.admin_secret:
        return
    token = request.query_params.get("token")
    header = request.headers.get("X-Admin-Token")
    if token == settings.admin_secret or header == settings.admin_secret:
        return
    raise HTTPException(status_code=401, detail="Invalid or missing admin token")


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    _: None = Depends(verify_admin),
    db: Database = Depends(get_db),
) -> HTMLResponse:
    queue = await db.list_queue(limit=100)
    tracks = await db.list_all_tracks(limit=200)
    stats = await db.count_by_status()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "queue": queue,
            "tracks": tracks,
            "stats": stats,
            "need_token": bool(request.app.state.settings.admin_secret),
        },
    )


@app.get("/api/queue")
async def api_queue(
    _: None = Depends(verify_admin),
    db: Database = Depends(get_db),
) -> list[dict]:
    return [_track_to_dict(t) for t in await db.list_queue(500)]


@app.get("/api/tracks")
async def api_tracks(
    _: None = Depends(verify_admin),
    db: Database = Depends(get_db),
) -> list[dict]:
    return [_track_to_dict(t) for t in await db.list_all_tracks(500)]


def _track_to_dict(t: TrackRecord) -> dict:
    return {
        "id": t.id,
        "telegram_user_id": t.telegram_user_id,
        "url": t.url,
        "title": t.title,
        "artist": t.artist,
        "stored_filename": t.stored_filename,
        "file_size_bytes": t.file_size_bytes,
        "mime_type": t.mime_type,
        "status": t.status.value,
        "error_message": t.error_message,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }
