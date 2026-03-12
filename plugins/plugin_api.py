"""Plugin API za WavePlayer.

Definiše bazni interfejs koji svi plugini moraju da implementiraju.
Plugini dobijaju pristup player-u kroz PluginContext objekat.

Svaki plugin je Python modul u plugins/ direktorijumu sa:
  - PLUGIN_INFO dict (name, version, description, author)
  - Klasa koja nasleđuje WavePlugin

PORTABILITY NOTES:
  - C++: plugin API bi bio shared library (.so/.dll) sa C interfejsom
  - Rust: trait WavePlugin + dylib
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum, auto

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Tip plugina — određuje gde se integriše u UI."""
    SUBTITLE = auto()       # Pretraga/download titlova
    METADATA = auto()       # Informacije o mediju (TMDb, OMDb...)
    STREAMING = auto()      # Streaming izvori
    TOOL = auto()           # Opšti alat (screenshot, konverzija...)
    UI_EXTENSION = auto()   # Proširenje UI-a


@dataclass
class PluginInfo:
    """Metapodaci o pluginu."""
    name: str
    version: str
    description: str
    author: str
    plugin_type: PluginType = PluginType.TOOL
    icon: str = "🧩"       # Emoji ili putanja do ikone
    url: str = ""           # Sajt/repo plugina
    min_player_version: str = "1.0.0"


@dataclass
class SubtitleResult:
    """Rezultat pretrage titlova."""
    title: str              # Naziv titla
    language: str           # Jezik (ISO 639-1: en, sr, de...)
    language_name: str      # Puno ime jezika (English, Serbian...)
    provider: str           # Ime provajdera (OpenSubtitles, Podnapisi...)
    download_url: str       # URL za download
    filename: str = ""      # Originalno ime fajla
    rating: float = 0.0     # Ocena (0-10)
    download_count: int = 0 # Broj download-a
    format: str = "srt"     # Format titla
    hash_match: bool = False  # Da li se hash poklapa sa fajlom
    extra: Dict[str, Any] = field(default_factory=dict)


class PluginContext:
    """Kontekst koji plugin dobija za interakciju sa player-om.

    Ovo je "bridge" između plugina i player-a — plugin nikad
    ne pristupa direktno Qt widgetima ili mpv engine-u.
    """

    def __init__(self) -> None:
        # Callback-ovi koje main_window registruje
        self._get_current_file: Optional[Callable[[], str]] = None
        self._get_media_hash: Optional[Callable[[], str]] = None
        self._load_subtitle: Optional[Callable[[str], bool]] = None
        self._load_file: Optional[Callable[[str], None]] = None
        self._show_osd: Optional[Callable[[str, int], None]] = None
        self._get_config: Optional[Callable[[str, Any], Any]] = None
        self._set_config: Optional[Callable[[str, Any], None]] = None
        self._get_video_info: Optional[Callable[[], Dict[str, Any]]] = None
        self._add_to_playlist: Optional[Callable[[List[str]], None]] = None
        self._get_data_dir: Optional[Callable[[], str]] = None

    def get_current_file(self) -> str:
        """Putanja do trenutno puštenog fajla."""
        if self._get_current_file:
            return self._get_current_file()
        return ""

    def get_media_hash(self) -> str:
        """Hash trenutnog medija (za subtitle matching)."""
        if self._get_media_hash:
            return self._get_media_hash()
        return ""

    def load_subtitle(self, path: str) -> bool:
        """Učitaj titl na trenutni video."""
        if self._load_subtitle:
            return self._load_subtitle(path)
        return False

    def show_osd(self, text: str, duration_ms: int = 2000) -> None:
        """Prikaži OSD poruku."""
        if self._show_osd:
            self._show_osd(text, duration_ms)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Čitaj config vrednost."""
        if self._get_config:
            return self._get_config(key, default)
        return default

    def set_config(self, key: str, value: Any) -> None:
        """Zapiši config vrednost."""
        if self._set_config:
            self._set_config(key, value)

    def get_video_info(self) -> Dict[str, Any]:
        """Info o trenutnom videu (width, height, duration, filename...)."""
        if self._get_video_info:
            return self._get_video_info()
        return {}

    def load_file(self, path_or_url: str) -> None:
        """Učitaj fajl ili URL u player."""
        if self._load_file:
            self._load_file(path_or_url)

    def add_to_playlist(self, paths: List[str]) -> None:
        """Dodaj fajlove/URL-ove u playlist."""
        if self._add_to_playlist:
            self._add_to_playlist(paths)

    def get_data_dir(self) -> str:
        """Direktorijum za plugin podatke (~/.config/WavePlayer/plugins/)."""
        if self._get_data_dir:
            return self._get_data_dir()
        return ""


class WavePlugin(ABC):
    """Bazna klasa za sve WavePlayer plugine.

    Svaki plugin mora da nasledi ovu klasu i implementira
    bar initialize() i shutdown() metode.
    """

    def __init__(self) -> None:
        self.context: Optional[PluginContext] = None
        self._enabled: bool = True

    @abstractmethod
    def get_info(self) -> PluginInfo:
        """Vrati info o pluginu."""
        ...

    def initialize(self, context: PluginContext) -> bool:
        """Inicijalizuj plugin sa kontekstom. Vrati True ako OK."""
        self.context = context
        return True

    def shutdown(self) -> None:
        """Oslobodi resurse plugina."""
        pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def configure(self, parent=None) -> None:
        """Opcioni settings dialog za plugin."""
        pass


class SubtitlePlugin(WavePlugin):
    """Specijalizovana bazna klasa za subtitle plugine.

    Subtitle plugini implementiraju search() i download() metode.
    """

    @abstractmethod
    def search(
        self,
        query: str,
        languages: List[str],
        file_hash: str = "",
        file_path: str = "",
    ) -> List[SubtitleResult]:
        """Pretraži titlove.

        Args:
            query: Naziv filma/serije ili putanja fajla
            languages: Lista željenih jezika (ISO 639-1)
            file_hash: Hash fajla za tačnije rezultate
            file_path: Putanja do fajla

        Returns:
            Lista SubtitleResult objekata
        """
        ...

    @abstractmethod
    def download(self, result: SubtitleResult, dest_dir: str) -> Optional[str]:
        """Download titl i vrati putanju do sačuvanog fajla.

        Args:
            result: SubtitleResult objekat iz search()
            dest_dir: Direktorijum gde se čuva fajl

        Returns:
            Putanja do sačuvanog fajla ili None ako nije uspelo
        """
        ...

    def get_supported_languages(self) -> List[Dict[str, str]]:
        """Vrati listu podržanih jezika kao [{code: 'en', name: 'English'}, ...]."""
        return [
            {"code": "en", "name": "English"},
            {"code": "sr", "name": "Serbian"},
            {"code": "hr", "name": "Croatian"},
            {"code": "bs", "name": "Bosnian"},
            {"code": "de", "name": "German"},
            {"code": "fr", "name": "French"},
            {"code": "es", "name": "Spanish"},
            {"code": "it", "name": "Italian"},
            {"code": "pt", "name": "Portuguese"},
            {"code": "ru", "name": "Russian"},
            {"code": "pl", "name": "Polish"},
            {"code": "nl", "name": "Dutch"},
            {"code": "ro", "name": "Romanian"},
            {"code": "hu", "name": "Hungarian"},
            {"code": "cs", "name": "Czech"},
            {"code": "tr", "name": "Turkish"},
            {"code": "el", "name": "Greek"},
            {"code": "bg", "name": "Bulgarian"},
            {"code": "ar", "name": "Arabic"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ja", "name": "Japanese"},
            {"code": "ko", "name": "Korean"},
        ]