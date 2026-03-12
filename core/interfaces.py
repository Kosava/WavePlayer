"""Abstract interfaces for media engine.

These interfaces define the contract between the UI and backend.
They contain NO UI-specific imports and map directly to:
  - C++: pure virtual classes (interfaces)
  - Rust: traits

PORTABILITY NOTES:
  - All methods use simple types (str, int, float, bool)
  - Enums map to C++ enum class / Rust enum
  - Dataclasses map to C++ struct / Rust struct
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Callable, Optional


class PlaybackState(Enum):
    """Stanje reprodukcije - mapira se na enum class u C++."""
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    BUFFERING = auto()


class MediaType(Enum):
    """Tip medija."""
    VIDEO = auto()
    AUDIO = auto()
    UNKNOWN = auto()


class MediaEngineInterface(ABC):
    """Interfejs za media engine.

    Apstraktna klasa koja definiše ugovor za sve media backend-ove.
    U C++ bi ovo bio čist virtualni razred (interface).
    U Rust-u bi ovo bio trait.
    """

    # --- Reprodukcija ---

    @abstractmethod
    def load(self, path: str) -> bool:
        """Učitaj media fajl. Vraća True ako je uspešno."""
        ...

    @abstractmethod
    def play(self) -> None:
        """Pokreni reprodukciju."""
        ...

    @abstractmethod
    def pause(self) -> None:
        """Pauziraj reprodukciju."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Zaustavi reprodukciju i resetuj poziciju."""
        ...

    @abstractmethod
    def seek(self, position_seconds: float) -> None:
        """Preskoči na poziciju u sekundama."""
        ...

    # --- Svojstva ---

    @abstractmethod
    def get_state(self) -> PlaybackState:
        """Trenutno stanje reprodukcije."""
        ...

    @abstractmethod
    def get_duration(self) -> float:
        """Ukupno trajanje u sekundama."""
        ...

    @abstractmethod
    def get_position(self) -> float:
        """Trenutna pozicija u sekundama."""
        ...

    @abstractmethod
    def get_volume(self) -> int:
        """Jačina zvuka (0-100)."""
        ...

    @abstractmethod
    def set_volume(self, volume: int) -> None:
        """Postavi jačinu zvuka (0-100)."""
        ...

    @abstractmethod
    def get_muted(self) -> bool:
        """Da li je zvuk utišan."""
        ...

    @abstractmethod
    def set_muted(self, muted: bool) -> None:
        """Utišaj/pojačaj zvuk."""
        ...

    @abstractmethod
    def get_speed(self) -> float:
        """Brzina reprodukcije (1.0 = normalno)."""
        ...

    @abstractmethod
    def set_speed(self, speed: float) -> None:
        """Postavi brzinu reprodukcije."""
        ...

    # --- Video-specifično ---

    @abstractmethod
    def get_video_width(self) -> int:
        """Širina video zapisa u pikselima."""
        ...

    @abstractmethod
    def get_video_height(self) -> int:
        """Visina video zapisa u pikselima."""
        ...

    # --- Životni ciklus ---

    @abstractmethod
    def initialize(self) -> bool:
        """Inicijalizuj engine. Poziva se jednom pri pokretanju."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Oslobodi resurse. Poziva se pri zatvaranju."""
        ...

    @abstractmethod
    def get_window_id(self) -> Optional[int]:
        """Vrati window ID za video renderovanje (ako postoji)."""
        ...

    @abstractmethod
    def set_window_id(self, wid: int) -> None:
        """Postavi window ID za video renderovanje."""
        ...


class EngineEventCallback:
    """Kontejner za callback-ove iz engine-a.

    U C++ bi ovo bio struct sa std::function memberima.
    U Rust-u bi ovo bio struct sa Box<dyn Fn> memberima.

    UI sloj registruje callback-ove koji se pozivaju
    kada engine promeni stanje.
    """

    def __init__(self) -> None:
        # Svaki callback je Optional[Callable]
        # UI sloj ih postavlja, engine ih poziva
        self.on_state_changed: Optional[Callable[[PlaybackState], None]] = None
        self.on_position_changed: Optional[Callable[[float], None]] = None
        self.on_duration_changed: Optional[Callable[[float], None]] = None
        self.on_volume_changed: Optional[Callable[[int], None]] = None
        self.on_media_loaded: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_end_of_file: Optional[Callable[[], None]] = None

    def emit_state_changed(self, state: PlaybackState) -> None:
        """Emituj promenu stanja."""
        if self.on_state_changed:
            self.on_state_changed(state)

    def emit_position_changed(self, position: float) -> None:
        """Emituj promenu pozicije."""
        if self.on_position_changed:
            self.on_position_changed(position)

    def emit_duration_changed(self, duration: float) -> None:
        """Emituj promenu trajanja."""
        if self.on_duration_changed:
            self.on_duration_changed(duration)

    def emit_volume_changed(self, volume: int) -> None:
        """Emituj promenu jačine zvuka."""
        if self.on_volume_changed:
            self.on_volume_changed(volume)

    def emit_media_loaded(self, path: str) -> None:
        """Emituj učitavanje medija."""
        if self.on_media_loaded:
            self.on_media_loaded(path)

    def emit_error(self, message: str) -> None:
        """Emituj grešku."""
        if self.on_error:
            self.on_error(message)

    def emit_end_of_file(self) -> None:
        """Emituj kraj fajla."""
        if self.on_end_of_file:
            self.on_end_of_file()
