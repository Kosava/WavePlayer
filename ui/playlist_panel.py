"""Side playlist panel widget.

Slide-out panel with search, file list and basic operations.
Supports M3U/M3U8 playlist import.

PORTABILITY NOTES:
  - C++: QFrame with QListWidget, identical layout
  - Rust: similar panel with qt6-rs
"""

import os
import logging
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
    QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List

from core.media_info import PlaylistItem

logger = logging.getLogger(__name__)


class PlaylistPanel(QFrame):
    """Bočni panel za playlist."""

    PANEL_WIDTH: int = 320

    # Signali
    item_activated = pyqtSignal(int)           # indeks stavke
    item_double_clicked = pyqtSignal(int)      # dupli klik na stavku
    files_added = pyqtSignal(list)             # lista putanja

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidePanel")
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setVisible(False)

        self._items: List[PlaylistItem] = []
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Postavi UI elemente."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header sa naslovom i dugmićima
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Playlist", self)
        header_label.setObjectName("panelHeader")

        self._add_btn = QPushButton("+", self)
        self._add_btn.setObjectName("panelBtn")
        self._add_btn.setFixedSize(28, 28)
        self._add_btn.setToolTip("Add files")

        self._clear_btn = QPushButton("🗑", self)
        self._clear_btn.setObjectName("panelBtn")
        self._clear_btn.setFixedSize(28, 28)
        self._clear_btn.setToolTip("Clear playlist")

        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(self._add_btn)
        header_layout.addWidget(self._clear_btn)

        # Pretraga
        self._search_edit = QLineEdit(self)
        self._search_edit.setObjectName("searchEdit")
        self._search_edit.setPlaceholderText("Search...")
        self._search_edit.setClearButtonEnabled(True)

        # Lista
        self._list_widget = QListWidget(self)
        self._list_widget.setObjectName("playlistWidget")
        self._list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self._list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        # Info na dnu
        self._info_label = QLabel("0 items", self)
        self._info_label.setObjectName("infoLabel")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(header_layout)
        layout.addWidget(self._search_edit)
        layout.addWidget(self._list_widget, 1)
        layout.addWidget(self._info_label)

    def _connect_signals(self) -> None:
        """Poveži interne signale."""
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._add_btn.clicked.connect(self._on_add_files)
        self._clear_btn.clicked.connect(self.clear)

    # --- Javne metode ---

    def add_item(self, item: PlaylistItem) -> None:
        """Dodaj stavku u playlist."""
        self._items.append(item)
        list_item = QListWidgetItem(item.display_name())
        list_item.setToolTip(item.file_path)
        self._list_widget.addItem(list_item)
        self._update_info()

    def add_items(self, items: List[PlaylistItem]) -> None:
        """Dodaj više stavki odjednom."""
        for item in items:
            self.add_item(item)

    def clear(self) -> None:
        """Obriši sve stavke."""
        self._items.clear()
        self._list_widget.clear()
        self._update_info()

    def set_current(self, index: int) -> None:
        """Označi trenutnu stavku."""
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item:
                font = item.font()
                font.setBold(i == index)
                item.setFont(font)
        self._list_widget.setCurrentRow(index)

    def get_item(self, index: int) -> PlaylistItem:
        """Vrati stavku po indeksu."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return PlaylistItem()

    def get_count(self) -> int:
        """Broj stavki u playlisti."""
        return len(self._items)

    def toggle_visible(self) -> None:
        """Prebaci vidljivost panela."""
        self.setVisible(not self.isVisible())

    # --- Privatne metode ---

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Obradi dupli klik na stavku."""
        row = self._list_widget.row(item)
        if row >= 0:
            self.item_double_clicked.emit(row)

    def _on_search_changed(self, text: str) -> None:
        """Filtriraj stavke po pretrazi."""
        search_lower = text.lower()
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item:
                visible = search_lower in item.text().lower() or not text
                item.setHidden(not visible)

    def _on_add_files(self) -> None:
        """Otvori dijalog za dodavanje fajlova ili M3U playlisti."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Files",
            "",
            "Media Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm "
            "*.mp3 *.flac *.ogg *.wav *.m4a);;"
            "Playlists (*.m3u *.m3u8);;"
            "All Files (*)",
        )
        if not files:
            return

        # Razdvoji M3U fajlove od media fajlova
        media_files = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in (".m3u", ".m3u8"):
                parsed = self._parse_m3u(f)
                media_files.extend(parsed)
            else:
                media_files.append(f)

        if media_files:
            self.files_added.emit(media_files)

    # --- M3U Parser ---

    @staticmethod
    def _parse_m3u(m3u_path: str) -> List[str]:
        """Parsiraj M3U/M3U8 playlist fajl.

        Podržava:
          - #EXTM3U header (opciono)
          - #EXTINF linije (preskače ih, čita samo putanje)
          - Apsolutne putanje (/path/to/file)
          - Relativne putanje (resolvirane prema lokaciji M3U fajla)
          - URL-ove (http://, https://, rtsp://)
          - UTF-8 i latin-1 encoding
          - Prazne linije i komentari (#)
        """
        entries: List[str] = []
        m3u_dir = os.path.dirname(os.path.abspath(m3u_path))

        # Probaj UTF-8 pa latin-1
        content = None
        for enc in ("utf-8", "latin-1"):
            try:
                with open(m3u_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, IOError):
                continue

        if content is None:
            logger.error(f"Ne mogu da pročitam M3U: {m3u_path}")
            return entries

        for line in content.splitlines():
            line = line.strip()

            # Preskoči prazne linije i komentare/metapodatke
            if not line or line.startswith("#"):
                continue

            # URL — dodaj direktno
            if any(line.startswith(s) for s in ("http://", "https://", "rtsp://", "rtp://", "mms://")):
                entries.append(line)
                continue

            # Lokalna putanja — resolviraj relativne
            if os.path.isabs(line):
                path = line
            else:
                path = os.path.normpath(os.path.join(m3u_dir, line))

            entries.append(path)

        logger.info(f"M3U parsiran: {m3u_path} → {len(entries)} stavki")
        return entries

    def _update_info(self) -> None:
        """Ažuriraj info labelu."""
        count = len(self._items)
        self._info_label.setText(f"{count} item{'s' if count != 1 else ''}")