"""Custom frameless title bar widget.

Provides window drag, minimize, maximize, close functionality.
Design matches the C++ reference (main_window.cpp).

PORTABILITY NOTES:
  - C++: QFrame subclass with identical layout
  - Rust: similar widget tree with qt6-rs
"""

from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent


class TitleBar(QFrame):
    """Custom title bar za frameless prozor.

    Pruža drag-to-move, minimize, maximize/restore, close.
    """

    TITLE_HEIGHT: int = 40

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._parent_window: QWidget = parent
        self._drag_position: QPoint = QPoint()
        self._is_dragging: bool = False

        self.setObjectName("titleBar")
        self.setFixedHeight(self.TITLE_HEIGHT)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Postavi UI elemente."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(0)

        # Ikonica aplikacije (placeholder)
        self._icon_label = QLabel("🎬", self)
        self._icon_label.setObjectName("titleIcon")
        self._icon_label.setFixedWidth(24)

        # Naslov
        self._title_label = QLabel("WavePlayer", self)
        self._title_label.setObjectName("titleLabel")

        # Dugmad za kontrolu prozora
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(2)

        self._minimize_btn = QPushButton("─", self)
        self._minimize_btn.setObjectName("windowBtn")
        self._minimize_btn.setFixedSize(40, 30)
        self._minimize_btn.setToolTip("Minimize")

        self._maximize_btn = QPushButton("□", self)
        self._maximize_btn.setObjectName("windowBtn")
        self._maximize_btn.setFixedSize(40, 30)
        self._maximize_btn.setToolTip("Maximize")

        self._close_btn = QPushButton("✕", self)
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setFixedSize(40, 30)
        self._close_btn.setToolTip("Close")

        btn_layout.addWidget(self._minimize_btn)
        btn_layout.addWidget(self._maximize_btn)
        btn_layout.addWidget(self._close_btn)

        layout.addWidget(self._icon_label)
        layout.addSpacing(8)
        layout.addWidget(self._title_label)
        layout.addStretch()
        layout.addLayout(btn_layout)

        # Konekcije
        self._minimize_btn.clicked.connect(self._on_minimize)
        self._maximize_btn.clicked.connect(self._on_maximize)
        self._close_btn.clicked.connect(self._on_close)

    def set_title(self, title: str) -> None:
        """Postavi naslov u title bar."""
        self._title_label.setText(title)

    def set_maximized_icon(self, is_maximized: bool) -> None:
        """Ažuriraj ikonu maximize dugmeta."""
        self._maximize_btn.setText("❐" if is_maximized else "□")
        tip = "Restore" if is_maximized else "Maximize"
        self._maximize_btn.setToolTip(tip)

    # --- Window kontrole ---

    def _on_minimize(self) -> None:
        """Minimiziraj prozor."""
        self._parent_window.showMinimized()

    def _on_maximize(self) -> None:
        """Maksimiziraj ili vrati prozor."""
        if self._parent_window.isMaximized():
            self._parent_window.showNormal()
            self.set_maximized_icon(False)
        else:
            self._parent_window.showMaximized()
            self.set_maximized_icon(True)

    def _on_close(self) -> None:
        """Zatvori prozor."""
        self._parent_window.close()

    # --- Drag za pomeranje prozora ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Započni drag prozora."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_position = (
                event.globalPosition().toPoint()
                - self._parent_window.frameGeometry().topLeft()
            )
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Pomeri prozor tokom drag-a."""
        if self._is_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            # Ako je maksimizovan, vrati u normalnu veličinu pre pomeranja
            if self._parent_window.isMaximized():
                self._parent_window.showNormal()
                self.set_maximized_icon(False)
                # Prilagodi drag poziciju
                self._drag_position = QPoint(
                    self._parent_window.width() // 2,
                    self.TITLE_HEIGHT // 2
                )
            new_pos = event.globalPosition().toPoint() - self._drag_position
            self._parent_window.move(new_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Završi drag."""
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Dupli klik za maximize/restore."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_maximize()
        super().mouseDoubleClickEvent(event)
