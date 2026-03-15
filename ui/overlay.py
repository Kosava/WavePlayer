"""On-screen display overlay — mpv native OSD sa animacijama i stilizacijom.

Faza 1 (ispravljeno):
  - Fade in/out animacije za sve overlay-e (60fps)
  - Redizajniran volume sa fiksnom pozicijom (ne pomerajući se)
  - Info panel gore na sredini (kao title notification)
  - Bolje centriranje i alignment
"""

import logging
import re
import time
from enum import Enum, auto
from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtCore import QTimer

from .themes import ThemeColors, get_theme

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
    INFO = auto()


# ═══════════════════════════════════════════════════════════════════════════════
#  ANIMACIJE — Easing functions
# ═══════════════════════════════════════════════════════════════════════════════

def ease_out_cubic(t: float) -> float:
    """Smooth ease out — brzo počinje, usporava na kraju."""
    return 1 - pow(1 - t, 3)

def ease_out_expo(t: float) -> float:
    """Exponential ease out — za brze fade-ove."""
    return 1 - pow(2, -10 * t) if t < 1 else 1


class Animation:
    """Jednostavna animacija sa easing-om."""
    
    def __init__(self, start_val: float, end_val: float, 
                 duration: float, easing: Callable[[float], float] = ease_out_cubic):
        self.start_val = start_val
        self.end_val = end_val
        self.duration = duration
        self.easing = easing
        self.start_time = time.time()
    
    def is_done(self) -> bool:
        return (time.time() - self.start_time) >= self.duration
    
    def value(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed >= self.duration:
            return self.end_val
        t = elapsed / self.duration
        eased = self.easing(t)
        return self.start_val + (self.end_val - self.start_val) * eased


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITY — Boje i formatiranje
# ═══════════════════════════════════════════════════════════════════════════════

def _hex_to_ass_color(hex_color: str) -> str:
    """Konvertuj hex boju (#RRGGBB) u ASS format (&HBBGGRR&)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) == 8:
        h = h[2:]
    if len(h) != 6:
        return "&HFFFFFF&"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{b}{g}{r}&"


def _parse_rgba(rgba_str: str) -> tuple:
    """Parsira 'rgba(r, g, b, a)' → (r, g, b, alpha_float_0_to_1)."""
    m = re.match(
        r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)',
        rgba_str
    )
    if not m:
        return (255, 255, 255, 1.0)
    r_val = int(m.group(1))
    g_val = int(m.group(2))
    b_val = int(m.group(3))
    a_val = float(m.group(4)) if m.group(4) else 1.0
    if a_val > 1.0:
        a_val = a_val / 255.0
    return (r_val, g_val, b_val, a_val)


def _color_to_mpv_osd(color_str: str) -> str:
    """Konvertuj hex ili rgba boju u mpv OSD format (#AARRGGBB)."""
    color_str = color_str.strip()
    if color_str.startswith("rgba") or color_str.startswith("rgb"):
        r, g, b, a = _parse_rgba(color_str)
        aa = int(a * 255)
        return f"#{aa:02X}{r:02X}{g:02X}{b:02X}"
    else:
        h = color_str.lstrip("#")
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        if len(h) == 6:
            return f"#FF{h.upper()}"
        if len(h) == 8:
            return f"#{h.upper()}"
        return "#FFFFFFFF"


def _rgba_to_ass(color_str: str) -> tuple:
    """Konvertuj boju u (ASS color &HBBGGRR&, ASS alpha &HAA&)."""
    color_str = color_str.strip()
    if color_str.startswith("rgba") or color_str.startswith("rgb"):
        r, g, b, a = _parse_rgba(color_str)
        ass_color = f"&H{b:02X}{g:02X}{r:02X}&"
        ass_alpha = f"&H{int((1.0 - a) * 255):02X}&"
        return ass_color, ass_alpha
    else:
        return _hex_to_ass_color(color_str), "&H00&"


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN CLASS — OsdOverlay sa animacijama
# ═══════════════════════════════════════════════════════════════════════════════

class OsdOverlay:
    """On-screen display — hibridni mpv OSD sa animacijama."""
    
    # Overlay ID-jevi za mpv
    OSD_SEEK_ID: int = 61
    OSD_INFO_ID: int = 60
    OSD_VOLUME_ID: int = 59
    
    # Trajanja
    DEFAULT_DISPLAY_MS: int = 1500
    FADE_DURATION: float = 0.25  # 250ms za fade
    PULSE_SPEED: float = 3.0

    def __init__(self, engine: "MpvEngine") -> None:
        self._engine = engine
        self._osd_enabled: bool = True
        self._fullscreen: bool = False
        
        self._theme: ThemeColors = get_theme("midnight_red")
        self._cache_colors()
        
        # Animacije
        self._animations: dict = {}
        self._opacity: dict = {}
        
        # Timers
        self._hide_timers: dict = {}
        
        # Animation loop (~60fps)
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._update_animations)
        self._anim_timer.start(16)
        
        # Pulse efekat
        self._pulse_time = 0
        
        self._setup_timers()
        logger.debug("OsdOverlay.__init__ (sa animacijama)")

    def _setup_timers(self) -> None:
        """Inicijalizuj timere za auto-hide."""
        for oid in [self.OSD_SEEK_ID, self.OSD_INFO_ID, self.OSD_VOLUME_ID]:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda o=oid: self._start_fade_out(o))
            self._hide_timers[oid] = timer

    def _cache_colors(self) -> None:
        """Kešira ASS boje iz teme."""
        t = self._theme
        self._ass_accent, _ = _rgba_to_ass(t.accent)
        self._ass_text, _ = _rgba_to_ass(t.osd_text)
        self._ass_subtext, _ = _rgba_to_ass(t.osd_subtext)
        self._ass_bg, self._ass_bg_alpha = _rgba_to_ass(t.osd_bg)
        self._ass_border, _ = _rgba_to_ass(t.bg_primary)
        self._ass_fill, _ = _rgba_to_ass(t.osd_progress_fill)
        self._ass_muted, _ = _rgba_to_ass(t.text_muted)

    def _apply_mpv_osd_style(self) -> None:
        """Postavi mpv OSD property-je iz teme za show-text poruke."""
        player = self._engine._player
        if not player:
            return
        t = self._theme
        try:
            player["osd-font-size"] = 38
            player["osd-color"] = _color_to_mpv_osd(t.osd_text)
            player["osd-border-color"] = _color_to_mpv_osd(t.bg_primary)
            player["osd-border-size"] = 2.0
            player["osd-shadow-offset"] = 1.5
            player["osd-shadow-color"] = _color_to_mpv_osd(t.osd_bg)
            player["osd-back-color"] = _color_to_mpv_osd(t.osd_bg)
            player["osd-align-x"] = "center"
            player["osd-align-y"] = "center"
            player["osd-margin-y"] = 20
        except Exception as e:
            logger.warning(f"mpv OSD stil greška: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    #  ANIMACIJE — Core
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_fade_in(self, overlay_id: int) -> None:
        """Pokreni fade-in animaciju."""
        current = self._opacity.get(overlay_id, 0.0)
        self._animations[overlay_id] = Animation(
            current, 1.0, self.FADE_DURATION, ease_out_cubic
        )

    def _start_fade_out(self, overlay_id: int) -> None:
        """Pokreni fade-out animaciju."""
        current = self._opacity.get(overlay_id, 1.0)
        self._animations[overlay_id] = Animation(
            current, 0.0, self.FADE_DURATION, ease_out_expo
        )

    def _update_animations(self) -> None:
        """Update loop — poziva se ~60fps."""
        self._pulse_time += 0.05
        
        done = []
        for oid, anim in self._animations.items():
            self._opacity[oid] = anim.value()
            if anim.is_done():
                done.append(oid)
                if anim.end_val == 0.0:
                    self._clear_overlay(oid)
        
        for oid in done:
            del self._animations[oid]
        
        # Re-render aktivnih overlay-a
        if self.OSD_SEEK_ID in self._opacity and self._opacity[self.OSD_SEEK_ID] > 0.01:
            if hasattr(self, '_last_seek_pos'):
                self._render_seek_bar(self._last_seek_pos, self._last_seek_dur)
        
        if self.OSD_VOLUME_ID in self._opacity and self._opacity[self.OSD_VOLUME_ID] > 0.01:
            if hasattr(self, '_last_volume'):
                self._render_volume(self._last_volume, self._last_muted)

    def _get_alpha(self, overlay_id: int) -> str:
        """Vrati ASS alpha string za trenutnu opacity."""
        opacity = self._opacity.get(overlay_id, 1.0)
        alpha = int((1.0 - opacity) * 255)
        return f"&H{alpha:02X}&"

    def _clear_overlay(self, overlay_id: int) -> None:
        """Pošalji prazan overlay da uklonimo sa ekrana."""
        try:
            if self._engine._player:
                self._engine._player.command(
                    "osd-overlay", id=overlay_id,
                    data="", res_x=0, res_y=720, z=0,
                    format="ass-events"
                )
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    #  KONFIGURACIJA
    # ═══════════════════════════════════════════════════════════════════════════

    def set_enabled(self, enabled: bool) -> None:
        self._osd_enabled = enabled
        if not enabled:
            for oid in [self.OSD_SEEK_ID, self.OSD_INFO_ID, self.OSD_VOLUME_ID]:
                self._start_fade_out(oid)

    def set_theme_colors(self, theme_name: str) -> None:
        """Postavi boje iz UI teme."""
        self._theme = get_theme(theme_name)
        self._cache_colors()
        self._apply_mpv_osd_style()

    def set_osd_theme(self, theme_name: str) -> None:
        """Kompatibilnost — OSD prati UI temu."""
        pass

    def set_fullscreen(self, fullscreen: bool) -> None:
        """Postavi fullscreen mode."""
        self._fullscreen = fullscreen
        if not fullscreen:
            self._start_fade_out(self.OSD_SEEK_ID)

    # ═══════════════════════════════════════════════════════════════════════════
    #  VOLUME — Fiksna pozicija, ne pomerajući se
    # ═══════════════════════════════════════════════════════════════════════════
    #
    #  Dizajn (fiksna pozicija — handle se pomera unutar bara, bar ostaje isti):
    #  
    #     🔊  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  75%
    #         ████████████████████●━━━━━━━━━━━
    #         ^^^^^^^^^^^^^^^^^^^^            (filled — accent)
    #                            ^           (handle — pulsing)
    #                             ^^^^^^^^^^ (empty — muted)
    #
    #  - Bar je uvek iste dužine, na istom mestu
    #  - Handle se pomera unutar fiksnog bara
    #  - Ikonica i % su fiksni

    def show_volume(self, volume: int, muted: bool = False) -> None:
        """Prikaži volume sa animiranim slider-om."""
        if not self._osd_enabled:
            return
        
        self._last_volume = volume
        self._last_muted = muted
        
        self._hide_timers[self.OSD_VOLUME_ID].stop()
        self._hide_timers[self.OSD_VOLUME_ID].start(self.DEFAULT_DISPLAY_MS)
        
        self._start_fade_in(self.OSD_VOLUME_ID)
        self._render_volume(volume, muted)

    def _render_volume(self, volume: int, muted: bool) -> None:
        """Render volume overlay — JEDAN red, fiksna pozicija, nema pomeranja.
        
        Sve se renderuje kao jedan ASS tekst blok sa inline color switchevima.
        Ikonica + bar + procenat su u jednom stringu sa jednim \\pos().
        Bar je uvek iste dužine (fiksni broj karaktera), samo se boje menjaju.
        """
        oid = self.OSD_VOLUME_ID
        alpha = self._get_alpha(oid)
        
        # Ikonica
        if muted or volume == 0:
            icon = "🔇"
            icon_color = self._ass_muted
        elif volume < 30:
            icon = "🔈"
            icon_color = self._ass_text
        elif volume < 70:
            icon = "🔉"
            icon_color = self._ass_text
        else:
            icon = "🔊"
            icon_color = self._ass_accent
        
        # Fiksne dimenzije bara
        bar_chars = 25
        
        # Pozicija handle-a unutar bara
        if muted:
            handle_pos = 0
        else:
            handle_pos = max(0, min(bar_chars, int((volume / 100) * bar_chars)))
        
        # Boje
        fill_color = self._ass_muted if muted else self._ass_fill
        
        # Procenat tekst — uvek fiksne širine (pad sa razmakom)
        if muted:
            vol_text = " MUT"
        else:
            vol_text = f"{volume:3d}%"
        
        # Y pozicija i centar
        pos_y = 60
        center_x = 360
        
        # ═══════════════════════════════════════════════════════════
        # Sve u JEDNOM ASS redu — jedan \pos(), inline color switch
        # ═══════════════════════════════════════════════════════════
        
        parts = []
        
        # Početni stil + pozicija (samo jednom!)
        parts.append(
            "{"
            f"\\an5"
            f"\\fs22"
            f"\\bord2"
            f"\\3c{self._ass_border}"
            f"\\shad0"
            f"\\1a{alpha}"
            f"\\pos({center_x},{pos_y})"
            "}"
        )
        
        # Ikonica
        parts.append(f"{{\\1c{icon_color}\\fs26}}{icon}  ")
        
        # Filled deo bara (accent boja)
        if handle_pos > 0:
            parts.append(
                f"{{\\1c{fill_color}\\fs18\\bord0}}"
                + "━" * handle_pos
            )
        
        # Handle krug (accent boja, malo veći)
        if not muted:
            parts.append(f"{{\\1c{self._ass_accent}\\fs20\\bord1\\3c{self._ass_text}}}●")
        
        # Empty deo bara (muted boja)
        empty_chars = bar_chars - handle_pos
        if empty_chars > 0:
            parts.append(
                f"{{\\1c{self._ass_muted}\\fs18\\bord0}}"
                + "━" * empty_chars
            )
        
        # Procenat
        vol_color = self._ass_muted if muted else self._ass_text
        parts.append(f"{{\\1c{vol_color}\\fs20\\b1\\bord1.5\\3c{self._ass_border}}}  {vol_text}")
        
        self._engine.osd_overlay(oid, "".join(parts))

    # ═══════════════════════════════════════════════════════════════════════════
    #  TOAST PORUKE (show-text — mpv kontroliše)
    # ═══════════════════════════════════════════════════════════════════════════

    def show_play(self) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text("▶ Play", 800)

    def show_pause(self) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text("⏸ Paused", 800)

    def show_title(self, title: str, duration_ms: int = 3000) -> None:
        """Title notification — sada ide kroz info panel gore."""
        if not self._osd_enabled:
            return
        # Koristimo info panel umesto show_text za bolju poziciju
        self._show_top_notification(f"🎬 {title}", duration_ms)

    def show_speed(self, speed: float) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text(f"⚡ {speed}x", self.DEFAULT_DISPLAY_MS)

    def show_buffering(self) -> None:
        if not self._osd_enabled:
            return
        self._engine.show_text("⏳ Buffering...", self.DEFAULT_DISPLAY_MS)

    # ═══════════════════════════════════════════════════════════════════════════
    #  TOP NOTIFICATION — Gore na sredini (za title, info)
    # ═══════════════════════════════════════════════════════════════════════════
    #
    #  Pozicija: Gornji centar ekrana (kao Netflix title notification)
    #  Dizajn: Pill shape sa pozadinom, centriran tekst

    def _show_top_notification(self, text: str, duration_ms: int = 3000) -> None:
        """Prikaži notification gore na sredini."""
        # Koristimo INFO_ID ali renderujemo drugačije
        self._hide_timers[self.OSD_INFO_ID].stop()
        self._hide_timers[self.OSD_INFO_ID].start(duration_ms)
        
        self._start_fade_in(self.OSD_INFO_ID)
        self._render_top_notification(text)

    def _render_top_notification(self, text: str) -> None:
        """Render notification gore na sredini."""
        oid = self.OSD_INFO_ID
        alpha = self._get_alpha(oid)
        
        # Pozicija: gore centar
        center_x = 360
        top_y = 80
        
        # "Pill" background (simulirano sa razmacima)
        padding = "  "
        display_text = padding + text + padding
        
        ass_parts = []
        
        # Pozadina (tamni pill)
        ass_parts.append(
            "{"
            f"\\an8"  # Top-center
            f"\\fs24"
            f"\\1c{self._ass_bg}"
            f"\\1a{alpha}"
            f"\\bord4"  # Debela "bordura" kao pozadina
            f"\\3c{self._ass_bg}"
            f"\\3a&H40&"  # Malo prozirna
            f"\\shad0"
            f"\\pos({center_x},{top_y})"
            "}" + "█" * len(display_text)  # Block chars za pozadinu
        )
        
        # Tekst
        ass_parts.append(
            "{"
            f"\\an8"  # Top-center
            f"\\fs26"
            f"\\b1"
            f"\\1c{self._ass_text}"
            f"\\3c{self._ass_border}"
            f"\\bord1.5"
            f"\\shad0"
            f"\\1a{alpha}"
            f"\\pos({center_x},{top_y + 2})"
            "}" + display_text
        )
        
        self._engine.osd_overlay(oid, "".join(ass_parts))

    # ═══════════════════════════════════════════════════════════════════════════
    #  INFO PANEL — GORE na sredini (za O taster, detaljni info)
    # ═══════════════════════════════════════════════════════════════════════════

    def show_info(self, info_text: str) -> None:
        """Prikaži info panel gore na sredini (umesto centra)."""
        if not self._osd_enabled:
            return
        
        self._hide_timers[self.OSD_INFO_ID].stop()
        self._hide_timers[self.OSD_INFO_ID].start(5000)
        
        self._start_fade_in(self.OSD_INFO_ID)
        self._render_info_top(info_text)

    def _render_info_top(self, info_text: str) -> None:
        """Render info panel gore na sredini."""
        oid = self.OSD_INFO_ID
        alpha = self._get_alpha(oid)
        
        lines = info_text.split("\n")
        ass_lines = []
        
        # Y pozicija — početak od vrha
        start_y = 100
        center_x = 360
        
        for i, line in enumerate(lines):
            escaped = self._escape_ass(line)
            y_pos = start_y + (i * 35)  # razmak između linija
            
            if i == 0:
                # Naslov — veći, bold, accent
                ass_lines.append(
                    "{"
                    f"\\an8"  # Top-center
                    f"\\fs28\\b1"
                    f"\\1c{self._ass_accent}"
                    f"\\3c{self._ass_border}"
                    f"\\bord2"
                    f"\\shad0"
                    f"\\1a{alpha}"
                    f"\\pos({center_x},{y_pos})"
                    "}" + escaped
                )
            else:
                # Ostalo — manje, subtext
                ass_lines.append(
                    "{"
                    f"\\an8"  # Top-center
                    f"\\fs22\\b0"
                    f"\\1c{self._ass_subtext}"
                    f"\\3c{self._ass_border}"
                    f"\\bord1"
                    f"\\shad0"
                    f"\\1a{alpha}"
                    f"\\pos({center_x},{y_pos})"
                    "}" + escaped
                )

        self._engine.osd_overlay(oid, "".join(ass_lines))

    # ═══════════════════════════════════════════════════════════════════════════
    #  SEEK BAR — Sa animacijama i pulse handle-om
    # ═══════════════════════════════════════════════════════════════════════════

    def show_seek(self, position: float, duration: float) -> None:
        """Prikaži seek bar sa fade-in animacijom."""
        if not self._osd_enabled or not self._fullscreen:
            return
        
        self._last_seek_pos = position
        self._last_seek_dur = duration
        
        self._hide_timers[self.OSD_SEEK_ID].stop()
        self._hide_timers[self.OSD_SEEK_ID].start(self.DEFAULT_DISPLAY_MS)
        
        self._start_fade_in(self.OSD_SEEK_ID)
        self._render_seek_bar(position, duration)

    def _render_seek_bar(self, position: float, duration: float) -> None:
        """Render seek bar sa trenutnom opacity-jem."""
        oid = self.OSD_SEEK_ID
        alpha = self._get_alpha(oid)
        
        pos_str = self._format_time(position)
        dur_str = self._format_time(duration)
        progress = position / duration if duration > 0 else 0.0

        bar_total = 50
        filled = max(0, int(progress * bar_total))
        empty = bar_total - filled

        # Pulsirajući handle
        pulse = 1.0 + 0.15 * abs((self._pulse_time % 2) - 1)
        handle_size = int(22 * pulse)

        ass_parts = []
        
        # Pozicija (levo)
        ass_parts.append(
            "{"
            f"\\an2"  # Bottom-center
            f"\\fs20\\b1"
            f"\\1c{self._ass_text}"
            f"\\3c{self._ass_border}"
            f"\\bord1.5\\shad0"
            f"\\1a{alpha}"
            "}" + pos_str + "  "
        )

        # Filled deo
        if filled > 0:
            ass_parts.append(
                "{"
                f"\\fs26\\b0"
                f"\\1c{self._ass_fill}"
                f"\\bord0\\shad0"
                f"\\1a{alpha}"
                "}" + "▬" * filled
            )

        # Pulsirajući handle
        ass_parts.append(
            "{"
            f"\\an5"
            f"\\fs{handle_size}"
            f"\\1c{self._ass_text}"
            f"\\3c{self._ass_fill}"
            f"\\bord1.5"
            f"\\shad0"
            f"\\1a{alpha}"
            "}⬤"
        )

        # Empty deo
        if empty > 0:
            ass_parts.append(
                "{"
                f"\\1c{self._ass_muted}"
                f"\\fs26\\bord0\\shad0"
                f"\\1a{alpha}"
                "}" + "━" * empty
            )

        # Trajanje (desno)
        ass_parts.append(
            "{"
            f"\\fs20\\b0"
            f"\\1c{self._ass_subtext}"
            f"\\3c{self._ass_border}"
            f"\\bord1.5\\shad0"
            f"\\1a{alpha}"
            "}" + "  " + dur_str
        )

        self._engine.osd_overlay(oid, "".join(ass_parts))

    # ═══════════════════════════════════════════════════════════════════════════
    #  CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    def close(self) -> None:
        self._anim_timer.stop()
        for timer in self._hide_timers.values():
            timer.stop()
        for oid in [self.OSD_SEEK_ID, self.OSD_INFO_ID, self.OSD_VOLUME_ID]:
            self._clear_overlay(oid)

    # ═══════════════════════════════════════════════════════════════════════════
    #  UTILITY
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _escape_ass(text: str) -> str:
        return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = int(max(0, seconds))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"