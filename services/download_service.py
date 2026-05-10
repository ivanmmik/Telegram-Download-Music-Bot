from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from services import url_validator as uv
from utils.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DownloadResult:
    path: Path
    filename: str
    size_bytes: int
    mime_type: str | None


class DownloadService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def probe_and_download(self, url: str) -> DownloadResult:
        timeout = aiohttp.ClientTimeout(
            total=None,
            sock_connect=self._settings.http_head_timeout_sec,
            sock_read=self._settings.download_timeout_sec,
        )
        connector = aiohttp.TCPConnector(ssl=True, limit=10)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            head_ok = False
            content_length: int | None = None
            content_type: str | None = None
            content_disposition: str | None = None

            try:
                async with session.head(
                    url,
                    allow_redirects=True,
                    headers={"User-Agent": "TG-Music-Bot/1.0"},
                ) as resp:
                    if resp.status in (405, 501):
                        head_ok = False
                    elif 200 <= resp.status < 300:
                        head_ok = True
                        content_length = self._parse_length(resp.headers.get("Content-Length"))
                        content_type = resp.headers.get("Content-Type")
                        content_disposition = resp.headers.get("Content-Disposition")
                    else:
                        logger.info("HEAD %s returned %s", url, resp.status)
            except (aiohttp.ClientError, TimeoutError) as e:
                logger.warning("HEAD failed for %s: %s", url, e)

            parsed_path = urlparse(url).path or ""
            ext_ok = uv._looks_like_audio_path(parsed_path)
            type_ok = uv.content_type_looks_audio(content_type)

            if not head_ok:
                if ext_ok:
                    type_ok = True
                else:
                    raise ValueError(
                        "Не удалось проверить файл по заголовкам. "
                        "Убедитесь, что ссылка ведёт напрямую на аудиофайл."
                    )

            if content_length is not None and content_length > self._settings.max_file_bytes:
                raise ValueError(
                    f"Файл слишком большой (>{self._settings.max_file_mb} МБ по заголовку)."
                )

            if not (ext_ok or type_ok):
                raise ValueError(
                    "Сервер не сообщил аудио Content-Type, а путь не похож на известное "
                    "расширение (.mp3, .flac, …). Прямая загрузка отклонена."
                )

            filename = uv.sanitize_filename_hint(url, content_disposition)
            safe_name = self._unique_name(filename)

            self._settings.download_dir.mkdir(parents=True, exist_ok=True)
            dest = self._settings.download_dir / safe_name

            downloaded = 0
            async with session.get(
                url,
                allow_redirects=True,
                headers={"User-Agent": "TG-Music-Bot/1.0"},
            ) as resp:
                if resp.status >= 400:
                    raise ValueError(f"HTTP {resp.status} при загрузке.")
                cl = self._parse_length(resp.headers.get("Content-Length"))
                if cl is not None and cl > self._settings.max_file_bytes:
                    raise ValueError(
                        f"Файл слишком большой (>{self._settings.max_file_mb} МБ)."
                    )
                ct = resp.headers.get("Content-Type") or content_type
                if not (ext_ok or uv.content_type_looks_audio(ct)):
                    raise ValueError("Ответ не похож на аудиофайл.")

                with dest.open("wb") as f:
                    async for chunk in resp.content.iter_chunked(256 * 1024):
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > self._settings.max_file_bytes:
                            dest.unlink(missing_ok=True)
                            raise ValueError(
                                f"Превышен лимит размера ({self._settings.max_file_mb} МБ)."
                            )
                        f.write(chunk)

            return DownloadResult(
                path=dest,
                filename=safe_name,
                size_bytes=downloaded,
                mime_type=ct,
            )

    @staticmethod
    def _parse_length(raw: str | None) -> int | None:
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @staticmethod
    def _unique_name(filename: str) -> str:
        stem = Path(filename).name or "track.bin"
        uid = uuid.uuid4().hex[:10]
        return f"{uid}_{stem}"
