from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.download_service import DownloadService
from storage.database import Database
from utils.config import Settings


class InjectMiddleware(BaseMiddleware):
    def __init__(
        self,
        settings: Settings,
        db: Database,
        download_service: DownloadService,
    ) -> None:
        self._settings = settings
        self._db = db
        self._download = download_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self._settings
        data["db"] = self._db
        data["download_service"] = self._download
        return await handler(event, data)
