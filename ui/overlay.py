"""On-screen display overlay — mpv native OSD.

Koristi mpv-ov sopstveni OSD sistem (show-text i osd-overlay komande)
umesto Qt widgeta. Ovo se renderuje UNUTAR mpv render pipeline-a,
što znači da je UVEK vidljivo iznad videa — bez obzira na X11/Wayland
stacking order probleme sa native window embedding-om.

ZAŠTO: mpv sa wid= kreira native X11 prozor koji pokriva sve Qt
child widgete. Ni Qt z-order (raise_()), ni top-level Tool window
ne mogu pouzdano da budu iznad mpv GPU output-a na svim kompozitorima.
mpv-ov sopstveni OSD je jedino rešenje koje radi 100%.

PORTABILITY NOTES:
  - C++: mpv_command(ctx, "show-text", ...) ili osd-overlay
  - Rust: mpv crate command("show-text", ...)
"""

import logging
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

from .themes import OsdTheme, get_osd_theme

if TYPE_CHECKING:
    from .mpv_engine import MpvEngine

logger = logging.getLogger(__name__)


class OverlayType(Enum):
    """Tip overlay poruke."""
    VOLUME = auto()
    SEEK = auto()
    PLAY_PAUSE = auto()
    TITLE = auto()
    SPEED = auto()
    BUFFERING = auto()


class OsdOverlay:
    """On-screen display — koristi mpv native OSD.

    Delegira prikaz teksta na mpv show-text komandu i
    ASS overlay za kompleksnije prikaze (info panel).
    """

    DEFAULT_DISPLAY_MS: int = 1500
    OSD_INFO_ID: int = 60  # overlay ID za info panel

    def __init__(self, engine: "MpvEngine") -> None:
        self._engine = engine
        self._osd_enabled: bool = True
        self._osd_theme: OsdTheme = get_osd_theme("minimal")
        logger.debug("OsdOverlay.__init__ (mpv native OSD)")

    def set_enabled(self, enabled: bool) -> None:
        self._osd_enabled = enabled
        if not enabled:
            self._remove_info_overlay()

    def set_osd_theme(self, theme_name: str) -> None:
        """Čuva temu za referencu (mpv koristi svoj stil)."""
        self._osd_theme = get_osd_theme(theme_name)

    # --- Javne metode za prikaz ---

    def show_volume(self, volume: int, muted: bool = False) -> None:
        if not self._osd_enabled:
            return
        if muted:
            text = "🔇 Muted"
        elif volume == 0:
            text = "🔇 0%"
        elif volume < 33:
            text = f"🔈 {volume}%"
        elif volume < 66:
            text = f"🔉 {volume}%"
        else:
            text = f"🔊 {volume}%"

        # Progress bar iz karaktera
        filled = int(volume / 100 * 20)
        bar = "█" * filled + "░" * (20 - filled)
        self._engine.show_text(f"{text}\n{bar}", self.DEFAULT_DISPLAY_MS)

    def show_seek(self, position: float, duration: float) -> None:
        if not self._osd_enabled:
            return
        time_str = self._format_time(position)
        total_str = self._format_time(duration)
        progress = position / duration if duration > 0 else 0.0
        filled = int(progress * 30)
        bar = "█" * filled + "░" * (30 - filled)
        self._engine.show_text(
            f"⏩ {time_str} / {total_str}\n{bar}",
            self.DEFAULT_DISPLAY_MS,
        )

    def show_play(self) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text("▶ Play", 800)

    def show_pause(self) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text("⏸ Paused", 800)

    def show_title(self, title: str) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text(f"🎬 {title}", 3000)

    def show_speed(self, speed: float) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text(f"⚡ {speed}x", self.DEFAULT_DISPLAY_MS)

    def show_buffering(self) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text("⏳ Buffering...", self.DEFAULT_DISPLAY_MS)

    def show_info(self, info_text: str) -> None:
        """Prikaži detaljne info koristeći mpv ASS overlay za lepši izgled."""
        if not self._osd_enabled:
            return

        # ASS formatiranje: centriran tekst sa poluprozirnom pozadinom
        lines = info_text.split("\n")
        ass_lines = []
        for i, line in enumerate(lines):
            if i == 0:
                # Naslov (veći, bold)
                ass_lines.append(
                    r"{\an5\fs28\b1\bord2\shad1\1c&HFFFFFF&\3c&H000000&}"
                    + line.replace("\\", "\\\\")
                )
            else:
                ass_lines.append(
                    r"{\an5\fs22\b0\bord1.5\shad1\1c&HDDDDDD&\3c&H000000&}"
                    + line.replace("\\", "\\\\")
                )

        ass_text = r"\N".join(ass_lines)
        self._engine.osd_overlay(self.OSD_INFO_ID, ass_text)

        # Auto-hide posle 5 sekundi
        try:
            from PyQt6.QtCore import QTimer
            # Koristi single-shot timer za uklanjanje
            if not hasattr(self, '_info_timer'):
                self._info_timer = QTimer()
                self._info_timer.setSingleShot(True)
                self._info_timer.timeout.connect(self._remove_info_overlay)
            self._info_timer.stop()
            self._info_timer.start(5000)
        except Exception:
            pass  # Ako nema Qt, overlay ostaje dok se ne pozove remove

    def _remove_info_overlay(self) -> None:
        """Ukloni info overlay."""
        self._engine.osd_overlay_remove(self.OSD_INFO_ID)

    def close(self) -> None:
        """Cleanup — pozovi pre zatvaranja."""
        self._remove_info_overlay()

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = int(max(0, seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"