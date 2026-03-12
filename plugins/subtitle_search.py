"""Subtitle Search Plugin za WavePlayer.

Pretražuje titlove sa više provajdera:
  - OpenSubtitles.com (REST API v2 — besplatan tier)
  - Podnapisi.net (XML API — besplatan)
  - Titlovi.com
  - YIFY Subtitles

Podržava pretragu po:
  - Imenu fajla / query stringu
  - Hash fajla (za tačnije pogotke)
  - Jeziku (korisnik bira u settings-u)

NAPOMENE:
  - OpenSubtitles zahteva API key (besplatan registracijom)
  - Podnapisi.net ne zahteva ključ za pretragu
  - Download titlova je uvek besplatan
"""

import gzip
import hashlib
import io
import json
import logging
import os
import struct
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import URLError, HTTPError

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox
)

from .plugin_api import (
    SubtitlePlugin,
    PluginInfo,
    PluginType,
    SubtitleResult,
    PluginContext,
)

logger = logging.getLogger(__name__)

# Subtitle providers
PROVIDERS = {
    "opensubtitles": True,
    "podnapisi": True,
    "titlovi": True,
    "yify": True,
}

# OpenSubtitles REST API v2
OS_API_BASE = "https://api.opensubtitles.com/api/v1"
OS_API_KEY = ""  # Korisnik unosi svoj ključ u settings-u
OS_USER_AGENT = "WavePlayer v1.0"

# Podnapisi.net
PODNAPISI_API = "https://www.podnapisi.net/subtitles/search/old"


def compute_opensubtitles_hash(filepath: str) -> str:
    """Izračunaj OpenSubtitles hash za fajl.

    Algoritam: prvih 64KB + poslednjih 64KB + veličina fajla,
    sve XOR-ovano u 64-bit little-endian integer.
    """
    try:
        file_size = os.path.getsize(filepath)
        if file_size < 131072:  # 128KB minimum
            return ""

        hash_val = file_size
        block_size = 65536  # 64KB

        with open(filepath, "rb") as f:
            # Prvih 64KB
            for _ in range(block_size // 8):
                data = f.read(8)
                if len(data) < 8:
                    break
                (val,) = struct.unpack("<Q", data)
                hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF

            # Poslednjih 64KB
            f.seek(max(0, file_size - block_size))
            for _ in range(block_size // 8):
                data = f.read(8)
                if len(data) < 8:
                    break
                (val,) = struct.unpack("<Q", data)
                hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF

        return f"{hash_val:016x}"
    except Exception as e:
        logger.warning(f"Hash računanje neuspešno: {e}")
        return ""


def _http_get(url: str, headers: Optional[Dict] = None, timeout: int = 15) -> bytes:
    """Jednostavan HTTP GET sa rate limiting."""
    time.sleep(1.2)  # Rate limit fix
    req = Request(url)
    req.add_header("User-Agent", OS_USER_AGENT)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_json(url: str, headers: Optional[Dict] = None) -> Dict:
    """HTTP GET koji vraća JSON."""
    data = _http_get(url, headers)
    return json.loads(data)


class SubtitleSearchPlugin(SubtitlePlugin):
    """Multi-provider subtitle search plugin."""

    def __init__(self) -> None:
        super().__init__()
        self._os_api_key: str = ""
        self._preferred_langs: List[str] = ["sr", "en"]

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="SubtitleSearch",
            version="1.0.0",
            description="Pretraga titlova — OpenSubtitles + Podnapisi.net + Titlovi + YIFY",
            author="WavePlayer",
            plugin_type=PluginType.SUBTITLE,
            icon="🔤",
        )

    def initialize(self, context: PluginContext) -> bool:
        self.context = context
        
        self._os_api_key = context.get_config(
            "plugins.subtitle_search.api_key", ""
        )
        
        langs = context.get_config(
            "plugins.subtitle_search.languages", []
        )
        
        self._preferred_langs = langs if langs else []
        
        providers = context.get_config(
            "plugins.subtitle_search.providers", {}
        )
        
        for p in PROVIDERS:
            if p in providers:
                PROVIDERS[p] = providers[p]
        
        logger.info(
            f"SubtitleSearch: api_key={'SET' if self._os_api_key else 'EMPTY'}, "
            f"langs={self._preferred_langs}, providers={PROVIDERS}"
        )
        
        return True

    def configure(self, parent=None):
        """Open configuration dialog for plugin settings."""
        dlg = QDialog(parent)
        dlg.setWindowTitle("Subtitle Plugin Settings")
        dlg.setMinimumWidth(400)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        # API Key section
        layout.addWidget(QLabel("<b>OpenSubtitles API Key</b>"))
        layout.addWidget(QLabel("(Get it free at opensubtitles.com)"))
        
        api_edit = QLineEdit(self._os_api_key)
        api_edit.setPlaceholderText("Enter your OpenSubtitles API key")
        layout.addWidget(api_edit)

        layout.addWidget(QLabel("<br><b>Enable/Disable Providers</b>"))

        # Provider checkboxes
        chk_os = QCheckBox("OpenSubtitles.com")
        chk_os.setChecked(PROVIDERS["opensubtitles"])
        layout.addWidget(chk_os)

        chk_pod = QCheckBox("Podnapisi.net")
        chk_pod.setChecked(PROVIDERS["podnapisi"])
        layout.addWidget(chk_pod)

        chk_titlovi = QCheckBox("Titlovi.com")
        chk_titlovi.setChecked(PROVIDERS["titlovi"])
        layout.addWidget(chk_titlovi)

        chk_yify = QCheckBox("YIFY Subtitles")
        chk_yify.setChecked(PROVIDERS["yify"])
        layout.addWidget(chk_yify)

        layout.addStretch()

        # Buttons
        btn_layout = QVBoxLayout()
        
        save_btn = QPushButton("Save Settings")
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

        def save():
            # Save API key
            self._os_api_key = api_edit.text().strip()

            if self.context:
                self.context.set_config(
                    "plugins.subtitle_search.api_key",
                    self._os_api_key
                )

            # Save provider settings
            PROVIDERS["opensubtitles"] = chk_os.isChecked()
            PROVIDERS["podnapisi"] = chk_pod.isChecked()
            PROVIDERS["titlovi"] = chk_titlovi.isChecked()
            PROVIDERS["yify"] = chk_yify.isChecked()

            # Save to context if available
            if self.context:
                self.context.set_config(
                    "plugins.subtitle_search.providers",
                    PROVIDERS.copy()
                )

            logger.info(f"SubtitleSearch settings saved: API key {'SET' if self._os_api_key else 'EMPTY'}, providers={PROVIDERS}")
            dlg.accept()

        def cancel():
            dlg.reject()

        save_btn.clicked.connect(save)
        cancel_btn.clicked.connect(cancel)

        dlg.exec()

    def search(
        self,
        query: str,
        languages: List[str],
        file_hash: str = "",
        file_path: str = "",
    ) -> List[SubtitleResult]:
        """Pretraži sve provajdere i spoji rezultate."""
        results = []

        # Izračunaj hash ako imamo fajl
        if file_path and not file_hash:
            file_hash = compute_opensubtitles_hash(file_path)

        # Ako nema query, koristi ime fajla
        if not query and file_path:
            query = Path(file_path).stem
            # Očisti ime od release grupa i sl.
            for char in "._-[]()":
                query = query.replace(char, " ")

        if not languages:
            languages = self._preferred_langs or []  # [] vraća sve jezike

        if not query:
            return results

        # OpenSubtitles
        if PROVIDERS["opensubtitles"]:
            try:
                os_results = self._search_opensubtitles(query, languages, file_hash)
                results.extend(os_results)
            except Exception as e:
                logger.warning(f"OpenSubtitles pretraga neuspešna: {e}")

        # Podnapisi.net
        if PROVIDERS["podnapisi"]:
            try:
                pod_results = self._search_podnapisi(query, languages)
                results.extend(pod_results)
            except Exception as e:
                logger.warning(f"Podnapisi pretraga neuspešna: {e}")

        # YIFY Subtitles
        if PROVIDERS["yify"]:
            try:
                results.extend(self._search_yify(query))
            except Exception as e:
                logger.warning(f"YIFY pretraga neuspešna: {e}")

        # Titlovi.com
        if PROVIDERS["titlovi"]:
            try:
                results.extend(self._search_titlovi(query))
            except Exception as e:
                logger.warning(f"Titlovi pretraga neuspešna: {e}")

        # Sortiraj: hash match prvo, pa po ratingu
        results.sort(key=lambda r: (-r.hash_match, -r.rating, -r.download_count))

        logger.info(f"SubtitleSearch: ukupno {len(results)} rezultata za '{query}'")
        return results

    def download(self, result: SubtitleResult, dest_dir: str) -> Optional[str]:
        """Download titl fajl."""
        try:
            if result.provider == "OpenSubtitles":
                return self._download_opensubtitles(result, dest_dir)
            elif result.provider == "Podnapisi":
                return self._download_podnapisi(result, dest_dir)
            elif result.provider in ["YIFY", "Titlovi"]:
                return self._download_generic(result, dest_dir)
            else:
                logger.error(f"Nepoznat provider: {result.provider}")
                return None
        except Exception as e:
            logger.error(f"Download greška: {e}")
            return None

    def _download_generic(self, result: SubtitleResult, dest_dir: str) -> Optional[str]:
        """Generički download za jednostavne provajdere."""
        content = _http_get(result.download_url)
        dest_path = os.path.join(dest_dir, result.filename or "subtitle.srt")
        with open(dest_path, "wb") as f:
            f.write(content)
        return dest_path

    # ═══════════════════════════════════════════
    #  OpenSubtitles.com (REST API v2)
    # ═══════════════════════════════════════════

    def _search_opensubtitles(
        self, query: str, languages: List[str], file_hash: str = ""
    ) -> List[SubtitleResult]:
        """Pretraži OpenSubtitles REST API."""
        if not self._os_api_key:
            logger.debug("OpenSubtitles: nema API ključa, preskačem")
            return []

        params = {
            "query": query,
            "languages": ",".join(languages),
        }
        if file_hash:
            params["moviehash"] = file_hash

        url = f"{OS_API_BASE}/subtitles?{urlencode(params)}"
        headers = {
            "Api-Key": self._os_api_key,
            "Content-Type": "application/json",
        }

        data = _http_get_json(url, headers)
        results = []

        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            files = attrs.get("files", [])
            if not files:
                continue

            file_info = files[0]
            lang = attrs.get("language", "en")

            results.append(SubtitleResult(
                title=attrs.get("release", query),
                language=lang,
                language_name=attrs.get("language", lang),
                provider="OpenSubtitles",
                download_url=str(file_info.get("file_id", "")),
                filename=file_info.get("file_name", ""),
                rating=float(attrs.get("ratings", 0)),
                download_count=int(attrs.get("download_count", 0)),
                format="srt",
                hash_match=bool(attrs.get("moviehash_match", False)),
                extra={"file_id": file_info.get("file_id")},
            ))

        return results

    def _download_opensubtitles(
        self, result: SubtitleResult, dest_dir: str
    ) -> Optional[str]:
        """Download sa OpenSubtitles API."""
        file_id = result.extra.get("file_id")
        if not file_id:
            return None

        # Step 1: Request download link
        url = f"{OS_API_BASE}/download"
        headers = {
            "Api-Key": self._os_api_key,
            "Content-Type": "application/json",
        }

        import urllib.request
        req = urllib.request.Request(url, method="POST")
        req.add_header("Api-Key", self._os_api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", OS_USER_AGENT)
        req.data = json.dumps({"file_id": file_id}).encode()

        with urlopen(req, timeout=15) as resp:
            dl_data = json.loads(resp.read())

        dl_link = dl_data.get("link")
        if not dl_link:
            return None

        # Step 2: Download fajl
        content = _http_get(dl_link)

        # Sačuvaj
        filename = result.filename or f"subtitle_{result.language}.srt"
        dest_path = os.path.join(dest_dir, filename)
        with open(dest_path, "wb") as f:
            f.write(content)

        logger.info(f"OpenSubtitles download: {dest_path}")
        return dest_path

    # ═══════════════════════════════════════════
    #  Podnapisi.net
    # ═══════════════════════════════════════════

    # Podnapisi jezik kodovi (razlikuju se od ISO 639-1)
    _PODNAPISI_LANG_MAP = {
        "en": "2", "sr": "36", "hr": "8", "bs": "48",
        "de": "5", "fr": "8", "es": "28", "it": "9",
        "pt": "32", "ru": "27", "pl": "26", "nl": "23",
        "ro": "33", "hu": "15", "cs": "7", "tr": "44",
        "el": "16", "bg": "33", "ar": "38", "zh": "17",
        "ja": "11", "ko": "4", "sl": "1",
    }

    def _search_podnapisi(
        self, query: str, languages: List[str]
    ) -> List[SubtitleResult]:
        """Pretraži Podnapisi.net."""
        results = []

        # Podnapisi koristi specifične ID-jeve za jezike
        lang_ids = []
        for lang in languages:
            lid = self._PODNAPISI_LANG_MAP.get(lang)
            if lid:
                lang_ids.append(lid)

        if not lang_ids:
            lang_ids = ["2"]  # Default engleski

        params = {
            "sXML": "1",
            "sK": query,
            "sJ": ",".join(lang_ids),
        }

        url = f"{PODNAPISI_API}?{urlencode(params)}"

        try:
            raw = _http_get(url)
            # Podnapisi vraća XML — parsiramo ručno za jednostavnost
            text = raw.decode("utf-8", errors="replace")
            results = self._parse_podnapisi_xml(text)
        except Exception as e:
            logger.warning(f"Podnapisi greška: {e}")

        return results

    def _parse_podnapisi_xml(self, xml_text: str) -> List[SubtitleResult]:
        """Parsiraj Podnapisi XML odgovor."""
        results = []
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)

            for sub in root.findall(".//subtitle"):
                title = sub.findtext("release", "")
                lang = sub.findtext("languageId", "2")
                lang_name = sub.findtext("languageName", "English")
                dl_url = sub.findtext("url", "")
                sub_id = sub.findtext("id", "")
                rating = float(sub.findtext("rating", "0") or "0")
                downloads = int(sub.findtext("downloads", "0") or "0")

                if not title or not sub_id:
                    continue

                # Mapiranje languageId nazad u ISO kod
                lang_code = "en"
                for code, lid in self._PODNAPISI_LANG_MAP.items():
                    if lid == lang:
                        lang_code = code
                        break

                results.append(SubtitleResult(
                    title=title,
                    language=lang_code,
                    language_name=lang_name,
                    provider="Podnapisi",
                    download_url=f"https://www.podnapisi.net/subtitles/{sub_id}/download",
                    filename=f"{title}.srt",
                    rating=rating,
                    download_count=downloads,
                    format="srt",
                    extra={"sub_id": sub_id},
                ))
        except Exception as e:
            logger.warning(f"Podnapisi XML parse greška: {e}")

        return results

    def _download_podnapisi(
        self, result: SubtitleResult, dest_dir: str
    ) -> Optional[str]:
        """Download sa Podnapisi.net (zip fajl)."""
        content = _http_get(result.download_url)

        # Podnapisi šalje ZIP fajl
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Pronađi .srt fajl u zip-u
                for name in zf.namelist():
                    if name.lower().endswith((".srt", ".ass", ".ssa", ".sub")):
                        extracted = zf.read(name)
                        dest_path = os.path.join(dest_dir, name)
                        with open(dest_path, "wb") as f:
                            f.write(extracted)
                        logger.info(f"Podnapisi download: {dest_path}")
                        return dest_path

            # Ako nema titl fajla u zip-u, sačuvaj ceo zip
            dest_path = os.path.join(dest_dir, "subtitle.zip")
            with open(dest_path, "wb") as f:
                f.write(content)
            return dest_path

        except zipfile.BadZipFile:
            # Možda nije zip — sačuvaj kao srt
            dest_path = os.path.join(dest_dir, result.filename or "subtitle.srt")
            with open(dest_path, "wb") as f:
                f.write(content)
            return dest_path

    # ═══════════════════════════════════════════
    #  YIFY Subtitles
    # ═══════════════════════════════════════════

    def _search_yify(self, query: str) -> List[SubtitleResult]:
        """Pretraži YIFY Subtitles."""
        results = []

        try:
            url = f"https://yifysubtitles.ch/search?q={quote(query)}"
            raw = _http_get(url)

            text = raw.decode("utf-8", errors="ignore")

            import re

            matches = re.findall(
                r'href="(/subtitle/[^"]+)"[^>]*>([^<]+)</a>', text
            )

            for link, title in matches[:10]:
                results.append(
                    SubtitleResult(
                        title=title.strip(),
                        language="en",
                        language_name="English",
                        provider="YIFY",
                        download_url="https://yifysubtitles.ch" + link,
                        filename=title.strip() + ".srt",
                    )
                )

        except Exception as e:
            logger.warning(f"YIFY error: {e}")

        return results

    # ═══════════════════════════════════════════
    #  Titlovi.com
    # ═══════════════════════════════════════════

    def _search_titlovi(self, query: str) -> List[SubtitleResult]:
        """Pretraži Titlovi.com."""
        results = []

        try:
            url = f"https://titlovi.com/titlovi/?prijevod={quote(query)}"
            raw = _http_get(url)

            text = raw.decode("utf-8", errors="ignore")

            import re

            matches = re.findall(
                r'href="(/titlovi/[^"]+)"[^>]*>([^<]+)</a>',
                text,
            )

            for link, title in matches[:10]:
                results.append(
                    SubtitleResult(
                        title=title.strip(),
                        language="sr",
                        language_name="Serbian",
                        provider="Titlovi",
                        download_url="https://titlovi.com" + link,
                        filename=title.strip() + ".srt",
                    )
                )

        except Exception as e:
            logger.warning(f"Titlovi error: {e}")

        return results