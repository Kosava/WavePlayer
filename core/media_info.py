"""Data classes for media information.

Pure data containers with no behavior or UI dependencies.
Maps directly to:
  - C++: struct with public members
  - Rust: struct with pub fields
"""

from dataclasses import dataclass, field
from typing import Optional, List

from .interfaces import MediaType


@dataclass
class MediaInfo:
    """Informacije o media fajlu.

    Čist podatkovni kontejner. U C++ bi ovo bio struct.
    """
    # Putanja do fajla
    file_path: str = ""

    # Osnovni podaci
    title: str = ""
    duration: float = 0.0
    media_type: MediaType = MediaType.UNKNOWN

    # Video podaci
    video_width: int = 0
    video_height: int = 0
    video_codec: str = ""
    video_bitrate: int = 0
    fps: float = 0.0

    # Audio podaci
    audio_codec: str = ""
    audio_bitrate: int = 0
    audio_channels: int = 0
    audio_sample_rate: int = 0

    # Titlovi - lista dostupnih
    subtitle_tracks: List[str] = field(default_factory=list)
    audio_tracks: List[str] = field(default_factory=list)

    # Metadata
    artist: str = ""
    album: str = ""
    year: str = ""
    cover_art: Optional[bytes] = None


@dataclass
class PlaylistItem:
    """Stavka u playlisti.

    Čist podatkovni kontejner za jednu stavku.
    """
    file_path: str = ""
    title: str = ""
    duration: float = 0.0
    media_type: MediaType = MediaType.UNKNOWN
    is_current: bool = False

    def display_name(self) -> str:
        """Prikazni naziv stavke."""
        if self.title:
            return self.title
        # Izvuci ime fajla iz putanje
        # Koristi jednostavan split umesto os.path za portabilnost
        name = self.file_path
        if "/" in name:
            name = name.rsplit("/", 1)[-1]
        if "\\" in name:
            name = name.rsplit("\\", 1)[-1]
        # Ukloni ekstenziju
        if "." in name:
            name = name.rsplit(".", 1)[0]
        return name


@dataclass
class PlayerConfig:
    """Konfiguracija plejera.

    Sva podešavanja na jednom mestu. U C++ bi ovo bio struct
    sa default vrednostima.
    """
    # Prozor
    window_width: int = 1280
    window_height: int = 720
    window_x: int = 100
    window_y: int = 100

    # Audio
    volume: int = 100
    muted: bool = False

    # Reprodukcija
    speed: float = 1.0
    auto_hide_delay_ms: int = 3000

    # UI
    playlist_visible: bool = False
    playlist_width: int = 320

    # Poslednji fajl
    last_file: str = ""
    last_position: float = 0.0
