"""TMDb Metadata Plugin za WavePlayer.

Preuzima metapodatke o filmovima i serijama sa The Movie Database (TMDb):
  - Poster, backdrop slike
  - Opis, ocena, žanrovi
  - Glumci, reditelj
  - Godina, trajanje

TMDb API v3 — besplatan uz registraciju na https://www.themoviedb.org/

Koristi se sa shortcut-om ili context menu-jem za prikaz info panela.
UI prikaz je u tmdb_dialog.py.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import URLError

from .plugin_api import (
    WavePlugin,
    PluginInfo,
    PluginType,
    PluginContext,
)

logger = logging.getLogger(__name__)

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


@dataclass
class MediaMetadata:
    """Metapodaci o filmu/seriji."""
    title: str = ""
    original_title: str = ""
    year: int = 0
    overview: str = ""
    rating: float = 0.0
    vote_count: int = 0
    genres: List[str] = field(default_factory=list)
    runtime: int = 0            # minuti
    poster_url: str = ""        # w500 poster
    backdrop_url: str = ""      # w1280 backdrop
    director: str = ""
    cast: List[str] = field(default_factory=list)
    media_type: str = "movie"   # movie ili tv
    tmdb_id: int = 0
    imdb_id: str = ""
    season: int = 0
    episode: int = 0
    episode_title: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _api_get(url: str, api_key: str) -> Dict:
    """TMDb API GET request."""
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}api_key={api_key}"
    req = Request(full_url)
    req.add_header("User-Agent", "WavePlayer/1.0")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _parse_filename(filename: str) -> Dict[str, str]:
    """Izvuci naziv, godinu, sezonu, epizodu iz imena fajla.

    Primeri:
      "Andor - S02E03 - Harvest.mkv" -> {title: "Andor", season: 2, episode: 3}
      "The.Matrix.1999.1080p.mkv"    -> {title: "The Matrix", year: 1999}
      "andor.s02e01.1080p.web.mkv"   -> {title: "andor", season: 2, episode: 1}
    """
    name = Path(filename).stem
    result = {"title": name, "year": "", "season": "", "episode": ""}

    # Pokušaj S01E02 format
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', name)
    if m:
        result["season"] = m.group(1)
        result["episode"] = m.group(2)
        # Naziv je sve pre SxxExx
        title_part = name[:m.start()]
        title_part = re.sub(r'[\.\-_\s]+$', '', title_part)
        for ch in "._-":
            title_part = title_part.replace(ch, " ")
        result["title"] = title_part.strip()
        return result

    # Pokušaj godinu (4 cifre)
    m = re.search(r'[\.\s\-_](\d{4})[\.\s\-_]', name)
    if m:
        result["year"] = m.group(1)
        title_part = name[:m.start()]
        for ch in "._-":
            title_part = title_part.replace(ch, " ")
        result["title"] = title_part.strip()
        return result

    # Samo očisti ime
    for ch in "._-[]()":
        name = name.replace(ch, " ")
    # Ukloni release info (1080p, x264, BluRay itd.)
    name = re.sub(
        r'\b(1080p|720p|2160p|4[kK]|[xXhH]\.?26[45]|BluRay|WEB|HDTV|BRRip|DVDRip|HEVC|AAC|DTS|REMUX)\b.*',
        '', name, flags=re.IGNORECASE
    )
    result["title"] = name.strip()
    return result


class TMDbPlugin(WavePlugin):
    """TMDb metadata plugin."""

    def __init__(self) -> None:
        super().__init__()
        self._api_key: str = ""
        self._cache: Dict[str, MediaMetadata] = {}
        self._language: str = "en-US"

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="TMDb",
            version="1.0.0",
            description="Film & TV metapodaci sa TheMovieDB.org",
            author="WavePlayer",
            plugin_type=PluginType.METADATA,
            icon="🎬",
            url="https://www.themoviedb.org/",
        )

    def initialize(self, context: PluginContext) -> bool:
        self.context = context
        self._api_key = context.get_config("plugins.tmdb.api_key", "")
        self._language = context.get_config("plugins.tmdb.language", "en-US")
        if not self._api_key:
            logger.info("TMDb: nema API ključa — registruj se na themoviedb.org")
        return True

    # --- Javne metode ---

    def show_metadata(self, file_path: str = "", parent=None) -> None:
        """Prikaži metadata dijalog za dati fajl ili trenutni.

        Ovo je glavna metoda koju main_window poziva iz context menija.
        Ako file_path nije dat, koristi se trenutno pušteni fajl.
        """
        from ui.tmdb_dialog import TMDbMetadataDialog

        if not file_path and self.context:
            file_path = self.context.get_current_file()

        if not file_path:
            if self.context:
                self.context.show_osd("Prvo učitaj video fajl", 2000)
            return

        dialog = TMDbMetadataDialog(self, file_path, parent)
        dialog.exec()

    def lookup_current(self) -> Optional[MediaMetadata]:
        """Potraži metapodatke za trenutno pušteni fajl."""
        if not self._api_key or not self.context:
            return None

        file_path = self.context.get_current_file()
        if not file_path:
            return None

        # Keš po putanji
        if file_path in self._cache:
            return self._cache[file_path]

        parsed = _parse_filename(os.path.basename(file_path))
        title = parsed["title"]
        if not title:
            return None

        # Da li je serija (ima sezonu/epizodu)?
        if parsed.get("season"):
            meta = self._search_tv(title, parsed)
        else:
            meta = self._search_movie(title, parsed.get("year", ""))

        if meta:
            self._cache[file_path] = meta
        return meta

    def lookup_file(self, file_path: str) -> Optional[MediaMetadata]:
        """Potraži metapodatke za specifičan fajl (za welcome screen itd.)."""
        if not self._api_key:
            return None

        # Keš po putanji
        if file_path in self._cache:
            return self._cache[file_path]

        parsed = _parse_filename(os.path.basename(file_path))
        title = parsed["title"]
        if not title:
            return None

        if parsed.get("season"):
            meta = self._search_tv(title, parsed)
        else:
            meta = self._search_movie(title, parsed.get("year", ""))

        if meta:
            self._cache[file_path] = meta
        return meta

    def get_info_text(self) -> str:
        """Vrati formatiran tekst za OSD prikaz."""
        meta = self.lookup_current()
        if not meta:
            return "ℹ Nema informacija"

        lines = [meta.title]
        if meta.year:
            lines[0] += f" ({meta.year})"
        if meta.genres:
            lines.append(" · ".join(meta.genres[:3]))
        if meta.rating > 0:
            stars = "★" * int(meta.rating / 2) + "☆" * (5 - int(meta.rating / 2))
            lines.append(f"{stars} {meta.rating:.1f}/10")
        if meta.director:
            lines.append(f"🎬 {meta.director}")
        if meta.cast:
            lines.append(f"👥 {', '.join(meta.cast[:4])}")
        if meta.overview:
            # Skrati opis na ~100 karaktera
            desc = meta.overview[:120]
            if len(meta.overview) > 120:
                desc += "..."
            lines.append(desc)

        return "\n".join(lines)

    def get_poster_url(self, file_path: str) -> str:
        """Vrati poster URL za fajl (za welcome screen thumbnails)."""
        meta = self._cache.get(file_path)
        if meta:
            return meta.poster_url
        return ""

    # --- Interne metode ---

    def _search_movie(self, title: str, year: str = "") -> Optional[MediaMetadata]:
        """Pretraži TMDb za film."""
        try:
            params = {"query": title, "language": self._language}
            if year:
                params["year"] = year
            url = f"{TMDB_API_BASE}/search/movie?{urlencode(params)}"
            data = _api_get(url, self._api_key)

            results = data.get("results", [])
            if not results:
                return None

            movie = results[0]
            tmdb_id = movie["id"]

            # Detaljni info
            detail_url = f"{TMDB_API_BASE}/movie/{tmdb_id}?language={self._language}&append_to_response=credits"
            detail = _api_get(detail_url, self._api_key)

            meta = MediaMetadata(
                title=detail.get("title", title),
                original_title=detail.get("original_title", ""),
                year=int(detail.get("release_date", "0000")[:4]) if detail.get("release_date") else 0,
                overview=detail.get("overview", ""),
                rating=float(detail.get("vote_average", 0)),
                vote_count=int(detail.get("vote_count", 0)),
                genres=[g["name"] for g in detail.get("genres", [])],
                runtime=int(detail.get("runtime", 0) or 0),
                poster_url=f"{TMDB_IMG_BASE}/w500{detail['poster_path']}" if detail.get("poster_path") else "",
                backdrop_url=f"{TMDB_IMG_BASE}/w1280{detail['backdrop_path']}" if detail.get("backdrop_path") else "",
                media_type="movie",
                tmdb_id=tmdb_id,
                imdb_id=detail.get("imdb_id", ""),
            )

            # Režiser i glumci
            credits = detail.get("credits", {})
            for crew in credits.get("crew", []):
                if crew.get("job") == "Director":
                    meta.director = crew.get("name", "")
                    break
            meta.cast = [c["name"] for c in credits.get("cast", [])[:6]]

            return meta

        except Exception as e:
            logger.warning(f"TMDb movie search greška: {e}")
            return None

    def _search_tv(self, title: str, parsed: Dict) -> Optional[MediaMetadata]:
        """Pretraži TMDb za seriju + epizodu."""
        try:
            params = {"query": title, "language": self._language}
            url = f"{TMDB_API_BASE}/search/tv?{urlencode(params)}"
            data = _api_get(url, self._api_key)

            results = data.get("results", [])
            if not results:
                return None

            show = results[0]
            tmdb_id = show["id"]

            # Detaljni info o seriji
            detail_url = f"{TMDB_API_BASE}/tv/{tmdb_id}?language={self._language}&append_to_response=credits"
            detail = _api_get(detail_url, self._api_key)

            meta = MediaMetadata(
                title=detail.get("name", title),
                original_title=detail.get("original_name", ""),
                year=int(detail.get("first_air_date", "0000")[:4]) if detail.get("first_air_date") else 0,
                overview=detail.get("overview", ""),
                rating=float(detail.get("vote_average", 0)),
                vote_count=int(detail.get("vote_count", 0)),
                genres=[g["name"] for g in detail.get("genres", [])],
                poster_url=f"{TMDB_IMG_BASE}/w500{detail['poster_path']}" if detail.get("poster_path") else "",
                backdrop_url=f"{TMDB_IMG_BASE}/w1280{detail['backdrop_path']}" if detail.get("backdrop_path") else "",
                media_type="tv",
                tmdb_id=tmdb_id,
            )

            credits = detail.get("credits", {})
            meta.cast = [c["name"] for c in credits.get("cast", [])[:6]]

            # Epizoda info
            season = parsed.get("season", "")
            episode = parsed.get("episode", "")
            if season and episode:
                meta.season = int(season)
                meta.episode = int(episode)
                try:
                    ep_url = f"{TMDB_API_BASE}/tv/{tmdb_id}/season/{season}/episode/{episode}?language={self._language}"
                    ep_data = _api_get(ep_url, self._api_key)
                    meta.episode_title = ep_data.get("name", "")
                    meta.overview = ep_data.get("overview", meta.overview)
                    meta.rating = float(ep_data.get("vote_average", meta.rating))
                    if ep_data.get("still_path"):
                        meta.backdrop_url = f"{TMDB_IMG_BASE}/w1280{ep_data['still_path']}"
                except Exception:
                    pass

                # Ažuriraj naslov
                meta.title = f"{meta.title} S{meta.season:02d}E{meta.episode:02d}"
                if meta.episode_title:
                    meta.title += f" — {meta.episode_title}"

            return meta

        except Exception as e:
            logger.warning(f"TMDb TV search greška: {e}")
            return None

    def configure(self, parent=None) -> None:
        """Podešavanja TMDb plugina — API ključ i jezik."""
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QLineEdit, QComboBox, QPushButton, QMessageBox,
        )
        from PyQt6.QtCore import Qt

        dlg = QDialog(parent)
        dlg.setWindowTitle("TMDb podešavanja")
        dlg.setMinimumWidth(420)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # API ključ
        layout.addWidget(QLabel("TMDb API ključ (v3):"))
        key_edit = QLineEdit()
        key_edit.setPlaceholderText("Unesi API ključ sa themoviedb.org")
        key_edit.setText(self._api_key)
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(key_edit)

        # Prikaz/sakrivanje ključa
        show_key_btn = QPushButton("👁 Prikaži")
        show_key_btn.setCheckable(True)
        show_key_btn.toggled.connect(
            lambda checked: key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel(
            '<a href="https://www.themoviedb.org/settings/api" style="color:#4fc3f7;">Preuzmi API ključ</a>'
        ))
        key_row.itemAt(0).widget().setOpenExternalLinks(True)
        key_row.addStretch()
        key_row.addWidget(show_key_btn)
        layout.addLayout(key_row)

        # Jezik
        layout.addWidget(QLabel("Jezik metapodataka:"))
        lang_combo = QComboBox()
        languages = [
            ("Engleski", "en-US"),
            ("Srpski", "sr-RS"),
            ("Hrvatski", "hr-HR"),
            ("Nemački", "de-DE"),
            ("Francuski", "fr-FR"),
            ("Španski", "es-ES"),
            ("Italijanski", "it-IT"),
            ("Portugalski", "pt-PT"),
            ("Ruski", "ru-RU"),
            ("Japanski", "ja-JP"),
            ("Korejski", "ko-KR"),
            ("Kineski", "zh-CN"),
        ]
        for name, code in languages:
            lang_combo.addItem(name, code)
        idx = lang_combo.findData(self._language)
        if idx >= 0:
            lang_combo.setCurrentIndex(idx)
        layout.addWidget(lang_combo)

        # Dugmad
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("Sačuvaj")
        cancel_btn = QPushButton("Otkaži")
        save_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_key = key_edit.text().strip()
            new_lang = lang_combo.currentData()

            self._api_key = new_key
            self._language = new_lang

            # Sačuvaj u config
            if self.context:
                self.context.set_config("plugins.tmdb.api_key", new_key)
                self.context.set_config("plugins.tmdb.language", new_lang)

            # Očisti keš jer se jezik možda promenio
            self._cache.clear()

            logger.info(f"TMDb: api_key={'set' if new_key else 'empty'}, lang={new_lang}")
