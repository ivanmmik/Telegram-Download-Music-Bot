"""Download audio from streaming platforms using yt-dlp."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamingDownloadResult:
    path: Path
    filename: str
    size_bytes: int
    title: str | None
    artist: str | None
    duration: int | None  # seconds


class StreamingDownloader:
    """Download audio from YouTube, SoundCloud, Spotify, Yandex Music, etc."""

    # Platforms supported by yt-dlp
    SUPPORTED_HOSTS: ClassVar[frozenset[str]] = frozenset({
        # YouTube
        "youtube.com", "youtu.be", "music.youtube.com",
        # SoundCloud
        "soundcloud.com",
        # Spotify (limited, needs cookies or premium in some cases)
        "spotify.com", "open.spotify.com",
        # Yandex Music
        "music.yandex.ru", "music.yandex.com",
        # Other popular platforms
        "bandcamp.com",
        "deezer.com",
        "tidal.com",
        "vk.com", "vk.ru", "vkontakte.ru",
    })

    def __init__(self, download_dir: Path, max_file_mb: int = 50) -> None:
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = max_file_mb * 1024 * 1024

    def is_streaming_url(self, url: str) -> bool:
        """Check if URL is from a supported streaming platform."""
        parsed = urlparse(url.strip())
        host = parsed.hostname or ""
        host_lower = host.lower()
        return any(
            host_lower == h or host_lower.endswith(f".{h}")
            for h in self.SUPPORTED_HOSTS
        )

    async def download(self, url: str) -> StreamingDownloadResult:
        """Download audio from streaming platform."""
        if not self.is_streaming_url(url):
            raise ValueError(f"URL не поддерживается для стриминговой загрузки: {url}")

        # Create safe filename base from URL
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", urlparse(url).path)[:50]
        output_template = str(self.download_dir / f"%(title)s_{safe_name}_%(id)s.%(ext)s")

        # yt-dlp options for best audio quality
        cmd = [
            "yt-dlp",
            "--format", "bestaudio[ext=m4a]/bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",  # Convert to mp3 for compatibility
            "--audio-quality", "0",  # Best quality
            "--output", output_template,
            "--no-playlist",  # Download single track only
            "--no-warnings",
            "--quiet",
            "--no-color",
            "--write-info-json",  # For metadata
            "--progress",  # Show progress (will be captured)
            url,
        ]

        logger.info("Starting yt-dlp download: %s", url)

        # Run yt-dlp in subprocess (it's CPU intensive)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=300,  # 5 minutes max
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError("Загрузка заняла слишком много времени (5 минут)")

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="ignore")[-500:]  # Last 500 chars
            logger.error("yt-dlp failed: %s", error_msg)
            raise RuntimeError(f"Не удалось скачать трек: {error_msg[:200]}")

        # Find downloaded file
        downloaded_files = list(self.download_dir.glob("*.mp3"))
        if not downloaded_files:
            raise RuntimeError("Файл не был скачан")

        # Get the most recently modified file (should be our download)
        downloaded_file = max(downloaded_files, key=lambda p: p.stat().st_mtime)

        # Check file size
        file_size = downloaded_file.stat().st_size
        if file_size > self.max_file_bytes:
            downloaded_file.unlink(missing_ok=True)
            raise ValueError(f"Файл слишком большой ({file_size / 1024 / 1024:.1f} MB > {self.max_file_bytes / 1024 / 1024:.0f} MB)")

        # Try to read metadata from info.json
        info_json = downloaded_file.with_suffix(".info.json")
        title = None
        artist = None
        duration = None
        if info_json.exists():
            import json
            try:
                with open(info_json, "r", encoding="utf-8") as f:
                    info = json.load(f)
                title = info.get("title")
                artist = info.get("artist") or info.get("uploader")
                duration = info.get("duration")
            except Exception as e:
                logger.warning("Could not parse info.json: %s", e)
            finally:
                info_json.unlink(missing_ok=True)  # Clean up

        logger.info("Downloaded: %s (%.2f MB)", downloaded_file.name, file_size / 1024 / 1024)

        return StreamingDownloadResult(
            path=downloaded_file,
            filename=downloaded_file.name,
            size_bytes=file_size,
            title=title,
            artist=artist,
            duration=duration,
        )
