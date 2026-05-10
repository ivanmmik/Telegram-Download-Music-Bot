import logging
import re
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, Message

from services.download_service import DownloadService
from services.url_validator import UrlValidationError, validate_url_for_download, validate_url_string
from storage.database import Database, TrackStatus
from utils.config import Settings

logger = logging.getLogger(__name__)

router = Router(name="commands")

_URL_IN_TEXT = re.compile(r"https?://\S+", re.I)


def _extract_url(text: str) -> str | None:
    text = text.strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text.split()[0]
    m = _URL_IN_TEXT.search(text)
    return m.group(0).rstrip(").,]") if m else None


async def _process_new_url(message: Message, db: Database, download: DownloadService, settings: Settings, url: str) -> None:
    user_id = message.from_user.id if message.from_user else 0
    track_id = await db.insert_track(user_id, url, status=TrackStatus.PENDING)

    try:
        validate_url_string(url)
        validate_url_for_download(url, allowed_hosts=settings.allowed_host_set)
    except UrlValidationError as e:
        await db.update_track(track_id, status=TrackStatus.REJECTED, error_message=str(e))
        await message.answer(str(e))
        return

    await db.update_track(track_id, status=TrackStatus.DOWNLOADING)
    status_msg = await message.answer("Проверяю ссылку и загружаю файл…")

    try:
        result = await download.probe_and_download(url)
        title_guess = Path(result.filename).stem
        await db.update_track(
            track_id,
            status=TrackStatus.COMPLETED,
            title=title_guess,
            stored_filename=result.filename,
            file_size_bytes=result.size_bytes,
            mime_type=result.mime_type,
            error_message=None,
        )
        await status_msg.delete()
        # Build caption with metadata if available
        caption_parts = [f"Добавлено в TG Music bot (id {track_id})."]
        if result.title:
            caption_parts.append(f"🎵 {result.title}")
        if result.artist:
            caption_parts.append(f"👤 {result.artist}")
        caption = "\n".join(caption_parts)
        
        await message.answer_document(
            FSInputFile(result.path),
            caption=caption,
        )
    except (ValueError, OSError, TimeoutError) as e:
        logger.exception("Download failed for track %s", track_id)
        await db.update_track(
            track_id,
            status=TrackStatus.FAILED,
            error_message=str(e),
        )
        await status_msg.edit_text(f"Не удалось скачать файл: {e}")
    except Exception as e:  # noqa: BLE001 — last-resort user feedback
        logger.exception("Unexpected error for track %s", track_id)
        await db.update_track(
            track_id,
            status=TrackStatus.FAILED,
            error_message=str(e),
        )
        await status_msg.edit_text("Произошла ошибка при загрузке. Попробуйте позже.")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🎧 Привет! Я TG Music bot — бот для диджеев.\n\n"
        "Отправь ссылку на трек и я скачаю его в лучшем качестве:\n"
        "• YouTube / YouTube Music\n"
        "• SoundCloud\n" 
        "• Spotify\n"
        "• Яндекс.Музыка\n"
        "• Bandcamp\n\n"
        "Также поддерживаются прямые ссылки на .mp3, .flac и др.\n\n"
        "Команды: /help, /add, /list, /delete, /status"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🎧 TG Music Bot — скачивание музыки для диджеев\n\n"
        "Поддерживаемые платформы:\n"
        "• YouTube / YouTube Music\n"
        "• SoundCloud\n"
        "• Spotify\n"
        "• Яндекс.Музыка\n"
        "• Bandcamp\n"
        "• Прямые ссылки на .mp3, .flac, .wav\n\n"
        "Команды:\n"
        "/add <url> — скачать трек по ссылке\n"
        "/list — твоя библиотека (последние 20)\n"
        "/delete <id> — удалить трек по номеру\n"
        "/status — статистика\n\n"
        "Просто отправь ссылку сообщением — бот поймёт."
    )


@router.message(Command("add"))
async def cmd_add(
    message: Message,
    command: CommandObject,
    db: Database,
    download_service: DownloadService,
    settings: Settings,
) -> None:
    raw = (command.args or "").strip()
    url = _extract_url(raw) if raw else None
    if not url:
        await message.answer(
            "Отправь ссылку на трек:\n"
            "• YouTube: https://youtube.com/watch?v=...\n"
            "• SoundCloud: https://soundcloud.com/artist/track\n"
            "• Spotify: https://open.spotify.com/track/...\n"
            "• Яндекс.Музыка: https://music.yandex.ru/album/...\n"
            "• Или прямую ссылку на .mp3"
        )
        return
    await _process_new_url(message, db, download_service, settings, url)


@router.message(Command("list"))
async def cmd_list(message: Message, db: Database) -> None:
    user_id = message.from_user.id if message.from_user else 0
    rows = await db.list_tracks_for_user(user_id, limit=20)
    if not rows:
        await message.answer("Пока нет записей. Добавьте ссылку через /add или просто отправьте URL.")
        return
    lines = []
    for r in rows:
        lines.append(
            f"#{r.id} | {r.status.value} | {r.url[:60]}{'…' if len(r.url) > 60 else ''}"
        )
        if r.error_message and r.status.value in ("failed", "rejected"):
            lines.append(f"   └ {r.error_message[:120]}")
    await message.answer("\n".join(lines))


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, db: Database, settings: Settings) -> None:
    user_id = message.from_user.id if message.from_user else 0
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Использование: /delete <id> (номер из /list)")
        return
    tid = int(arg)
    track = await db.get_track(tid, user_id)
    if not track:
        await message.answer("Запись не найдена.")
        return
    if track.stored_filename:
        path = settings.download_dir / track.stored_filename
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not delete file %s: %s", path, e)
    deleted = await db.delete_track(tid, user_id)
    if deleted:
        await message.answer(f"Запись #{tid} удалена.")
    else:
        await message.answer("Не удалось удалить запись.")


@router.message(Command("status"))
async def cmd_status(message: Message, db: Database) -> None:
    user_id = message.from_user.id if message.from_user else 0
    rows = await db.list_tracks_for_user(user_id, limit=200)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
    summary = ", ".join(parts) if parts else "нет записей"
    await message.answer(f"Бот работает. Ваши записи: {summary}.")
