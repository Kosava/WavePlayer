"""Torrent status overlay widget.

Shows download progress, buffer status, peers, speed
overlaid on the video widget during torrent streaming.

PORTABILITY NOTES:
  - C++: QWidget with identical layout
  - Rust: similar widget with qt6-rs
"""

from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QTimer


class TorrentOverlay(QWidget):
    """Overlay za prikaz torrent statusa tokom streaming-a.

    Prikazuje se u donjem levom uglu video widgeta.
    Automatski se sakriva kad download završi.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self) -> None:
        self.setFixedSize(320, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Kontejner
        self._container = QFrame(self)
        self._container.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 185);
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

        c_layout = QVBoxLayout(self._container)
        c_layout.setContentsMargins(14, 10, 14, 10)
        c_layout.setSpacing(5)

        # Naslov
        self._title = QLabel("⏳ Buffering torrent...")
        self._title.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold; background: transparent;")
        c_layout.addWidget(self._title)

        # Buffer progress bar
        self._buffer_bar = QProgressBar()
        self._buffer_bar.setFixedHeight(6)
        self._buffer_bar.setRange(0, 1000)
        self._buffer_bar.setTextVisible(False)
        self._buffer_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 3px;
            }
        """)
        c_layout.addWidget(self._buffer_bar)

        # Status red 1: speed + progress
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._speed_label = QLabel("↓ 0 KB/s")
        self._speed_label.setStyleSheet("color: #10b981; font-size: 11px; background: transparent; font-family: 'Consolas', monospace;")
        self._progress_label = QLabel("0%")
        self._progress_label.setStyleSheet("color: #999999; font-size: 11px; background: transparent; font-family: 'Consolas', monospace;")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row1.addWidget(self._speed_label)
        row1.addStretch()
        row1.addWidget(self._progress_label)
        c_layout.addLayout(row1)

        # Status red 2: peers + upload + ETA
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self._peers_label = QLabel("👥 0")
        self._peers_label.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        self._upload_label = QLabel("↑ 0 KB/s")
        self._upload_label.setStyleSheet("color: #666666; font-size: 10px; background: transparent; font-family: 'Consolas', monospace;")
        self._eta_label = QLabel("")
        self._eta_label.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        self._eta_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row2.addWidget(self._peers_label)
        row2.addWidget(self._upload_label)
        row2.addStretch()
        row2.addWidget(self._eta_label)
        c_layout.addLayout(row2)

        layout.addWidget(self._container)

    def update_status(self, status) -> None:
        """Ažuriraj prikaz iz TorrentStatus objekta."""
        from core.torrent_engine import TorrentState, TorrentEngine

        # Naslov prema stanju
        state_text = {
            TorrentState.LOADING_METADATA: "🔍 Učitavanje metapodataka...",
            TorrentState.DOWNLOADING: "⬇ Preuzimanje...",
            TorrentState.BUFFERING: f"⏳ Buffering ({status.buffer_progress * 100:.0f}%)",
            TorrentState.READY: "✅ Spreman za reprodukciju",
            TorrentState.STREAMING: "▶ Streaming...",
            TorrentState.SEEDING: "⬆ Seeding",
            TorrentState.PAUSED: "⏸ Pauzirano",
            TorrentState.ERROR: f"❌ {status.error_message[:40]}",
        }
        self._title.setText(state_text.get(status.state, ""))

        # Buffer bar
        self._buffer_bar.setValue(int(status.buffer_progress * 1000))

        # Boja buffer bara prema stanju
        if status.buffer_progress >= 1.0:
            chunk_color = "#10b981"  # zelena = ready
        elif status.buffer_progress > 0.5:
            chunk_color = "#f59e0b"  # žuta = pola
        else:
            chunk_color = "#e50914"  # crvena = malo
        self._buffer_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255, 255, 255, 0.12);
                border-radius: 3px; border: none;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 3px;
            }}
        """)

        # Speed
        self._speed_label.setText(f"↓ {TorrentEngine.format_speed(status.download_rate)}")
        self._upload_label.setText(f"↑ {TorrentEngine.format_speed(status.upload_rate)}")

        # Progress
        total = TorrentEngine.format_size(status.total_size) if status.total_size > 0 else "?"
        done = TorrentEngine.format_size(status.downloaded)
        self._progress_label.setText(f"{done} / {total}  ({status.progress * 100:.1f}%)")

        # Peers
        self._peers_label.setText(f"👥 {status.num_peers} ({status.num_seeds} seeds)")

        # ETA
        if status.eta_seconds > 0:
            mins = status.eta_seconds // 60
            secs = status.eta_seconds % 60
            if mins > 60:
                hours = mins // 60
                mins = mins % 60
                self._eta_label.setText(f"ETA {hours}h {mins}m")
            elif mins > 0:
                self._eta_label.setText(f"ETA {mins}m {secs}s")
            else:
                self._eta_label.setText(f"ETA {secs}s")
        else:
            self._eta_label.setText("")

        self.setVisible(True)

    def hide_overlay(self) -> None:
        self.setVisible(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self) -> None:
        """Pozicioniraj u donji levi ugao parent widgeta."""
        parent = self.parentWidget()
        if parent:
            x = 12
            y = parent.height() - self.height() - 12
            self.move(x, y)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reposition()
