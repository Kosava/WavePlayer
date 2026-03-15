"""YouTube Search & Playlist dialog za WavePlayer.

Omogućava pretragu YouTube videa, paste YouTube URL/playliste,
izbor kvaliteta i dodavanje u player playlist.

Koristi YouTubePlugin (yt-dlp) kao backend.
"""

import logging
import os
from typing import List, Optional, Callable

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QFrame,
    QMessageBox,
    QSizePolicy,
    QTabWidget,
    QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  QUALITY PRESETS
# ═══════════════════════════════════════════

# (label, ytdl-format string, opis)
QUALITY_PRESETS = [
    ("Audio Only",   "bestaudio/best",                          "Samo audio — za muziku"),
    ("360p",         "bestvideo[height<=360]+bestaudio/best",   "Niska rezolucija"),
    ("480p",         "bestvideo[height<=480]+bestaudio/best",   "Srednja rezolucija"),
    ("720p",         "bestvideo[height<=720]+bestaudio/best",   "HD"),
    ("1080p",        "bestvideo[height<=1080]+bestaudio/best",  "Full HD"),
    ("Best",         "bestvideo+bestaudio/best",                "Najbolji dostupan kvalitet"),
]

# Config ključevi
CFG_YT_QUALITY = "plugins.youtube.default_quality"
CFG_YT_QUALITY_DEFAULT = 0  # Audio Only


# ═══════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════


class YouTubeSearchWorker(QThread):
    """Background pretraga YouTube-a."""

    finished = pyqtSignal(list)   # List[YouTubeResult]
    error = pyqtSignal(str)

    def __init__(self, plugin, query: str, max_results: int = 15):
        super().__init__()
        self._plugin = plugin
        self._query = query
        self._max_results = max_results

    def run(self):
        try:
            results = self._plugin.search(self._query, self._max_results)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class YouTubePlaylistWorker(QThread):
    """Background ekstrakcija YouTube playliste."""

    finished = pyqtSignal(list)   # List[YouTubeResult]
    error = pyqtSignal(str)

    def __init__(self, plugin, url: str, max_items: int = 100):
        super().__init__()
        self._plugin = plugin
        self._url = url
        self._max_items = max_items

    def run(self):
        try:
            items = self._plugin.get_playlist_items(self._url, self._max_items)
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════
#  YOUTUBE SEARCH DIALOG
# ═══════════════════════════════════════════


class YouTubeDialog(QDialog):
    """Dialog za YouTube pretragu, URL paste i playlist import.

    Rezultati se šalju u player playlist ili direktno puštaju.

    Signali:
      play_requested(str)      — pusti ovaj URL odmah
      add_requested(list[str]) — dodaj URL-ove u playlist
    """

    play_requested = pyqtSignal(str)
    add_requested = pyqtSignal(list)

    def __init__(self, youtube_plugin, config=None, parent=None):
        super().__init__(parent)

        self._plugin = youtube_plugin
        self._config = config
        self._search_results = []
        self._playlist_results = []
        self._search_worker: Optional[YouTubeSearchWorker] = None
        self._playlist_worker: Optional[YouTubePlaylistWorker] = None

        self.setWindowTitle("YouTube")
        self.setMinimumSize(750, 550)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._setup_ui()
        self._load_quality_setting()

    # ───────────────────────────
    #  UI SETUP
    # ───────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Header ──
        header = QLabel("▶  YouTube")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        # ── Tabs: Pretraga | URL / Playlista ──
        self._tabs = QTabWidget()
        self._tabs.addTab(self._create_search_tab(), "🔍  Pretraga")
        self._tabs.addTab(self._create_url_tab(), "🔗  URL / Playlista")
        layout.addWidget(self._tabs, 1)

        # ── Quality + akcioni red (dno) ──
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        bottom.addWidget(QLabel("Kvalitet:"))
        self._quality_combo = QComboBox()
        self._quality_combo.setObjectName("settingsCombo")
        self._quality_combo.setMinimumWidth(140)
        for label, _fmt, desc in QUALITY_PRESETS:
            self._quality_combo.addItem(f"{label}", _fmt)
        self._quality_combo.setToolTip(
            "Kvalitet videa/audio — Audio Only je idealan za muziku"
        )
        bottom.addWidget(self._quality_combo)
        bottom.addStretch()

        self._play_btn = QPushButton("▶  Pusti")
        self._play_btn.setObjectName("settingsPrimaryBtn")
        self._play_btn.setMinimumWidth(100)
        self._play_btn.clicked.connect(self._on_play)
        self._play_btn.setEnabled(False)
        bottom.addWidget(self._play_btn)

        self._add_btn = QPushButton("➕  Dodaj u playlist")
        self._add_btn.setObjectName("settingsSecondaryBtn")
        self._add_btn.setMinimumWidth(140)
        self._add_btn.clicked.connect(self._on_add_to_playlist)
        self._add_btn.setEnabled(False)
        bottom.addWidget(self._add_btn)

        self._close_btn = QPushButton("Zatvori")
        self._close_btn.setObjectName("settingsSecondaryBtn")
        self._close_btn.clicked.connect(self.reject)
        bottom.addWidget(self._close_btn)

        layout.addLayout(bottom)

    def _create_search_tab(self) -> QWidget:
        """Tab za YouTube pretragu."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("searchEdit")
        self._search_edit.setPlaceholderText("Pretraži YouTube...")
        self._search_edit.returnPressed.connect(self._start_search)
        search_row.addWidget(self._search_edit, 1)

        self._search_btn = QPushButton("🔍  Traži")
        self._search_btn.setObjectName("settingsPrimaryBtn")
        self._search_btn.clicked.connect(self._start_search)
        search_row.addWidget(self._search_btn)

        layout.addLayout(search_row)

        # Progress
        self._search_progress = QProgressBar()
        self._search_progress.setVisible(False)
        self._search_progress.setFixedHeight(3)
        self._search_progress.setRange(0, 0)  # indeterminate
        self._search_progress.setTextVisible(False)
        layout.addWidget(self._search_progress)

        # Rezultati
        self._search_list = QListWidget()
        self._search_list.setObjectName("playlistWidget")
        self._search_list.setAlternatingRowColors(True)
        self._search_list.itemSelectionChanged.connect(self._on_search_selection)
        self._search_list.itemDoubleClicked.connect(self._on_play)
        layout.addWidget(self._search_list, 1)

        # Info label
        self._search_info = QLabel("Unesite pojam za pretragu")
        self._search_info.setObjectName("infoLabel")
        self._search_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._search_info)

        return tab

    def _create_url_tab(self) -> QWidget:
        """Tab za paste URL / playlist URL."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # URL input
        url_label = QLabel("YouTube URL ili Playlist URL:")
        url_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(url_label)

        url_row = QHBoxLayout()
        url_row.setSpacing(6)

        self._url_edit = QLineEdit()
        self._url_edit.setObjectName("searchEdit")
        self._url_edit.setPlaceholderText(
            "https://www.youtube.com/watch?v=... ili playlist?list=..."
        )
        self._url_edit.returnPressed.connect(self._on_url_action)
        url_row.addWidget(self._url_edit, 1)

        self._url_play_btn = QPushButton("▶  Pusti")
        self._url_play_btn.setObjectName("settingsPrimaryBtn")
        self._url_play_btn.clicked.connect(self._on_url_play)
        url_row.addWidget(self._url_play_btn)

        self._url_add_btn = QPushButton("➕  Dodaj")
        self._url_add_btn.setObjectName("settingsSecondaryBtn")
        self._url_add_btn.clicked.connect(self._on_url_add)
        url_row.addWidget(self._url_add_btn)

        layout.addLayout(url_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("settingsSeparator")
        layout.addWidget(sep)

        # Playlist loading section
        pl_label = QLabel("Playlist sadržaj:")
        pl_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(pl_label)

        # Progress
        self._url_progress = QProgressBar()
        self._url_progress.setVisible(False)
        self._url_progress.setFixedHeight(3)
        self._url_progress.setRange(0, 0)
        self._url_progress.setTextVisible(False)
        layout.addWidget(self._url_progress)

        # Playlist rezultati
        self._playlist_list = QListWidget()
        self._playlist_list.setObjectName("playlistWidget")
        self._playlist_list.setAlternatingRowColors(True)
        self._playlist_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self._playlist_list.itemDoubleClicked.connect(self._on_playlist_item_play)
        layout.addWidget(self._playlist_list, 1)

        # Playlist action row
        pl_actions = QHBoxLayout()

        self._url_info = QLabel("Nalepite YouTube playlist URL iznad")
        self._url_info.setObjectName("infoLabel")
        pl_actions.addWidget(self._url_info, 1)

        self._load_playlist_btn = QPushButton("📋  Učitaj playlistu")
        self._load_playlist_btn.setObjectName("settingsSecondaryBtn")
        self._load_playlist_btn.clicked.connect(self._on_load_playlist)
        pl_actions.addWidget(self._load_playlist_btn)

        self._add_all_btn = QPushButton("➕  Dodaj sve u playlist")
        self._add_all_btn.setObjectName("settingsPrimaryBtn")
        self._add_all_btn.clicked.connect(self._on_add_all_playlist)
        self._add_all_btn.setEnabled(False)
        pl_actions.addWidget(self._add_all_btn)

        layout.addLayout(pl_actions)

        return tab

    # ───────────────────────────
    #  QUALITY SETTINGS
    # ───────────────────────────

    def _load_quality_setting(self):
        """Učitaj default kvalitet iz config-a."""
        if self._config:
            idx = self._config.get(CFG_YT_QUALITY, CFG_YT_QUALITY_DEFAULT)
            idx = max(0, min(idx, len(QUALITY_PRESETS) - 1))
            self._quality_combo.setCurrentIndex(idx)

    def _get_quality_format(self) -> str:
        """Vrati trenutno izabrani ytdl-format string."""
        idx = self._quality_combo.currentIndex()
        if 0 <= idx < len(QUALITY_PRESETS):
            return QUALITY_PRESETS[idx][1]
        return "bestaudio/best"

    def _get_quality_label(self) -> str:
        """Vrati naziv kvaliteta za OSD."""
        idx = self._quality_combo.currentIndex()
        if 0 <= idx < len(QUALITY_PRESETS):
            return QUALITY_PRESETS[idx][0]
        return "Auto"

    # ───────────────────────────
    #  SEARCH TAB
    # ───────────────────────────

    def _start_search(self):
        query = self._search_edit.text().strip()
        if not query:
            return

        # Ako je URL, prebaci na URL tab
        if self._plugin.is_youtube_url(query):
            self._url_edit.setText(query)
            self._tabs.setCurrentIndex(1)
            self._on_url_action()
            return

        self._search_list.clear()
        self._search_results = []
        self._search_progress.setVisible(True)
        self._search_btn.setEnabled(False)
        self._play_btn.setEnabled(False)
        self._add_btn.setEnabled(False)
        self._search_info.setText("Pretražujem...")

        self._search_worker = YouTubeSearchWorker(self._plugin, query)
        self._search_worker.finished.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_done(self, results):
        self._search_progress.setVisible(False)
        self._search_btn.setEnabled(True)
        self._search_results = results

        if not results:
            self._search_info.setText("Nema rezultata")
            return

        self._search_info.setText(f"{len(results)} rezultata")

        for r in results:
            # Formatiraj liniju
            duration = r.duration if r.duration else "LIVE" if r.is_live else "?"
            channel = r.channel if r.channel else ""
            views = ""
            if r.view_count > 0:
                views = self._format_views(r.view_count)

            title = r.title
            if len(title) > 65:
                title = title[:62] + "..."

            parts = [title]
            if channel:
                parts.append(f"  [{channel}]")

            line1 = "".join(parts)
            line2_parts = [f"⏱ {duration}"]
            if views:
                line2_parts.append(f"👁 {views}")
            if r.is_live:
                line2_parts.append("🔴 LIVE")

            text = f"{line1}\n    {' • '.join(line2_parts)}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r)
            item.setSizeHint(QSize(0, 48))
            self._search_list.addItem(item)

    def _on_search_error(self, msg):
        self._search_progress.setVisible(False)
        self._search_btn.setEnabled(True)
        self._search_info.setText(f"Greška: {msg}")
        logger.error(f"YouTube search error: {msg}")

    def _on_search_selection(self):
        has_sel = len(self._search_list.selectedItems()) > 0
        self._play_btn.setEnabled(has_sel)
        self._add_btn.setEnabled(has_sel)

    # ───────────────────────────
    #  URL / PLAYLIST TAB
    # ───────────────────────────

    def _on_url_action(self):
        """Automatski detektuj — single video ili playlist."""
        url = self._url_edit.text().strip()
        if not url:
            return

        if "playlist?list=" in url or "&list=" in url:
            self._on_load_playlist()
        else:
            self._on_url_play()

    def _on_url_play(self):
        """Pusti URL direktno."""
        url = self._url_edit.text().strip()
        if not url:
            return

        self._apply_quality_to_mpv()
        self.play_requested.emit(url)
        self._url_info.setText(f"▶  Puštam: {url[:60]}...")
        self.accept()

    def _on_url_add(self):
        """Dodaj URL u playlist."""
        url = self._url_edit.text().strip()
        if not url:
            return

        self._apply_quality_to_mpv()
        self.add_requested.emit([url])
        self._url_info.setText(f"➕  Dodato u playlist")

    def _on_load_playlist(self):
        """Učitaj YouTube playlistu."""
        url = self._url_edit.text().strip()
        if not url:
            return

        self._playlist_list.clear()
        self._playlist_results = []
        self._url_progress.setVisible(True)
        self._load_playlist_btn.setEnabled(False)
        self._add_all_btn.setEnabled(False)
        self._url_info.setText("Učitavam playlistu...")

        self._playlist_worker = YouTubePlaylistWorker(self._plugin, url)
        self._playlist_worker.finished.connect(self._on_playlist_done)
        self._playlist_worker.error.connect(self._on_playlist_error)
        self._playlist_worker.start()

    def _on_playlist_done(self, items):
        self._url_progress.setVisible(False)
        self._load_playlist_btn.setEnabled(True)
        self._playlist_results = items

        if not items:
            self._url_info.setText("Playlista je prazna ili nije pronađena")
            return

        self._url_info.setText(f"📋  {len(items)} stavki u playlisti")
        self._add_all_btn.setEnabled(True)

        for i, r in enumerate(items, 1):
            title = r.title
            if len(title) > 60:
                title = title[:57] + "..."
            duration = r.duration if r.duration else "?"
            channel = r.channel if r.channel else ""

            text = f"{i}. {title}"
            if channel:
                text += f"  [{channel}]"
            text += f"  ⏱ {duration}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._playlist_list.addItem(item)

    def _on_playlist_error(self, msg):
        self._url_progress.setVisible(False)
        self._load_playlist_btn.setEnabled(True)
        self._url_info.setText(f"Greška: {msg}")
        logger.error(f"YouTube playlist error: {msg}")

    def _on_playlist_item_play(self, item: QListWidgetItem):
        """Double-click na stavku u playlisti — pusti."""
        result = item.data(Qt.ItemDataRole.UserRole)
        if result and result.url:
            self._apply_quality_to_mpv()
            self.play_requested.emit(result.url)
            self.accept()

    def _on_add_all_playlist(self):
        """Dodaj celu playlistu u player."""
        if not self._playlist_results:
            return

        urls = [r.url for r in self._playlist_results if r.url]
        if urls:
            self._apply_quality_to_mpv()
            self.add_requested.emit(urls)
            self._url_info.setText(f"➕  Dodato {len(urls)} stavki u playlist")

    # ───────────────────────────
    #  BOTTOM BAR ACTIONS
    # ───────────────────────────

    def _on_play(self):
        """Pusti izabranu stavku iz search rezultata."""
        if self._tabs.currentIndex() == 0:
            # Search tab
            current = self._search_list.currentItem()
            if not current:
                return
            result = current.data(Qt.ItemDataRole.UserRole)
            if result and result.url:
                self._apply_quality_to_mpv()
                self.play_requested.emit(result.url)
                self.accept()
        else:
            # URL tab — pusti URL
            self._on_url_play()

    def _on_add_to_playlist(self):
        """Dodaj izabrane stavke u playlist."""
        if self._tabs.currentIndex() == 0:
            # Search tab — izabrana stavka
            items = self._search_list.selectedItems()
            urls = []
            for item in items:
                result = item.data(Qt.ItemDataRole.UserRole)
                if result and result.url:
                    urls.append(result.url)
            if urls:
                self._apply_quality_to_mpv()
                self.add_requested.emit(urls)
                self._search_info.setText(
                    f"➕  Dodato {len(urls)} u playlist"
                )
        else:
            # URL tab — dodaj URL
            self._on_url_add()

    # ───────────────────────────
    #  MPV QUALITY
    # ───────────────────────────

    def _apply_quality_to_mpv(self):
        """Postavi ytdl-format na mpv pre puštanja.

        Ovo se radi kroz plugin context koji ima pristup do mpv engine-a,
        ili se format prosledi kao deo URL-a. Najjednostavnije je da
        main_window postavi mpv property pre loadovanja.
        """
        # Sačuvaj izabrani kvalitet u config za sledeći put
        if self._config:
            self._config.set(CFG_YT_QUALITY, self._quality_combo.currentIndex())

    def get_quality_format(self) -> str:
        """Javna metoda — main_window čita format pre loadFile."""
        return self._get_quality_format()

    def get_quality_label(self) -> str:
        """Javna metoda — za OSD prikaz."""
        return self._get_quality_label()

    # ───────────────────────────
    #  HELPERS
    # ───────────────────────────

    @staticmethod
    def _format_views(count: int) -> str:
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{count / 1_000:.0f}K"
        return str(count)

    def closeEvent(self, event):
        # Očisti worker-e
        for w in (self._search_worker, self._playlist_worker):
            if w and w.isRunning():
                w.quit()
                w.wait(2000)
        super().closeEvent(event)
