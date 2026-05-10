import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiogram import Bot, Dispatcher

from bot.handlers import setup_routers
from bot.middlewares import InjectMiddleware
from services.download_service import DownloadService
from storage.database import Database
from utils.config import get_settings
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.bot_token.strip():
        raise SystemExit("Укажите BOT_TOKEN в .env для запуска бота.")
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(settings.database_path)
    await db.connect()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    download_service = DownloadService(settings)
    dp.message.middleware(InjectMiddleware(settings, db, download_service))
    dp.include_router(setup_routers())

    logger.info("Starting polling…")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
