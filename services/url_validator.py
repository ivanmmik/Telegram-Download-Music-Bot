from __future__ import annotations

import re
from urllib.parse import urlparse

# Streaming platforms that need special handling (yt-dlp)
STREAMING_HOST_SUFFIXES: tuple[str, ...] = (
    "youtube.com",
    "youtu.be",
    "music.youtube.com",
    "spotify.com",
    "soundcloud.com",
    "music.yandex.ru",
    "music.yandex.com",
    "music.apple.com",
    "itunes.apple.com",
    "deezer.com",
    "tidal.com",
    "bandcamp.com",
)

# Truly blocked hosts (social media without audio focus)
BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    "ok.ru",
    "rutube.ru",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "tiktok.com",
)

AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".aiff", ".wma"}
)

class UrlValidationError(Exception):
    """URL cannot be processed as a direct legal download."""


def _host_blocked(host: str) -> bool:
    h = host.lower()
    for suffix in BLOCKED_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def _is_streaming_host(host: str) -> bool:
    """Check if host is a streaming platform (YouTube, Spotify, etc)."""
    h = host.lower()
    for suffix in STREAMING_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def is_streaming_url(url: str) -> bool:
    """Check if URL is from a supported streaming platform."""
    parsed = urlparse(url.strip())
    host = parsed.hostname
    if not host:
        return False
    return _is_streaming_host(host)


def _looks_like_audio_path(path: str) -> bool:
    lower = path.lower().split("?", 1)[0]
    return any(lower.endswith(ext) for ext in AUDIO_EXTENSIONS)


def validate_url_string(url: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UrlValidationError("Нужна ссылка с протоколом http или https.")
    if not parsed.netloc:
        raise UrlValidationError("В ссылке отсутствует домен.")


def validate_url_for_download(
    url: str,
    *,
    allowed_hosts: frozenset[str],
) -> None:
    """
    Raises UrlValidationError if the URL must not be downloaded.
    Streaming platforms (YouTube, Spotify, etc.) are now allowed.
    """
    validate_url_string(url)
    parsed = urlparse(url.strip())
    host = parsed.hostname
    if not host:
        raise UrlValidationError("Не удалось определить хост ссылки.")
    if _host_blocked(host):
        raise UrlValidationError(
            "Этот источник не поддерживается."
        )
    # Note: streaming platforms (YouTube, Spotify, etc.) are handled separately
    # and are allowed through this validation
    if allowed_hosts and host.lower() not in allowed_hosts:
        raise UrlValidationError(
            "Домен не входит в список разрешённых источников (ALLOWED_HOSTS). "
            "Обратитесь к администратору бота или используйте разрешённый хост."
        )


def is_probably_direct_media_url(url: str) -> bool:
    """Heuristic before HEAD: path ends with known audio extension."""
    parsed = urlparse(url.strip())
    return _looks_like_audio_path(parsed.path or "")


def content_type_looks_audio(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct.startswith("audio/"):
        return True
    if ct == "application/ogg":
        return True
    return False


def sanitize_filename_hint(url: str, content_disposition: str | None) -> str:
    if content_disposition:
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition, re.I)
        if m:
            name = m.group(1).strip()
            if name:
                return name[:200]
    path = urlparse(url).path
    if path and "/" in path:
        base = path.rsplit("/", 1)[-1]
        if base:
            return base[:200]
    return "track.bin"
