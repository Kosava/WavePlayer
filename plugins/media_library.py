"""Media Library Plugin za WavePlayer.

Organizuje medijsku kolekciju sa automatskim metapodacima:
  - Skenira zadane direktorijume za video/audio fajlove
  - Prati istoriju gledanja (watch history)
  - Pamti poziciju za nastavak (resume)
  - Kategorije: Filmovi, Serije, Muzika, Nedavno gledano
  - Pretraga po nazivu

Podatke čuva u JSON fajlu u config direktorijumu.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .plugin_api import (
    WavePlugin,
    PluginInfo,
    PluginType,
    PluginContext,
)

logger = logging.getLogger(__name__)

# Podržane media ekstenzije
VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".mpg", ".mpeg", ".3gp", ".ogv",
}
AUDIO_EXTS = {
    ".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus",
    ".aac", ".wma", ".ape", ".alac",
}
ALL_MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


@dataclass
class LibraryItem:
    """Stavka u media biblioteci."""
    path: str                       # Apsolutna putanja
    title: str = ""                 # Naziv za prikaz
    media_type: str = "video"       # video, audio, tv
    duration: float = 0.0           # Trajanje u sekundama
    size_mb: float = 0.0            # Veličina fajla u MB
    added_at: float = 0.0          # Unix timestamp kada je dodato
    last_played: float = 0.0       # Poslednje puštanje
    play_count: int = 0             # Koliko puta pušteno
    resume_position: float = 0.0   # Pozicija za nastavak (sekunde)
    watched: bool = False           # Da li je odgledano (>90%)
    favorite: bool = False          # Omiljeno
    # Serija info
    series_name: str = ""
    season: int = 0
    episode: int = 0
    # Metadata (popunjava TMDb plugin ako postoji)
    year: int = 0
    rating: float = 0.0
    genres: List[str] = field(default_factory=list)
    poster_url: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class LibraryData:
    """Kompletni podaci biblioteke."""
    items: Dict[str, LibraryItem] = field(default_factory=dict)  # path -> item
    scan_dirs: List[str] = field(default_factory=list)
    last_scan: float = 0.0


def _parse_series_info(filename: str) -> Dict[str, Any]:
    """Izvuci serija/sezona/epizoda iz imena fajla."""
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', filename)
    if m:
        title = filename[:m.start()]
        for ch in "._-":
            title = title.replace(ch, " ")
        return {
            "series": title.strip(),
            "season": int(m.group(1)),
            "episode": int(m.group(2)),
        }
    return {}


def _clean_title(filename: str) -> str:
    """Očisti ime fajla u čitljiv naslov."""
    name = Path(filename).stem
    # Ukloni release info
    name = re.sub(
        r'[\.\s\-_]*(1080p|720p|2160p|4[kK]|[xXhH]\.?26[45]|BluRay|WEB|HDTV|BRRip|'
        r'DVDRip|HEVC|AAC|DTS|REMUX|HDR|SDR|PROPER|REPACK|iNTERNAL).*',
        '', name, flags=re.IGNORECASE
    )
    for ch in "._-[]()":
        name = name.replace(ch, " ")
    # Ukloni višestruke razmake
    name = re.sub(r'\s+', ' ', name).strip()
    return name


class MediaLibraryPlugin(WavePlugin):
    """Media Library — organizacija medijske kolekcije."""

    def __init__(self) -> None:
        super().__init__()
        self._data: LibraryData = LibraryData()
        self._db_path: str = ""
        self._dirty: bool = False

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="MediaLibrary",
            version="1.0.0",
            description="Organizacija medijske kolekcije sa istorijom gledanja",
            author="WavePlayer",
            plugin_type=PluginType.TOOL,
            icon="📚",
        )

    def initialize(self, context: PluginContext) -> bool:
        self.context = context

        # DB putanja
        data_dir = context.get_data_dir()
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)
            self._db_path = os.path.join(data_dir, "media_library.json")
        else:
            self._db_path = os.path.expanduser("~/.config/WavePlayer/media_library.json")

        # Učitaj postojeće podatke
        self._load_db()

        # Scan direktorijumi iz config-a
        scan_dirs = context.get_config("plugins.library.scan_dirs", [])
        if scan_dirs:
            self._data.scan_dirs = scan_dirs

        logger.info(f"MediaLibrary: {len(self._data.items)} stavki, "
                      f"{len(self._data.scan_dirs)} scan dir-ova")
        return True

    def shutdown(self) -> None:
        """Sačuvaj podatke pre gašenja."""
        if self._dirty:
            self._save_db()

    # --- Skeniranje ---

    def scan(self, directories: Optional[List[str]] = None) -> int:
        """Skeniraj direktorijume za medijske fajlove. Vrati broj novih."""
        dirs = directories or self._data.scan_dirs
        if not dirs:
            return 0

        new_count = 0
        for dir_path in dirs:
            if not os.path.isdir(dir_path):
                logger.warning(f"Scan dir ne postoji: {dir_path}")
                continue

            for root, _, files in os.walk(dir_path):
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in ALL_MEDIA_EXTS:
                        continue

                    full_path = os.path.join(root, fname)
                    if full_path in self._data.items:
                        continue

                    item = self._create_item(full_path, fname, ext)
                    self._data.items[full_path] = item
                    new_count += 1

        if new_count > 0:
            self._data.last_scan = time.time()
            self._dirty = True
            self._save_db()

        logger.info(f"Scan završen: {new_count} novih, ukupno {len(self._data.items)}")
        return new_count

    def add_scan_dir(self, dir_path: str) -> None:
        """Dodaj direktorijum za skeniranje."""
        if dir_path not in self._data.scan_dirs:
            self._data.scan_dirs.append(dir_path)
            self._dirty = True
            if self.context:
                self.context.set_config("plugins.library.scan_dirs", self._data.scan_dirs)

    # --- Pristup podacima ---

    def get_all(self) -> List[LibraryItem]:
        """Sve stavke, sortirane po datumu dodavanja."""
        return sorted(self._data.items.values(), key=lambda x: -x.added_at)

    def get_recent(self, limit: int = 20) -> List[LibraryItem]:
        """Nedavno gledani fajlovi."""
        played = [i for i in self._data.items.values() if i.last_played > 0]
        played.sort(key=lambda x: -x.last_played)
        return played[:limit]

    def get_movies(self) -> List[LibraryItem]:
        """Samo filmovi (video koji nisu serije)."""
        return [
            i for i in self._data.items.values()
            if i.media_type == "video" and not i.series_name
        ]

    def get_series(self) -> Dict[str, List[LibraryItem]]:
        """Serije grupisane po imenu."""
        groups: Dict[str, List[LibraryItem]] = {}
        for item in self._data.items.values():
            if item.series_name:
                if item.series_name not in groups:
                    groups[item.series_name] = []
                groups[item.series_name].append(item)

        # Sortiraj epizode unutar svake serije
        for name in groups:
            groups[name].sort(key=lambda x: (x.season, x.episode))

        return groups

    def get_music(self) -> List[LibraryItem]:
        """Samo audio fajlovi."""
        return [i for i in self._data.items.values() if i.media_type == "audio"]

    def get_favorites(self) -> List[LibraryItem]:
        """Omiljene stavke."""
        return [i for i in self._data.items.values() if i.favorite]

    def get_unwatched(self) -> List[LibraryItem]:
        """Neodgledani video fajlovi."""
        return [
            i for i in self._data.items.values()
            if i.media_type in ("video", "tv") and not i.watched
        ]

    def search(self, query: str) -> List[LibraryItem]:
        """Pretraži biblioteku po nazivu."""
        q = query.lower()
        return [
            i for i in self._data.items.values()
            if q in i.title.lower() or q in i.series_name.lower()
            or q in os.path.basename(i.path).lower()
            or any(q in tag.lower() for tag in i.tags)
        ]

    # --- Tracking ---

    def record_play(self, file_path: str) -> None:
        """Zabeleži da je fajl pušten."""
        item = self._data.items.get(file_path)
        if not item:
            # Dodaj u biblioteku ako nije
            fname = os.path.basename(file_path)
            ext = os.path.splitext(fname)[1].lower()
            if ext in ALL_MEDIA_EXTS:
                item = self._create_item(file_path, fname, ext)
                self._data.items[file_path] = item

        if item:
            item.last_played = time.time()
            item.play_count += 1
            self._dirty = True

    def update_position(self, file_path: str, position: float, duration: float) -> None:
        """Ažuriraj resume poziciju i watched status."""
        item = self._data.items.get(file_path)
        if item:
            item.resume_position = position
            if duration > 0:
                item.duration = duration
                # Označi kao odgledano ako je >90%
                if position / duration > 0.9:
                    item.watched = True
                    item.resume_position = 0  # Resetuj resume
            self._dirty = True

    def toggle_favorite(self, file_path: str) -> bool:
        """Toggle omiljeno. Vrati novi status."""
        item = self._data.items.get(file_path)
        if item:
            item.favorite = not item.favorite
            self._dirty = True
            return item.favorite
        return False

    # --- Statistike ---

    def get_stats(self) -> Dict[str, Any]:
        """Statistike biblioteke."""
        items = list(self._data.items.values())
        total_size = sum(i.size_mb for i in items)
        total_duration = sum(i.duration for i in items)
        return {
            "total_items": len(items),
            "total_size_gb": round(total_size / 1024, 1),
            "total_hours": round(total_duration / 3600, 1),
            "movies": len(self.get_movies()),
            "series": len(self.get_series()),
            "music": len(self.get_music()),
            "watched": sum(1 for i in items if i.watched),
            "favorites": sum(1 for i in items if i.favorite),
        }

    # --- Interne metode ---

    def _create_item(self, full_path: str, filename: str, ext: str) -> LibraryItem:
        """Kreiraj LibraryItem iz fajla."""
        is_audio = ext in AUDIO_EXTS
        title = _clean_title(filename)
        series_info = _parse_series_info(filename)

        try:
            size_mb = os.path.getsize(full_path) / (1024 * 1024)
        except OSError:
            size_mb = 0

        item = LibraryItem(
            path=full_path,
            title=title,
            media_type="audio" if is_audio else ("tv" if series_info else "video"),
            size_mb=round(size_mb, 1),
            added_at=time.time(),
        )

        if series_info:
            item.series_name = series_info.get("series", "")
            item.season = series_info.get("season", 0)
            item.episode = series_info.get("episode", 0)
            item.title = f"S{item.season:02d}E{item.episode:02d} — {title}"

        return item

    def _load_db(self) -> None:
        """Učitaj podatke iz JSON fajla."""
        if not self._db_path or not os.path.exists(self._db_path):
            return

        try:
            with open(self._db_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            items = {}
            for path, item_data in raw.get("items", {}).items():
                # Konvertuj genres i tags iz JSON
                if "genres" not in item_data:
                    item_data["genres"] = []
                if "tags" not in item_data:
                    item_data["tags"] = []
                items[path] = LibraryItem(**item_data)

            self._data.items = items
            self._data.scan_dirs = raw.get("scan_dirs", [])
            self._data.last_scan = raw.get("last_scan", 0)

            logger.debug(f"Library DB učitan: {len(items)} stavki")

        except Exception as e:
            logger.warning(f"Library DB greška: {e}")

    def _save_db(self) -> None:
        """Sačuvaj podatke u JSON fajl."""
        if not self._db_path:
            return

        try:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

            data = {
                "items": {path: asdict(item) for path, item in self._data.items.items()},
                "scan_dirs": self._data.scan_dirs,
                "last_scan": self._data.last_scan,
            }

            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self._dirty = False
            logger.debug(f"Library DB sačuvan: {len(self._data.items)} stavki")

        except Exception as e:
            logger.error(f"Library DB save greška: {e}")
