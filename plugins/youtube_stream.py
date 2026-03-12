"""YouTube Stream Plugin za WavePlayer.

Omogućava pretragu i reprodukciju YouTube videa/muzike
direktno u WavePlayer-u koristeći yt-dlp za ekstrakciju URL-ova.

Zahteva: yt-dlp (pip install yt-dlp)

Funkcionalnosti:
  - Pretraga YouTube videa po ključnoj reči
  - Direktno puštanje YouTube URL-ova
  - Ekstrakcija audio stream-a za muziku
  - Playlist podrška
  - Trending/Popular muzika
"""

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .plugin_api import (
    WavePlugin,
    PluginInfo,
    PluginType,
    PluginContext,
)

logger = logging.getLogger(__name__)


@dataclass
class YouTubeResult:
    """Rezultat YouTube pretrage."""
    title: str
    url: str
    video_id: str
    channel: str = ""
    duration: str = ""          # "3:45" format
    duration_seconds: int = 0
    view_count: int = 0
    thumbnail: str = ""
    is_live: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


def _has_ytdlp() -> bool:
    """Proveri da li je yt-dlp instaliran."""
    return shutil.which("yt-dlp") is not None


def _format_duration(seconds: int) -> str:
    """Formatiraj sekunde u MM:SS ili H:MM:SS."""
    if seconds <= 0:
        return "LIVE"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_views(count: int) -> str:
    """Formatiraj broj pregleda: 1.2M, 456K, itd."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.0f}K"
    return str(count)


class YouTubePlugin(WavePlugin):
    """YouTube stream/search plugin koristeći yt-dlp."""

    def __init__(self) -> None:
        super().__init__()
        self._ytdlp_path: str = ""
        self._prefer_audio: bool = False
        self._max_quality: str = "1080"  # max rezolucija

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="YouTube",
            version="1.0.0",
            description="YouTube pretraga i streaming (yt-dlp)",
            author="WavePlayer",
            plugin_type=PluginType.STREAMING,
            icon="▶",
            url="https://github.com/yt-dlp/yt-dlp",
        )

    def initialize(self, context: PluginContext) -> bool:
        self.context = context

        # Pronađi yt-dlp
        self._ytdlp_path = shutil.which("yt-dlp") or ""
        if not self._ytdlp_path:
            logger.warning("YouTube plugin: yt-dlp nije instaliran! pip install yt-dlp")
            return True  # Plugin se učita ali neće raditi bez yt-dlp

        self._prefer_audio = context.get_config("plugins.youtube.prefer_audio", False)
        self._max_quality = context.get_config("plugins.youtube.max_quality", "1080")

        logger.info(f"YouTube plugin: yt-dlp={self._ytdlp_path}")
        return True

    # --- Javne metode ---

    def search(self, query: str, max_results: int = 15) -> List[YouTubeResult]:
        """Pretraži YouTube."""
        if not self._ytdlp_path:
            logger.error("yt-dlp nije instaliran")
            return []

        try:
            cmd = [
                self._ytdlp_path,
                f"ytsearch{max_results}:{query}",
                "--dump-json",
                "--flat-playlist",
                "--no-warnings",
                "--quiet",
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=20
            )

            if result.returncode != 0:
                logger.warning(f"yt-dlp search error: {result.stderr[:200]}")
                return []

            results = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    vid = YouTubeResult(
                        title=data.get("title", "Unknown"),
                        url=data.get("url", data.get("webpage_url", "")),
                        video_id=data.get("id", ""),
                        channel=data.get("channel", data.get("uploader", "")),
                        duration_seconds=int(data.get("duration", 0) or 0),
                        duration=_format_duration(int(data.get("duration", 0) or 0)),
                        view_count=int(data.get("view_count", 0) or 0),
                        thumbnail=data.get("thumbnail", ""),
                        is_live=bool(data.get("is_live", False)),
                    )
                    # Generiši URL ako nemamo
                    if not vid.url and vid.video_id:
                        vid.url = f"https://www.youtube.com/watch?v={vid.video_id}"
                    results.append(vid)
                except (json.JSONDecodeError, KeyError):
                    continue

            logger.info(f"YouTube search: {len(results)} rezultata za '{query}'")
            return results

        except subprocess.TimeoutExpired:
            logger.warning("YouTube search timeout")
            return []
        except Exception as e:
            logger.error(f"YouTube search greška: {e}")
            return []

    def get_stream_url(self, youtube_url: str, audio_only: bool = False) -> Optional[str]:
        """Izvuci direktan stream URL za mpv.

        mpv ima ugrađenu yt-dlp podršku, pa obično samo prosleđujemo
        YouTube URL direktno. Ali ova metoda može da izvuče specifičan
        format ako je potrebno.
        """
        if not self._ytdlp_path:
            return youtube_url  # mpv će probati sam

        try:
            format_spec = "bestaudio" if audio_only else f"bestvideo[height<={self._max_quality}]+bestaudio/best"

            cmd = [
                self._ytdlp_path,
                youtube_url,
                "-f", format_spec,
                "-g",  # Samo ispiši URL
                "--no-warnings",
                "--quiet",
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )

            if result.returncode == 0 and result.stdout.strip():
                urls = result.stdout.strip().split("\n")
                return urls[0]

            return youtube_url  # Fallback — mpv će probati sam

        except Exception as e:
            logger.warning(f"get_stream_url greška: {e}")
            return youtube_url

    def play(self, url: str, audio_only: bool = False) -> None:
        """Pusti YouTube URL u player-u.

        mpv ima nativnu yt-dlp podršku — dovoljno je proslediti
        YouTube URL i mpv će sam pozvati yt-dlp za ekstrakciju.
        """
        if not self.context:
            return

        # mpv nativno podržava YouTube URL-ove ako je yt-dlp instaliran
        # Ne trebamo ekstrahovati — samo prosledimo URL
        self.context.load_file(url)
        self.context.show_osd(f"▶ YouTube: Loading...", 3000)

    def play_audio(self, url: str) -> None:
        """Pusti samo audio sa YouTube-a (za muziku)."""
        self.play(url, audio_only=True)

    def get_playlist_items(self, playlist_url: str, max_items: int = 50) -> List[YouTubeResult]:
        """Izvuci stavke iz YouTube playliste."""
        if not self._ytdlp_path:
            return []

        try:
            cmd = [
                self._ytdlp_path,
                playlist_url,
                "--dump-json",
                "--flat-playlist",
                f"--playlist-end={max_items}",
                "--no-warnings",
                "--quiet",
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )

            items = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    vid = YouTubeResult(
                        title=data.get("title", "Unknown"),
                        url=f"https://www.youtube.com/watch?v={data.get('id', '')}",
                        video_id=data.get("id", ""),
                        channel=data.get("channel", data.get("uploader", "")),
                        duration_seconds=int(data.get("duration", 0) or 0),
                        duration=_format_duration(int(data.get("duration", 0) or 0)),
                    )
                    items.append(vid)
                except (json.JSONDecodeError, KeyError):
                    continue

            return items

        except Exception as e:
            logger.error(f"Playlist extraction greška: {e}")
            return []

    def add_playlist_to_player(self, playlist_url: str) -> int:
        """Dodaj celu YouTube playlistu u player. Vrati broj dodatih."""
        items = self.get_playlist_items(playlist_url)
        if items and self.context:
            urls = [item.url for item in items if item.url]
            self.context.add_to_playlist(urls)
            self.context.show_osd(f"▶ Dodato {len(urls)} videa iz playliste", 3000)
            return len(urls)
        return 0

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """Proveri da li je URL YouTube link."""
        patterns = [
            r'(youtube\.com/watch\?v=)',
            r'(youtu\.be/)',
            r'(youtube\.com/playlist\?list=)',
            r'(youtube\.com/shorts/)',
            r'(music\.youtube\.com/)',
        ]
        return any(re.search(p, url) for p in patterns)
