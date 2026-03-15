"""TMDb Metadata Dialog za WavePlayer.

Prikazuje bogat prikaz metapodataka o filmu/seriji:
  - Backdrop kao header pozadina (zatamnjen gradient)
  - Poster levo, info desno
  - Naslov, godina, ocena sa zvezdama, žanrovi, trajanje
  - Opis ispod
  - Glumci + reditelj
  - IMDb link dugme

Slike se preuzimaju u background thread-u i keširaju lokalno
u ~/.config/WavePlayer/tmdb_cache/

PORTABILITY NOTES:
  - C++: QDialog + QNetworkAccessManager za async slike
  - Rust: egui::Window + reqwest za slike
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QGraphicsOpacityEffect,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QLinearGradient, QColor, QFont, QDesktopServices
from PyQt6.QtCore import QUrl

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  CACHE
# ═══════════════════════════════════════════

def _get_cache_dir() -> Path:
    """Vrati direktorijum za keširanje TMDb slika."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".cache"
    cache_dir = base / "WavePlayer" / "tmdb_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key(url: str) -> str:
    """Generiši cache filename od URL-a."""
    h = hashlib.md5(url.encode()).hexdigest()
    ext = ".jpg"
    if ".png" in url:
        ext = ".png"
    return h + ext


def _load_cached(url: str) -> Optional[bytes]:
    """Učitaj sliku iz keša ako postoji."""
    path = _get_cache_dir() / _cache_key(url)
    if path.exists():
        return path.read_bytes()
    return None


def _save_cache(url: str, data: bytes) -> None:
    """Sačuvaj sliku u keš."""
    path = _get_cache_dir() / _cache_key(url)
    try:
        path.write_bytes(data)
    except Exception as e:
        logger.warning(f"TMDb cache write greška: {e}")


# ═══════════════════════════════════════════
#  IMAGE DOWNLOAD WORKER
# ═══════════════════════════════════════════

class ImageDownloadWorker(QThread):
    """Background thread za preuzimanje slike."""
    finished = pyqtSignal(str, bytes)   # (image_type, data)
    error = pyqtSignal(str, str)        # (image_type, error_msg)

    def __init__(self, url: str, image_type: str):
        super().__init__()
        self._url = url
        self._type = image_type

    def run(self):
        try:
            # Prvo proveri keš
            cached = _load_cached(self._url)
            if cached:
                self.finished.emit(self._type, cached)
                return

            req = Request(self._url)
            req.add_header("User-Agent", "WavePlayer/1.0")
            with urlopen(req, timeout=15) as resp:
                data = resp.read()

            # Sačuvaj u keš
            _save_cache(self._url, data)
            self.finished.emit(self._type, data)

        except Exception as e:
            self.error.emit(self._type, str(e))


# ═══════════════════════════════════════════
#  METADATA SEARCH WORKER
# ═══════════════════════════════════════════

class MetadataSearchWorker(QThread):
    """Background thread za TMDb pretragu."""
    finished = pyqtSignal(object)   # MediaMetadata ili None
    error = pyqtSignal(str)

    def __init__(self, plugin, file_path: str):
        super().__init__()
        self._plugin = plugin
        self._file_path = file_path

    def run(self):
        try:
            # Plugin koristi context.get_current_file() ali mi
            # želimo da pretražimo specifičan fajl, pa koristimo
            # direktno interne metode
            import os
            from plugins.tmdb_metadata import _parse_filename

            parsed = _parse_filename(os.path.basename(self._file_path))
            title = parsed["title"]
            if not title:
                self.finished.emit(None)
                return

            if parsed.get("season"):
                meta = self._plugin._search_tv(title, parsed)
            else:
                meta = self._plugin._search_movie(title, parsed.get("year", ""))

            self.finished.emit(meta)

        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════
#  TMDb METADATA DIALOG
# ═══════════════════════════════════════════

class TMDbMetadataDialog(QDialog):
    """Dijalog za prikaz metapodataka filma/serije sa TMDb."""

    def __init__(self, plugin, file_path: str, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._file_path = file_path
        self._metadata = None
        self._workers = []   # Drži referencu na aktivne thread-ove
        self._poster_pixmap: Optional[QPixmap] = None
        self._backdrop_pixmap: Optional[QPixmap] = None

        self.setWindowTitle("🎬 Metapodaci filma")
        self.setMinimumSize(700, 500)
        self.resize(780, 600)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._apply_style()
        self._setup_ui()
        self._start_search()

    # ═══════════════════════════════════════════
    #  STYLE
    # ═══════════════════════════════════════════

    def _apply_style(self):
        """Primeni temu na dijalog."""
        try:
            from ui.themes import get_theme
            if self.parent():
                from core.config import Config
                config = getattr(self.parent(), '_config', None)
                theme_name = config.get("ui.theme", "midnight_red") if config else "midnight_red"
            else:
                theme_name = "midnight_red"
            c = get_theme(theme_name)
        except Exception:
            # Fallback boje
            class FallbackTheme:
                bg_primary = "#0f0f0f"
                bg_secondary = "#141414"
                bg_tertiary = "#1e1e1e"
                text_primary = "#e0e0e0"
                text_secondary = "#999999"
                text_muted = "#666666"
                accent = "#e50914"
                accent_hover = "#f40612"
                border = "#1e1e1e"
                border_hover = "#333333"
            c = FallbackTheme()

        self._theme = c
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.bg_primary};
                color: {c.text_primary};
            }}
            QLabel {{
                color: {c.text_primary};
                background: transparent;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {c.bg_secondary};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {c.text_muted};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QPushButton {{
                background-color: {c.bg_tertiary};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {c.border_hover};
                border-color: {c.border_hover};
            }}
            QPushButton#accent_btn {{
                background-color: {c.accent};
                color: #ffffff;
                border: none;
                font-weight: bold;
            }}
            QPushButton#accent_btn:hover {{
                background-color: {c.accent_hover};
            }}
        """)

    # ═══════════════════════════════════════════
    #  UI SETUP
    # ═══════════════════════════════════════════

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Backdrop area ──
        self._backdrop_frame = QFrame()
        self._backdrop_frame.setFixedHeight(220)
        self._backdrop_frame.setStyleSheet("background: transparent;")
        main_layout.addWidget(self._backdrop_frame)

        # Backdrop label (slika)
        self._backdrop_label = QLabel(self._backdrop_frame)
        self._backdrop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._backdrop_label.setScaledContents(True)
        self._backdrop_label.setGeometry(0, 0, self.width(), 220)

        # Gradient overlay preko backdrop-a
        self._gradient_label = QLabel(self._backdrop_frame)
        self._gradient_label.setGeometry(0, 0, self.width(), 220)

        # ── Scroll area za sadržaj ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 0, 24, 20)
        content_layout.setSpacing(16)
        scroll.setWidget(content)

        # ── Poster + Info (horizontalni layout) ──
        top_row = QHBoxLayout()
        top_row.setSpacing(20)

        # Poster
        self._poster_label = QLabel()
        self._poster_label.setFixedSize(180, 270)
        self._poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._poster_label.setStyleSheet(f"""
            background-color: {self._theme.bg_tertiary};
            border-radius: 8px;
            border: 1px solid {self._theme.border};
            font-size: 48px;
            color: {self._theme.text_muted};
        """)
        self._poster_label.setText("🎬")
        top_row.addWidget(self._poster_label, alignment=Qt.AlignmentFlag.AlignTop)

        # Info kolona
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        self._title_label = QLabel("Učitavanje...")
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(f"""
            font-size: 22px;
            font-weight: bold;
            color: {self._theme.text_primary};
        """)
        info_layout.addWidget(self._title_label)

        self._year_genre_label = QLabel("")
        self._year_genre_label.setWordWrap(True)
        self._year_genre_label.setStyleSheet(f"""
            font-size: 13px;
            color: {self._theme.text_secondary};
        """)
        info_layout.addWidget(self._year_genre_label)

        self._rating_label = QLabel("")
        self._rating_label.setStyleSheet(f"""
            font-size: 15px;
            color: {self._theme.accent};
        """)
        info_layout.addWidget(self._rating_label)

        self._runtime_label = QLabel("")
        self._runtime_label.setStyleSheet(f"""
            font-size: 13px;
            color: {self._theme.text_secondary};
        """)
        info_layout.addWidget(self._runtime_label)

        # Dugmad
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._imdb_btn = QPushButton("🔗 IMDb")
        self._imdb_btn.setObjectName("accent_btn")
        self._imdb_btn.setVisible(False)
        self._imdb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._imdb_btn.clicked.connect(self._open_imdb)
        btn_row.addWidget(self._imdb_btn)

        self._tmdb_btn = QPushButton("🌐 TMDb")
        self._tmdb_btn.setVisible(False)
        self._tmdb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tmdb_btn.clicked.connect(self._open_tmdb)
        btn_row.addWidget(self._tmdb_btn)

        btn_row.addStretch()
        info_layout.addLayout(btn_row)

        info_layout.addStretch()
        top_row.addLayout(info_layout, stretch=1)
        content_layout.addLayout(top_row)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {self._theme.border}; max-height: 1px;")
        content_layout.addWidget(sep)

        # ── Opis ──
        self._overview_label = QLabel("")
        self._overview_label.setWordWrap(True)
        self._overview_label.setStyleSheet(f"""
            font-size: 13px;
            line-height: 1.5;
            color: {self._theme.text_primary};
        """)
        content_layout.addWidget(self._overview_label)

        # ── Režiser ──
        self._director_label = QLabel("")
        self._director_label.setStyleSheet(f"""
            font-size: 13px;
            color: {self._theme.text_secondary};
        """)
        content_layout.addWidget(self._director_label)

        # ── Glumci ──
        self._cast_label = QLabel("")
        self._cast_label.setWordWrap(True)
        self._cast_label.setStyleSheet(f"""
            font-size: 13px;
            color: {self._theme.text_secondary};
        """)
        content_layout.addWidget(self._cast_label)

        # ── Loading indicator ──
        self._loading_label = QLabel("⏳ Preuzimanje metapodataka...")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(f"""
            font-size: 14px;
            color: {self._theme.text_muted};
            padding: 40px;
        """)
        content_layout.addWidget(self._loading_label)

        content_layout.addStretch()

        # ── Bottom bar ──
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet(f"""
            background-color: {self._theme.bg_secondary};
            border-top: 1px solid {self._theme.border};
        """)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(16, 8, 16, 8)

        self._source_label = QLabel("TMDb — The Movie Database")
        self._source_label.setStyleSheet(f"""
            font-size: 11px;
            color: {self._theme.text_muted};
        """)
        bottom_layout.addWidget(self._source_label)

        bottom_layout.addStretch()

        close_btn = QPushButton("Zatvori")
        close_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(close_btn)

        main_layout.addWidget(bottom_frame)

    # ═══════════════════════════════════════════
    #  SEARCH
    # ═══════════════════════════════════════════

    def _start_search(self):
        """Pokreni pretragu metapodataka u background-u."""
        if not self._plugin._api_key:
            self._loading_label.setText(
                "⚠ TMDb API ključ nije podešen.\n\n"
                "Registruj se na themoviedb.org i unesi API ključ\n"
                "u Podešavanja → Plugini → TMDb."
            )
            return

        worker = MetadataSearchWorker(self._plugin, self._file_path)
        worker.finished.connect(self._on_metadata_received)
        worker.error.connect(self._on_search_error)
        self._workers.append(worker)
        worker.start()

    def _on_metadata_received(self, metadata):
        """Primljeni metapodaci sa TMDb-a."""
        self._loading_label.setVisible(False)

        if metadata is None:
            self._title_label.setText("Nije pronađeno")
            self._overview_label.setText(
                f"Nema rezultata za:\n{os.path.basename(self._file_path)}\n\n"
                "Pokušaj sa tačnim nazivom filma."
            )
            return

        self._metadata = metadata
        self._populate_ui(metadata)

        # Preuzmi slike
        if metadata.poster_url:
            self._start_image_download(metadata.poster_url, "poster")
        if metadata.backdrop_url:
            self._start_image_download(metadata.backdrop_url, "backdrop")

    def _on_search_error(self, error_msg: str):
        """Greška pri pretrazi."""
        self._loading_label.setText(f"⚠ Greška: {error_msg}")

    # ═══════════════════════════════════════════
    #  POPULATE UI
    # ═══════════════════════════════════════════

    def _populate_ui(self, meta):
        """Popuni UI sa metapodacima."""
        # Naslov
        title = meta.title
        if meta.year:
            title += f"  ({meta.year})"
        self._title_label.setText(title)

        # Godina + žanrovi
        parts = []
        if meta.genres:
            parts.append(" · ".join(meta.genres[:4]))
        if meta.media_type == "tv":
            parts.append("📺 Serija")
        else:
            parts.append("🎬 Film")
        self._year_genre_label.setText("   ".join(parts))

        # Ocena
        if meta.rating > 0:
            full_stars = int(meta.rating / 2)
            half = (meta.rating / 2) - full_stars >= 0.5
            empty = 5 - full_stars - (1 if half else 0)
            stars = "★" * full_stars
            if half:
                stars += "½"
            stars += "☆" * empty
            self._rating_label.setText(
                f"{stars}  {meta.rating:.1f} / 10   ({meta.vote_count:,} glasova)"
            )

        # Trajanje
        if meta.runtime > 0:
            hours = meta.runtime // 60
            mins = meta.runtime % 60
            if hours > 0:
                self._runtime_label.setText(f"⏱ {hours}h {mins}min")
            else:
                self._runtime_label.setText(f"⏱ {mins} min")

        # Opis
        if meta.overview:
            self._overview_label.setText(meta.overview)
        else:
            self._overview_label.setText("Opis nije dostupan.")

        # Režiser
        if meta.director:
            self._director_label.setText(f"🎬  Režija: {meta.director}")

        # Glumci
        if meta.cast:
            self._cast_label.setText(f"👥  Glumci: {', '.join(meta.cast)}")

        # Dugmad
        if meta.imdb_id:
            self._imdb_btn.setVisible(True)
        self._tmdb_btn.setVisible(True)

        # Epizoda info
        if meta.season and meta.episode:
            ep_text = f"Sezona {meta.season}, Epizoda {meta.episode}"
            if meta.episode_title:
                ep_text += f" — {meta.episode_title}"
            self._runtime_label.setText(
                self._runtime_label.text() + f"   |   {ep_text}"
                if self._runtime_label.text() else ep_text
            )

    # ═══════════════════════════════════════════
    #  IMAGE HANDLING
    # ═══════════════════════════════════════════

    def _start_image_download(self, url: str, image_type: str):
        """Preuzmi sliku u background thread-u."""
        worker = ImageDownloadWorker(url, image_type)
        worker.finished.connect(self._on_image_downloaded)
        worker.error.connect(self._on_image_error)
        self._workers.append(worker)
        worker.start()

    def _on_image_downloaded(self, image_type: str, data: bytes):
        """Slika preuzeta."""
        pixmap = QPixmap()
        pixmap.loadFromData(data)

        if pixmap.isNull():
            logger.warning(f"TMDb: nevažeća slika ({image_type})")
            return

        if image_type == "poster":
            self._poster_pixmap = pixmap
            scaled = pixmap.scaled(
                180, 270,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._poster_label.setPixmap(scaled)
            self._poster_label.setStyleSheet(f"""
                border-radius: 8px;
                border: 1px solid {self._theme.border};
            """)

        elif image_type == "backdrop":
            self._backdrop_pixmap = pixmap
            self._update_backdrop()

    def _on_image_error(self, image_type: str, error: str):
        logger.warning(f"TMDb: greška pri preuzimanju {image_type}: {error}")

    def _update_backdrop(self):
        """Ažuriraj backdrop sliku sa gradient overlay-em."""
        if not self._backdrop_pixmap:
            return

        w = self._backdrop_frame.width()
        h = self._backdrop_frame.height()

        if w <= 0 or h <= 0:
            return

        # Skaliraj backdrop
        scaled = self._backdrop_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        # Crop na centar ako je veći
        if scaled.width() > w or scaled.height() > h:
            x = (scaled.width() - w) // 2
            y = (scaled.height() - h) // 2
            scaled = scaled.copy(x, y, w, h)

        # Napravi gradient overlay
        result = QPixmap(scaled.size())
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        painter.drawPixmap(0, 0, scaled)

        # Tamni gradient odozgo i odozdo
        bg_color = QColor(self._theme.bg_primary)

        # Gradient odozgo (blagi)
        grad_top = QLinearGradient(0, 0, 0, h * 0.3)
        bg_top = QColor(bg_color)
        bg_top.setAlpha(160)
        grad_top.setColorAt(0, bg_top)
        bg_top.setAlpha(0)
        grad_top.setColorAt(1, bg_top)
        painter.fillRect(0, 0, w, int(h * 0.3), grad_top)

        # Gradient odozdo (jači)
        grad_bottom = QLinearGradient(0, h * 0.4, 0, h)
        bg_bot = QColor(bg_color)
        bg_bot.setAlpha(0)
        grad_bottom.setColorAt(0, bg_bot)
        bg_bot.setAlpha(240)
        grad_bottom.setColorAt(0.7, bg_bot)
        bg_bot.setAlpha(255)
        grad_bottom.setColorAt(1, bg_bot)
        painter.fillRect(0, int(h * 0.4), w, h - int(h * 0.4), grad_bottom)

        # Opšte zatamnjenje
        overlay = QColor(bg_color)
        overlay.setAlpha(80)
        painter.fillRect(0, 0, w, h, overlay)

        painter.end()

        self._backdrop_label.setPixmap(result)
        self._backdrop_label.setGeometry(0, 0, w, h)
        self._gradient_label.setGeometry(0, 0, w, h)

    # ═══════════════════════════════════════════
    #  LINKS
    # ═══════════════════════════════════════════

    def _open_imdb(self):
        """Otvori IMDb stranicu u browseru."""
        if self._metadata and self._metadata.imdb_id:
            url = f"https://www.imdb.com/title/{self._metadata.imdb_id}/"
            QDesktopServices.openUrl(QUrl(url))

    def _open_tmdb(self):
        """Otvori TMDb stranicu u browseru."""
        if not self._metadata:
            return
        media = self._metadata.media_type
        tmdb_id = self._metadata.tmdb_id
        url = f"https://www.themoviedb.org/{media}/{tmdb_id}"
        QDesktopServices.openUrl(QUrl(url))

    # ═══════════════════════════════════════════
    #  RESIZE
    # ═══════════════════════════════════════════

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Ažuriraj backdrop pri resize-u
        w = self._backdrop_frame.width()
        h = self._backdrop_frame.height()
        self._backdrop_label.setGeometry(0, 0, w, h)
        self._gradient_label.setGeometry(0, 0, w, h)
        if self._backdrop_pixmap:
            self._update_backdrop()

    # ═══════════════════════════════════════════
    #  CLEANUP
    # ═══════════════════════════════════════════

    def closeEvent(self, event):
        """Oslobodi worker thread-ove."""
        for w in self._workers:
            if w.isRunning():
                w.quit()
                w.wait(2000)
        self._workers.clear()
        super().closeEvent(event)

    def reject(self):
        """Override reject da očisti workere."""
        for w in self._workers:
            if w.isRunning():
                w.quit()
                w.wait(2000)
        self._workers.clear()
        super().reject()
