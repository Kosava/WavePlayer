"""MPV media engine implementation.

Wraps libmpv via python-mpv library.
This module has NO UI imports - only core interfaces.
"""

import logging
import locale
import os
import time
from typing import Optional

try:
    locale.setlocale(locale.LC_NUMERIC, "C")
except locale.Error:
    pass

try:
    import mpv
    HAS_MPV = True
except ImportError:
    HAS_MPV = False

from .interfaces import (
    MediaEngineInterface,
    PlaybackState,
    EngineEventCallback,
)

logger = logging.getLogger(__name__)

SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".vtt", ".idx", ".sup", ".smi", ".lrc", ".txt"}

def is_subtitle_file(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in SUBTITLE_EXTENSIONS)

class MpvEngine(MediaEngineInterface):
    def __init__(self, callbacks: EngineEventCallback) -> None:
        self._callbacks: EngineEventCallback = callbacks
        self._player: Optional["mpv.MPV"] = None
        self._state: PlaybackState = PlaybackState.STOPPED
        self._duration: float = 0.0
        self._position: float = 0.0
        self._volume: int = 100
        self._muted: bool = False
        self._speed: float = 1.0
        self._window_id: Optional[int] = None
        self._last_error: Optional[str] = None

    def initialize(self) -> bool:
        if not HAS_MPV:
            logger.error("python-mpv nije instaliran!")
            self._callbacks.emit_error("python-mpv nije instaliran")
            return False

        try:
            self._player = mpv.MPV(
                log_handler=self._mpv_log_handler,
                loglevel="info",
                vo="gpu,x11",
                input_default_bindings=False,
                input_vo_keyboard=False,
                osc=False,
                input_cursor=False,
                keep_open="yes",
                cursor_autohide="no",
                embeddedfonts="no",  # Onemogući embedovane fontove koji mogu sadržati ASS stilove
            )

            if self._window_id is not None:
                self._player["wid"] = self._window_id

            self._setup_observers()
            logger.info("MPV engine inicijalizovan uspešno")
            return True

        except Exception as e:
            logger.error(f"Greška pri inicijalizaciji MPV: {e}")
            self._callbacks.emit_error(f"MPV inicijalizacija neuspešna: {e}")
            return False

    def _setup_observers(self) -> None:
        if not self._player:
            return

        @self._player.property_observer("time-pos")
        def _on_time_pos(_name, value):
            if value is not None:
                self._position = value

        @self._player.property_observer("duration")
        def _on_duration(_name, value):
            if value is not None:
                self._duration = value
                self._callbacks.emit_duration_changed(value)

        @self._player.property_observer("pause")
        def _on_pause(_name, value):
            if value is not None:
                old = self._state
                self._state = PlaybackState.PAUSED if value else PlaybackState.PLAYING
                if old != self._state:
                    self._callbacks.emit_state_changed(self._state)

        @self._player.property_observer("idle-active")
        def _on_idle(_name, value):
            if value:
                self._state = PlaybackState.STOPPED
                self._callbacks.emit_state_changed(self._state)
                self._callbacks.emit_end_of_file()

        @self._player.property_observer("volume")
        def _on_volume(_name, value):
            if value is not None:
                self._volume = int(value)

        @self._player.property_observer("eof-reached")
        def _on_eof(_name, value):
            if value:
                pass

    def _mpv_log_handler(self, loglevel: str, component: str, message: str) -> None:
        if loglevel == "error":
            logger.error(f"[mpv/{component}] {message.strip()}")
        elif loglevel == "warn":
            logger.warning(f"[mpv/{component}] {message.strip()}")
        elif loglevel == "info":
            logger.info(f"[mpv/{component}] {message.strip()}")
        else:
            logger.debug(f"[mpv/{component}] {message.strip()}")

    def _force_subtitle_rerender(self) -> None:
        if not self._player:
            return
        try:
            sid = self._player["sid"]
            if sid and sid != "no":
                self._player["sid"] = "no"
                time.sleep(0.05)
                self._player["sid"] = sid
                logger.info(f"[SUB-DEBUG] Subtitle re-render FORCED (sid={sid})")
        except Exception:
            pass

    def shutdown(self) -> None:
        if self._player:
            try:
                self._player.terminate()
            except Exception as e:
                logger.error(f"Greška pri zatvaranju MPV: {e}")
            finally:
                self._player = None
        self._state = PlaybackState.STOPPED
        logger.info("MPV engine ugašen")

    def load(self, path: str) -> bool:
        logger.info(f"MPV_ENGINE.load: {path}")
        if not self._player:
            return False

        is_url = any(path.startswith(s) for s in ("http://", "https://", "rtsp://", "rtp://", "mms://"))
        if not is_url and not os.path.exists(path):
            self._last_error = f"Fajl ne postoji: {path}"
            return False

        try:
            self._player.command('loadfile', path)
            time.sleep(0.2)
            self._state = PlaybackState.PLAYING
            self._callbacks.emit_state_changed(self._state)
            self._callbacks.emit_media_loaded(path)
            return True
        except Exception as e:
            logger.error(f"MPV load greška: {e}")
            self._last_error = str(e)
            return False

    def load_subtitle(self, path: str) -> bool:
        if not self._player:
            return False
        try:
            self._player.command("sub-add", path, "select")
            logger.info(f"Učitan titl: {path}")
            time.sleep(0.1)                    # mali delay da mpv obradi titl
            self.apply_subtitle_config(None)   # primeni stilove
            return True
        except Exception as e:
            logger.error(f"Greška pri učitavanju titla: {e}")
            return False

    def play(self) -> None:
        if self._player and self._state == PlaybackState.PAUSED:
            self._player["pause"] = False

    def pause(self) -> None:
        if self._player and self._state == PlaybackState.PLAYING:
            self._player["pause"] = True

    def stop(self) -> None:
        if self._player:
            self._player.command("stop")
            self._state = PlaybackState.STOPPED
            self._position = 0.0
            self._duration = 0.0
            self._callbacks.emit_state_changed(self._state)

    def seek(self, position_seconds: float) -> None:
        if self._player:
            self._player.seek(position_seconds, reference="absolute")

    def get_state(self) -> PlaybackState:
        return self._state

    def get_duration(self) -> float:
        return self._duration

    def get_position(self) -> float:
        return self._position

    def get_volume(self) -> int:
        return self._volume

    def set_volume(self, volume: int) -> None:
        if self._player:
            clamped = max(0, min(100, volume))
            self._player["volume"] = clamped
            self._volume = clamped

    def get_muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        if self._player:
            self._player["mute"] = muted
            self._muted = muted

    def get_speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> None:
        if self._player:
            clamped = max(0.25, min(4.0, speed))
            self._player["speed"] = clamped
            self._speed = clamped

    def get_video_width(self) -> int:
        return int(self._player["video-params/w"] or 0) if self._player else 0

    def get_video_height(self) -> int:
        return int(self._player["video-params/h"] or 0) if self._player else 0

    def get_window_id(self) -> Optional[int]:
        return self._window_id

    def set_window_id(self, wid: int) -> None:
        self._window_id = wid
        if self._player:
            self._player["wid"] = wid

    def set_video_eq(self, prop: str, value: int) -> None:
        if self._player:
            try:
                self._player[prop] = max(-100, min(100, value))
            except Exception:
                pass

    def get_video_eq(self, prop: str) -> int:
        if self._player:
            try:
                return int(self._player[prop])
            except Exception:
                return 0
        return 0

    def get_current_video_output(self) -> str:
        if self._player:
            try:
                return str(self._player["current-vo"]) or ""
            except Exception:
                return ""
        return ""

    def apply_subtitle_config(self, cfg) -> None:
        if not self._player:
            return

        try:
            # === BEZBEDNO postavljanje (bez .get() kada je cfg=None) ===
            font = cfg.get("subtitles.font_family", "Arial") if cfg else "Arial"
            size = cfg.get("subtitles.font_size", 46) if cfg else 46
            bold = cfg.get("subtitles.bold", True) if cfg else True
            italic = cfg.get("subtitles.italic", False) if cfg else False
            color = cfg.get("subtitles.color", "#FFFFFF") if cfg else "#FFFFFF"

            self._player["sub-font"] = font
            self._player["sub-font-size"] = size
            self._player["sub-bold"] = bold
            self._player["sub-italic"] = italic
            self._player["sub-color"] = color

            bg_enabled = cfg.get("subtitles.bg_enabled", False) if cfg else True
            logger.info(f"[SUB-DEBUG] bg_enabled={bg_enabled}")

            if bg_enabled:
                opacity_str = str(cfg.get("subtitles.bg_opacity", "100") if cfg else "100")
                alpha = {"80": 0.8, "50": 0.5, "100": 1.0, "darkgray": 0.8}.get(opacity_str, 1.0)
                back_color = f"0.2/0.2/0.2/{alpha}" if opacity_str == "darkgray" else f"0/0/0/{alpha}"

                self._player["sub-back-color"] = back_color
                self._player["sub-border-style"] = "background-box"
                padding = max(6, (cfg.get("subtitles.bg_padding", 10) if cfg else 10) // 2)
                self._player["sub-shadow-offset"] = padding
                self._player["sub-shadow-color"] = "0/0/0/0"
                self._player["sub-border-size"] = 0.0
                self._player["sub-border-color"] = "0/0/0/0"

                logger.info(f"[SUB-DEBUG] background-box AKTIVIRAN (padding={padding}, alpha={alpha})")
            else:
                self._player["sub-back-color"] = "0/0/0/0"
                self._player["sub-border-style"] = "outline-and-shadow"

            # KORISTI STRIP umesto FORCE da potpuno ukloniš ASS stilove iz SRT fajlova!
            self._player["sub-ass-override"] = "strip"
            logger.info("[SUB-DEBUG] ass_override → strip")

            logger.info("Subtitle konfiguracija primenjena na mpv")
            self._force_subtitle_rerender()

        except Exception as e:
            logger.warning(f"Greška pri primeni subtitle config-a: {e}")

    def set_aspect_ratio(self, ratio: str) -> None:
        if self._player:
            self._player["video-aspect-override"] = "-1" if ratio == "auto" else ratio

    def set_zoom(self, zoom: float) -> None:
        if self._player:
            self._player["video-zoom"] = zoom

    def set_pan(self, x: float, y: float) -> None:
        if self._player:
            self._player["video-pan-x"] = x
            self._player["video-pan-y"] = y

    def set_rotation(self, degrees: int) -> None:
        if self._player:
            self._player["video-rotate"] = str(degrees)

    def set_deinterlace(self, enabled: bool) -> None:
        if self._player:
            self._player["deinterlace"] = "yes" if enabled else "no"

    def screenshot(self, mode: str = "subtitles") -> None:
        if self._player:
            self._player.command("screenshot", mode)

    def show_text(self, text: str, duration_ms: int = 1500, level: int = 1) -> None:
        if self._player:
            try:
                self._player.command("show-text", text, str(duration_ms), str(level))
            except Exception as e:
                logger.warning(f"show_text greška: {e}")

    def osd_overlay(self, overlay_id: int, ass_text: str) -> None:
        if self._player:
            try:
                self._player.command("osd-overlay", id=overlay_id, data=ass_text,
                                     res_x=0, res_y=720, z=0, format="ass-events")
            except Exception:
                pass

    def osd_overlay_remove(self, overlay_id: int) -> None:
        if self._player:
            try:
                self._player.command("osd-overlay", id=overlay_id, format="none")
            except Exception:
                pass