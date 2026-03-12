"""Application configuration management.

Handles loading, saving, and accessing configuration values.
Uses JSON file for storage - portable across all platforms.

PORTABILITY NOTES:
  - C++: QSettings or nlohmann::json
  - Rust: serde + serde_json with config crate
  - No UI dependencies - pure data + file I/O
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from .media_info import PlayerConfig

logger = logging.getLogger(__name__)


# Podrazumevani direktorijum za konfiguraciju
# Na Linux-u: ~/.config/WavePlayer/
# Na Windows-u: %APPDATA%/WavePlayer/
def _get_config_dir() -> Path:
    """Vrati direktorijum za konfiguraciju.

    Koristi XDG standard na Linux-u, AppData na Windows-u.
    """
    # Proveri XDG_CONFIG_HOME (Linux)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    elif os.name == "nt":
        # Windows
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        # Linux/macOS fallback
        base = Path.home() / ".config"

    return base / "WavePlayer"


# Podrazumevani fajl za konfiguraciju
CONFIG_DIR: Path = _get_config_dir()
CONFIG_FILE: str = "config.json"

# Podrazumevane vrednosti - koriste se ako nema config fajla
DEFAULTS: dict[str, Any] = {
    # Prozor
    "window": {
        "width": 1280,
        "height": 720,
        "x": 100,
        "y": 100,
        "maximized": False,
    },
    # Audio
    "audio": {
        "volume": 100,
        "muted": False,
    },
    # Reprodukcija
    "playback": {
        "speed": 1.0,
        "resume_playback": True,
    },
    # UI
    "ui": {
        "playlist_visible": False,
        "playlist_width": 320,
        "auto_hide_delay_ms": 3000,
        "show_osd": True,
        "theme": "midnight_red",
        "osd_theme": "minimal",
    },
    # Engine
    "engine": {
        "backend": "mpv",
        "hardware_decoding": "auto",
        "vo": "gpu",
    },
    # Titlovi - HRT broadcast stil po defaultu
    # Beli tekst sa debelim crnim outline-om, bez pozadine
    "subtitles": {
        "auto_load": "exact",
        "preferred_lang": "sr",
        "fallback_lang": "en",
        "auto_select": True,
        "encoding": "Auto-detect",
        "fix_timing": False,
        # Font - čist sans-serif kao HRT
        "font_family": "Arial",
        "font_size": 46,
        "bold": True,
        "italic": False,
        # Boje - beli tekst sa debelim crnim obrubom
        "color": "#FFFFFF",
        "border_color": "#000000",
        "border_size": 3.0,
        "shadow_color": "#000000",
        "shadow_offset": 1.0,
        # Bez pozadine - outline daje kontrast
        "bg_enabled": False,
        "bg_opacity": "80",
        "bg_padding": 8,
        # Pozicija - nisko, centrirano
        "position": 98,
        "margin_v": 20,
        "margin_h": 25,
        "alignment": "bottom_center",
        "scale_with_window": True,
        "justify": "center",
        # Sinhronizacija
        "delay": 0.0,
        "speed": 1.0,
        "fps_override": "Auto",
        # ASS
        "ass_override": "no",
        "ass_hinting": "none",
        "ass_shaping": "complex",
        "vsfilter_compat": True,
        "ass_force_margins": False,
        "stretch_ass": False,
        # Napredno
        "secondary_enabled": False,
        "secondary_lang": "en",
        "blend": "no",
        "clear_on_seek": True,
        "gray": False,
        "filter_sdh": False,
        "filter_regex": "",
    },
    # Poslednji fajl (za resume)
    "last_session": {
        "file": "",
        "position": 0.0,
        "playlist": [],
    },
    # Nedavni fajlovi
    "recent_files": [],
    # Torrent streaming
    "torrent": {
        "download_dir": "",  # prazan = ~/Downloads/WavePlayer
        "buffer_mb": 500,
        "max_download_kbps": 0,    # 0 = unlimited
        "max_upload_kbps": 0,
        "port_min": 6881,
        "port_max": 6891,
        "seed_after_download": True,
        "seed_ratio": 1.0,
        "dht_enabled": True,
        "encryption": 1,           # 0=off, 1=enabled, 2=forced
        "connections_limit": 200,
        "preallocate": False,
        "delete_on_close": False,
    },
    # Plugini
    "plugins": {
        "enabled": True,           # Globalni on/off za plugin sistem
        "auto_update": False,      # Automatsko ažuriranje plugina
        "directory": "",           # prazan = ~/.config/WavePlayer/plugins/
        "installed": {},           # {"plugin_id": {"enabled": True, "version": "1.0", ...}}
    },
}

# Maksimalan broj nedavnih fajlova
MAX_RECENT_FILES: int = 20


class Config:
    """Centralna konfiguracija aplikacije.

    Učitava JSON fajl pri kreiranju, čuva promene odmah.
    Thread-safe nije potreban jer se koristi samo iz UI niti.

    Pristup vrednostima:
        config = Config()
        volume = config.get("audio.volume", 100)
        config.set("audio.volume", 80)
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path:
            self._config_path = Path(config_path)
        else:
            self._config_path = CONFIG_DIR / CONFIG_FILE

        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Učitaj konfiguraciju iz JSON fajla."""
        # Počni sa default vrednostima
        self._data = self._deep_copy(DEFAULTS)

        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Spoji sačuvane vrednosti sa default-ovima
                self._deep_merge(self._data, saved)
                logger.info(f"Konfiguracija učitana: {self._config_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Greška pri učitavanju config-a: {e}")
                logger.info("Koristim podrazumevane vrednosti")
        else:
            logger.info("Config fajl ne postoji, koristim default vrednosti")

    def save(self) -> None:
        """Sačuvaj konfiguraciju u JSON fajl."""
        try:
            # Kreiraj direktorijum ako ne postoji
            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Konfiguracija sačuvana: {self._config_path}")
        except IOError as e:
            logger.error(f"Greška pri čuvanju config-a: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Vrati vrednost po dot-notaciji ključu.

        Primer: config.get("audio.volume", 100)
        """
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Postavi vrednost po dot-notaciji ključu.

        Primer: config.set("audio.volume", 80)
        """
        keys = key.split(".")
        target = self._data
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def get_section(self, section: str) -> dict[str, Any]:
        """Vrati celu sekciju kao dict.

        Primer: config.get_section("audio") -> {"volume": 100, "muted": False}
        """
        return self._data.get(section, {})

    # --- Convenience metode ---

    def to_player_config(self) -> PlayerConfig:
        """Konvertuj u PlayerConfig dataclass."""
        return PlayerConfig(
            window_width=self.get("window.width", 1280),
            window_height=self.get("window.height", 720),
            window_x=self.get("window.x", 100),
            window_y=self.get("window.y", 100),
            volume=self.get("audio.volume", 100),
            muted=self.get("audio.muted", False),
            speed=self.get("playback.speed", 1.0),
            auto_hide_delay_ms=self.get("ui.auto_hide_delay_ms", 3000),
            playlist_visible=self.get("ui.playlist_visible", False),
            playlist_width=self.get("ui.playlist_width", 320),
            last_file=self.get("last_session.file", ""),
            last_position=self.get("last_session.position", 0.0),
        )

    def from_player_config(self, config: PlayerConfig) -> None:
        """Ažuriraj iz PlayerConfig dataclass-a."""
        self.set("window.width", config.window_width)
        self.set("window.height", config.window_height)
        self.set("window.x", config.window_x)
        self.set("window.y", config.window_y)
        self.set("audio.volume", config.volume)
        self.set("audio.muted", config.muted)
        self.set("playback.speed", config.speed)
        self.set("ui.playlist_visible", config.playlist_visible)
        self.set("ui.playlist_width", config.playlist_width)
        self.set("last_session.file", config.last_file)
        self.set("last_session.position", config.last_position)

    def add_recent_file(self, file_path: str) -> None:
        """Dodaj fajl u listu nedavnih."""
        recent: list = self.get("recent_files", [])
        # Ukloni ako već postoji (pomeri na vrh)
        if file_path in recent:
            recent.remove(file_path)
        # Dodaj na početak
        recent.insert(0, file_path)
        # Ograniči listu
        recent = recent[:MAX_RECENT_FILES]
        self.set("recent_files", recent)

    def get_recent_files(self) -> list[str]:
        """Vrati listu nedavnih fajlova."""
        return self.get("recent_files", [])

    def clear_recent_files(self) -> None:
        """Obriši listu nedavnih fajlova."""
        self.set("recent_files", [])

    # --- Plugin metode ---

    def get_plugin_enabled(self, name: str, default: bool = True) -> bool:
        """Vrati da li je plugin uključen."""
        return self.get(f"plugins.enabled.{name}", default)

    def set_plugin_enabled(self, name: str, value: bool) -> None:
        """Postavi da li je plugin uključen."""
        self.set(f"plugins.enabled.{name}", value)

    def get_plugins_dir(self) -> Path:
        """Vrati direktorijum za plugine."""
        custom = self.get("plugins.directory", "")
        if custom:
            return Path(custom)
        return self._config_path.parent / "plugins"

    def get_installed_plugins(self) -> dict:
        """Vrati dict instaliranih plugina."""
        return self.get("plugins.installed", {})

    def set_plugin_enabled_old(self, plugin_id: str, enabled: bool) -> None:
        """Uključi/isključi plugin (stara metoda - u installed dict)."""
        installed = self.get("plugins.installed", {})
        if plugin_id in installed:
            installed[plugin_id]["enabled"] = enabled
            self.set("plugins.installed", installed)

    def register_plugin(self, plugin_id: str, name: str, version: str,
                        description: str = "", author: str = "") -> None:
        """Registruj novi plugin u config."""
        installed = self.get("plugins.installed", {})
        installed[plugin_id] = {
            "enabled": True,
            "name": name,
            "version": version,
            "description": description,
            "author": author,
        }
        self.set("plugins.installed", installed)

    def unregister_plugin(self, plugin_id: str) -> None:
        """Ukloni plugin iz config-a."""
        installed = self.get("plugins.installed", {})
        installed.pop(plugin_id, None)
        self.set("plugins.installed", installed)

    # --- Pomoćne metode ---

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """Rekurzivno spoji override u base dict."""
        for key, value in override.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                Config._deep_merge(base[key], value)
            else:
                base[key] = value

    @staticmethod
    def _deep_copy(data: dict) -> dict:
        """Duboka kopija dict-a (bez copy modula za portabilnost)."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = Config._deep_copy(value)
            elif isinstance(value, list):
                result[key] = list(value)
            else:
                result[key] = value
        return result

    def __repr__(self) -> str:
        return f"Config(path={self._config_path})"