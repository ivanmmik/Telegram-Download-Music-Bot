from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class TrackStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(slots=True)
class TrackRecord:
    id: int
    telegram_user_id: int
    url: str
    title: str | None
    artist: str | None
    stored_filename: str | None
    file_size_bytes: int | None
    mime_type: str | None
    status: TrackStatus
    error_message: str | None
    created_at: str
    updated_at: str


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._init_schema()
        await self._db.commit()
        logger.info("SQLite ready at %s", self._path)

    async def close(self) -> None:
        await self._db.close()

    async def _init_schema(self) -> None:
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                stored_filename TEXT,
                file_size_bytes INTEGER,
                mime_type TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tracks_user ON tracks(telegram_user_id);
            CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
            """
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def insert_track(
        self,
        telegram_user_id: int,
        url: str,
        status: TrackStatus = TrackStatus.PENDING,
        error_message: str | None = None,
    ) -> int:
        now = self._now()
        cur = await self._db.execute(
            """
            INSERT INTO tracks (
                telegram_user_id, url, status, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (telegram_user_id, url, status.value, error_message, now, now),
        )
        await self._db.commit()
        return int(cur.lastrowid)

    async def update_track(
        self,
        track_id: int,
        *,
        status: TrackStatus | None = None,
        title: str | None = None,
        artist: str | None = None,
        stored_filename: str | None = None,
        file_size_bytes: int | None = None,
        mime_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status.value)
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if artist is not None:
            fields.append("artist = ?")
            values.append(artist)
        if stored_filename is not None:
            fields.append("stored_filename = ?")
            values.append(stored_filename)
        if file_size_bytes is not None:
            fields.append("file_size_bytes = ?")
            values.append(file_size_bytes)
        if mime_type is not None:
            fields.append("mime_type = ?")
            values.append(mime_type)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        fields.append("updated_at = ?")
        values.append(self._now())
        values.append(track_id)
        await self._db.execute(
            f"UPDATE tracks SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await self._db.commit()

    async def list_tracks_for_user(
        self, telegram_user_id: int, limit: int = 30
    ) -> list[TrackRecord]:
        cur = await self._db.execute(
            """
            SELECT * FROM tracks
            WHERE telegram_user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (telegram_user_id, limit),
        )
        rows = await cur.fetchall()
        return [self._row_to_track(r) for r in rows]

    async def get_track(self, track_id: int, telegram_user_id: int) -> TrackRecord | None:
        cur = await self._db.execute(
            "SELECT * FROM tracks WHERE id = ? AND telegram_user_id = ?",
            (track_id, telegram_user_id),
        )
        row = await cur.fetchone()
        return self._row_to_track(row) if row else None

    async def delete_track(self, track_id: int, telegram_user_id: int) -> bool:
        cur = await self._db.execute(
            "DELETE FROM tracks WHERE id = ? AND telegram_user_id = ?",
            (track_id, telegram_user_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def list_queue(self, limit: int = 100) -> list[TrackRecord]:
        cur = await self._db.execute(
            """
            SELECT * FROM tracks
            WHERE status IN ('pending', 'downloading')
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        return [self._row_to_track(r) for r in rows]

    async def list_all_tracks(self, limit: int = 200) -> list[TrackRecord]:
        cur = await self._db.execute(
            "SELECT * FROM tracks ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [self._row_to_track(r) for r in rows]

    async def count_by_status(self) -> dict[str, int]:
        cur = await self._db.execute(
            "SELECT status, COUNT(*) AS c FROM tracks GROUP BY status"
        )
        rows = await cur.fetchall()
        return {str(r["status"]): int(r["c"]) for r in rows}

    def _row_to_track(self, row: aiosqlite.Row) -> TrackRecord:
        return TrackRecord(
            id=int(row["id"]),
            telegram_user_id=int(row["telegram_user_id"]),
            url=str(row["url"]),
            title=row["title"],
            artist=row["artist"],
            stored_filename=row["stored_filename"],
            file_size_bytes=row["file_size_bytes"],
            mime_type=row["mime_type"],
            status=TrackStatus(row["status"]),
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
