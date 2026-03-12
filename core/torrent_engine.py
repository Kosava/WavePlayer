"""Torrent streaming engine for WavePlayer.

Downloads torrents with streaming-optimized piece selection:
1. First and last pieces downloaded immediately (file structure)
2. Sequential download from current position
3. Buffer threshold before playback starts
4. Continuous progress monitoring via Qt signals

Uses libtorrent (python-libtorrent / python3-libtorrent).

PORTABILITY NOTES:
  - C++: libtorrent C++ API directly
  - Rust: libtorrent-sys or cratetorrent
"""

import logging
import os
import math
import time
import threading
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable, List, Tuple

logger = logging.getLogger(__name__)

try:
    import libtorrent as lt
    HAS_LIBTORRENT = True
except ImportError:
    HAS_LIBTORRENT = False

# Video ekstenzije za prepoznavanje glavnog fajla u torrentu
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".mpg", ".mpeg", ".3gp", ".ogv",
}


class TorrentState(Enum):
    """Stanje torrent download-a."""
    IDLE = auto()
    LOADING_METADATA = auto()
    DOWNLOADING = auto()
    BUFFERING = auto()
    READY = auto()          # Dovoljno buffered za playback
    STREAMING = auto()      # Playback aktivan, download nastavlja
    SEEDING = auto()
    PAUSED = auto()
    ERROR = auto()


@dataclass
class TorrentStatus:
    """Snapshot stanja torrenta za UI."""
    state: TorrentState = TorrentState.IDLE
    progress: float = 0.0          # 0.0 - 1.0 ukupno
    download_rate: float = 0.0     # bytes/sec
    upload_rate: float = 0.0       # bytes/sec
    num_peers: int = 0
    num_seeds: int = 0
    total_size: int = 0
    downloaded: int = 0
    buffer_progress: float = 0.0   # 0.0 - 1.0 buffer
    video_file: str = ""           # putanja do video fajla
    name: str = ""
    eta_seconds: int = 0
    error_message: str = ""


class TorrentCallbacks:
    """Callback-ovi iz torrent engine-a ka UI-u.

    UI registruje callback-ove, engine ih poziva iz svog thread-a.
    UI mora obezbediti thread-safe prijem (npr. QTimer polling).
    """
    def __init__(self) -> None:
        self.on_state_changed: Optional[Callable[[TorrentState], None]] = None
        self.on_progress: Optional[Callable[[TorrentStatus], None]] = None
        self.on_ready_to_play: Optional[Callable[[str], None]] = None  # video_file_path
        self.on_metadata_received: Optional[Callable[[str, List[str]], None]] = None  # name, files
        self.on_error: Optional[Callable[[str], None]] = None


class TorrentEngine:
    """Torrent streaming engine.

    Strategija download-a za streaming:
    1. Učitaj metadata (magnet) ili parsiraj .torrent
    2. Nađi najveći video fajl
    3. Postavi prioritet: prvi komadi + poslednji komadi = max
    4. Uključi sequential download
    5. Prati buffer — kad dostigne threshold, javi READY
    6. Tokom playback-a, pomeri prioritete prema seek poziciji

    Thread model:
    - libtorrent ima svoj thread pool
    - Mi koristimo monitor thread za polling statusa
    - Callback-ovi se pozivaju iz monitor thread-a
    """

    # Podrazumevane vrednosti (override iz Config-a)
    DEFAULT_DOWNLOAD_DIR = os.path.join(str(Path.home()), "Downloads", "WavePlayer")
    DEFAULT_BUFFER_MB = 70          # PATCH 1: Smanjen sa 500MB na 70MB
    DEFAULT_MAX_DOWNLOAD = 0       # 0 = unlimited
    DEFAULT_MAX_UPLOAD = 0
    DEFAULT_PORT_MIN = 6881
    DEFAULT_PORT_MAX = 6891

    def __init__(self, callbacks: TorrentCallbacks) -> None:
        self._callbacks = callbacks
        self._session: Optional["lt.session"] = None
        self._handle: Optional["lt.torrent_handle"] = None
        self._state = TorrentState.IDLE
        self._status = TorrentStatus()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._video_file_index: int = -1
        self._video_file_path: str = ""

        # Konfigurabilno
        self._download_dir: str = self.DEFAULT_DOWNLOAD_DIR
        self._buffer_bytes: int = self.DEFAULT_BUFFER_MB * 1024 * 1024
        self._max_download: int = self.DEFAULT_MAX_DOWNLOAD
        self._max_upload: int = self.DEFAULT_MAX_UPLOAD
        self._port_min: int = self.DEFAULT_PORT_MIN
        self._port_max: int = self.DEFAULT_PORT_MAX
        self._seed_after: bool = True
        self._seed_ratio: float = 1.0
        self._dht_enabled: bool = True
        self._encryption: int = 1  # 0=off, 1=enabled, 2=forced
        self._connections_limit: int = 200
        self._prealloc: bool = False

    def apply_config(self, cfg) -> None:
        """Primeni podešavanja iz Config objekta."""
        download_dir = cfg.get("torrent.download_dir", "").strip()
        if not download_dir:
            download_dir = self.DEFAULT_DOWNLOAD_DIR
        self._download_dir = download_dir
        
        self._buffer_bytes = cfg.get("torrent.buffer_mb", self.DEFAULT_BUFFER_MB) * 1024 * 1024
        
        self._max_download = cfg.get("torrent.max_download_kbps", 0) * 1024
        self._max_upload = cfg.get("torrent.max_upload_kbps", 0) * 1024
        self._port_min = cfg.get("torrent.port_min", self.DEFAULT_PORT_MIN)
        self._port_max = cfg.get("torrent.port_max", self.DEFAULT_PORT_MAX)
        self._seed_after = cfg.get("torrent.seed_after_download", True)
        self._seed_ratio = cfg.get("torrent.seed_ratio", 1.0)
        self._dht_enabled = cfg.get("torrent.dht_enabled", True)
        self._encryption = cfg.get("torrent.encryption", 1)
        self._connections_limit = cfg.get("torrent.connections_limit", 200)
        self._prealloc = cfg.get("torrent.preallocate", False)

        if self._session:
            self._apply_session_settings()

    def initialize(self) -> bool:
        """Inicijalizuj libtorrent sesiju."""
        if not HAS_LIBTORRENT:
            logger.error("python-libtorrent nije instaliran!")
            if self._callbacks.on_error:
                self._callbacks.on_error("libtorrent nije instaliran")
            return False

        try:
            settings = lt.session_params()
            self._session = lt.session(settings)
            self._apply_session_settings()

            if not self._download_dir:
                self._download_dir = self.DEFAULT_DOWNLOAD_DIR
            os.makedirs(self._download_dir, exist_ok=True)

            logger.info(f"Torrent engine inicijalizovan (dir: {self._download_dir})")
            return True

        except Exception as e:
            logger.error(f"Torrent init greška: {e}")
            if self._callbacks.on_error:
                self._callbacks.on_error(f"Torrent init: {e}")
            return False

    def _apply_session_settings(self) -> None:
        """Primeni settings na libtorrent sesiju."""
        if not self._session:
            return

        try:
            s = self._session.get_settings()

            s["listen_interfaces"] = f"0.0.0.0:{self._port_min},[::0]:{self._port_min}"
            s["download_rate_limit"] = self._max_download if self._max_download > 0 else 0
            s["upload_rate_limit"] = self._max_upload if self._max_upload > 0 else 0
            s["connections_limit"] = self._connections_limit
            s["enable_dht"] = self._dht_enabled

            enc_map = {0: lt.enc_policy.disabled, 1: lt.enc_policy.enabled, 2: lt.enc_policy.forced}
            enc = enc_map.get(self._encryption, lt.enc_policy.enabled)
            pe = lt.pe_settings()
            pe.in_enc_policy = enc
            pe.out_enc_policy = enc

            # Streaming optimizacije
            s["request_timeout"] = 10
            s["peer_timeout"] = 20
            s["urlseed_timeout"] = 10
            s["auto_manage_prefer_seeds"] = True
            s["close_redundant_connections"] = True
            s["piece_timeout"] = 5
            s["request_queue_time"] = 1

            s["disk_io_write_mode"] = 0 if self._prealloc else 2

            # Performance boost
            s["connections_limit"] = 400
            s["active_downloads"] = 50
            s["active_seeds"] = 20
            s["cache_size"] = 2048

            self._session.apply_settings(s)

        except Exception as e:
            logger.error(f"Greška pri primeni settings: {e}")

    def add_torrent(self, source: str) -> bool:
        """Dodaj torrent iz magnet linka ili .torrent fajla."""
        if not self._session:
            if not self.initialize():
                return False

        try:
            if source.startswith("magnet:"):
                params = lt.parse_magnet_uri(source)
            else:
                info = lt.torrent_info(source)
                params = lt.add_torrent_params()
                params.ti = info

            params.save_path = self._download_dir
            params.storage_mode = (lt.storage_mode_t.storage_mode_allocate
                                   if self._prealloc
                                   else lt.storage_mode_t.storage_mode_sparse)

            self._handle = self._session.add_torrent(params)
            self._handle.set_sequential_download(True)
            self._set_state(TorrentState.LOADING_METADATA)
            self._start_monitor()

            logger.info(f"Torrent dodat: {source[:80]}")
            return True

        except Exception as e:
            logger.error(f"Greška pri dodavanju torrenta: {e}")
            self._set_state(TorrentState.ERROR)
            self._status.error_message = str(e)
            if self._callbacks.on_error:
                self._callbacks.on_error(str(e))
            return False

    def _start_monitor(self) -> None:
        """Pokreni monitor thread za praćenje statusa."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="torrent-monitor"
        )
        self._monitor_thread.start()

    def _monitor_loop(self) -> None:
        """Glavni monitoring loop — pokreće se u zasebnom thread-u."""
        metadata_received = False
        ready_triggered = False

        while self._running and self._handle:
            try:
                if not self._handle.is_valid():
                    break

                s = self._handle.status()

                # Ažuriraj status
                self._status.progress = s.progress
                self._status.download_rate = s.download_rate
                self._status.upload_rate = s.upload_rate
                self._status.num_peers = s.num_peers
                self._status.num_seeds = s.num_seeds
                self._status.downloaded = s.total_done
                self._status.name = s.name or ""

                # ETA
                if s.download_rate > 0 and s.total_wanted > 0:
                    remaining = s.total_wanted - s.total_done
                    self._status.eta_seconds = int(remaining / s.download_rate)
                else:
                    self._status.eta_seconds = 0

                # Metadata faza
                if s.state == lt.torrent_status.downloading_metadata:
                    self._set_state(TorrentState.LOADING_METADATA)
                    time.sleep(0.5)
                    continue

                # Metadata primljena — nađi video fajl i prioritizuj
                if not metadata_received and s.has_metadata:
                    metadata_received = True
                    self._on_metadata_ready()

                # Download faza
                if s.state in (lt.torrent_status.downloading,
                               lt.torrent_status.checking_files,
                               lt.torrent_status.checking_resume_data):

                    buffered = self._calculate_buffer_bytes()
                    self._status.buffer_progress = min(1.0, buffered / max(1, self._buffer_bytes))

                    if not ready_triggered and buffered >= self._buffer_bytes and self._video_file_path:
                        if os.path.exists(self._video_file_path):
                            ready_triggered = True
                            logger.info(f"Buffer spreman ({buffered // 1024 // 1024} MB), pokrećem playback")
                            self._set_state(TorrentState.READY)
                            if self._callbacks.on_ready_to_play:
                                try:
                                    self._callbacks.on_ready_to_play(self._video_file_path)
                                except Exception as e:
                                    logger.error(f"Greška u on_ready_to_play: {e}")
                    
                    if self._state not in (TorrentState.READY, TorrentState.STREAMING):
                        if buffered < self._buffer_bytes:
                            self._set_state(TorrentState.BUFFERING)
                        else:
                            self._set_state(TorrentState.READY)

                # Seeding
                elif s.state == lt.torrent_status.seeding:
                    self._set_state(TorrentState.SEEDING)

                # Emit progress
                if self._callbacks.on_progress:
                    try:
                        self._callbacks.on_progress(self._status)
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Monitor loop greška: {e}")

            time.sleep(1.0)

    def _on_metadata_ready(self) -> None:
        """Metadata primljena — identifikuj video i postavi prioritete."""
        if not self._handle or not self._handle.has_metadata():
            return

        ti = self._handle.torrent_file()
        if not ti:
            return

        self._status.total_size = ti.total_size()

        # Nađi najveći video fajl
        files = ti.files()
        best_idx = -1
        best_size = 0
        file_list = []

        for i in range(files.num_files()):
            path = files.file_path(i)
            size = files.file_size(i)
            file_list.append(path)
            ext = os.path.splitext(path)[1].lower()
            if ext in VIDEO_EXTENSIONS and size > best_size:
                best_size = size
                best_idx = i

        if best_idx < 0:
            for i in range(files.num_files()):
                if files.file_size(i) > best_size:
                    best_size = files.file_size(i)
                    best_idx = i

        self._video_file_index = best_idx
        self._video_file_path = os.path.join(
            self._download_dir, files.file_path(best_idx)
        ) if best_idx >= 0 else ""

        self._status.video_file = self._video_file_path
        logger.info(f"Video fajl: {self._video_file_path} ({best_size / 1024 / 1024:.0f} MB)")

        # Javi UI o metadata
        name = ti.name()
        if self._callbacks.on_metadata_received:
            try:
                self._callbacks.on_metadata_received(name, file_list)
            except Exception as e:
                logger.error(f"Greška u on_metadata_received: {e}")

        # Postavi file priorities — samo video fajl
        priorities = [0] * files.num_files()
        if best_idx >= 0:
            priorities[best_idx] = 7
        self._handle.prioritize_files(priorities)

        # Postavi piece priorities za streaming
        self._prioritize_for_streaming()

    def _prioritize_for_streaming(self, playback_piece: int = 0) -> None:
        """Postavi piece prioritete za streaming od zadate pozicije."""
        if not self._handle or not self._handle.has_metadata():
            return

        ti = self._handle.torrent_file()
        if not ti:
            return

        files = ti.files()
        num_pieces = ti.num_pieces()
        piece_length = ti.piece_length()

        if self._video_file_index < 0:
            return

        # Nađi piece range za video fajl
        file_offset = files.file_offset(self._video_file_index)
        file_size = files.file_size(self._video_file_index)
        first_piece = file_offset // piece_length
        last_piece = min((file_offset + file_size - 1) // piece_length, num_pieces - 1)

        buffer_pieces = max(20, self._buffer_bytes // piece_length)

        # Postavi sve na normalan
        priorities = [1] * num_pieces

        # Van video fajla — ignoriši
        for i in range(num_pieces):
            if i < first_piece or i > last_piece:
                priorities[i] = 0

        # Prvih buffer_pieces od playback pozicije — max
        start = max(first_piece, playback_piece)
        for i in range(start, min(start + buffer_pieces, last_piece + 1)):
            priorities[i] = 7

        # Poslednjih 30 komada video fajla
        for i in range(max(first_piece, last_piece - 30), last_piece + 1):
            priorities[i] = 7

        # Prvih 5 komada — header
        for i in range(first_piece, min(first_piece + 5, last_piece + 1)):
            priorities[i] = 7

        self._handle.prioritize_pieces(priorities)

    def _calculate_buffer_bytes(self) -> int:
        """Izračunaj koliko je bajta buffered za video fajl (uzastopno od početka)."""
        if not self._handle or not self._handle.has_metadata():
            return 0

        ti = self._handle.torrent_file()
        if not ti or self._video_file_index < 0:
            return 0

        files = ti.files()
        piece_length = ti.piece_length()
        file_offset = files.file_offset(self._video_file_index)
        file_size = files.file_size(self._video_file_index)
        first_piece = file_offset // piece_length
        last_piece = min((file_offset + file_size - 1) // piece_length, ti.num_pieces() - 1)

        pieces = self._handle.status().pieces
        buffered = 0
        for i in range(first_piece, last_piece + 1):
            if pieces[i]:
                buffered += piece_length

        return min(buffered, file_size)

    def update_playback_position(self, position_seconds: float, duration: float) -> None:
        """Ažuriraj prioritete na osnovu playback pozicije."""
        if not self._handle or not self._handle.has_metadata() or duration <= 0:
            return

        ti = self._handle.torrent_file()
        if not ti or self._video_file_index < 0:
            return

        files = ti.files()
        piece_length = ti.piece_length()
        file_offset = files.file_offset(self._video_file_index)
        file_size = files.file_size(self._video_file_index)

        progress_ratio = position_seconds / duration
        byte_pos = int(file_size * progress_ratio) + file_offset
        current_piece = byte_pos // piece_length

        self._prioritize_for_streaming(current_piece)

        if self._state == TorrentState.READY:
            self._set_state(TorrentState.STREAMING)

    def set_streaming(self) -> None:
        """Označi da je playback počeo."""
        if self._state == TorrentState.READY:
            self._set_state(TorrentState.STREAMING)

    # --- Kontrole ---

    def pause(self) -> None:
        if self._handle:
            self._handle.pause()
            self._set_state(TorrentState.PAUSED)

    def resume(self) -> None:
        if self._handle:
            self._handle.resume()
            self._set_state(TorrentState.DOWNLOADING)

    def stop(self) -> None:
        """Zaustavi download i ukloni torrent."""
        self._running = False
        if self._handle and self._session:
            try:
                self._session.remove_torrent(self._handle)
            except Exception as e:
                logger.warning(f"Greška pri uklanjanju torrenta: {e}")
        self._handle = None
        self._video_file_index = -1
        self._video_file_path = ""
        self._status = TorrentStatus()
        self._set_state(TorrentState.IDLE)

    def shutdown(self) -> None:
        """Ugasi ceo torrent engine."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3)
        self.stop()
        self._session = None
        logger.info("Torrent engine ugašen")

    # --- Getteri ---

    def get_state(self) -> TorrentState:
        return self._state

    def get_status(self) -> TorrentStatus:
        return self._status

    def get_video_file_path(self) -> str:
        return self._video_file_path

    def is_active(self) -> bool:
        return self._state not in (TorrentState.IDLE, TorrentState.ERROR, TorrentState.PAUSED)

    def _set_state(self, new_state: TorrentState) -> None:
        if self._state != new_state:
            self._state = new_state
            self._status.state = new_state
            if self._callbacks.on_state_changed:
                try:
                    self._callbacks.on_state_changed(new_state)
                except Exception as e:
                    logger.error(f"Greška u on_state_changed: {e}")

    @staticmethod
    def is_torrent_source(source: str) -> bool:
        """Proveri da li je source magnet link ili .torrent fajl."""
        if source.startswith("magnet:"):
            return True
        if os.path.isfile(source) and source.lower().endswith(".torrent"):
            return True
        return False

    @staticmethod
    def format_size(bytes_val: int) -> str:
        """Formatiraj bajte u čitljiv string."""
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{bytes_val / 1024 / 1024:.1f} MB"
        else:
            return f"{bytes_val / 1024 / 1024 / 1024:.2f} GB"

    @staticmethod
    def format_speed(bytes_per_sec: float) -> str:
        """Formatiraj brzinu."""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / 1024 / 1024:.2f} MB/s"