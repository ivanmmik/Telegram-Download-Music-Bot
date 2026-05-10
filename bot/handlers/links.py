from aiogram import F, Router
from aiogram.types import Message

from bot.handlers.commands import _extract_url, _process_new_url
from services.download_service import DownloadService
from storage.database import Database
from utils.config import Settings

router = Router(name="links")


@router.message(F.text, ~F.text.startswith("/"))
async def handle_plain_link(
    message: Message,
    db: Database,
    download_service: DownloadService,
    settings: Settings,
) -> None:
    text = message.text or ""
    url = _extract_url(text)
    if not url:
        return
    if len(text) > len(url) + 2:
        return
    await _process_new_url(message, db, download_service, settings, url)
