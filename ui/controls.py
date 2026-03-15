"""Playback control bar widget.

Bottom bar with progress slider, play/pause, volume, settings, etc.
Progress slider podržava prikaz buffer napretka za torrent streaming.

PORTABILITY NOTES:
  - C++: QFrame with identical widget tree
  - Rust: similar layout with qt6-rs
  - All signals map to Qt signals/slots in C++
"""

from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
    QStyleOptionSlider,
    QStyle,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QMouseEvent, QPainter, QColor, QLinearGradient, QPen


class BufferedProgressSlider(QSlider):
    """Custom progress slider sa tri vizuelne zone:

    1. Groove (pozadina)     — tamna boja (slider_groove)
    2. Buffer zona           — svetlija boja, prikazuje koliko je torrent
                               buffered unapred (buffer_color)
    3. Played zona           — akcent gradient, prikazuje trenutnu poziciju
                               (progress_gradient_start → progress_gradient_end)

    Buffer zona se prikazuje samo kad je buffer_ratio > 0.
    Klik-to-seek radi kao i pre.
    """

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self._buffer_ratio: float = 0.0  # 0.0 – 1.0

        # Boje — postavljaju se iz styles.py
        self._groove_color = QColor("#2a2a2a")
        self._buffer_color = QColor(255, 255, 255, 38)  # rgba(255,255,255,0.15)
        self._gradient_start = QColor("#e50914")
        self._gradient_end = QColor("#ff4444")
        self._handle_color = QColor("#ffffff")
        self._handle_border_color = QColor("#e50914")

    # --- Buffer API ---

    def set_buffer_ratio(self, ratio: float) -> None:
        """Postavi buffer napredak (0.0 – 1.0). 0 = nema buffer prikaza."""
        self._buffer_ratio = max(0.0, min(1.0, ratio))
        self.update()

    def buffer_ratio(self) -> float:
        return self._buffer_ratio

    # --- Boje API ---

    def set_colors(
        self,
        groove: str = "",
        buffer: str = "",
        grad_start: str = "",
        grad_end: str = "",
        handle: str = "",
        handle_border: str = "",
    ) -> None:
        """Postavi boje iz teme."""
        if groove:
            self._groove_color = QColor(groove)
        if buffer:
            self._buffer_color = _parse_color(buffer)
        if grad_start:
            self._gradient_start = QColor(grad_start)
        if grad_end:
            self._gradient_end = QColor(grad_end)
        if handle:
            self._handle_color = QColor(handle)
        if handle_border:
            self._handle_border_color = QColor(handle_border)
        self.update()

    # --- Click-to-seek ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt,
                QStyle.SubControl.SC_SliderGroove, self
            )
            if self.orientation() == Qt.Orientation.Horizontal:
                pos = event.position().x()
                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    int(pos - groove.x()), groove.width()
                )
            else:
                pos = event.position().y()
                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    int(pos - groove.y()), groove.height(),
                    upsideDown=True
                )
            self.setValue(val)
            self.sliderMoved.emit(val)
            event.accept()
        super().mousePressEvent(event)

    # --- Custom Paint ---

    def paintEvent(self, event) -> None:
        """Crta groove → buffer → played → handle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Dimenzije groove-a
        groove_h = 5
        groove_y = (h - groove_h) // 2
        groove_r = groove_h // 2  # border-radius

        # Handle dimenzije
        handle_w = 14
        handle_h = 14
        handle_r = handle_w // 2

        # Usable area (bez pola handle-a na krajevima)
        margin = handle_w // 2
        usable_w = w - handle_w

        # Pozicije kao ratio
        val_range = self.maximum() - self.minimum()
        if val_range > 0:
            played_ratio = (self.value() - self.minimum()) / val_range
        else:
            played_ratio = 0.0

        played_x = margin + int(usable_w * played_ratio)
        buffer_x = margin + int(usable_w * self._buffer_ratio)

        # 1) Groove pozadina (cela traka)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._groove_color)
        painter.drawRoundedRect(
            margin, groove_y, usable_w, groove_h, groove_r, groove_r
        )

        # 2) Buffer zona (ako postoji)
        if self._buffer_ratio > 0.0 and buffer_x > margin:
            painter.setBrush(self._buffer_color)
            buf_w = min(buffer_x - margin, usable_w)
            painter.drawRoundedRect(
                margin, groove_y, buf_w, groove_h, groove_r, groove_r
            )

        # 3) Played zona (gradient)
        if played_ratio > 0.0:
            grad = QLinearGradient(margin, 0, played_x, 0)
            grad.setColorAt(0.0, self._gradient_start)
            grad.setColorAt(1.0, self._gradient_end)
            painter.setBrush(grad)
            play_w = max(0, played_x - margin)
            painter.drawRoundedRect(
                margin, groove_y, play_w, groove_h, groove_r, groove_r
            )

        # 4) Handle
        handle_cx = played_x
        handle_cy = h // 2
        handle_rect = QRect(
            handle_cx - handle_r, handle_cy - handle_r,
            handle_w, handle_h
        )

        # Handle border
        painter.setPen(QPen(self._handle_border_color, 2))
        painter.setBrush(self._handle_color)
        painter.drawEllipse(handle_rect)

        painter.end()


def _parse_color(s: str) -> QColor:
    """Parse boju iz stringa — podržava hex i rgba()."""
    s = s.strip()
    if s.startswith("rgba("):
        # rgba(255, 255, 255, 0.15)
        inner = s[5:].rstrip(")")
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 4:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            a = float(parts[3])
            return QColor(r, g, b, int(a * 255))
    return QColor(s)


class ControlBar(QFrame):
    """Donja kontrolna traka za reprodukciju."""

    CONTROL_HEIGHT: int = 100

    # --- Signali ---
    play_pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)
    volume_changed = pyqtSignal(int)
    mute_toggled = pyqtSignal(bool)
    speed_changed = pyqtSignal(float)
    fullscreen_clicked = pyqtSignal()
    playlist_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()          # NOVO: settings signal

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlBar")
        self.setFixedHeight(self.CONTROL_HEIGHT)

        self._duration: float = 0.0
        self._is_seeking: bool = False
        self._current_speed_index: int = 2
        self._speed_values: list[float] = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 8, 20, 8)
        main_layout.setSpacing(6)

        # Red 1: Progress bar
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)

        self._time_label = QLabel("0:00", self)
        self._time_label.setObjectName("timeLabel")
        self._time_label.setFixedWidth(55)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._progress_slider = BufferedProgressSlider(Qt.Orientation.Horizontal, self)
        self._progress_slider.setObjectName("progressSlider")
        self._progress_slider.setRange(0, 1000)
        self._progress_slider.setValue(0)

        self._duration_label = QLabel("0:00", self)
        self._duration_label.setObjectName("durationLabel")
        self._duration_label.setFixedWidth(55)

        progress_layout.addWidget(self._time_label)
        progress_layout.addWidget(self._progress_slider, 1)
        progress_layout.addWidget(self._duration_label)

        # Red 2: Dugmad
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        # Leva grupa: playback
        left_group = QHBoxLayout()
        left_group.setSpacing(6)

        self._prev_btn = self._make_btn("⏮", "controlBtn", 34, 34, "Previous")
        self._play_pause_btn = self._make_btn("▶", "playPauseBtn", 44, 44, "Play")
        self._stop_btn = self._make_btn("⏹", "controlBtn", 34, 34, "Stop")
        self._next_btn = self._make_btn("⏭", "controlBtn", 34, 34, "Next")

        left_group.addWidget(self._prev_btn)
        left_group.addWidget(self._play_pause_btn)
        left_group.addWidget(self._stop_btn)
        left_group.addWidget(self._next_btn)

        # Srednja grupa: volume
        center_group = QHBoxLayout()
        center_group.setSpacing(6)

        self._mute_btn = self._make_btn("🔊", "controlBtn", 32, 32, "Mute")
        self._mute_btn.setCheckable(True)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._volume_slider.setObjectName("volumeSlider")
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_slider.setFixedWidth(100)

        center_group.addWidget(self._mute_btn)
        center_group.addWidget(self._volume_slider)

        # Desna grupa: extra + settings
        right_group = QHBoxLayout()
        right_group.setSpacing(6)

        self._speed_btn = QPushButton("1.0x", self)
        self._speed_btn.setObjectName("textBtn")
        self._speed_btn.setFixedSize(50, 30)
        self._speed_btn.setToolTip("Playback speed")

        self._playlist_btn = self._make_btn("☰", "controlBtn", 32, 32, "Playlist")
        self._playlist_btn.setCheckable(True)

        self._settings_btn = self._make_btn("⚙", "controlBtn", 32, 32, "Settings (Ctrl+,)")

        self._fullscreen_btn = self._make_btn("⛶", "controlBtn", 32, 32, "Fullscreen")

        right_group.addWidget(self._speed_btn)
        right_group.addWidget(self._playlist_btn)
        right_group.addWidget(self._settings_btn)
        right_group.addWidget(self._fullscreen_btn)

        buttons_layout.addLayout(left_group)
        buttons_layout.addStretch()
        buttons_layout.addLayout(center_group)
        buttons_layout.addStretch()
        buttons_layout.addLayout(right_group)

        main_layout.addLayout(progress_layout)
        main_layout.addLayout(buttons_layout)

    def _make_btn(self, text: str, name: str, w: int, h: int, tooltip: str) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName(name)
        btn.setFixedSize(w, h)
        btn.setToolTip(tooltip)
        return btn

    def _connect_signals(self) -> None:
        self._play_pause_btn.clicked.connect(self.play_pause_clicked.emit)
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        self._next_btn.clicked.connect(self.next_clicked.emit)
        self._prev_btn.clicked.connect(self.prev_clicked.emit)
        self._fullscreen_btn.clicked.connect(self.fullscreen_clicked.emit)
        self._playlist_btn.clicked.connect(self.playlist_clicked.emit)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)

        self._volume_slider.valueChanged.connect(self.volume_changed.emit)
        self._mute_btn.toggled.connect(self._on_mute_toggled)

        self._progress_slider.sliderPressed.connect(self._on_seek_start)
        self._progress_slider.sliderReleased.connect(self._on_seek_end)
        self._progress_slider.sliderMoved.connect(self._on_slider_moved)

        self._speed_btn.clicked.connect(self._on_speed_clicked)

    # --- Javne metode ---

    def set_playing(self, is_playing: bool) -> None:
        self._play_pause_btn.setText("⏸" if is_playing else "▶")
        self._play_pause_btn.setToolTip("Pause" if is_playing else "Play")

    def set_duration(self, duration: float) -> None:
        self._duration = duration
        self._duration_label.setText(self._format_time(duration))

    def set_position(self, position: float) -> None:
        if not self._is_seeking and self._duration > 0:
            value = int((position / self._duration) * 1000)
            self._progress_slider.setValue(value)
            self._time_label.setText(self._format_time(position))

    def set_volume(self, volume: int) -> None:
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(volume)
        self._volume_slider.blockSignals(False)

    def set_muted(self, muted: bool) -> None:
        self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(muted)
        self._mute_btn.blockSignals(False)
        self._mute_btn.setText("🔇" if muted else "🔊")

    def set_fullscreen_icon(self, is_fullscreen: bool) -> None:
        self._fullscreen_btn.setText("⛶" if not is_fullscreen else "🗗")

    def set_playlist_checked(self, checked: bool) -> None:
        self._playlist_btn.blockSignals(True)
        self._playlist_btn.setChecked(checked)
        self._playlist_btn.blockSignals(False)

    def reset(self) -> None:
        self._progress_slider.setValue(0)
        self._progress_slider.set_buffer_ratio(0.0)
        self._time_label.setText("0:00")
        self._duration_label.setText("0:00")
        self._duration = 0.0
        self.set_playing(False)

    def set_buffer_ratio(self, ratio: float) -> None:
        """Postavi buffer napredak (0.0 – 1.0) za torrent streaming."""
        self._progress_slider.set_buffer_ratio(ratio)

    def set_progress_colors(
        self,
        groove: str = "",
        buffer: str = "",
        grad_start: str = "",
        grad_end: str = "",
        handle: str = "",
        handle_border: str = "",
    ) -> None:
        """Postavi boje progress slidera iz teme."""
        self._progress_slider.set_colors(
            groove=groove,
            buffer=buffer,
            grad_start=grad_start,
            grad_end=grad_end,
            handle=handle,
            handle_border=handle_border,
        )

    # --- Privatne metode ---

    def _on_seek_start(self) -> None:
        self._is_seeking = True

    def _on_seek_end(self) -> None:
        self._is_seeking = False
        if self._duration > 0:
            position = (self._progress_slider.value() / 1000.0) * self._duration
            self.seek_requested.emit(position)

    def _on_slider_moved(self, value: int) -> None:
        if self._duration > 0:
            position = (value / 1000.0) * self._duration
            self._time_label.setText(self._format_time(position))

    def _on_mute_toggled(self, checked: bool) -> None:
        self._mute_btn.setText("🔇" if checked else "🔊")
        self.mute_toggled.emit(checked)

    def _on_speed_clicked(self) -> None:
        self._current_speed_index = (
            (self._current_speed_index + 1) % len(self._speed_values)
        )
        speed = self._speed_values[self._current_speed_index]
        self._speed_btn.setText(f"{speed}x")
        self.speed_changed.emit(speed)

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = int(max(0, seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"