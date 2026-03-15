"""Subtitle Search Dialog za WavePlayer.

Prikazuje UI za pretragu i preuzimanje titlova.
Koristi subtitle plugin kao backend (duck typing — ne zavisi od
tačnog tipa, samo od search/download interfejsa).

Funkcije:
  - Pretraga po imenu/queriju
  - Izbor jezika
  - Lista rezultata sa provajderom, ocenom, brojem download-a
  - Preuzimanje selektovanog titla
  - Podešavanja za provajdere (API ključevi)
  - Automatsko učitavanje titla u player nakon download-a
"""

import logging
import os
from typing import Any, List, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QProgressBar,
    QMessageBox,
    QComboBox,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

from plugins.plugin_api import SubtitleResult

logger = logging.getLogger(__name__)

# Jezici — fallback lista, plugin može imati svoju
_FALLBACK_LANGUAGES = [
    ("Srpski", "sr"),
    ("Engleski", "en"),
    ("Hrvatski", "hr"),
    ("Bosanski", "bs"),
    ("Slovenački", "sl"),
    ("Makedonski", "mk"),
    ("Nemački", "de"),
    ("Francuski", "fr"),
    ("Španski", "es"),
    ("Italijanski", "it"),
    ("Portugalski", "pt"),
    ("Ruski", "ru"),
    ("Poljski", "pl"),
    ("Holandski", "nl"),
    ("Rumunski", "ro"),
    ("Mađarski", "hu"),
    ("Češki", "cs"),
    ("Turski", "tr"),
    ("Grčki", "el"),
    ("Bugarski", "bg"),
    ("Arapski", "ar"),
    ("Kineski", "zh"),
    ("Japanski", "ja"),
    ("Korejski", "ko"),
]


def _compute_hash(file_path: str) -> str:
    """Pokušaj da importuješ hash funkciju iz plugina, fallback na prazan string."""
    try:
        from plugins.subtitle_search import compute_opensubtitles_hash
        return compute_opensubtitles_hash(file_path)
    except ImportError:
        return ""


def _get_language_options() -> list:
    """Pokušaj da importuješ jezičku listu iz plugina."""
    try:
        from plugins.subtitle_search import LANGUAGE_OPTIONS
        return LANGUAGE_OPTIONS
    except ImportError:
        return _FALLBACK_LANGUAGES


# ═══════════════════════════════════════════
#  PROVIDER COLORS & ICONS
# ═══════════════════════════════════════════

PROVIDER_COLORS = {
    "OpenSubtitles": "#4CAF50",
    "OpenSubtitles.org": "#66BB6A",
    "Podnapisi": "#2196F3",
    "Subdl": "#FF9800",
    "Titlovi.com": "#E91E63",
}

PROVIDER_ICONS = {
    "OpenSubtitles": "🟢",
    "OpenSubtitles.org": "🌍",
    "Podnapisi": "🔵",
    "Subdl": "🟠",
    "Titlovi.com": "🇷🇸",
}


# ═══════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════

class SubtitleDownloadWorker(QThread):
    """Worker za preuzimanje titla u pozadini."""
    finished = pyqtSignal(bool, str)  # (success, file_path_or_error_msg)
    progress = pyqtSignal(str)

    def __init__(self, plugin: Any, result: SubtitleResult, dest_dir: str):
        super().__init__()
        self._plugin = plugin
        self._result = result
        self._dest_dir = dest_dir

    def run(self):
        try:
            self.progress.emit("Preuzimanje titla...")
            path = self._plugin.download(self._result, self._dest_dir)
            if path is None:
                self.finished.emit(False, "Neuspelo preuzimanje titla")
                return
            self.finished.emit(True, path)
        except Exception as e:
            self.finished.emit(False, str(e))


class SubtitleSearchWorker(QThread):
    """Worker za pretragu titlova u pozadini."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(
        self,
        plugin: Any,
        query: str,
        languages: List[str],
        file_path: str = "",
        file_hash: str = "",
    ):
        super().__init__()
        self._plugin = plugin
        self._query = query
        self._languages = languages
        self._file_path = file_path
        self._file_hash = file_hash

    def run(self):
        try:
            self.status.emit("Pretraga titlova...")
            results = self._plugin.search(
                self._query, self._languages, self._file_hash, self._file_path
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════
#  SUBTITLE SEARCH DIALOG
# ═══════════════════════════════════════════

class SubtitleSearchDialog(QDialog):
    """Dijalog za pretragu i preuzimanje titlova.

    Plugin se prosleđuje kao Any — koristi se duck typing.
    Plugin mora imati: search(), download(), configure() metode,
    i opcione properties: providers, os_api_key, subdl_api_key.
    """

    def __init__(self, plugin: Any, file_path: str, parent=None):
        super().__init__(parent)

        self._plugin = plugin
        self._file_path = file_path
        self._results: List[SubtitleResult] = []
        self._selected_result: Optional[SubtitleResult] = None
        self._downloaded_path: Optional[str] = None
        self._worker: Optional[SubtitleSearchWorker] = None
        self._download_worker: Optional[SubtitleDownloadWorker] = None

        self.setWindowTitle("🔤 Pretraga titlova")
        self.setMinimumSize(780, 520)
        self.resize(850, 580)

        self._setup_ui()
        self._start_search()

    # ═══════════════════════════════════════════
    #  UI SETUP
    # ═══════════════════════════════════════════

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Top bar: pretraga + jezik ──
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self._query_edit = QLineEdit()
        self._query_edit.setPlaceholderText("Naziv filma ili serije...")
        self._query_edit.setText(
            os.path.splitext(os.path.basename(self._file_path))[0]
        )
        self._query_edit.returnPressed.connect(self._start_search)
        top_layout.addWidget(self._query_edit, stretch=3)

        # Jezik
        self._lang_combo = QComboBox()
        self._lang_combo.setMinimumWidth(130)
        for name, code in _get_language_options():
            self._lang_combo.addItem(name, code)
        idx = self._lang_combo.findData("sr")
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        top_layout.addWidget(self._lang_combo)

        # Dugme za pretragu
        self._search_btn = QPushButton("🔍 Traži")
        self._search_btn.setMinimumWidth(80)
        self._search_btn.clicked.connect(self._start_search)
        top_layout.addWidget(self._search_btn)

        # Dugme za podešavanja
        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setToolTip("Podešavanja provajdera (API ključevi)")
        self._settings_btn.setFixedWidth(36)
        self._settings_btn.clicked.connect(self._open_settings)
        top_layout.addWidget(self._settings_btn)

        layout.addLayout(top_layout)

        # ── Aktivni provajderi info ──
        self._provider_label = QLabel()
        self._provider_label.setStyleSheet("font-size: 11px; color: #888; padding: 2px 0;")
        self._update_provider_label()
        layout.addWidget(self._provider_label)

        # ── Rezultati: TreeWidget za kolone ──
        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels([
            "Naziv", "Jezik", "Provajder", "⬇", "⭐", "Format"
        ])
        self._results_tree.setRootIsDecorated(False)
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._results_tree.setSortingEnabled(True)
        self._results_tree.setIndentation(0)

        header = self._results_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self._results_tree.itemSelectionChanged.connect(self._on_selection)
        self._results_tree.itemDoubleClicked.connect(self._download_selected)

        layout.addWidget(self._results_tree)

        # ── Progress bar ──
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(4)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # ── Status label ──
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; color: #888; padding: 2px 0;")
        layout.addWidget(self._status_label)

        # ── Bottom bar: dugmad ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._hash_label = QLabel()
        self._hash_label.setStyleSheet("font-size: 11px; color: #666;")
        btn_layout.addWidget(self._hash_label)

        btn_layout.addStretch()

        # Preuzmi
        self._download_btn = QPushButton("⬇ Preuzmi i učitaj")
        self._download_btn.setMinimumWidth(140)
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._download_selected)
        btn_layout.addWidget(self._download_btn)

        # Zatvori
        cancel = QPushButton("Zatvori")
        cancel.clicked.connect(self.reject)
        btn_layout.addWidget(cancel)

        layout.addLayout(btn_layout)

    def _update_provider_label(self):
        """Ažuriraj prikaz aktivnih provajdera."""
        providers = getattr(self._plugin, 'providers', None)
        if not providers:
            self._provider_label.setText("Provajderi: info nedostupan")
            return

        os_key = getattr(self._plugin, 'os_api_key', '') or ''
        subdl_key = getattr(self._plugin, 'subdl_api_key', '') or ''

        parts = []
        for name, enabled in providers.items():
            icon = PROVIDER_ICONS.get(name.capitalize(), "⚪")
            display_name = {
                "opensubtitles": "OpenSubtitles",
                "opensubtitles_org": "OS.org",
                "podnapisi": "Podnapisi",
                "subdl": "Subdl",
                "titlovi": "Titlovi.com",
            }.get(name, name.capitalize())

            if name == "opensubtitles":
                if enabled and os_key:
                    parts.append(f"{icon} {display_name} ✓")
                elif enabled:
                    parts.append(f"⚠ {display_name} (nema API key)")
                else:
                    parts.append(f"○ {display_name} (isklj.)")
            elif name == "opensubtitles_org":
                icon = "🌍"
                if enabled:
                    parts.append(f"{icon} {display_name} ✓")
                else:
                    parts.append(f"○ {display_name} (isklj.)")
            elif name == "podnapisi":
                icon = "🔵"
                if enabled:
                    parts.append(f"{icon} {display_name} ✓")
                else:
                    parts.append(f"○ {display_name} (isklj.)")
            elif name == "subdl":
                if enabled and subdl_key:
                    parts.append(f"{icon} {display_name} ✓")
                elif enabled:
                    parts.append(f"⚠ {display_name} (nema API key)")
                else:
                    parts.append(f"○ {display_name} (isklj.)")
            elif name == "titlovi":
                icon = "🇷🇸"
                tit_user = getattr(self._plugin, '_titlovi_username', '') or ''
                if enabled and tit_user:
                    parts.append(f"{icon} {display_name} ✓")
                elif enabled:
                    parts.append(f"⚠ {display_name} (nema login)")
                else:
                    parts.append(f"○ {display_name} (isklj.)")
            else:
                parts.append(f"{'✓' if enabled else '○'} {display_name}")

        self._provider_label.setText("Provajderi:  " + "   |   ".join(parts))

    # ═══════════════════════════════════════════
    #  SETTINGS
    # ═══════════════════════════════════════════

    def _open_settings(self):
        """Otvori podešavanja provajdera."""
        if hasattr(self._plugin, 'configure'):
            self._plugin.configure(self)
            self._update_provider_label()
        else:
            QMessageBox.information(
                self, "Info", "Ovaj plugin nema podešavanja."
            )

    # ═══════════════════════════════════════════
    #  SELECTION
    # ═══════════════════════════════════════════

    def _on_selection(self):
        items = self._results_tree.selectedItems()
        if items:
            item = items[0]
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            logger.debug(f"Selection: idx={idx}, results_len={len(self._results)}")
            if idx is not None and isinstance(idx, int) and 0 <= idx < len(self._results):
                self._selected_result = self._results[idx]
                self._download_btn.setEnabled(True)

                r = self._selected_result
                details = []
                if r.filename:
                    details.append(r.filename)
                if r.hash_match:
                    details.append("✅ Hash match!")
                self._status_label.setText("  ".join(details) if details else f"Izabran: {r.title}")
                return
            else:
                logger.warning(f"Selection idx invalid: idx={idx}, type={type(idx)}")

        self._download_btn.setEnabled(False)
        self._selected_result = None

    # ═══════════════════════════════════════════
    #  SEARCH
    # ═══════════════════════════════════════════

    def _start_search(self):
        query = self._query_edit.text().strip()
        if not query:
            return

        self._results_tree.clear()
        self._results = []
        self._selected_result = None
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._download_btn.setEnabled(False)
        self._search_btn.setEnabled(False)
        self._status_label.setText("Pretraga u toku...")
        self._hash_label.setText("")

        lang = self._lang_combo.currentData()
        file_hash = _compute_hash(self._file_path)
        if file_hash:
            self._hash_label.setText(f"Hash: {file_hash[:12]}...")

        self._worker = SubtitleSearchWorker(
            self._plugin, query, [lang], self._file_path, file_hash
        )
        self._worker.finished.connect(self._on_search_finished)
        self._worker.error.connect(self._on_error)
        self._worker.status.connect(self._on_status)
        self._worker.start()

    def _on_status(self, msg: str):
        self._status_label.setText(msg)

    def _on_search_finished(self, results: List[SubtitleResult]):
        self._progress.setVisible(False)
        self._search_btn.setEnabled(True)
        self._results = results

        if not results:
            self._status_label.setText("Nema pronađenih titlova za ovaj upit.")
            return

        hash_count = sum(1 for r in results if r.hash_match)
        self._status_label.setText(
            f"Pronađeno {len(results)} titlova"
            + (f"  ({hash_count} hash match)" if hash_count else "")
        )

        # VAŽNO: isključi sorting dok se dodaju stavke
        # inače Qt reorderuje posle svakog addTopLevelItem i
        # emituje itemSelectionChanged signale tokom populacije
        self._results_tree.setSortingEnabled(False)
        self._results_tree.blockSignals(True)

        for i, r in enumerate(results):
            item = QTreeWidgetItem()

            # Naziv
            title = r.title
            if r.hash_match:
                title = f"✅ {title}"
            item.setText(0, title)
            item.setToolTip(0, r.filename or r.title)

            # Jezik
            item.setText(1, r.language_name)

            # Provajder
            icon = PROVIDER_ICONS.get(r.provider, "")
            item.setText(2, f"{icon} {r.provider}")
            color = PROVIDER_COLORS.get(r.provider)
            if color:
                item.setForeground(2, QColor(color))

            # Downloads
            if r.download_count > 0:
                if r.download_count >= 1000:
                    item.setText(3, f"{r.download_count // 1000}k")
                else:
                    item.setText(3, str(r.download_count))
            else:
                item.setText(3, "-")
            item.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)

            # Rating
            if r.rating > 0:
                item.setText(4, f"{r.rating:.1f}")
            else:
                item.setText(4, "-")
            item.setTextAlignment(4, Qt.AlignmentFlag.AlignCenter)

            # Format
            item.setText(5, r.format.upper() if r.format else "SRT")
            item.setTextAlignment(5, Qt.AlignmentFlag.AlignCenter)

            # Hash match highlight
            if r.hash_match:
                for col in range(6):
                    item.setForeground(col, QColor("#00E676"))

            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self._results_tree.addTopLevelItem(item)

        # Ponovo uključi sorting i signale
        self._results_tree.blockSignals(False)
        self._results_tree.setSortingEnabled(True)

        # Selektuj prvi rezultat i aktiviraj dugme
        if self._results_tree.topLevelItemCount() > 0:
            first = self._results_tree.topLevelItem(0)
            self._results_tree.setCurrentItem(first)
            # Eksplicitno postavi selekciju jer blockSignals
            # je mogao da proguta signal
            idx = first.data(0, Qt.ItemDataRole.UserRole)
            if idx is not None and 0 <= idx < len(self._results):
                self._selected_result = self._results[idx]
                self._download_btn.setEnabled(True)

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._search_btn.setEnabled(True)
        self._status_label.setText(f"Greška: {msg}")
        QMessageBox.warning(self, "Greška pri pretrazi", msg)

    # ═══════════════════════════════════════════
    #  DOWNLOAD
    # ═══════════════════════════════════════════

    def _download_selected(self):
        if not self._selected_result:
            items = self._results_tree.selectedItems()
            if not items:
                return
            item = items[0]
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            if idx is not None and 0 <= idx < len(self._results):
                self._selected_result = self._results[idx]
            else:
                return

        result = self._selected_result
        dest_dir = os.path.dirname(self._file_path) or os.getcwd()

        self._download_btn.setEnabled(False)
        self._search_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._status_label.setText(
            f"Preuzimanje: {result.title} ({result.provider})..."
        )

        self._download_worker = SubtitleDownloadWorker(self._plugin, result, dest_dir)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.progress.connect(self._on_status)
        self._download_worker.start()

    def _on_download_finished(self, success: bool, message: str):
        self._progress.setVisible(False)
        self._download_btn.setEnabled(True)
        self._search_btn.setEnabled(True)

        if success:
            self._downloaded_path = message
            basename = os.path.basename(message)
            self._status_label.setText(f"✅ Titl preuzet: {basename}")
            self.accept()
        else:
            self._status_label.setText(f"❌ Greška: {message}")
            QMessageBox.warning(self, "Greška pri preuzimanju", message)

    # ═══════════════════════════════════════════
    #  PROPERTIES
    # ═══════════════════════════════════════════

    @property
    def selected_result(self) -> Optional[SubtitleResult]:
        """Selektovani SubtitleResult (ili None)."""
        return self._selected_result

    @property
    def downloaded_path(self) -> Optional[str]:
        """Putanja preuzetog titla (postoji samo ako je download uspeo)."""
        return self._downloaded_path