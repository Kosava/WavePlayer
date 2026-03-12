"""Welcome screen widget.

Prikazuje se umesto drop-zone-a kada nema učitanog medija.
Sadrži kartice za modove, listu nedavnih fajlova i drag & drop.

MOUSE EVENT HANDLING:
  ModeCard i RecentFileItem su QFrame-ovi koji hvataju klikove
  kroz mousePressEvent. Svi child QLabel-i imaju
  WA_TransparentForMouseEvents atribut tako da propuštaju
  klikove na parent frame umesto da ih "gutaju".

PORTABILITY NOTES:
  - C++: QWidget with QVBoxLayout, same signal pattern
  - Rust: egui panel with cards layout
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QPushButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor

logger = logging.getLogger(__name__)


def _make_label(text: str, object_name: str, parent: QWidget = None) -> QLabel:
    """Kreiraj QLabel koji propušta mouse evente na parent widget.

    Ovo je ključno za ModeCard i RecentFileItem — bez ovoga
    QLabel hvata klik pre nego što QFrame dobije mousePressEvent.
    """
    label = QLabel(text, parent)
    label.setObjectName(object_name)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return label


# ═══════════════════════════════════════════
#  MODE CARD
# ═══════════════════════════════════════════

class ModeCard(QFrame):
    """Jedna kartica za mod reprodukcije (Otvori fajl, Torrent, URL).

    Svi child QLabel-i imaju WA_TransparentForMouseEvents
    tako da klikovi uvek stižu do ovog QFrame-a.
    """

    clicked = pyqtSignal(str)  # emituje mode_id

    def __init__(
        self,
        mode_id: str,
        icon: str,
        title: str,
        description: str,
        hotkey: str = "",
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._mode_id = mode_id
        self.setObjectName("welcomeCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        # Hotkey badge (gore desno)
        if hotkey:
            top_row = QHBoxLayout()
            top_row.addStretch()
            hotkey_label = _make_label(hotkey, "welcomeHotkey")
            top_row.addWidget(hotkey_label)
            layout.addLayout(top_row)
        else:
            layout.addSpacing(8)

        # Ikona
        icon_label = _make_label(icon, "welcomeCardIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(icon_label)

        # Naslov
        title_label = _make_label(title, "welcomeCardTitle")
        layout.addWidget(title_label)

        # Opis
        desc_label = _make_label(description, "welcomeCardDesc")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        layout.addStretch()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._mode_id)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════
#  RECENT FILE ITEM
# ═══════════════════════════════════════════

class RecentFileItem(QFrame):
    """Jedan red u listi nedavnih fajlova.

    Svi child QLabel-i imaju WA_TransparentForMouseEvents.
    """

    clicked = pyqtSignal(str)  # emituje file_path

    def __init__(self, file_path: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self.setObjectName("recentItem")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # Ikona prema tipu
        icon = self._get_icon(file_path)
        icon_label = _make_label(icon, "recentIcon")
        icon_label.setFixedWidth(28)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # Info (ime + meta)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        name = os.path.basename(file_path)
        name_label = _make_label(name, "recentName")
        name_label.setMaximumWidth(400)
        info_layout.addWidget(name_label)

        # Meta info (tip + veličina)
        meta = self._get_meta(file_path)
        meta_label = _make_label(meta, "recentMeta")
        info_layout.addWidget(meta_label)

        layout.addLayout(info_layout, 1)

        # Vremenska oznaka (ako fajl postoji)
        time_str = self._get_time_str(file_path)
        if time_str:
            time_label = _make_label(time_str, "recentTime")
            layout.addWidget(time_label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._file_path)
        super().mousePressEvent(event)

    @staticmethod
    def _get_icon(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus", ".aac", ".wma"}:
            return "🎵"
        if ext == ".torrent" or path.startswith("magnet:"):
            return "🧲"
        return "🎬"

    @staticmethod
    def _get_meta(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        audio_exts = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus", ".aac", ".wma"}

        type_str = "Audio" if ext in audio_exts else "Video"

        # Pokušaj veličinu
        try:
            if os.path.exists(path):
                size = os.path.getsize(path)
                if size >= 1_073_741_824:
                    size_str = f"{size / 1_073_741_824:.1f} GB"
                elif size >= 1_048_576:
                    size_str = f"{size / 1_048_576:.0f} MB"
                elif size >= 1024:
                    size_str = f"{size / 1024:.0f} KB"
                else:
                    size_str = f"{size} B"
                return f"{type_str} • {size_str}"
        except OSError:
            pass

        return type_str

    @staticmethod
    def _get_time_str(path: str) -> str:
        """Vrati relativno vreme poslednjeg pristupa."""
        try:
            if not os.path.exists(path):
                return ""
            mtime = os.path.getmtime(path)
            dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            diff = now - dt
            hours = diff.total_seconds() / 3600
            if hours < 1:
                return "Upravo"
            elif hours < 24:
                return f"Pre {int(hours)}h"
            elif hours < 48:
                return "Juče"
            else:
                days = int(hours / 24)
                if days < 30:
                    return f"Pre {days}d"
                return dt.strftime("%d.%m.%Y")
        except (OSError, ValueError):
            return ""


# ═══════════════════════════════════════════
#  WELCOME WIDGET
# ═══════════════════════════════════════════

class WelcomeWidget(QWidget):
    """Početni ekran — prikazuje se dok nema učitanog medija.

    Signals:
        open_file_requested:     Korisnik želi da otvori lokalni fajl
        open_torrent_requested:  Korisnik želi torrent/magnet
        open_url_requested:      Korisnik želi URL stream
        file_selected:           Korisnik kliknuo na recent file (emituje path)
        clear_recent_requested:  Korisnik želi da obriše istoriju
    """

    open_file_requested = pyqtSignal()
    open_torrent_requested = pyqtSignal()
    open_url_requested = pyqtSignal()
    file_selected = pyqtSignal(str)
    clear_recent_requested = pyqtSignal()

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("welcomeWidget")
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scroll area za mali prozor
        scroll = QScrollArea()
        scroll.setObjectName("welcomeScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("welcomeContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(0)

        # ── Logo ──
        logo = QLabel("WavePlayer")
        logo.setObjectName("welcomeLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        layout.addSpacing(8)

        # ── Subtitle ──
        subtitle = QLabel("Izaberite način reprodukcije")
        subtitle.setObjectName("welcomeSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(40)

        # ── Kartice ──
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        card_open = ModeCard(
            mode_id="open_file",
            icon="📂",
            title="Otvori fajl",
            description="MP4, MKV, AVI, MP3, FLAC i drugi formati sa računara",
            hotkey="Ctrl+O",
        )
        card_open.clicked.connect(self._on_card_clicked)
        cards_layout.addWidget(card_open)

        card_torrent = ModeCard(
            mode_id="torrent",
            icon="🧲",
            title="Torrent stream",
            description="Streamuj video iz magnet linkova ili .torrent fajlova",
            hotkey="Ctrl+T",
        )
        card_torrent.clicked.connect(self._on_card_clicked)
        cards_layout.addWidget(card_torrent)

        card_url = ModeCard(
            mode_id="url",
            icon="🌐",
            title="Mrežni stream",
            description="Unesi URL za direktan stream sa interneta",
            hotkey="Ctrl+U",
        )
        card_url.clicked.connect(self._on_card_clicked)
        cards_layout.addWidget(card_url)

        layout.addLayout(cards_layout)

        layout.addSpacing(40)

        # ── Nedavni fajlovi ──
        self._recent_container = QFrame()
        self._recent_container.setObjectName("recentContainer")

        recent_layout = QVBoxLayout(self._recent_container)
        recent_layout.setContentsMargins(24, 20, 24, 20)
        recent_layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("📋  Nedavno otvarani")
        header_label.setObjectName("recentHeader")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Clear dugme — QPushButton sa clicked signalom (pouzdan)
        clear_btn = QPushButton("Očisti istoriju")
        clear_btn.setObjectName("recentClearBtn")
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setFlat(True)
        clear_btn.clicked.connect(self._on_clear_recent)
        header_layout.addWidget(clear_btn)

        recent_layout.addLayout(header_layout)

        # Lista fajlova
        self._file_list_layout = QVBoxLayout()
        self._file_list_layout.setSpacing(4)
        self._file_list_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.addLayout(self._file_list_layout)

        # Prazna poruka
        self._empty_label = QLabel("Nema nedavnih fajlova")
        self._empty_label.setObjectName("recentEmpty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setVisible(False)
        recent_layout.addWidget(self._empty_label)

        layout.addWidget(self._recent_container)

        layout.addStretch()

        # ── Drag & Drop hint ──
        drop_hint = QLabel("Ili prevucite fajl direktno u prozor")
        drop_hint.setObjectName("welcomeDropHint")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(drop_hint)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # --- Populacija recent fajlova ---

    def set_recent_files(self, file_paths: list[str]) -> None:
        """Popuni listu nedavnih fajlova. Pozovi iz MainWindow."""
        # Očisti stare
        self._clear_file_list()

        if not file_paths:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)

        # Prikaži max 8 fajlova
        for path in file_paths[:8]:
            item = RecentFileItem(path)
            item.clicked.connect(self._on_recent_clicked)
            self._file_list_layout.addWidget(item)

    def _clear_file_list(self) -> None:
        """Ukloni sve iteme iz liste."""
        while self._file_list_layout.count():
            child = self._file_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    # --- Signal handlers ---

    def _on_card_clicked(self, mode_id: str) -> None:
        if mode_id == "open_file":
            self.open_file_requested.emit()
        elif mode_id == "torrent":
            self.open_torrent_requested.emit()
        elif mode_id == "url":
            self.open_url_requested.emit()

    def _on_recent_clicked(self, file_path: str) -> None:
        self.file_selected.emit(file_path)

    def _on_clear_recent(self) -> None:
        self.clear_recent_requested.emit()
        self._clear_file_list()
        self._empty_label.setVisible(True)


# ═══════════════════════════════════════════
#  STYLESHEET FRAGMENT
# ═══════════════════════════════════════════

def get_welcome_stylesheet(colors) -> str:
    """Generiši stylesheet za welcome widget. Prima ThemeColors objekat."""

    def _to_rgba(hex_color: str) -> str:
        """Konvertuj #AARRGGBB hex u rgba() za Qt CSS kompatibilnost."""
        if hex_color.startswith("rgba"):
            return hex_color
        h = hex_color.lstrip("#")
        if len(h) == 8:
            a, r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
            return f"rgba({r}, {g}, {b}, {round(a / 255, 3)})"
        return hex_color

    accent_subtle_rgba = _to_rgba(colors.accent_subtle)

    return f"""
/* ── Welcome Widget ── */
#welcomeWidget {{
    background-color: {colors.bg_primary};
}}

#welcomeContent {{
    background-color: transparent;
}}

#welcomeScroll {{
    background-color: transparent;
    border: none;
}}

#welcomeLogo {{
    font-size: 42px;
    font-weight: 300;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
    color: {colors.accent};
    letter-spacing: -1px;
}}

#welcomeSubtitle {{
    font-size: 15px;
    font-weight: 300;
    color: {colors.text_muted};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

/* ── Kartice ── */
#welcomeCard {{
    background-color: {colors.bg_secondary};
    border: 1px solid {colors.border};
    border-radius: 16px;
}}

#welcomeCard:hover {{
    border-color: {colors.accent};
    background-color: {colors.bg_tertiary};
}}

#welcomeCardIcon {{
    font-size: 28px;
}}

#welcomeCardTitle {{
    font-size: 16px;
    font-weight: 600;
    color: {colors.text_primary};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#welcomeCardDesc {{
    font-size: 12px;
    color: {colors.text_muted};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
    line-height: 1.4;
}}

#welcomeHotkey {{
    font-size: 10px;
    font-weight: 600;
    color: {colors.accent};
    background-color: {accent_subtle_rgba};
    border-radius: 4px;
    padding: 2px 8px;
    font-family: 'Consolas', 'SF Mono', monospace;
}}

/* ── Nedavni fajlovi ── */
#recentContainer {{
    background-color: {colors.bg_secondary};
    border: 1px solid {colors.border};
    border-radius: 12px;
}}

#recentHeader {{
    font-size: 13px;
    font-weight: 500;
    color: {colors.text_primary};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#recentClearBtn {{
    font-size: 12px;
    color: {colors.accent};
    background: transparent;
    border: none;
    padding: 2px 6px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#recentClearBtn:hover {{
    color: {colors.accent_hover};
}}

#recentItem {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}}

#recentItem:hover {{
    background-color: {colors.bg_tertiary};
    border-color: {colors.border_hover};
}}

#recentIcon {{
    font-size: 18px;
}}

#recentName {{
    font-size: 13px;
    color: {colors.text_primary};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#recentMeta {{
    font-size: 11px;
    color: {colors.text_muted};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#recentTime {{
    font-size: 11px;
    color: {colors.text_muted};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#recentEmpty {{
    font-size: 13px;
    color: {colors.text_muted};
    padding: 16px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

/* ── Drop hint ── */
#welcomeDropHint {{
    font-size: 12px;
    color: {colors.text_muted};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}
"""