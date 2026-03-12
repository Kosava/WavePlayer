"""Main application window.

Frameless window that assembles all UI components.
Acts as the "wiring" layer between UI widgets and core engine.

THREAD SAFETY:
  mpv callbacks fire from mpv's thread. We use QTimer polling
  for position updates. State changes use Qt's signal mechanism
  by connecting through the EngineEventCallback which must be
  called from the main thread (enforced by our architecture).
"""

import logging
import os
import threading
from typing import Optional, List

from PyQt6.QtWidgets import (
    QMainWindow,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFileDialog,
    QApplication,
    QMenu,
    QInputDialog,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QProgressBar,
    QMessageBox,
    QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, pyqtSignal, QThread
from PyQt6.QtGui import QKeyEvent, QAction, QKeySequence, QShortcut, QColor

from core.interfaces import PlaybackState, EngineEventCallback
from core.mpv_engine import MpvEngine, is_subtitle_file
from core.torrent_engine import TorrentEngine, TorrentCallbacks, TorrentState
from core.media_info import PlaylistItem, MediaType
from core.config import Config, CONFIG_DIR

# Plugin imports
from plugins import PluginManager, PluginContext
from plugins.plugin_api import SubtitlePlugin, SubtitleResult
from plugins.subtitle_search import SubtitleSearchPlugin, compute_opensubtitles_hash

from .title_bar import TitleBar
from .video_widget import VideoWidget
from .controls import ControlBar
from .playlist_panel import PlaylistPanel
from .overlay import OsdOverlay
from .torrent_overlay import TorrentOverlay
from .styles import get_stylesheet
from .settings_dialog import SettingsDialog
from .subtitle_dialog import SubtitleSearchDialog  # Kreiraćemo ovaj fajl

logger = logging.getLogger(__name__)


class SubtitleSearchWorker(QThread):
    """Worker thread for subtitle search to avoid blocking UI."""
    
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, plugin: SubtitleSearchPlugin, query: str, languages: List[str], 
                 file_path: str = "", file_hash: str = ""):
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
    """Dialog for searching and downloading subtitles."""
    
    def __init__(self, plugin: SubtitleSearchPlugin, file_path: str, parent=None):
        super().__init__(parent)
        
        self._plugin = plugin
        self._file_path = file_path
        self._results: List[SubtitleResult] = []
        self._selected_result: Optional[SubtitleResult] = None
        self._worker: Optional[SubtitleSearchWorker] = None
        
        self.setWindowTitle("Pretraga titlova")
        self.setMinimumSize(700, 500)
        self.setModal(True)
        
        self._setup_ui()
        self._start_search()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Search query
        query_layout = QHBoxLayout()
        query_layout.addWidget(QLabel("Pretraga:"))
        
        self._query_edit = QLineEdit()
        self._query_edit.setPlaceholderText("Naziv filma/serije...")
        self._query_edit.setText(os.path.splitext(os.path.basename(self._file_path))[0])
        query_layout.addWidget(self._query_edit)
        
        self._search_btn = QPushButton("🔍 Traži")
        self._search_btn.clicked.connect(self._start_search)
        query_layout.addWidget(self._search_btn)
        
        layout.addLayout(query_layout)
        
        # Language selection
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Jezik:"))
        
        self._lang_combo = QComboBox()
        languages = [
            ("Srpski", "sr"),
            ("Engleski", "en"),
            ("Hrvatski", "hr"),
            ("Bosanski", "bs"),
            ("Nemački", "de"),
            ("Francuski", "fr"),
            ("Španski", "es"),
            ("Italijanski", "it"),
            ("Ruski", "ru"),
        ]
        for name, code in languages:
            self._lang_combo.addItem(name, code)
        self._lang_combo.setCurrentIndex(0)  # Srpski
        lang_layout.addWidget(self._lang_combo)
        lang_layout.addStretch()
        
        layout.addLayout(lang_layout)
        
        # Results list
        self._results_list = QListWidget()
        self._results_list.setAlternatingRowColors(True)
        self._results_list.itemDoubleClicked.connect(self._download_selected)
        layout.addWidget(self._results_list, 1)
        
        # Progress bar
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self._download_btn = QPushButton("⬇ Preuzmi")
        self._download_btn.clicked.connect(self._download_selected)
        self._download_btn.setEnabled(False)
        btn_layout.addWidget(self._download_btn)
        
        btn_layout.addStretch()
        
        self._cancel_btn = QPushButton("Odustani")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def _start_search(self):
        query = self._query_edit.text().strip()
        if not query:
            return
        
        # Clear previous results
        self._results_list.clear()
        self._results = []
        self._download_btn.setEnabled(False)
        
        # Show progress
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)  # Indeterminate
        self._search_btn.setEnabled(False)
        
        # Get selected language
        lang_code = self._lang_combo.currentData()
        
        # Calculate file hash
        file_hash = compute_opensubtitles_hash(self._file_path)
        
        # Start worker thread
        self._worker = SubtitleSearchWorker(
            self._plugin, query, [lang_code], self._file_path, file_hash
        )
        self._worker.finished.connect(self._on_search_finished)
        self._worker.error.connect(self._on_search_error)
        self._worker.start()
    
    def _on_search_finished(self, results: List[SubtitleResult]):
        self._results = results
        
        self._progress.setVisible(False)
        self._search_btn.setEnabled(True)
        
        if not results:
            item = QListWidgetItem("❌ Nema pronađenih titlova")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._results_list.addItem(item)
            return
        
        for r in results:
            # Create display text
            title = r.title[:60] + "..." if len(r.title) > 60 else r.title
            lang = r.language_name
            rating = f"★ {r.rating:.1f}" if r.rating > 0 else ""
            downloads = f"⬇ {r.download_count}" if r.download_count > 0 else ""
            provider = f"[{r.provider}]"
            hash_match = "✓ TAČAN" if r.hash_match else ""
            
            text = f"{title} - {lang} {provider}"
            if rating:
                text += f" {rating}"
            if downloads:
                text += f" {downloads}"
            if hash_match:
                text += f" {hash_match}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r)
            
            # Color based on hash match
            if r.hash_match:
                item.setForeground(QColor("#00FF00"))
            elif r.rating > 7:
                item.setForeground(QColor("#FFFF00"))
            
            self._results_list.addItem(item)
    
    def _on_search_error(self, error_msg: str):
        self._progress.setVisible(False)
        self._search_btn.setEnabled(True)
        
        QMessageBox.warning(self, "Greška", f"Došlo je do greške pri pretrazi:\n{error_msg}")
    
    def _download_selected(self):
        current = self._results_list.currentItem()
        if not current:
            return
        
        result = current.data(Qt.ItemDataRole.UserRole)
        if not result:
            return
        
        self._selected_result = result
        self.accept()
    
    @property
    def selected_result(self) -> Optional[SubtitleResult]:
        return self._selected_result


class MainWindow(QMainWindow):

    APP_NAME: str = "WavePlayer"
    MIN_WIDTH: int = 800
    MIN_HEIGHT: int = 500

    _torrent_ready_signal = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()

        self._is_fullscreen: bool = False
        self._playlist_current: int = -1
        self._current_file: str = ""  # PATCH 1: dodata promenljiva za trenutni fajl

        self._config = Config()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._callbacks = EngineEventCallback()
        self._engine = MpvEngine(self._callbacks)

        # Torrent engine
        self._torrent_callbacks = TorrentCallbacks()
        self._torrent = TorrentEngine(self._torrent_callbacks)
        self._torrent.apply_config(self._config)
        
        self._torrent_ready_signal.connect(self._play_torrent_file)
        self._torrent_callbacks.on_ready_to_play = self._on_torrent_ready
        self._torrent_callbacks.on_progress = lambda s: None
        self._torrent_callbacks.on_state_changed = lambda s: None

        # Plugin system initialization
        self._plugin_mgr = PluginManager()
        self._plugin_ctx = self._create_plugin_context()
        self._plugin_ctx.config = self._config  # Dodaj config u plugin context
        self._plugin_mgr.load_all()
        self._plugin_mgr.initialize_all(self._plugin_ctx)

        self._setup_ui()
        self._setup_engine_bridge()
        self._setup_shortcuts()
        self._setup_update_timer()

        self._load_settings()
        self._init_engine()

        self._apply_theme(self._config.get("ui.theme", "midnight_red"))
        self._overlay.set_osd_theme(self._config.get("ui.osd_theme", "minimal"))

        # Popuni welcome screen sa nedavnim fajlovima
        self._refresh_welcome()

        logger.info("MainWindow inicijalizovan")

    def _create_plugin_context(self) -> PluginContext:
        """Create and configure the plugin context."""
        ctx = PluginContext()
        
        # Basic file info
        ctx._get_current_file = lambda: self._get_current_file()
        ctx._get_media_hash = lambda: self._get_media_hash()
        
        # Subtitle loading
        ctx._load_subtitle = lambda path: self._engine.load_subtitle(path)
        
        # File loading
        ctx._load_file = lambda path: self._load_file(path)
        
        # OSD display
        ctx._show_osd = lambda text, ms: self._show_plugin_osd(text, ms)
        
        # Config access
        ctx._get_config = lambda key, default=None: self._config.get(key, default)
        ctx._set_config = lambda key, value: self._config.set(key, value)
        
        # Video info
        ctx._get_video_info = lambda: self._get_video_info()
        
        # Playlist
        ctx._add_to_playlist = lambda paths: self._add_to_playlist(paths)
        
        # Data directory
        ctx._get_data_dir = lambda: self._config.get_plugins_dir()
        
        return ctx

    def _get_current_file(self) -> str:
        """Get current playing file path."""
        return self._current_file

    def _get_media_hash(self) -> str:
        """Get hash of current media for subtitle matching."""
        if not self._current_file:
            return ""
        
        return compute_opensubtitles_hash(self._current_file)

    def _get_video_info(self) -> dict:
        """Get video information for plugins."""
        return {
            "width": self._engine.get_video_width(),
            "height": self._engine.get_video_height(),
            "duration": self._engine.get_duration(),
            "position": self._engine.get_position(),
            "filename": self._current_file,
            "state": self._engine.get_state().value if self._engine.get_state() else 0,
        }

    def _show_plugin_osd(self, text: str, duration_ms: int = 2000) -> None:
        """Show OSD message from plugins."""
        self._overlay.show_title(text, duration_ms)

    def _add_to_playlist(self, paths: List[str]) -> None:
        """Add files to playlist."""
        media_files = [p for p in paths if not is_subtitle_file(p)]
        sub_files = [p for p in paths if is_subtitle_file(p)]

        for path in media_files:
            item = PlaylistItem(file_path=path, media_type=MediaType.VIDEO)
            self._playlist_panel.add_item(item)

        # Load subtitles for current video
        for path in sub_files:
            self._on_subtitle_dropped(path)

    def _setup_ui(self) -> None:
        central_frame = QFrame(self)
        central_frame.setObjectName("centralFrame")
        self.setCentralWidget(central_frame)

        main_layout = QVBoxLayout(central_frame)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._title_bar = TitleBar(self)
        main_layout.addWidget(self._title_bar)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._video_widget = VideoWidget(self)
        self._video_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        content_layout.addWidget(self._video_widget, 1)

        self._overlay = OsdOverlay(self._engine)

        # Torrent status overlay (donji levi ugao videa)
        self._torrent_overlay = TorrentOverlay(self._video_widget)

        self._playlist_panel = PlaylistPanel(self)
        content_layout.addWidget(self._playlist_panel)

        main_layout.addLayout(content_layout, 1)

        self._control_bar = ControlBar(self)
        main_layout.addWidget(self._control_bar)

        self._connect_ui_signals()

    def _connect_ui_signals(self) -> None:
        
        cb = self._control_bar
        cb.play_pause_clicked.connect(self._on_play_pause)
        cb.stop_clicked.connect(self._on_stop)
        cb.seek_requested.connect(self._on_seek)
        cb.volume_changed.connect(self._on_volume_changed)
        cb.mute_toggled.connect(self._on_mute_toggled)
        cb.speed_changed.connect(self._on_speed_changed)
        cb.fullscreen_clicked.connect(self._toggle_fullscreen)
        cb.playlist_clicked.connect(self._toggle_playlist)
        cb.next_clicked.connect(self._on_next)
        cb.prev_clicked.connect(self._on_prev)
        cb.settings_clicked.connect(self._open_settings)

        vw = self._video_widget
        vw.file_dropped.connect(self._load_file)
        vw.subtitle_dropped.connect(self._on_subtitle_dropped)
        vw.double_clicked.connect(self._toggle_fullscreen)
        vw.right_clicked.connect(self._show_context_menu)

        # Welcome screen signali
        welcome = self._video_widget.welcome
        welcome.open_file_requested.connect(self._open_file_dialog)
        welcome.open_torrent_requested.connect(self._open_torrent_dialog)
        welcome.open_url_requested.connect(self._open_url_dialog)
        welcome.file_selected.connect(self._load_file)
        welcome.clear_recent_requested.connect(self._clear_recent)

        self._playlist_panel.item_double_clicked.connect(self._on_playlist_item)
        self._playlist_panel.files_added.connect(self._on_files_added)

    def _setup_engine_bridge(self) -> None:
        
        self._callbacks.on_state_changed = self._on_engine_state_changed
        self._callbacks.on_duration_changed = self._on_engine_duration_changed
        self._callbacks.on_media_loaded = self._on_engine_media_loaded
        self._callbacks.on_error = self._on_engine_error
        self._callbacks.on_end_of_file = self._on_engine_eof

    def _setup_shortcuts(self) -> None:
        """QShortcut radi globalno — rešava problem mpv window fokusa."""
        def _sc(key, handler):
            s = QShortcut(key if isinstance(key, QKeySequence) else QKeySequence(key), self)
            s.setContext(Qt.ShortcutContext.WindowShortcut)
            s.activated.connect(handler)

        _sc(Qt.Key.Key_Space, self._shortcut_play_pause)
        _sc(Qt.Key.Key_F, self._toggle_fullscreen)
        _sc(Qt.Key.Key_F11, self._toggle_fullscreen)
        _sc(Qt.Key.Key_Escape, self._shortcut_escape)
        _sc(Qt.Key.Key_Up, self._shortcut_volume_up)
        _sc(Qt.Key.Key_Down, self._shortcut_volume_down)
        _sc(Qt.Key.Key_Right, self._shortcut_seek_forward)
        _sc(Qt.Key.Key_Left, self._shortcut_seek_backward)
        _sc(Qt.Key.Key_M, self._shortcut_mute)
        _sc(Qt.Key.Key_N, self._on_next)
        _sc(Qt.Key.Key_P, self._on_prev)
        _sc(QKeySequence.StandardKey.Open, self._open_file_dialog)
        _sc(QKeySequence("Ctrl+Q"), self.close)
        _sc(QKeySequence("Ctrl+,"), self._open_settings)
        _sc(QKeySequence("Ctrl+U"), self._open_url_dialog)
        _sc(QKeySequence("Ctrl+T"), self._open_torrent_dialog)
        _sc(QKeySequence("Ctrl+Shift+S"), self._open_subtitle_search)  # Pretraga titlova
        _sc(QKeySequence("Ctrl+Y"), self._open_youtube_search)  # YouTube pretraga
        _sc(Qt.Key.Key_Home, self._on_stop)          # Vrati se na welcome
        _sc(Qt.Key.Key_L, self._toggle_playlist)      # Show/hide playlist
        _sc(Qt.Key.Key_O, self._shortcut_osd_info)    # OSD media info

    # --- Plugin-specific shortcuts ---

    def _open_subtitle_search(self) -> None:
        """Open subtitle search dialog."""
        if not self._current_file:  # PATCH 3: koristi self._current_file umesto hasattr provere
            self._overlay.show_title("Prvo učitaj video fajl")
            return
        
        # Get subtitle plugin
        subtitle_plugin = self._plugin_mgr.get_plugin("SubtitleSearch")
        if not subtitle_plugin:
            self._overlay.show_title("Plugin za titlove nije dostupan")
            return
        
        dialog = SubtitleSearchDialog(subtitle_plugin, self._current_file, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_result:
            # Download and load selected subtitle
            result = dialog.selected_result
            dest_dir = os.path.join(str(CONFIG_DIR), "subtitles")
            os.makedirs(dest_dir, exist_ok=True)
            
            # IZMENA: Umesto dohvatanja specifičnog provider plugina,
            # koristimo SubtitleSearch plugin za download
            plugin = self._plugin_mgr.get_plugin("SubtitleSearch")
            if not plugin:
                logger.error("SubtitleSearch plugin nije pronađen")
                self._overlay.show_title("❌ Greška: Plugin za titlove nije dostupan")
                return
            
            path = plugin.download(result, dest_dir)
            if path:
                self._on_subtitle_dropped(path)
                self._overlay.show_title(f"Titl učitan: {os.path.basename(path)}")
            else:
                self._overlay.show_title("❌ Greška pri preuzimanju titla")

    def _open_youtube_search(self) -> None:
        """Open YouTube search dialog."""
        youtube_plugin = self._plugin_mgr.get_plugin("YouTube")
        if youtube_plugin and hasattr(youtube_plugin, "show_search_dialog"):
            youtube_plugin.show_search_dialog(self)
        else:
            self._overlay.show_title("YouTube plugin nije dostupan")

    # --- Shortcut handlers ---

    def _shortcut_play_pause(self) -> None:
        self._on_play_pause()
        st = self._engine.get_state()
        self._overlay.show_play() if st == PlaybackState.PLAYING else self._overlay.show_pause()

    def _shortcut_escape(self) -> None:
        if self._is_fullscreen:
            self._toggle_fullscreen()

    def _shortcut_volume_up(self) -> None:
        step = self._config.get("audio.volume_step", 5)
        self._engine.set_volume(min(100, self._engine.get_volume() + step))
        self._control_bar.set_volume(self._engine.get_volume())
        self._overlay.show_volume(self._engine.get_volume())

    def _shortcut_volume_down(self) -> None:
        step = self._config.get("audio.volume_step", 5)
        self._engine.set_volume(max(0, self._engine.get_volume() - step))
        self._control_bar.set_volume(self._engine.get_volume())
        self._overlay.show_volume(self._engine.get_volume())

    def _shortcut_seek_forward(self) -> None:
        step = self._config.get("playback.seek_step", 10)
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        new = min(pos + step, dur)
        self._engine.seek(new)
        self._overlay.show_seek(new, dur)

    def _shortcut_seek_backward(self) -> None:
        step = self._config.get("playback.seek_step", 10)
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        new = max(0, pos - step)
        self._engine.seek(new)
        self._overlay.show_seek(new, dur)

    def _shortcut_mute(self) -> None:
        muted = not self._engine.get_muted()
        self._engine.set_muted(muted)
        self._control_bar.set_muted(muted)
        self._overlay.show_volume(self._engine.get_volume(), muted)

    def _shortcut_osd_info(self) -> None:
        """Prikaži OSD sa detaljnim info o trenutnom mediju (O taster)."""
        if self._engine.get_state() == PlaybackState.STOPPED:
            return

        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        vol = self._engine.get_volume()
        speed = self._engine.get_speed()
        muted = self._engine.get_muted()
        w = self._engine.get_video_width()
        h = self._engine.get_video_height()

        # Naziv fajla iz title bara
        title = self._get_current_file()

        # Formatiranje vremena
        def fmt(s: float) -> str:
            t = int(max(0, s))
            hrs, rem = divmod(t, 3600)
            mins, secs = divmod(rem, 60)
            return f"{hrs}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins}:{secs:02d}"

        progress = (pos / dur * 100) if dur > 0 else 0

        lines = []
        if title:
            lines.append(title)
        lines.append(f"{fmt(pos)} / {fmt(dur)}  ({progress:.1f}%)")
        if w > 0 and h > 0:
            lines.append(f"{w}×{h}")
        vol_str = f"🔇 Muted" if muted else f"🔊 {vol}%"
        if speed != 1.0:
            vol_str += f"  ⚡ {speed}x"
        lines.append(vol_str)

        self._overlay.show_info("\n".join(lines))

    def _setup_update_timer(self) -> None:
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(100)
        self._update_timer.timeout.connect(self._update_position)
        self._update_timer.start()

        # Torrent status polling (sporiji — svake sekunde)
        self._torrent_timer = QTimer(self)
        self._torrent_timer.setInterval(1000)
        self._torrent_timer.timeout.connect(self._update_torrent_status)
        self._torrent_timer.start()

    def _init_engine(self) -> None:
        
        wid = self._video_widget.get_window_id()
        self._engine.set_window_id(wid)
        if not self._engine.initialize():
            logger.error("Engine inicijalizacija neuspešna")
            return
        # Primeni subtitle stil iz config-a na mpv
        self._engine.apply_subtitle_config(self._config)

    # --- Theme ---

    def _apply_theme(self, theme_name: str) -> None:
        self.setStyleSheet(get_stylesheet(theme_name))
        logger.info(f"Primenjena tema: {theme_name}")

    def _on_theme_changed(self, theme_name: str) -> None:
        self._apply_theme(theme_name)

    def _on_osd_theme_changed(self, theme_name: str) -> None:
        self._overlay.set_osd_theme(theme_name)
        self._overlay.show_title("OSD Theme Preview")

    # --- Settings ---

    def _open_settings(self) -> None:
        
        dialog = SettingsDialog(self._config, self._plugin_mgr, self)
        dialog.theme_changed.connect(self._on_theme_changed)
        dialog.osd_theme_changed.connect(self._on_osd_theme_changed)
        old_theme = self._config.get("ui.theme", "midnight_red")
        old_osd = self._config.get("ui.osd_theme", "minimal")
        dialog.setStyleSheet(get_stylesheet(old_theme))
        result = dialog.exec()
        if result != SettingsDialog.DialogCode.Accepted:
            self._apply_theme(old_theme)
            self._overlay.set_osd_theme(old_osd)
        else:
            self._apply_theme(self._config.get("ui.theme", "midnight_red"))
            self._overlay.set_osd_theme(self._config.get("ui.osd_theme", "minimal"))
            # Primeni subtitle promene na mpv
            self._engine.apply_subtitle_config(self._config)
            # Primeni torrent promene
            self._torrent.apply_config(self._config)

    # ═══════════════════════════════════════════
    #  CONTEXT MENU
    # ═══════════════════════════════════════════

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self._get_context_menu_style())

        # Plugin submenu
        plugin_menu = menu.addMenu("🧩  Plugini")
        
        # Subtitle search (ako postoji plugin)
        subtitle_plugin = self._plugin_mgr.get_plugin("SubtitleSearch")
        if subtitle_plugin:
            plugin_menu.addAction("🔍  Pretraga titlova").triggered.connect(
                self._open_subtitle_search)
        
        # YouTube plugin
        youtube_plugin = self._plugin_mgr.get_plugin("YouTube")
        if youtube_plugin:
            plugin_menu.addAction("▶  YouTube pretraga").triggered.connect(
                self._open_youtube_search)
        
        # Media library plugin
        library_plugin = self._plugin_mgr.get_plugin("MediaLibrary")
        if library_plugin and hasattr(library_plugin, "show_library"):
            plugin_menu.addAction("📚  Medijska biblioteka").triggered.connect(
                lambda: library_plugin.show_library(self))
        
        # TMDb metadata plugin
        tmdb_plugin = self._plugin_mgr.get_plugin("TMDb")
        if tmdb_plugin and hasattr(tmdb_plugin, "show_metadata"):
            plugin_menu.addAction("🎬  Metapodaci filma").triggered.connect(
                lambda: self._show_movie_metadata(tmdb_plugin))
        
        # Ako nema pluginova
        if plugin_menu.isEmpty():
            plugin_menu.addAction("Nema dostupnih pluginova").setEnabled(False)
        
        menu.addSeparator()

        menu.addAction("📂  Otvori fajl...").triggered.connect(self._open_file_dialog)
        menu.addAction("💬  Učitaj titlove...").triggered.connect(self._load_subtitle_dialog)
        menu.addAction("🧲  Otvori magnet / torrent...").triggered.connect(self._open_torrent_dialog)
        menu.addAction("🌐  Otvori URL stream...").triggered.connect(self._open_url_dialog)
        menu.addSeparator()

        state = self._engine.get_state()
        pp = menu.addAction("⏸  Pauza" if state == PlaybackState.PLAYING else "▶  Play")
        pp.triggered.connect(self._on_play_pause)
        menu.addAction("⏹  Stop").triggered.connect(self._on_stop)
        menu.addSeparator()

        # Titlovi submenu
        sub_menu = menu.addMenu("💬  Titlovi")
        sub_tracks = self._get_subtitle_tracks()
        if sub_tracks:
            current_sid = self._get_current_subtitle_id()
            off = sub_menu.addAction("Isključi")
            off.setCheckable(True)
            off.setChecked(current_sid == 0)
            off.triggered.connect(lambda: self._set_subtitle_track(0))
            sub_menu.addSeparator()
            for tid, tname in sub_tracks:
                a = sub_menu.addAction(tname)
                a.setCheckable(True)
                a.setChecked(tid == current_sid)
                a.triggered.connect(lambda c, t=tid: self._set_subtitle_track(t))
        else:
            sub_menu.addAction("Nema titlova").setEnabled(False)

        # Audio submenu
        audio_menu = menu.addMenu("🔊  Audio")
        audio_tracks = self._get_audio_tracks()
        if audio_tracks:
            current_aid = self._get_current_audio_id()
            for tid, tname in audio_tracks:
                a = audio_menu.addAction(tname)
                a.setCheckable(True)
                a.setChecked(tid == current_aid)
                a.triggered.connect(lambda c, t=tid: self._set_audio_track(t))
        else:
            audio_menu.addAction("Nema track-ova").setEnabled(False)

        menu.addSeparator()

        # Seek
        seek_menu = menu.addMenu("⏩  Preskoči")
        for label, secs in [("-60s", -60), ("-10s", -10), ("+10s", 10), ("+30s", 30), ("+60s", 60)]:
            seek_menu.addAction(label).triggered.connect(
                lambda c, s=secs: self._seek_relative(s))

        # Speed
        speed_menu = menu.addMenu("⚡  Brzina")
        cur_speed = self._engine.get_speed()
        for spd in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            lbl = f"{spd}x" + ("  ✓" if abs(spd - cur_speed) < 0.01 else "")
            speed_menu.addAction(lbl).triggered.connect(
                lambda c, s=spd: self._engine.set_speed(s))

        menu.addSeparator()

        # ── Video opcije ──
        video_menu = menu.addMenu("🖥  Video")

        # Aspect ratio
        ar_menu = video_menu.addMenu("Aspect Ratio")
        for label, val in [("Auto", "auto"), ("16:9", "16:9"), ("16:10", "16:10"), ("4:3", "4:3"),
                           ("2.35:1", "2.35:1"), ("1.85:1", "1.85:1"),
                           ("21:9", "21:9"), ("1:1", "1:1")]:
            ar_menu.addAction(label).triggered.connect(
                lambda c, v=val: self._set_aspect_ratio(v))

        # Zoom
        zoom_menu = video_menu.addMenu("Zoom")
        for label, val in [("Normalan", 0.0), ("+10%", 0.1), ("+25%", 0.22),
                           ("+50%", 0.41), ("+100%", 0.7), ("-10%", -0.1),
                           ("-25%", -0.22), ("-50%", -0.41)]:
            zoom_menu.addAction(label).triggered.connect(
                lambda c, v=val: self._engine.set_zoom(v))

        # Rotacija
        rot_menu = video_menu.addMenu("Rotacija")
        for label, val in [("0° (normalno)", 0), ("90° CW", 90),
                           ("180°", 180), ("270° CCW", 270)]:
            rot_menu.addAction(label).triggered.connect(
                lambda c, v=val: self._engine.set_rotation(v))

        video_menu.addSeparator()

        # Deinterlace toggle
        deint = video_menu.addAction("Deinterlace")
        deint.setCheckable(True)
        try:
            deint.setChecked(self._engine._player and
                             str(self._engine._player.get("deinterlace", "no")) == "yes")
        except Exception:
            pass
        deint.triggered.connect(lambda checked: self._engine.set_deinterlace(checked))

        video_menu.addSeparator()

        # Video EQ
        eq_menu = video_menu.addMenu("Podešavanja slike")
        for prop, name in [("brightness", "Svetlina"), ("contrast", "Kontrast"),
                           ("saturation", "Saturacija"), ("gamma", "Gamma"),
                           ("hue", "Nijansa")]:
            prop_menu = eq_menu.addMenu(name)
            current = self._engine.get_video_eq(prop)
            for label, val in [("Reset (0)", 0), ("+10", current + 10),
                               ("+5", current + 5), ("-5", current - 5),
                               ("-10", current - 10)]:
                prop_menu.addAction(f"{label}  [{current}]" if val == 0 else label).triggered.connect(
                    lambda c, p=prop, v=val: self._engine.set_video_eq(p, v))

        # Reset all video
        video_menu.addSeparator()
        reset_vid = video_menu.addAction("Reset sve video opcije")
        reset_vid.triggered.connect(self._reset_video_settings)

        video_menu.addSeparator()

        # Screenshot
        ss_menu = video_menu.addMenu("Screenshot")
        ss_menu.addAction("Sa titlovima").triggered.connect(
            lambda: self._engine.screenshot("subtitles"))
        ss_menu.addAction("Bez titlova").triggered.connect(
            lambda: self._engine.screenshot("video"))

        menu.addSeparator()

        fs_text = "🗗  Izađi iz fullscreen-a" if self._is_fullscreen else "⛶  Fullscreen"
        menu.addAction(fs_text).triggered.connect(self._toggle_fullscreen)

        pl = menu.addAction("☰  Playlist")
        pl.setCheckable(True)
        pl.setChecked(self._playlist_panel.isVisible())
        pl.triggered.connect(self._toggle_playlist)

        menu.addSeparator()
        menu.addAction("⚙  Podešavanja...").triggered.connect(self._open_settings)

        global_pos = self._video_widget.mapToGlobal(QPoint(pos.x(), pos.y()))
        menu.exec(global_pos)

    def _show_movie_metadata(self, tmdb_plugin) -> None:
        """Show movie metadata for current file."""
        if not self._current_file:
            self._overlay.show_title("Prvo učitaj video fajl")
            return
        
        filename = os.path.basename(self._current_file)
        # Extract movie name from filename (simplified)
        import re
        movie_name = re.sub(r'[._\[\]\(\)]', ' ', filename)
        movie_name = re.sub(r'\s+(19|20)\d{2}.*$', '', movie_name).strip()
        
        tmdb_plugin.show_metadata(movie_name, self)

    def _get_context_menu_style(self) -> str:
        from .themes import get_theme
        c = get_theme(self._config.get("ui.theme", "midnight_red"))
        return f"""
            QMenu {{
                background-color: {c.bg_secondary};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 8px;
                padding: 6px 0;
                font-size: 13px;
            }}
            QMenu::item {{ padding: 8px 24px 8px 16px; }}
            QMenu::item:selected {{ background-color: {c.accent}; color: white; }}
            QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 12px; }}
            QMenu::item:disabled {{ color: {c.text_muted}; }}
        """

    # --- Subtitle / Audio ---

    def _on_subtitle_dropped(self, path: str) -> None:
        """Titl fajl prevučen na video widget."""
        if self._engine.load_subtitle(path):
            name = os.path.basename(path)
            self._overlay.show_title(f"Titl: {name}")

    def _load_subtitle_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Učitaj titlove", "",
            "Subtitles (*.srt *.ass *.ssa *.sub *.vtt *.idx *.sup *.smi);;All Files (*)")
        if path:
            self._on_subtitle_dropped(path)

    def _get_subtitle_tracks(self) -> list:
        if not self._engine._player:
            return []
        try:
            result = []
            for t in self._engine._player.track_list:
                if t.get("type") == "sub":
                    tid = t.get("id", 0)
                    lang = t.get("lang", "")
                    title = t.get("title", "")
                    ext = " [ext]" if t.get("external") else ""
                    name = f"{title} ({lang})" if lang and title else (title or lang or f"Track {tid}")
                    result.append((tid, f"{name}{ext}"))
            return result
        except Exception:
            return []

    def _get_current_subtitle_id(self) -> int:
        if not self._engine._player:
            return 0
        try:
            sid = self._engine._player.sid
            return sid if sid and sid != "no" else 0
        except Exception:
            return 0

    def _set_subtitle_track(self, tid: int) -> None:
        if not self._engine._player:
            return
        try:
            if tid == 0:
                self._engine._player.sid = "no"
                self._overlay.show_title("Titlovi isključeni")
            else:
                self._engine._player.sid = tid
                name = next((n for t, n in self._get_subtitle_tracks() if t == tid), f"Track {tid}")
                self._overlay.show_title(f"Titl: {name}")
        except Exception as e:
            logger.error(f"Sub track greška: {e}")

    def _get_audio_tracks(self) -> list:
        if not self._engine._player:
            return []
        try:
            result = []
            for t in self._engine._player.track_list:
                if t.get("type") == "audio":
                    tid = t.get("id", 0)
                    lang = t.get("lang", "")
                    title = t.get("title", "")
                    codec = t.get("codec", "")
                    name = f"{title} ({lang})" if lang and title else (title or lang or f"Track {tid}")
                    if codec:
                        name += f" [{codec}]"
                    result.append((tid, name))
            return result
        except Exception:
            return []

    def _get_current_audio_id(self) -> int:
        if not self._engine._player:
            return 1
        try:
            aid = self._engine._player.aid
            return aid if aid else 1
        except Exception:
            return 1

    def _set_audio_track(self, tid: int) -> None:
        if not self._engine._player:
            return
        try:
            self._engine._player.aid = tid
            name = next((n for t, n in self._get_audio_tracks() if t == tid), f"Track {tid}")
            self._overlay.show_title(f"Audio: {name}")
        except Exception as e:
            logger.error(f"Audio track greška: {e}")

    def _seek_relative(self, seconds: float) -> None:
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        new = max(0, min(pos + seconds, dur))
        self._engine.seek(new)
        self._overlay.show_seek(new, dur)

    def _set_aspect_ratio(self, ratio: str) -> None:
        self._engine.set_aspect_ratio(ratio)
        self._overlay.show_title(f"Aspect: {ratio}")

    def _reset_video_settings(self) -> None:
        self._engine.set_aspect_ratio("auto")
        self._engine.set_zoom(0.0)
        self._engine.set_pan(0.0, 0.0)
        self._engine.set_rotation(0)
        for prop in ["brightness", "contrast", "saturation", "gamma", "hue"]:
            self._engine.set_video_eq(prop, 0)
        self._overlay.show_title("Video reset")

    # --- Torrent ---

    def _open_torrent_dialog(self, checked=False) -> None:
        """Otvori dijalog za magnet link ili .torrent fajl."""
        from PyQt6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, "Torrent", "Unesi magnet link ili ostavi prazno za .torrent fajl:",
        )
        if ok:
            if text.strip().startswith("magnet:") or text.strip():
                self._start_torrent(text.strip())
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, "Otvori .torrent", "",
                    "Torrent Files (*.torrent);;All Files (*)")
                if path:
                    self._start_torrent(path)

    def _start_torrent(self, source: str) -> None:
        """Pokreni torrent streaming."""
        from pathlib import Path
        
        if not self._torrent._download_dir:
            self._torrent._download_dir = str(Path.home() / "Downloads" / "WavePlayer")
        
        os.makedirs(self._torrent._download_dir, exist_ok=True)
        self._torrent.apply_config(self._config)

        if self._torrent.add_torrent(source):
            self._overlay.show_title("🧲 Torrent učitan — buffering...")
            self._torrent_overlay.setVisible(True)
        else:
            self._overlay.show_title("❌ Greška pri učitavanju torrenta")

    def _on_torrent_ready(self, video_path: str) -> None:
        """Torrent je bufferovao dovoljno — pokreni playback (thread-safe via signal)."""
        self._torrent_ready_signal.emit(video_path)

    def _play_torrent_file(self, video_path: str) -> None:
        """Pokreni video iz torrenta (poziva se iz main thread-a)."""
        logger.info(f"Pokrećem torrent video: {video_path}")
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            self._overlay.show_title("▶ Torrent stream spreman!")
            self._load_file(video_path)
            self._torrent.set_streaming()
        else:
            logger.error(f"Torrent video fajl nedostupan: {video_path}")

    def _update_torrent_status(self) -> None:
        """Polling torrent statusa iz main thread-a."""
        if not self._torrent.is_active():
            if self._torrent_overlay.isVisible():
                self._torrent_overlay.hide_overlay()
            return

        status = self._torrent.get_status()
        self._torrent_overlay.update_status(status)

        # Ako streaming, ažuriraj piece prioritete prema playback poziciji
        if status.state == TorrentState.STREAMING:
            pos = self._engine.get_position()
            dur = self._engine.get_duration()
            if dur > 0:
                self._torrent.update_playback_position(pos, dur)

    # --- URL stream ---

    def _open_url_dialog(self, checked=False) -> None:
        """Otvori dijalog za URL stream (http/https/rtsp)."""
        from PyQt6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, "Mrežni stream", "Unesi URL (http, https, rtsp):",
        )
        if ok and text.strip():
            self._load_file(text.strip())

    # --- Welcome screen ---

    def _refresh_welcome(self) -> None:
        """Ažuriraj welcome screen sa najnovijim recent fajlovima."""
        recent = self._config.get_recent_files()
        self._video_widget.welcome.set_recent_files(recent)

    def _clear_recent(self) -> None:
        """Obriši listu nedavnih fajlova."""
        self._config.clear_recent_files()
        self._config.save()

    # --- Player akcije ---

    def _on_play_pause(self) -> None:
        state = self._engine.get_state()
        if state == PlaybackState.PLAYING:
            self._engine.pause()
        elif state == PlaybackState.PAUSED:
            self._engine.play()

    def _on_stop(self) -> None:
        self._engine.stop()
        self._control_bar.reset()
        self._video_widget.show_drop_zone()
        self._refresh_welcome()

    def _on_seek(self, position: float) -> None:
        self._engine.seek(position)

    def _on_volume_changed(self, volume: int) -> None:
        self._engine.set_volume(volume)

    def _on_mute_toggled(self, muted: bool) -> None:
        self._engine.set_muted(muted)

    def _on_speed_changed(self, speed: float) -> None:
        self._engine.set_speed(speed)

    def _on_next(self) -> None:
        if self._playlist_panel.get_count() > 0:
            nxt = self._playlist_current + 1
            if nxt < self._playlist_panel.get_count():
                self._on_playlist_item(nxt)

    def _on_prev(self) -> None:
        if self._playlist_current > 0:
            self._on_playlist_item(self._playlist_current - 1)

    # --- Fajl operacije ---

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Media File", "",
            "Media Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm "
            "*.mp3 *.flac *.ogg *.wav *.m4a);;"
            "Playlists (*.m3u *.m3u8);;"
            "All Files (*)")
        if path:
            self._load_file(path)

    def _load_file(self, file_path: str) -> None:
        """Učitaj medijski fajl, subtitle, torrent ili M3U playlist."""
        # PATCH 2: zapamti trenutni fajl
        self._current_file = file_path
        
        # Proveri da li je subtitle
        if is_subtitle_file(file_path):
            self._on_subtitle_dropped(file_path)
            return

        # Proveri da li je torrent
        if TorrentEngine.is_torrent_source(file_path):
            self._start_torrent(file_path)
            return

        # Proveri da li je LOKALNI M3U playlist fajl (ne URL stream)
        is_url = any(file_path.startswith(s) for s in ("http://", "https://", "rtsp://", "rtp://", "mms://"))
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".m3u", ".m3u8") and not is_url:
            entries = self._playlist_panel._parse_m3u(file_path)
            if entries:
                self._on_files_added(entries)
                self._config.add_recent_file(file_path)
                self._config.save()
                self._refresh_welcome()
            else:
                logger.error(f"M3U playlist je prazan: {file_path}")
            return

        if not hasattr(self, '_engine') or not self._engine:
            logger.error("MPV engine nije inicijalizovan!")
            return

        if self._engine.load(file_path):
            self._video_widget.hide_drop_zone()
            name = os.path.basename(file_path)
            self._title_bar.set_title(f"{self.APP_NAME} - {name}")
            self._overlay.show_title(name)
            self._config.add_recent_file(file_path)
            self._config.save()
            self._refresh_welcome()
            self.setFocus()
        else:
            logger.error(f"Neuspešno učitavanje: {file_path}")

    def _on_files_added(self, file_paths: list) -> None:
        media_files = [p for p in file_paths if not is_subtitle_file(p)]
        sub_files = [p for p in file_paths if is_subtitle_file(p)]

        for path in media_files:
            self._playlist_panel.add_item(
                PlaylistItem(file_path=path, media_type=MediaType.VIDEO))

        # Učitaj titlove na trenutni video
        for path in sub_files:
            self._on_subtitle_dropped(path)

        if self._engine.get_state() == PlaybackState.STOPPED and media_files:
            self._load_file(media_files[0])
            self._playlist_current = self._playlist_panel.get_count() - len(media_files)
            self._playlist_panel.set_current(self._playlist_current)

    def _on_playlist_item(self, index: int) -> None:
        item = self._playlist_panel.get_item(index)
        if item.file_path:
            self._playlist_current = index
            self._playlist_panel.set_current(index)
            self._load_file(item.file_path)

    # --- Engine callbacks ---

    def _on_engine_state_changed(self, state: PlaybackState) -> None:
        self._control_bar.set_playing(state == PlaybackState.PLAYING)

    def _on_engine_duration_changed(self, duration: float) -> None:
        self._control_bar.set_duration(duration)

    def _on_engine_media_loaded(self, path: str) -> None:
        pass

    def _on_engine_error(self, message: str) -> None:
        logger.error(f"Engine greška: {message}")

    def _on_engine_eof(self) -> None:
        self._on_next()

    def _update_position(self) -> None:
        if self._engine.get_state() == PlaybackState.PLAYING:
            pos = self._engine.get_position()
            self._control_bar.set_position(pos)

    # --- Window ---

    def _toggle_fullscreen(self) -> None:
        self._is_fullscreen = not self._is_fullscreen
        central = self.centralWidget()

        if self._is_fullscreen:
            self._pre_fs_geometry = self.geometry()
            self._title_bar.setVisible(False)
            self._control_bar.setVisible(False)
            # Ukloni border i radius za čist fullscreen
            if central:
                central.setStyleSheet("#centralFrame { border: none; border-radius: 0px; }")
            self.setWindowFlags(Qt.WindowType.Window)
            self.showFullScreen()
        else:
            self._title_bar.setVisible(True)
            self._control_bar.setVisible(True)
            # Vrati normalan stil
            if central:
                central.setStyleSheet("")
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
            self.showNormal()
            if hasattr(self, '_pre_fs_geometry'):
                self.setGeometry(self._pre_fs_geometry)
            self.show()
        self._control_bar.set_fullscreen_icon(self._is_fullscreen)
        self.setFocus()

    def _toggle_playlist(self) -> None:
        self._playlist_panel.toggle_visible()
        self._control_bar.set_playlist_checked(self._playlist_panel.isVisible())

    # --- Settings persistence ---

    def _load_settings(self) -> None:
        cfg = self._config.to_player_config()
        self.resize(cfg.window_width, cfg.window_height)
        self.move(cfg.window_x, cfg.window_y)
        self._control_bar.set_volume(cfg.volume)
        if cfg.playlist_visible:
            self._playlist_panel.setVisible(True)
            self._control_bar.set_playlist_checked(True)

    def _save_settings(self) -> None:
        
        self._config.set("window.width", self.width())
        self._config.set("window.height", self.height())
        self._config.set("window.x", self.x())
        self._config.set("window.y", self.y())
        self._config.set("audio.volume", self._engine.get_volume())
        self._config.set("ui.playlist_visible", self._playlist_panel.isVisible())
        self._config.save()

    def closeEvent(self, event) -> None:
        
        # Shutdown plugins
        self._plugin_mgr.shutdown_all()
        
        self._save_settings()
        self._update_timer.stop()
        self._torrent_timer.stop()
        self._overlay.close()  # Zatvori OSD top-level prozor
        self._torrent.shutdown()
        self._engine.shutdown()
        super().closeEvent(event)