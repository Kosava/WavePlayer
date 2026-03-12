import os
from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QMessageBox,
    QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

from plugins.plugin_api import SubtitleResult
from plugins.subtitle_search import SubtitleSearchPlugin, compute_opensubtitles_hash


class SubtitleDownloadWorker(QThread):
    """Novi worker za preuzimanje titla u pozadini"""
    finished = pyqtSignal(bool, str)  # (success, message/file_path)
    progress = pyqtSignal(str)

    def __init__(self, plugin: SubtitleSearchPlugin, result: SubtitleResult, save_path: str):
        super().__init__()
        self._plugin = plugin
        self._result = result
        self._save_path = save_path

    def run(self):
        try:
            self.progress.emit("Preuzimanje titla...")
            content = self._plugin.download(self._result)
            
            if content is None:
                self.finished.emit(False, "Neuspelo preuzimanje titla")
                return
            
            # Snimi u fajl
            with open(self._save_path, 'wb') as f:
                f.write(content)
            
            self.finished.emit(True, self._save_path)
            
        except Exception as e:
            self.finished.emit(False, str(e))


class SubtitleSearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self,
        plugin: SubtitleSearchPlugin,
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
            results = self._plugin.search(
                self._query, self._languages, self._file_hash, self._file_path
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class SubtitleSearchDialog(QDialog):
    def __init__(self, plugin: SubtitleSearchPlugin, file_path: str, parent=None):
        super().__init__(parent)

        self._plugin = plugin
        self._file_path = file_path
        self._results: List[SubtitleResult] = []
        self._selected_result: Optional[SubtitleResult] = None
        self._worker: Optional[SubtitleSearchWorker] = None
        self._download_worker: Optional[SubtitleDownloadWorker] = None

        self.setWindowTitle("Pretraga titlova")
        self.setMinimumSize(700, 500)

        self._setup_ui()
        self._start_search()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        query_layout = QHBoxLayout()
        query_layout.addWidget(QLabel("Pretraga:"))

        self._query_edit = QLineEdit()
        self._query_edit.setText(
            os.path.splitext(os.path.basename(self._file_path))[0]
        )
        query_layout.addWidget(self._query_edit)

        self._search_btn = QPushButton("🔍 Traži")
        self._search_btn.clicked.connect(self._start_search)
        query_layout.addWidget(self._search_btn)

        layout.addLayout(query_layout)

        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Jezik:"))

        self._lang_combo = QComboBox()
        langs = [
            ("Srpski", "sr"),
            ("Engleski", "en"),
            ("Hrvatski", "hr"),
            ("Bosanski", "bs"),
            ("Nemački", "de"),
        ]
        for name, code in langs:
            self._lang_combo.addItem(name, code)

        lang_layout.addWidget(self._lang_combo)
        lang_layout.addStretch()
        layout.addLayout(lang_layout)

        self._results_list = QListWidget()
        self._results_list.itemSelectionChanged.connect(self._on_selection)
        self._results_list.itemDoubleClicked.connect(self._download_selected)
        layout.addWidget(self._results_list)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Status label za poruke
        self._status_label = QLabel("")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        btn_layout = QHBoxLayout()

        self._download_btn = QPushButton("⬇ Preuzmi")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._download_selected)
        btn_layout.addWidget(self._download_btn)

        btn_layout.addStretch()

        cancel = QPushButton("Odustani")
        cancel.clicked.connect(self.reject)
        btn_layout.addWidget(cancel)

        layout.addLayout(btn_layout)

    def _on_selection(self):
        items = self._results_list.selectedItems()
        self._download_btn.setEnabled(bool(items))

    def _start_search(self):
        query = self._query_edit.text().strip()
        if not query:
            return

        self._results_list.clear()
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._download_btn.setEnabled(False)
        self._status_label.setVisible(False)

        lang = self._lang_combo.currentData()
        file_hash = compute_opensubtitles_hash(self._file_path)

        self._worker = SubtitleSearchWorker(
            self._plugin, query, [lang], self._file_path, file_hash
        )

        self._worker.finished.connect(self._on_search_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_search_finished(self, results: List[SubtitleResult]):
        self._progress.setVisible(False)

        if not results:
            self._results_list.addItem("❌ Nema pronađenih titlova")
            return

        for r in results:
            text = f"{r.title}  [{r.language_name}]  ({r.provider})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r)

            if r.provider == "OpenSubtitles":
                item.setForeground(QColor("#4CAF50"))
            elif r.provider == "Podnapisi":
                item.setForeground(QColor("#2196F3"))
            elif r.provider == "Titlovi":
                item.setForeground(QColor("#FFC107"))
            elif r.provider == "YIFY":
                item.setForeground(QColor("#9C27B0"))

            if r.hash_match:
                item.setForeground(QColor("#00FF00"))

            self._results_list.addItem(item)

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        QMessageBox.warning(self, "Greška", msg)

    def _download_selected(self):
        item = self._results_list.currentItem()
        if not item:
            return

        result = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, SubtitleResult):
            return

        # Generiši putanju za čuvanje (isto ime kao video, .srt ekstenzija)
        base_path = os.path.splitext(self._file_path)[0]
        save_path = f"{base_path}.srt"

        # Ako već postoji, dodaj broj
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base_path}.{counter}.srt"
            counter += 1

        self._selected_result = result
        self._download_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._status_label.setText("Preuzimanje titla...")
        self._status_label.setVisible(True)

        # Pokreni worker za preuzimanje
        self._download_worker = SubtitleDownloadWorker(self._plugin, result, save_path)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    def _on_download_finished(self, success: bool, message: str):
        self._progress.setVisible(False)
        self._status_label.setVisible(False)
        self._download_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "Uspeh", f"Titl preuzet:\n{message}")
            self.accept()  # Zatvori dijalog tek nakon uspešnog preuzimanja
        else:
            QMessageBox.warning(self, "Greška pri preuzimanju", message)

    @property
    def selected_result(self):
        return self._selected_result