"""Subtitle Search Plugin za WavePlayer v3.

Pretražuje titlove sa više provajdera:
  - OpenSubtitles.com (REST API v2 — besplatan tier, zahteva API key)
  - Podnapisi.net (XML API — potpuno besplatan, ne treba API key)
  - OpenSubtitles.org (stari REST, besplatan za hash pretragu)
  - Subdl.com (REST API — besplatan tier, zahteva API key)

NAPOMENE:
  - OpenSubtitles.com REST API: besplatan tier, 5 req/sec, 20 download/dan
    registracija na opensubtitles.com/consumers za API key
  - Podnapisi.net: potpuno besplatan, ne zahteva registraciju
  - OpenSubtitles.org: stari REST API, hash lookup bez API key-a
  - Subdl.com: besplatan tier sa API key-em
"""

import gzip
import io
import json
import logging
import os
import re
import struct
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QFrame,
)
from PyQt6.QtCore import Qt

from .plugin_api import (
    SubtitlePlugin,
    PluginInfo,
    PluginType,
    SubtitleResult,
    PluginContext,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  KONSTANTE
# ═══════════════════════════════════════════

USER_AGENT = "WavePlayer v1.0"

# OpenSubtitles REST API v2 (novi sajt, zahteva API key)
OS_API_BASE = "https://api.opensubtitles.com/api/v1"

# OpenSubtitles.org stari REST API (besplatan hash search)
OS_ORG_API = "https://rest.opensubtitles.org/search"

# Podnapisi.net XML API
PODNAPISI_API = "https://www.podnapisi.net/subtitles/search/old"

# Subdl.com API
SUBDL_API_BASE = "https://api.subdl.com/api/v1/subtitles"

# Titlovi.com API (Kodi API — zahteva registraciju na titlovi.com)
TITLOVI_API = "https://kodi.titlovi.com/api/subtitles"

# Default provajderi
DEFAULT_PROVIDERS = {
    "opensubtitles": True,
    "podnapisi": True,
    "opensubtitles_org": True,   # besplatan, hash search
    "titlovi": False,            # titlovi.com — treba username/password
    "subdl": False,
}

# Titlovi.com jezički mapping
TITLOVI_LANG_MAP = {
    "sr": "Srpski", "en": "English", "hr": "Hrvatski",
    "bs": "Bosanski", "sl": "Slovenski", "mk": "Makedonski",
}
TITLOVI_LANG_REVERSE = {v: k for k, v in TITLOVI_LANG_MAP.items()}

# Podnapisi jezik kodovi (ISO 639-1 → Podnapisi ID)
PODNAPISI_LANG_MAP = {
    "sq": "42", "ar": "38", "be": "46", "bs": "48", "bg": "33",
    "ca": "49", "zh": "17", "hr": "38", "cs": "7", "da": "24",
    "nl": "23", "en": "2", "et": "20", "fi": "31", "fr": "8",
    "de": "5", "el": "16", "he": "22", "hi": "42", "hu": "15",
    "is": "6", "it": "9", "ja": "11", "ko": "4", "lv": "21",
    "lt": "19", "mk": "35", "ms": "50", "no": "3", "pl": "26",
    "pt": "32", "ro": "13", "ru": "27", "sr": "36", "sk": "37",
    "sl": "1", "es": "28", "sv": "25", "th": "44", "tr": "30",
    "uk": "34", "vi": "45",
}
PODNAPISI_LANG_REVERSE = {v: k for k, v in PODNAPISI_LANG_MAP.items()}

# Jezici koji se prikazuju u UI-u
LANGUAGE_OPTIONS = [
    ("Srpski", "sr"), ("Engleski", "en"), ("Hrvatski", "hr"),
    ("Bosanski", "bs"), ("Slovenački", "sl"), ("Makedonski", "mk"),
    ("Nemački", "de"), ("Francuski", "fr"), ("Španski", "es"),
    ("Italijanski", "it"), ("Portugalski", "pt"), ("Ruski", "ru"),
    ("Poljski", "pl"), ("Holandski", "nl"), ("Rumunski", "ro"),
    ("Mađarski", "hu"), ("Češki", "cs"), ("Turski", "tr"),
    ("Grčki", "el"), ("Bugarski", "bg"), ("Arapski", "ar"),
    ("Kineski", "zh"), ("Japanski", "ja"), ("Korejski", "ko"),
]
LANGUAGE_NAMES = {code: name for name, code in LANGUAGE_OPTIONS}

# OpenSubtitles.org jezički kodovi (3-slovna)
LANG_2_TO_3 = {
    "sr": "srp", "en": "eng", "hr": "hrv", "bs": "bos", "sl": "slv",
    "mk": "mac", "de": "ger", "fr": "fre", "es": "spa", "it": "ita",
    "pt": "por", "ru": "rus", "pl": "pol", "nl": "dut", "ro": "rum",
    "hu": "hun", "cs": "cze", "tr": "tur", "el": "gre", "bg": "bul",
    "ar": "ara", "zh": "chi", "ja": "jpn", "ko": "kor",
}


# ═══════════════════════════════════════════
#  HTTP HELPERS
# ═══════════════════════════════════════════

def _http_request(
    url: str,
    headers: Optional[Dict] = None,
    data: Optional[bytes] = None,
    method: str = "GET",
    timeout: int = 15,
) -> bytes:
    req = Request(url, method=method)
    req.add_header("User-Agent", USER_AGENT)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data:
        req.data = data
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as e:
        logger.warning(f"HTTP {e.code} za {url}: {e.reason}")
        raise
    except URLError as e:
        logger.warning(f"URL greška za {url}: {e.reason}")
        raise


def _http_get_json(url: str, headers: Optional[Dict] = None) -> Any:
    raw = _http_request(url, headers)
    return json.loads(raw)


def _http_request_with_retry(
    url: str,
    headers: Optional[Dict] = None,
    data: Optional[bytes] = None,
    method: str = "GET",
    timeout: int = 15,
    retries: int = 2,
    delay: float = 2.0,
) -> bytes:
    """HTTP request sa retry logikom za 5xx greške."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            return _http_request(url, headers, data, method, timeout)
        except HTTPError as e:
            last_error = e
            if e.code >= 500 and attempt < retries:
                logger.info(f"Server {e.code}, retry {attempt+1}/{retries} za {delay}s...")
                time.sleep(delay)
                delay *= 1.5
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(delay)
                continue
            raise
    raise last_error  # type: ignore


# ═══════════════════════════════════════════
#  QUERY PARSING
# ═══════════════════════════════════════════

def _clean_query(raw: str) -> str:
    """Očisti query od viška za bolju pretragu.

    'Andor - S02E03 - Harvest' → 'Andor S02E03'
    'The.Last.of.Us.S01E05.720p.WEB' → 'The Last of Us S01E05'
    'Cold.Storage.2026.1080p.WEBRip.x264.AAC5.1-[YTS.BZ]' → 'Cold Storage 2026'
    """
    q = raw.replace(".", " ").replace("_", " ")

    # Ukloni group tagove u zagradama PRVO
    q = re.sub(r'[\[\(][^\]\)]*[\]\)]', '', q)

    # Ukloni kvalitet/codec tagove (proširen regex)
    q = re.sub(
        r'\b('
        r'720p|1080p|2160p|4k|uhd|'
        r'web|webrip|web-?dl|bluray|blu-?ray|brrip|bdrip|'
        r'hdtv|hdrip|dvdrip|dvdscr|cam|ts|tc|'
        r'x264|x265|h\.?264|h\.?265|hevc|avc|'
        r'aac\d*[\. ]?\d*|ac3|eac3|atmos|dts|truehd|flac|mp3|'
        r'remux|proper|repack|extended|unrated|'
        r'yts|yify|rarbg|ettv|eztv|sparks|'
        r'\d+ch|\d+\.\d+ch|5\.1|7\.1|2\.0'
        r')\b',
        '', q, flags=re.IGNORECASE
    )

    # Ukloni trailing crte i tačke od group name-a (npr "-YTS BZ")
    q = re.sub(r'[\-–—]+\s*\w*\s*$', '', q)

    # Ukloni trailing ALL-CAPS reči (release group names: BONE, NTG, AOC, SPARKS...)
    # Ali samo ako pre toga postoji godina (4 cifre)
    q = re.sub(r'(\b\d{4}\b)\s+[A-Z]{2,}\s*$', r'\1', q)

    # Zadrži samo ime + S01E01 (za serije)
    m = re.search(r'(S\d{1,2}E\d{1,2})', q, re.IGNORECASE)
    if m:
        q = q[:m.start()] + " " + m.group(1)

    # Očisti višestruke razmake i crte
    q = re.sub(r'[\-–—]+', ' ', q)
    q = " ".join(q.split()).strip()
    return q


def _extract_series_query(raw: str) -> str:
    """Za Podnapisi: izvuci samo ime serije (bez S01E01).
    Podnapisi bolje radi sa kraćim query-jem.
    """
    q = raw.replace(".", " ").replace("_", " ")
    q = re.sub(r'[\[\(][^\]\)]*[\]\)]', '', q)
    q = re.sub(r'[\-–—]+', ' ', q)
    m = re.search(r'S\d{1,2}E\d{1,2}', q, re.IGNORECASE)
    if m:
        q = q[:m.start()].strip()
    q = " ".join(q.split()).strip()
    return q if q else raw


# ═══════════════════════════════════════════
#  HASH COMPUTING
# ═══════════════════════════════════════════

def compute_opensubtitles_hash(filepath: str) -> str:
    try:
        if not filepath or not os.path.isfile(filepath):
            return ""
        file_size = os.path.getsize(filepath)
        if file_size < 131072:
            return ""
        hash_val = file_size
        block_size = 65536
        with open(filepath, "rb") as f:
            for _ in range(block_size // 8):
                d = f.read(8)
                if len(d) < 8:
                    break
                (val,) = struct.unpack("<Q", d)
                hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF
            f.seek(max(0, file_size - block_size))
            for _ in range(block_size // 8):
                d = f.read(8)
                if len(d) < 8:
                    break
                (val,) = struct.unpack("<Q", d)
                hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF
        return f"{hash_val:016x}"
    except Exception as e:
        logger.warning(f"Hash računanje neuspešno: {e}")
        return ""


# ═══════════════════════════════════════════
#  SUBTITLE SEARCH PLUGIN
# ═══════════════════════════════════════════

class SubtitleSearchPlugin(SubtitlePlugin):
    """Multi-provider subtitle search plugin v3."""

    def __init__(self) -> None:
        super().__init__()
        self._os_api_key: str = ""
        self._os_username: str = ""
        self._os_password: str = ""
        self._os_token: str = ""
        self._subdl_api_key: str = ""
        self._titlovi_username: str = ""
        self._titlovi_password: str = ""
        self._titlovi_token: str = ""
        self._titlovi_user_id: int = 0
        self._preferred_langs: List[str] = ["sr", "en"]
        self._providers: Dict[str, bool] = DEFAULT_PROVIDERS.copy()

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="SubtitleSearch",
            version="3.0.0",
            description="Pretraga titlova — OS.com + OS.org + Podnapisi + Titlovi.com + Subdl",
            author="WavePlayer",
            plugin_type=PluginType.SUBTITLE,
            icon="🔤",
        )

    def initialize(self, context: PluginContext) -> bool:
        self.context = context
        self._os_api_key = context.get_config("plugins.subtitle_search.api_key", "")
        self._os_username = context.get_config("plugins.subtitle_search.os_username", "")
        self._os_password = context.get_config("plugins.subtitle_search.os_password", "")
        self._subdl_api_key = context.get_config("plugins.subtitle_search.subdl_api_key", "")
        self._titlovi_username = context.get_config("plugins.subtitle_search.titlovi_username", "")
        self._titlovi_password = context.get_config("plugins.subtitle_search.titlovi_password", "")
        langs = context.get_config("plugins.subtitle_search.languages", [])
        self._preferred_langs = langs if langs else ["sr", "en"]
        providers = context.get_config("plugins.subtitle_search.providers", {})
        for p in self._providers:
            if p in providers:
                self._providers[p] = providers[p]
        logger.info(
            f"SubtitleSearch v3: api_key={'SET' if self._os_api_key else 'EMPTY'}, "
            f"langs={self._preferred_langs}, providers={self._providers}"
        )
        return True

    # ── Properties za subtitle_dialog ──

    @property
    def providers(self) -> Dict[str, bool]:
        return self._providers.copy()

    @property
    def os_api_key(self) -> str:
        return self._os_api_key

    @property
    def subdl_api_key(self) -> str:
        return self._subdl_api_key

    # ── Configure dialog ──

    def configure(self, parent=None):
        dlg = QDialog(parent)
        dlg.setWindowTitle("Subtitle Search — Podešavanja")
        dlg.setMinimumWidth(520)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        # --- OpenSubtitles.com ---
        os_group = QFrame()
        os_group.setObjectName("pluginConfigGroup")
        os_lay = QVBoxLayout(os_group)
        os_lay.setContentsMargins(12, 10, 12, 10)
        os_lay.setSpacing(6)

        h = QLabel("🔑 OpenSubtitles.com (REST API v2)")
        h.setStyleSheet("font-weight: bold; font-size: 13px;")
        os_lay.addWidget(h)
        n = QLabel(
            'Besplatan — registruj se na '
            '<a href="https://www.opensubtitles.com/en/consumers">'
            'opensubtitles.com/consumers</a>  (20 dl/dan)'
        )
        n.setOpenExternalLinks(True)
        n.setWordWrap(True)
        n.setStyleSheet("font-size: 11px; color: #888;")
        os_lay.addWidget(n)

        kr = QHBoxLayout()
        kr.addWidget(QLabel("API Key:"))
        api_edit = QLineEdit(self._os_api_key)
        api_edit.setPlaceholderText("API key...")
        api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        kr.addWidget(api_edit)
        os_lay.addLayout(kr)

        ur = QHBoxLayout()
        ur.addWidget(QLabel("Username:"))
        user_edit = QLineEdit(self._os_username)
        user_edit.setPlaceholderText("Opciono")
        ur.addWidget(user_edit)
        os_lay.addLayout(ur)

        pr = QHBoxLayout()
        pr.addWidget(QLabel("Password:"))
        pass_edit = QLineEdit(self._os_password)
        pass_edit.setPlaceholderText("Opciono")
        pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pr.addWidget(pass_edit)
        os_lay.addLayout(pr)

        show_key = QCheckBox("Prikaži lozinke")
        show_key.toggled.connect(lambda c: (
            api_edit.setEchoMode(QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password),
            pass_edit.setEchoMode(QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password),
        ))
        os_lay.addWidget(show_key)
        chk_os = QCheckBox("Omogući OpenSubtitles.com")
        chk_os.setChecked(self._providers.get("opensubtitles", True))
        os_lay.addWidget(chk_os)
        layout.addWidget(os_group)

        # --- OpenSubtitles.org (besplatan) ---
        osorg_group = QFrame()
        osorg_group.setObjectName("pluginConfigGroup")
        osorg_lay = QVBoxLayout(osorg_group)
        osorg_lay.setContentsMargins(12, 10, 12, 10)
        osorg_lay.setSpacing(6)
        oh = QLabel("🌍 OpenSubtitles.org (besplatan)")
        oh.setStyleSheet("font-weight: bold; font-size: 13px;")
        osorg_lay.addWidget(oh)
        on = QLabel("Stari REST API — besplatan, bez registracije. Direktan download.")
        on.setStyleSheet("font-size: 11px; color: #888;")
        on.setWordWrap(True)
        osorg_lay.addWidget(on)
        chk_osorg = QCheckBox("Omogući OpenSubtitles.org")
        chk_osorg.setChecked(self._providers.get("opensubtitles_org", True))
        osorg_lay.addWidget(chk_osorg)
        layout.addWidget(osorg_group)

        # --- Podnapisi ---
        pod_group = QFrame()
        pod_group.setObjectName("pluginConfigGroup")
        pod_lay = QVBoxLayout(pod_group)
        pod_lay.setContentsMargins(12, 10, 12, 10)
        pod_lay.setSpacing(6)
        ph = QLabel("🌐 Podnapisi.net")
        ph.setStyleSheet("font-weight: bold; font-size: 13px;")
        pod_lay.addWidget(ph)
        pn = QLabel("Potpuno besplatan, ne zahteva registraciju.")
        pn.setStyleSheet("font-size: 11px; color: #888;")
        pod_lay.addWidget(pn)
        chk_pod = QCheckBox("Omogući Podnapisi")
        chk_pod.setChecked(self._providers.get("podnapisi", True))
        pod_lay.addWidget(chk_pod)
        layout.addWidget(pod_group)

        # --- Subdl ---
        subdl_group = QFrame()
        subdl_group.setObjectName("pluginConfigGroup")
        subdl_lay = QVBoxLayout(subdl_group)
        subdl_lay.setContentsMargins(12, 10, 12, 10)
        subdl_lay.setSpacing(6)
        sh = QLabel("📥 Subdl.com")
        sh.setStyleSheet("font-weight: bold; font-size: 13px;")
        subdl_lay.addWidget(sh)
        sn = QLabel('<a href="https://subdl.com">subdl.com</a> — besplatan tier sa API key-em')
        sn.setOpenExternalLinks(True)
        sn.setWordWrap(True)
        sn.setStyleSheet("font-size: 11px; color: #888;")
        subdl_lay.addWidget(sn)
        skr = QHBoxLayout()
        skr.addWidget(QLabel("API Key:"))
        subdl_edit = QLineEdit(self._subdl_api_key)
        subdl_edit.setPlaceholderText("Subdl API key...")
        subdl_edit.setEchoMode(QLineEdit.EchoMode.Password)
        skr.addWidget(subdl_edit)
        subdl_lay.addLayout(skr)
        chk_subdl = QCheckBox("Omogući Subdl")
        chk_subdl.setChecked(self._providers.get("subdl", False))
        subdl_lay.addWidget(chk_subdl)
        layout.addWidget(subdl_group)

        # --- Titlovi.com ---
        tit_group = QFrame()
        tit_group.setObjectName("pluginConfigGroup")
        tit_lay = QVBoxLayout(tit_group)
        tit_lay.setContentsMargins(12, 10, 12, 10)
        tit_lay.setSpacing(6)
        th = QLabel("🇷🇸 Titlovi.com")
        th.setStyleSheet("font-weight: bold; font-size: 13px;")
        tit_lay.addWidget(th)
        tn = QLabel(
            'Najveća ex-YU baza titlova — registruj se na '
            '<a href="https://www.titlovi.com">titlovi.com</a>  '
            '(besplatan nalog)'
        )
        tn.setOpenExternalLinks(True)
        tn.setWordWrap(True)
        tn.setStyleSheet("font-size: 11px; color: #888;")
        tit_lay.addWidget(tn)
        tur = QHBoxLayout()
        tur.addWidget(QLabel("Username:"))
        tit_user_edit = QLineEdit(self._titlovi_username)
        tit_user_edit.setPlaceholderText("Titlovi.com username")
        tur.addWidget(tit_user_edit)
        tit_lay.addLayout(tur)
        tpr = QHBoxLayout()
        tpr.addWidget(QLabel("Password:"))
        tit_pass_edit = QLineEdit(self._titlovi_password)
        tit_pass_edit.setPlaceholderText("Titlovi.com password")
        tit_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        tpr.addWidget(tit_pass_edit)
        tit_lay.addLayout(tpr)
        chk_tit = QCheckBox("Omogući Titlovi.com")
        chk_tit.setChecked(self._providers.get("titlovi", False))
        tit_lay.addWidget(chk_tit)
        layout.addWidget(tit_group)

        # --- Dugmad ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Odustani")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("Sačuvaj")
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        def save():
            self._os_api_key = api_edit.text().strip()
            self._os_username = user_edit.text().strip()
            self._os_password = pass_edit.text().strip()
            self._subdl_api_key = subdl_edit.text().strip()
            self._titlovi_username = tit_user_edit.text().strip()
            self._titlovi_password = tit_pass_edit.text().strip()
            self._providers["opensubtitles"] = chk_os.isChecked()
            self._providers["opensubtitles_org"] = chk_osorg.isChecked()
            self._providers["podnapisi"] = chk_pod.isChecked()
            self._providers["subdl"] = chk_subdl.isChecked()
            self._providers["titlovi"] = chk_tit.isChecked()
            if self.context:
                self.context.set_config("plugins.subtitle_search.api_key", self._os_api_key)
                self.context.set_config("plugins.subtitle_search.os_username", self._os_username)
                self.context.set_config("plugins.subtitle_search.os_password", self._os_password)
                self.context.set_config("plugins.subtitle_search.subdl_api_key", self._subdl_api_key)
                self.context.set_config("plugins.subtitle_search.titlovi_username", self._titlovi_username)
                self.context.set_config("plugins.subtitle_search.titlovi_password", self._titlovi_password)
                self.context.set_config("plugins.subtitle_search.providers", self._providers.copy())
            logger.info(f"SubtitleSearch saved: providers={self._providers}")
            dlg.accept()

        save_btn.clicked.connect(save)
        dlg.exec()

    # ═══════════════════════════════════════════
    #  OS LOGIN
    # ═══════════════════════════════════════════

    def _os_login(self) -> bool:
        if not self._os_api_key or not self._os_username or not self._os_password:
            return False
        if self._os_token:
            return True
        try:
            body = json.dumps({"username": self._os_username, "password": self._os_password}).encode()
            raw = _http_request(f"{OS_API_BASE}/login", headers=self._os_headers(), data=body, method="POST")
            data = json.loads(raw)
            self._os_token = data.get("token", "")
            if self._os_token:
                logger.info("OpenSubtitles.com: login uspešan")
                return True
        except Exception as e:
            logger.warning(f"OpenSubtitles login greška: {e}")
        return False

    # ═══════════════════════════════════════════
    #  SEARCH
    # ═══════════════════════════════════════════

    def search(
        self, query: str, languages: List[str],
        file_hash: str = "", file_path: str = "",
    ) -> List[SubtitleResult]:
        results = []

        if file_path and not file_hash:
            file_hash = compute_opensubtitles_hash(file_path)

        if not query and file_path:
            query = Path(file_path).stem

        clean_q = _clean_query(query) if query else ""
        short_q = _extract_series_query(query) if query else ""

        if not languages:
            languages = self._preferred_langs or ["en"]
        if not clean_q:
            return results

        file_size = 0
        if file_path and os.path.isfile(file_path):
            file_size = os.path.getsize(file_path)

        # ── Paralelna pretraga svih provajdera ──
        from concurrent.futures import ThreadPoolExecutor, as_completed

        futures = {}

        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="sub") as pool:
            # 1) OpenSubtitles.com
            if self._providers.get("opensubtitles") and self._os_api_key:
                futures[pool.submit(
                    self._search_opensubtitles, clean_q, languages, file_hash
                )] = "OpenSubtitles.com"

            # 2) OpenSubtitles.org (besplatan, sa retry)
            if self._providers.get("opensubtitles_org"):
                futures[pool.submit(
                    self._search_os_org_with_retry, clean_q, languages, file_hash, file_size
                )] = "OpenSubtitles.org"

            # 3) Podnapisi
            if self._providers.get("podnapisi"):
                futures[pool.submit(
                    self._search_podnapisi_smart, clean_q, short_q, languages
                )] = "Podnapisi"

            # 4) Subdl
            if self._providers.get("subdl") and self._subdl_api_key:
                futures[pool.submit(
                    self._search_subdl, clean_q, languages
                )] = "Subdl"

            # 5) Titlovi.com
            if self._providers.get("titlovi") and self._titlovi_username:
                futures[pool.submit(
                    self._search_titlovi, clean_q, languages
                )] = "Titlovi.com"

            for future in as_completed(futures, timeout=20):
                name = futures[future]
                try:
                    r = future.result()
                    if r:
                        results.extend(r)
                    logger.info(f"{name}: {len(r) if r else 0} rezultata")
                except Exception as e:
                    logger.warning(f"{name} greška: {e}")

        # Deduplikacija
        seen = set()
        unique = []
        for r in results:
            key = (r.download_url, r.language)
            if key not in seen:
                seen.add(key)
                unique.append(r)

        unique.sort(key=lambda r: (-r.hash_match, -r.download_count, -r.rating))
        logger.info(f"SubtitleSearch ukupno: {len(unique)} rezultata za '{clean_q}'")
        return unique

    def _search_os_org_with_retry(
        self, query: str, languages: List[str],
        file_hash: str, file_size: int, max_retries: int = 2,
    ) -> List[SubtitleResult]:
        """OS.org sa retry-jem za DNS/connection greške."""
        for attempt in range(max_retries):
            try:
                return self._search_opensubtitles_org(query, languages, file_hash, file_size)
            except Exception as e:
                err_str = str(e).lower()
                if "name or service not known" in err_str or "temporary failure" in err_str:
                    if attempt < max_retries - 1:
                        logger.debug(f"OS.org DNS fail, retry {attempt + 1}...")
                        time.sleep(1.0)
                        continue
                raise
        return []

    def _search_podnapisi_smart(
        self, clean_q: str, short_q: str, languages: List[str],
    ) -> List[SubtitleResult]:
        """Podnapisi sa fallback na kraći query."""
        try:
            r = self._search_podnapisi(clean_q, languages)
            if not r and short_q and short_q != clean_q:
                time.sleep(0.5)
                r = self._search_podnapisi(short_q, languages)
            return r
        except HTTPError as e:
            if e.code == 429:
                logger.info("Podnapisi 429 — retry za 3s...")
                time.sleep(3)
                return self._search_podnapisi(clean_q, languages)
            raise

    # ═══════════════════════════════════════════
    #  DOWNLOAD
    # ═══════════════════════════════════════════

    def download(self, result: SubtitleResult, dest_dir: str) -> Optional[str]:
        try:
            os.makedirs(dest_dir, exist_ok=True)
            p = result.provider
            if p == "OpenSubtitles":
                return self._download_opensubtitles(result, dest_dir)
            elif p in ("OpenSubtitles.org", "Podnapisi", "Subdl", "Titlovi.com"):
                return self._download_direct(result, dest_dir)
            else:
                logger.error(f"Nepoznat provider: {p}")
                return None
        except Exception as e:
            logger.error(f"Download greška ({result.provider}): {e}")
            return None

    # ═══════════════════════════════════════════
    #  OPENSUBTITLES.COM
    # ═══════════════════════════════════════════

    def _os_headers(self) -> Dict[str, str]:
        h = {"Api-Key": self._os_api_key, "Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self._os_token:
            h["Authorization"] = f"Bearer {self._os_token}"
        return h

    def _search_opensubtitles(self, query: str, languages: List[str], file_hash: str = "") -> List[SubtitleResult]:
        if not self._os_api_key:
            return []
        params: Dict[str, str] = {"query": query, "languages": ",".join(languages)}
        if file_hash:
            params["moviehash"] = file_hash
        url = f"{OS_API_BASE}/subtitles?{urlencode(params)}"
        data = _http_get_json(url, self._os_headers())
        results = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            files = attrs.get("files", [])
            if not files:
                continue
            fi = files[0]
            lang = attrs.get("language", "en")
            results.append(SubtitleResult(
                title=attrs.get("release", query),
                language=lang, language_name=LANGUAGE_NAMES.get(lang, lang),
                provider="OpenSubtitles",
                download_url=str(fi.get("file_id", "")),
                filename=fi.get("file_name", ""),
                rating=float(attrs.get("ratings", 0)),
                download_count=int(attrs.get("download_count", 0)),
                format="srt",
                hash_match=bool(attrs.get("moviehash_match", False)),
                extra={"file_id": fi.get("file_id")},
            ))
        return results

    def _download_opensubtitles(self, result: SubtitleResult, dest_dir: str) -> Optional[str]:
        file_id = result.extra.get("file_id")
        if not file_id:
            return None
        if self._os_username and self._os_password and not self._os_token:
            self._os_login()
        req_body = json.dumps({"file_id": file_id}).encode()
        raw = _http_request_with_retry(
            f"{OS_API_BASE}/download", headers=self._os_headers(),
            data=req_body, method="POST", retries=2, delay=3.0,
        )
        dl_data = json.loads(raw)
        dl_link = dl_data.get("link")
        if not dl_link:
            remaining = dl_data.get("remaining", "?")
            msg = dl_data.get("message", "nema download linka")
            raise RuntimeError(f"OpenSubtitles: {msg} (preostalo: {remaining}/dan)")
        content = _http_request(dl_link)
        filename = result.filename or f"subtitle_{result.language}.srt"
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        dest_path = os.path.join(dest_dir, filename)
        with open(dest_path, "wb") as f:
            f.write(content)
        logger.info(f"OpenSubtitles.com download: {dest_path}")
        return dest_path

    # ═══════════════════════════════════════════
    #  OPENSUBTITLES.ORG (besplatan)
    # ═══════════════════════════════════════════

    def _search_opensubtitles_org(
        self, query: str, languages: List[str],
        file_hash: str = "", file_size: int = 0,
    ) -> List[SubtitleResult]:
        results = []
        headers = {"User-Agent": "TemporaryUserAgent"}
        lang3 = [LANG_2_TO_3.get(l, "eng") for l in languages]
        lang_str = ",".join(lang3)

        # Hash search
        if file_hash and file_size:
            url = f"{OS_ORG_API}/moviebytesize-{file_size}/moviehash-{file_hash}/sublanguageid-{lang_str}"
            try:
                data = _http_get_json(url, headers)
                if isinstance(data, list):
                    for item in data[:15]:
                        r = self._parse_os_org(item, True)
                        if r:
                            results.append(r)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"OS.org hash search: {e}")

        # Query search
        url = f"{OS_ORG_API}/query-{quote(query)}/sublanguageid-{lang_str}"
        try:
            data = _http_get_json(url, headers)
            if isinstance(data, list):
                for item in data[:20]:
                    r = self._parse_os_org(item, False)
                    if r:
                        results.append(r)
        except Exception as e:
            logger.debug(f"OS.org query search: {e}")
        return results

    def _parse_os_org(self, item: Dict, hash_match: bool) -> Optional[SubtitleResult]:
        dl_link = item.get("SubDownloadLink", "")
        if not dl_link:
            return None
        lang3 = item.get("SubLanguageID", "eng")
        lang2 = next((k for k, v in LANG_2_TO_3.items() if v == lang3), "en")
        return SubtitleResult(
            title=item.get("MovieReleaseName", "") or item.get("SubFileName", ""),
            language=lang2, language_name=LANGUAGE_NAMES.get(lang2, lang3),
            provider="OpenSubtitles.org",
            download_url=dl_link,
            filename=item.get("SubFileName", ""),
            rating=float(item.get("SubRating", "0") or "0"),
            download_count=int(item.get("SubDownloadsCnt", "0") or "0"),
            format=item.get("SubFormat", "srt"),
            hash_match=hash_match,
            extra={"gz_link": dl_link, "imdb_id": item.get("IDMovieImdb", "")},
        )

    # ═══════════════════════════════════════════
    #  PODNAPISI.NET
    # ═══════════════════════════════════════════

    def _search_podnapisi(self, query: str, languages: List[str]) -> List[SubtitleResult]:
        results = []
        lang_ids = [PODNAPISI_LANG_MAP[l] for l in languages if l in PODNAPISI_LANG_MAP]
        if not lang_ids:
            lang_ids = ["2"]
        params = {"sXML": "1", "sK": query, "sJ": ",".join(lang_ids)}
        url = f"{PODNAPISI_API}?{urlencode(params)}"
        raw = _http_request(url)
        text = raw.decode("utf-8", errors="replace")
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(text)
            for sub in root.findall(".//subtitle"):
                title = sub.findtext("release", "")
                lang_id = sub.findtext("languageId", "2")
                lang_name_raw = sub.findtext("languageName", "English")
                sub_id = sub.findtext("id", "")
                rating = float(sub.findtext("rating", "0") or "0")
                downloads = int(sub.findtext("downloads", "0") or "0")
                if not title or not sub_id:
                    continue
                lang_code = PODNAPISI_LANG_REVERSE.get(lang_id, "en")
                results.append(SubtitleResult(
                    title=title, language=lang_code,
                    language_name=LANGUAGE_NAMES.get(lang_code, lang_name_raw),
                    provider="Podnapisi",
                    download_url=f"https://www.podnapisi.net/subtitles/{sub_id}/download",
                    filename=f"{title}.srt", rating=rating, download_count=downloads,
                    format="srt", extra={"sub_id": sub_id},
                ))
        except Exception as e:
            logger.warning(f"Podnapisi XML parse: {e}")
        return results

    # ═══════════════════════════════════════════
    #  SUBDL.COM
    # ═══════════════════════════════════════════

    def _search_subdl(self, query: str, languages: List[str]) -> List[SubtitleResult]:
        if not self._subdl_api_key:
            return []
        lm = {
            "sr": "serbian", "en": "english", "hr": "croatian", "bs": "bosnian",
            "de": "german", "fr": "french", "es": "spanish", "it": "italian",
            "pt": "portuguese", "ru": "russian", "pl": "polish", "nl": "dutch",
            "ro": "romanian", "hu": "hungarian", "cs": "czech", "tr": "turkish",
        }
        ln = [lm[l] for l in languages if l in lm]
        params = {"api_key": self._subdl_api_key, "film_name": query}
        if ln:
            params["languages"] = ",".join(ln)
        data = _http_get_json(f"{SUBDL_API_BASE}?{urlencode(params)}")
        if not data.get("status"):
            return []
        results = []
        for item in data.get("subtitles", []):
            lang = item.get("language", "english").lower()
            lc = next((k for k, v in lm.items() if v == lang), "en")
            dl_url = item.get("url", "")
            if dl_url and not dl_url.startswith("http"):
                dl_url = f"https://dl.subdl.com{dl_url}"
            results.append(SubtitleResult(
                title=item.get("release_name", query),
                language=lc, language_name=LANGUAGE_NAMES.get(lc, lang.capitalize()),
                provider="Subdl", download_url=dl_url,
                filename=item.get("release_name", "subtitle") + ".srt",
                rating=float(item.get("rating", 0) or 0),
                download_count=int(item.get("download_count", 0) or 0),
                format="srt", extra={"subdl_url": dl_url},
            ))
        return results

    # ═══════════════════════════════════════════
    #  GENERIC DOWNLOAD (ZIP/GZ/raw)
    # ═══════════════════════════════════════════

    def _download_direct(self, result: SubtitleResult, dest_dir: str) -> Optional[str]:
        """Univerzalan download — handluje ZIP, GZIP i raw fajlove."""
        dl_url = result.download_url
        if not dl_url:
            return None

        # Titlovi.com zahteva User-Agent i Referer header
        extra_headers = None
        if result.provider == "Titlovi.com":
            extra_headers = {
                "User-Agent": USER_AGENT,
                "Referer": "https://www.titlovi.com",
            }

        content = _http_request_with_retry(
            dl_url, headers=extra_headers, retries=2, delay=2.0
        )

        # GZIP?
        if dl_url.endswith(".gz") or content[:2] == b'\x1f\x8b':
            try:
                decompressed = gzip.decompress(content)
                fn = result.filename or f"subtitle_{result.language}.srt"
                if fn.endswith(".gz"):
                    fn = fn[:-3]
                fn = re.sub(r'[<>:"/\\|?*]', '_', fn)
                dest = os.path.join(dest_dir, fn)
                with open(dest, "wb") as f:
                    f.write(decompressed)
                logger.info(f"Download (gzip): {dest}")
                return dest
            except Exception:
                pass

        # ZIP?
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                sub_ext = (".srt", ".ass", ".ssa", ".sub", ".vtt")
                for name in zf.namelist():
                    if name.lower().endswith(sub_ext):
                        extracted = zf.read(name)
                        safe = re.sub(r'[<>:"/\\|?*]', '_', os.path.basename(name))
                        dest = os.path.join(dest_dir, safe)
                        with open(dest, "wb") as f:
                            f.write(extracted)
                        logger.info(f"Download (zip): {dest}")
                        return dest
                dest = os.path.join(dest_dir, "subtitle.zip")
                with open(dest, "wb") as f:
                    f.write(content)
                return dest
        except zipfile.BadZipFile:
            pass

        # Raw
        fn = result.filename or f"subtitle_{result.language}.srt"
        fn = re.sub(r'[<>:"/\\|?*]', '_', fn)
        dest = os.path.join(dest_dir, fn)
        with open(dest, "wb") as f:
            f.write(content)
        logger.info(f"Download (raw): {dest}")
        return dest

    # ═══════════════════════════════════════════
    #  TITLOVI.COM
    # ═══════════════════════════════════════════

    def _titlovi_login(self) -> bool:
        """Login na Titlovi.com API — dobija token za pretragu.

        Token se čuva u memoriji sa expiration datumom. Ako je token
        istekao ili ističe za manje od 1h, automatski se refreshuje.
        """
        if self._titlovi_token and self._titlovi_user_id:
            # Proveri da li token ističe uskoro
            if hasattr(self, '_titlovi_token_expires'):
                from datetime import datetime, timedelta
                try:
                    if self._titlovi_token_expires > datetime.now() + timedelta(hours=1):
                        return True
                    else:
                        logger.info("Titlovi.com: token ističe uskoro, refresh...")
                        self._titlovi_token = ""
                        self._titlovi_user_id = 0
                except Exception:
                    return True
            else:
                return True
        if not self._titlovi_username or not self._titlovi_password:
            return False

        try:
            # Titlovi API: POST /gettoken sa params u query stringu
            params = urlencode({
                "username": self._titlovi_username,
                "password": self._titlovi_password,
                "json": "true",
                "returnStatusCode": "true",
            })
            url = f"{TITLOVI_API}/gettoken?{params}"
            raw = _http_request(url, method="POST")
            data = json.loads(raw)

            if isinstance(data, dict):
                token = data.get("Token") or data.get("token", "")
                user_id = data.get("UserId") or data.get("userid", 0)
                if token:
                    self._titlovi_token = token
                    self._titlovi_user_id = int(user_id) if user_id else 0
                    exp = data.get("ExpirationDate", "")
                    # Čuvaj expiration datum za automatski refresh
                    if exp:
                        try:
                            from datetime import datetime
                            import re as _re
                            m = _re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", exp)
                            if m:
                                self._titlovi_token_expires = datetime.fromisoformat(m.group(1))
                        except Exception:
                            pass
                    logger.info(f"Titlovi.com: login uspešan (userid={self._titlovi_user_id}, expires: {exp})")
                    return True
                else:
                    msg = data.get("Message") or data.get("message", "nepoznata greška")
                    logger.warning(f"Titlovi.com login: {msg}")
        except Exception as e:
            logger.warning(f"Titlovi.com login greška: {e}")

        return False

    def _search_titlovi(
        self, query: str, languages: List[str]
    ) -> List[SubtitleResult]:
        """Pretraži Titlovi.com API (v2 — ispravan pristup iz Kodi addon-a).

        API zahteva GET /search sa token, userid, json i returnStatusCode
        parametrima u query stringu. Bez userid → 401.
        """
        if not self._titlovi_login():
            logger.warning("Titlovi.com: nije moguće prijaviti se")
            return []

        # Titlovi koristi lokalizovana imena za jezike
        lang_names = []
        for lang in languages:
            tl = TITLOVI_LANG_MAP.get(lang)
            if tl:
                lang_names.append(tl)
        lang_param = "|".join(lang_names) if lang_names else ""

        # Parametri za search — mora token + userid + json + returnStatusCode
        search_params: Dict[str, str] = {
            "token": self._titlovi_token,
            "userid": str(self._titlovi_user_id),
            "query": query,
            "json": "true",
            "returnStatusCode": "true",
        }
        if lang_param:
            search_params["lang"] = lang_param

        data = None
        url = f"{TITLOVI_API}/search?{urlencode(search_params, doseq=True)}"

        # Jedan GET poziv — ispravan pristup iz Kodi addon-a deklica v2.0.1
        try:
            data = _http_get_json(url)
            logger.debug("Titlovi.com: GET search uspeo")
        except HTTPError as e:
            logger.warning(f"Titlovi.com GET search: HTTP {e.code}")
            # Ako 401 — token je istekao, pokušaj refresh
            if e.code == 401:
                logger.info("Titlovi.com: token istekao, pokušavam ponovo login...")
                self._titlovi_token = ""
                self._titlovi_user_id = 0
                if self._titlovi_login():
                    search_params["token"] = self._titlovi_token
                    search_params["userid"] = str(self._titlovi_user_id)
                    url = f"{TITLOVI_API}/search?{urlencode(search_params, doseq=True)}"
                    try:
                        data = _http_get_json(url)
                        logger.debug("Titlovi.com: retry GET search uspeo")
                    except Exception as e2:
                        logger.warning(f"Titlovi.com retry GET neuspeo: {e2}")
        except Exception as e:
            logger.warning(f"Titlovi.com search greška: {e}")

        if data is None:
            logger.warning("Titlovi.com: search neuspeo")
            return []

        logger.info(f"Titlovi.com response: type={type(data).__name__}, "
                     f"keys={list(data.keys()) if isinstance(data, dict) else f'list[{len(data)}]'}")

        results = []

        # API vraća rezultate pod ključem "SubtitleResults"
        items = []
        if isinstance(data, dict):
            if "SubtitleResults" in data and isinstance(data["SubtitleResults"], list):
                items = data["SubtitleResults"]
            else:
                # Fallback: probaj stare ključeve
                for key in ("ExactMatch", "CloseMatch", "Popular", "data"):
                    if key in data and isinstance(data[key], list):
                        items.extend(data[key])
                if not items and "results" in data:
                    items = data["results"]
        elif isinstance(data, list):
            items = data

        for item in items[:25]:
            # API vraća Title="Predator: Badlands", Release="1080p.HDRip.x264-BOTHD"
            api_title = item.get("Title", "") or item.get("title", "")
            api_release = item.get("Release", "") or item.get("release", "")
            api_year = item.get("Year", "") or item.get("year", "")

            # Kombinuj: "Title (Year) Release" — kao u Kodi addon-u
            title_parts = []
            if api_title:
                title_parts.append(api_title)
            if api_year:
                title_parts.append(f"({api_year})")
            if api_release:
                title_parts.append(api_release)
            title = " ".join(title_parts) if title_parts else ""

            lang_name = item.get("Lang", "") or item.get("lang", "")
            sub_id = str(item.get("Id", "") or item.get("id", ""))
            rating = float(item.get("Rating", 0) or 0)
            dl_count = int(item.get("DownloadCount", 0) or item.get("Downloads", 0) or 0)
            sub_type = item.get("Type", "") or item.get("type", "")

            if not title or not sub_id:
                continue

            # Reverse lookup lang
            lang_code = TITLOVI_LANG_REVERSE.get(lang_name, "sr")

            # Download URL
            dl_url = item.get("DownloadUrl", "") or item.get("Link", "") or item.get("downloadUrl", "")
            if not dl_url:
                # Konstruiši iz ID-a
                dl_url = f"https://titlovi.com/downloads/default.ashx?type=1&mediaid={sub_id}"

            results.append(SubtitleResult(
                title=title,
                language=lang_code,
                language_name=lang_name or LANGUAGE_NAMES.get(lang_code, "Srpski"),
                provider="Titlovi.com",
                download_url=dl_url,
                filename=f"{title}.srt",
                rating=rating,
                download_count=dl_count,
                format="srt",
                extra={"media_id": sub_id, "type": sub_type},
            ))

        return results