"""Video rendering widget.

Container widget that provides a window ID for mpv to render into.
Handles drag & drop for both media files and subtitle files.

IMPORTANT: mpv with wid= embeds its own X11 window inside this widget.
That child window can intercept mouse events. We use input_cursor=False
in mpv to prevent this, but as a fallback we also place a transparent
overlay QWidget on top to catch all mouse/keyboard events.

PORTABILITY NOTES:
  - C++: QWidget with winId() passed to mpv
  - Rust: similar pattern with qt6-rs widget
"""

import os

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QMouseEvent, QDragEnterEvent, QDropEvent

from .welcome_widget import WelcomeWidget

# Subtitle ekstenzije za prepoznavanje pri drag & drop
SUBTITLE_EXTENSIONS = {
    ".srt", ".ass", ".ssa", ".sub", ".vtt", ".idx", ".sup", ".smi",
}

MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".flac", ".ogg", ".wav", ".m4a", ".m4v", ".ts",
    ".mpg", ".mpeg", ".3gp", ".ogv", ".opus", ".aac", ".wma",
}


def _get_ext(path: str) -> str:
    """Vrati ekstenziju fajla (lowercase, sa tačkom)."""
    _, ext = os.path.splitext(path)
    return ext.lower()


class MouseOverlay(QWidget):
    """Transparentan widget koji hvata mouse evente iznad mpv-a.

    Sedi iznad mpv native window-a ali ISPOD OSD overlay-a.
    Samo hvata desni klik i dupli klik.
    Levi klik nije bindovan — ne radi ništa.
    """

    double_clicked = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Za razlikovanje single vs double click na desni taster ne treba
        # ali za levi: ignorišemo single, hvatamo samo double
        self._dbl_pending = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(event.pos())
            event.accept()
            return
        # Levi klik — ne radimo ništa (samo propuštamo dalje)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        event.accept()

    def paintEvent(self, event) -> None:
        # Potpuno transparentan — ne crta ništa
        pass


class VideoWidget(QFrame):
    """Widget za prikaz videa.

    Pruža window ID koji mpv koristi za renderovanje.
    Prikazuje WelcomeWidget kada nema videa (zamenjuje stari drop zone).
    Koristi MouseOverlay za pouzdano hvatanje klikova.
    """

    # Signali
    file_dropped = pyqtSignal(str)
    subtitle_dropped = pyqtSignal(str)
    double_clicked = pyqtSignal()
    right_clicked = pyqtSignal(object)     # QPoint — desni klik

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("videoWidget")
        self.setAcceptDrops(True)

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(320, 240)

        self._setup_ui()
        self._show_drop_zone()

    def _setup_ui(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Welcome screen (zamenjuje stari QLabel drop zone)
        self._welcome = WelcomeWidget(self)
        self._layout.addWidget(self._welcome)

        # Mouse overlay — hvata klikove iznad mpv native window-a
        # Kreiran OVDE, ali OSD overlay (kreiran u main_window)
        # će biti raise()-ovan iznad njega u raise_osd_overlay()
        self._mouse_overlay = MouseOverlay(self)
        self._mouse_overlay.double_clicked.connect(self.double_clicked.emit)
        self._mouse_overlay.right_clicked.connect(self.right_clicked.emit)

    @property
    def welcome(self) -> WelcomeWidget:
        """Pristup welcome widgetu za povezivanje signala iz MainWindow."""
        return self._welcome

    def raise_osd_above_mouse(self, osd_widget) -> None:
        """Pozovi iz main_window nakon kreiranja OSD-a.

        Osigurava da je OSD iznad mouse overlay-a za vidljivost,
        ali OSD ima WA_TransparentForMouseEvents pa propušta klikove.
        """
        osd_widget.raise_()

    def get_window_id(self) -> int:
        return int(self.winId())

    def _show_drop_zone(self) -> None:
        self._welcome.setVisible(True)
        self._mouse_overlay.setVisible(False)  # Ne blokiraj welcome klikove

    def hide_drop_zone(self) -> None:
        self._welcome.setVisible(False)
        self._mouse_overlay.setVisible(True)   # Aktiviraj za mpv window
        self._mouse_overlay.raise_()

    def show_drop_zone(self) -> None:
        self._welcome.setVisible(True)
        self._mouse_overlay.setVisible(False)  # Oslobodi welcome evente

    def resizeEvent(self, event) -> None:
        """Drži mouse overlay iste veličine kao video widget."""
        super().resizeEvent(event)
        self._mouse_overlay.setGeometry(0, 0, self.width(), self.height())
        if not self._welcome.isVisible():
            self._mouse_overlay.raise_()

    # --- Drag & Drop ---

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime and mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        pass

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        if mime and mime.hasUrls():
            urls = mime.urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path:
                    ext = _get_ext(file_path)
                    if ext in SUBTITLE_EXTENSIONS:
                        # Ovo je titl fajl — emituj subtitle signal
                        self.subtitle_dropped.emit(file_path)
                    else:
                        # Media fajl
                        self.file_dropped.emit(file_path)
                    event.acceptProposedAction()
