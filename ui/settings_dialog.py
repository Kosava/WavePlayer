"""Settings dialog for WavePlayer.

Comprehensive settings with categorized navigation, theme previews,
OSD customization, keybinding editor, and more.

PORTABILITY NOTES:
  - C++: QDialog with identical widget tree
  - Rust: similar dialog with qt6-rs
"""

import logging
import os
from typing import Optional, Dict, Any, Callable

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QWidget,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QButtonGroup,
    QMessageBox,  # Dodato za plugin dijaloge
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPaintEvent

from core.config import Config
from .themes import (
    THEMES,
    THEME_META,
    ThemeColors,
    get_theme,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  CUSTOM WIDGETS
# ═══════════════════════════════════════════


class ThemePreviewWidget(QFrame):
    """Mali preview widget za jednu temu sa prikazom boja."""

    clicked = pyqtSignal(str)  # theme_key

    def __init__(
        self, theme_key: str, colors: ThemeColors, meta: dict, parent=None
    ) -> None:
        super().__init__(parent)
        self._theme_key = theme_key
        self._colors = colors
        self._meta = meta
        self._selected = False

        self.setObjectName("themeCard")
        self.setFixedSize(130, 100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)

        # Color preview strip
        preview = QFrame(self)
        preview.setFixedHeight(40)
        preview.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {self._colors.bg_primary},
                    stop:0.45 {self._colors.bg_primary},
                    stop:0.5 {self._colors.accent},
                    stop:0.55 {self._colors.accent},
                    stop:1 {self._colors.bg_tertiary}
                );
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.06);
            }}
        """)
        layout.addWidget(preview)

        # Ikona + naziv
        name_layout = QHBoxLayout()
        name_layout.setSpacing(4)
        name_layout.setContentsMargins(0, 0, 0, 0)

        icon = QLabel(self._meta.get("icon", "🎨"))
        icon.setStyleSheet("font-size: 12px; background: transparent;")

        name = QLabel(self._meta.get("name", self._theme_key))
        name.setObjectName("themeCardName")

        name_layout.addWidget(icon)
        name_layout.addWidget(name)
        name_layout.addStretch()
        layout.addLayout(name_layout)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._theme_key)
        super().mousePressEvent(event)


class SettingsRow(QFrame):
    """Jedan red u settings-u: label + control, sa opcionalnim opisom."""

    def __init__(
        self,
        label: str,
        widget: QWidget,
        description: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)

        # Leva strana: label + opis
        left = QVBoxLayout()
        left.setSpacing(2)

        lbl = QLabel(label)
        lbl.setObjectName("settingsLabel")
        left.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setObjectName("settingsSubLabel")
            desc.setWordWrap(True)
            left.addWidget(desc)

        layout.addLayout(left, 1)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)


class SettingsGroup(QFrame):
    """Grupa settings redova sa naslovom."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsGroup")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(4)

        if title:
            title_lbl = QLabel(title)
            title_lbl.setObjectName("settingsGroupTitle")
            self._layout.addWidget(title_lbl)
            self._layout.addSpacing(4)

    def add_row(
        self,
        label: str,
        widget: QWidget,
        description: str = "",
    ) -> SettingsRow:
        row = SettingsRow(label, widget, description, self)
        self._layout.addWidget(row)
        return row

    def add_separator(self) -> None:
        sep = QFrame(self)
        sep.setObjectName("settingsSeparator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        self._layout.addWidget(sep)

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


# ═══════════════════════════════════════════
#  SETTINGS DIALOG
# ═══════════════════════════════════════════


class SettingsDialog(QDialog):
    """Modalni settings dijalog.

    Kategorije u levom sidebaru:
    1. Izgled (Themes + OSD)
    2. Reprodukcija
    3. Audio
    4. Video / Engine
    5. Interfejs
    6. Prečice
    7. Napredno

    Signali:
        theme_changed(str) - emituje se kad korisnik odabere novu temu
        settings_changed() - emituje se kad se bilo koje podešavanje promeni
    """

    DIALOG_WIDTH: int = 820
    DIALOG_HEIGHT: int = 580
    SIDEBAR_WIDTH: int = 180

    theme_changed = pyqtSignal(str)
    settings_changed = pyqtSignal()

    # Navigacione kategorije: (id, ikona, naziv)
    CATEGORIES = [
        ("appearance", "🎨", "Izgled"),
        ("playback", "▶", "Reprodukcija"),
        ("audio", "🔊", "Audio"),
        ("video", "🖥", "Video / Engine"),
        ("subtitles", "💬", "Titlovi"),
        ("torrent", "🔽", "Streaming"),
        ("plugins", "🧩", "Plugini"),
        ("interface", "🪟", "Interfejs"),
        ("shortcuts", "⌨", "Prečice"),
        ("advanced", "⚙", "Napredno"),
    ]

    def __init__(self, config: Config, plugin_mgr=None, parent=None) -> None:
        super().__init__(parent)

        self._config = config
        self._plugin_mgr = plugin_mgr
        self._pending_changes: Dict[str, Any] = {}

        # Trenutne vrednosti za teme
        self._current_theme = config.get("ui.theme", "midnight_red")

        # Preview widgeti za selekciju
        self._theme_cards: Dict[str, ThemePreviewWidget] = {}

        self.setWindowTitle("Settings")
        self.setObjectName("settingsDialog")
        self.setFixedSize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        """Postavi layout: sidebar + stacked content."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame(self)
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(self.SIDEBAR_WIDTH)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 16, 10, 16)
        sidebar_layout.setSpacing(2)

        # Logo/naslov
        title = QLabel("⚙  Settings")
        title.setObjectName("settingsSectionTitle")
        title.setStyleSheet("font-size: 16px; padding: 4px 6px 12px 6px;")
        sidebar_layout.addWidget(title)

        # Navigaciona dugmad
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        for idx, (cat_id, icon, name) in enumerate(self.CATEGORIES):
            btn = QPushButton(f"  {icon}  {name}", self)
            btn.setObjectName("settingsNavBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._nav_group.addButton(btn, idx)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Verzija na dnu
        ver = QLabel("WavePlayer v1.0")
        ver.setObjectName("settingsSubLabel")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # ── Content area ──
        content_frame = QFrame(self)
        content_frame.setObjectName("settingsContent")

        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Stacked widget za stranice
        self._stack = QStackedWidget(content_frame)

        # Kreiraj sve stranice
        self._stack.addWidget(self._create_appearance_page())
        self._stack.addWidget(self._create_playback_page())
        self._stack.addWidget(self._create_audio_page())
        self._stack.addWidget(self._create_video_page())
        self._stack.addWidget(self._create_subtitles_page())
        self._stack.addWidget(self._create_torrent_page())
        self._stack.addWidget(self._create_plugins_page())  # Izmenjena plugin stranica
        self._stack.addWidget(self._create_interface_page())
        self._stack.addWidget(self._create_shortcuts_page())
        self._stack.addWidget(self._create_advanced_page())

        content_layout.addWidget(self._stack, 1)

        # Donji bar sa dugmadima
        bottom_bar = QFrame(content_frame)
        bottom_bar.setFixedHeight(56)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 10, 20, 10)
        bottom_layout.setSpacing(10)

        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.setObjectName("settingsSecondaryBtn")
        self._reset_btn.clicked.connect(self._on_reset)

        bottom_layout.addWidget(self._reset_btn)
        bottom_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("settingsSecondaryBtn")
        self._cancel_btn.clicked.connect(self.reject)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("settingsPrimaryBtn")
        self._apply_btn.clicked.connect(self._on_apply)

        bottom_layout.addWidget(self._cancel_btn)
        bottom_layout.addWidget(self._apply_btn)

        content_layout.addWidget(bottom_bar)

        main_layout.addWidget(content_frame, 1)

        # Poveži navigaciju
        self._nav_group.idClicked.connect(self._stack.setCurrentIndex)

        # Selektuj prvu stranicu
        first_btn = self._nav_group.button(0)
        if first_btn:
            first_btn.setChecked(True)

    # ═══════════════════════════════════════════
    #  PAGE BUILDERS
    # ═══════════════════════════════════════════

    def _make_scroll_page(self) -> tuple:
        """Napravi scroll area stranicu. Vraća (scroll_area, content_layout)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        scroll.setWidget(inner)
        return scroll, layout

    def _add_page_header(self, layout: QVBoxLayout, title: str, desc: str = "") -> None:
        """Dodaj naslov i opis stranice."""
        t = QLabel(title)
        t.setObjectName("settingsSectionTitle")
        layout.addWidget(t)
        if desc:
            d = QLabel(desc)
            d.setObjectName("settingsSectionDesc")
            d.setWordWrap(True)
            layout.addWidget(d)
        layout.addSpacing(4)

    # ── 1. Izgled ──

    def _create_appearance_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Izgled", "Odaberite temu za player i OSD overlay")

        # Player teme
        group1 = SettingsGroup("Player tema")

        theme_grid = QGridLayout()
        theme_grid.setSpacing(10)

        col = 0
        row = 0
        for key in THEMES:
            meta = THEME_META.get(key, {"name": key, "icon": "🎨"})
            card = ThemePreviewWidget(key, THEMES[key], meta)
            card.clicked.connect(self._on_theme_selected)
            self._theme_cards[key] = card
            theme_grid.addWidget(card, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

        container = QWidget()
        container.setLayout(theme_grid)
        container.setStyleSheet("background: transparent;")
        group1.add_widget(container)
        layout.addWidget(group1)

        # OSD podešavanja
        group3 = SettingsGroup("OSD podešavanja")

        self._osd_display_ms = QSpinBox()
        self._osd_display_ms.setObjectName("settingsSpin")
        self._osd_display_ms.setRange(500, 10000)
        self._osd_display_ms.setSingleStep(100)
        self._osd_display_ms.setSuffix(" ms")
        group3.add_row("Trajanje prikaza", self._osd_display_ms,
                        "Koliko dugo OSD poruka ostaje na ekranu")

        self._osd_show_check = QCheckBox("Omogući")
        group3.add_row("Prikaži OSD", self._osd_show_check,
                        "Prikaži indikatore za volume, seek, play/pause")

        layout.addWidget(group3)
        layout.addStretch()
        return scroll

    # ── 2. Reprodukcija ──

    def _create_playback_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Reprodukcija", "Podešavanja reprodukcije medija")

        group1 = SettingsGroup("Opšte")

        self._resume_check = QCheckBox("Omogući")
        group1.add_row("Nastavi reprodukciju", self._resume_check,
                        "Nastavi od poslednje pozicije pri otvaranju fajla")

        self._default_speed = QDoubleSpinBox()
        self._default_speed.setObjectName("settingsSpin")
        self._default_speed.setRange(0.25, 4.0)
        self._default_speed.setSingleStep(0.25)
        self._default_speed.setDecimals(2)
        self._default_speed.setSuffix("x")
        group1.add_row("Podrazumevana brzina", self._default_speed,
                        "Brzina reprodukcije pri pokretanju")

        self._auto_play_check = QCheckBox("Omogući")
        group1.add_row("Auto-play", self._auto_play_check,
                        "Automatski pusti fajl kad se učita")

        layout.addWidget(group1)

        group2 = SettingsGroup("Seeking")

        self._seek_step = QSpinBox()
        self._seek_step.setObjectName("settingsSpin")
        self._seek_step.setRange(1, 60)
        self._seek_step.setSuffix(" sec")
        group2.add_row("Korak preskakanja", self._seek_step,
                        "Koliko sekundi preskoči strelicama levo/desno")

        self._precise_seek = QCheckBox("Omogući")
        group2.add_row("Precizan seek", self._precise_seek,
                        "Precizniji ali sporiji seek do tačnog frejma")

        layout.addWidget(group2)

        group3 = SettingsGroup("Playlist")

        self._loop_combo = QComboBox()
        self._loop_combo.setObjectName("settingsCombo")
        self._loop_combo.addItems(["Bez ponavljanja", "Ponovi playlist", "Ponovi fajl"])
        group3.add_row("Ponavljanje", self._loop_combo)

        self._shuffle_check = QCheckBox("Omogući")
        group3.add_row("Nasumičan redosled", self._shuffle_check)

        layout.addWidget(group3)
        layout.addStretch()
        return scroll

    # ── 3. Audio ──

    def _create_audio_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Audio", "Podešavanja zvuka")

        group1 = SettingsGroup("Jačina zvuka")

        self._default_volume = QSlider(Qt.Orientation.Horizontal)
        self._default_volume.setObjectName("volumeSlider")
        self._default_volume.setRange(0, 100)
        self._default_volume.setFixedWidth(180)
        group1.add_row("Podrazumevana jačina", self._default_volume,
                        "Početna jačina zvuka pri pokretanju")

        self._volume_step = QSpinBox()
        self._volume_step.setObjectName("settingsSpin")
        self._volume_step.setRange(1, 25)
        self._volume_step.setSuffix("%")
        group1.add_row("Korak jačine", self._volume_step,
                        "Koliko % menja strelica gore/dole")

        self._volume_boost = QCheckBox("Omogući (do 150%)")
        group1.add_row("Pojačanje zvuka", self._volume_boost,
                        "Dozvoli pojačanje iznad 100%")

        layout.addWidget(group1)

        group2 = SettingsGroup("Audio izlaz")

        self._audio_device = QComboBox()
        self._audio_device.setObjectName("settingsCombo")
        self._audio_device.addItems(["Sistemski default", "PulseAudio", "ALSA", "JACK"])
        group2.add_row("Audio uređaj", self._audio_device)

        self._normalize_check = QCheckBox("Omogući")
        group2.add_row("Normalizacija", self._normalize_check,
                        "Ujednači jačinu zvuka između fajlova")

        layout.addWidget(group2)
        layout.addStretch()
        return scroll

    # ── 4. Video / Engine ──

    def _create_video_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Video / Engine", "Podešavanja video renderovanja")

        group1 = SettingsGroup("Renderovanje")

        self._hw_decode = QComboBox()
        self._hw_decode.setObjectName("settingsCombo")
        self._hw_decode.addItems(["Auto", "vaapi", "vdpau", "nvdec", "Isključeno"])
        group1.add_row("Hardversko dekodiranje", self._hw_decode,
                        "Koristite GPU za dekodiranje videa")

        self._vo_combo = QComboBox()
        self._vo_combo.setObjectName("settingsCombo")
        self._vo_combo.addItems(["gpu", "gpu-next", "x11", "wayland"])
        group1.add_row("Video output", self._vo_combo,
                        "MPV video output backend")

        self._deinterlace = QCheckBox("Omogući")
        group1.add_row("Deinterlacing", self._deinterlace,
                        "Automatski deinterlace za stari sadržaj")

        layout.addWidget(group1)

        group2 = SettingsGroup("Kvalitet")

        self._scale_combo = QComboBox()
        self._scale_combo.setObjectName("settingsCombo")
        self._scale_combo.addItems(["bilinear", "spline36", "ewa_lanczos", "ewa_lanczossharp"])
        group2.add_row("Scaling algoritam", self._scale_combo,
                        "Metod za skaliranje videa")

        self._dither_check = QCheckBox("Omogući")
        group2.add_row("Dithering", self._dither_check)

        self._icc_check = QCheckBox("Omogući")
        group2.add_row("ICC profil", self._icc_check,
                        "Koristi ICC kolor profil monitora")

        layout.addWidget(group2)
        layout.addStretch()
        return scroll

    # ── 5. Titlovi (bomi-style comprehensive) ──

    def _create_subtitles_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Titlovi", "Kompletna podešavanja titlova — učitavanje, izgled, pozicija i sinhronizacija")

        # ── Učitavanje ──
        g_load = SettingsGroup("Učitavanje titlova")

        self._sub_auto = QComboBox()
        self._sub_auto.setObjectName("settingsCombo")
        self._sub_auto.addItems([
            "Tačan naziv fajla",
            "Sadrži naziv videa",
            "Svi iz istog foldera",
            "Isključeno",
        ])
        g_load.add_row("Automatsko učitavanje", self._sub_auto,
                        "Kako tražiti titlove pored video fajla")

        self._sub_preferred_lang = QComboBox()
        self._sub_preferred_lang.setObjectName("settingsCombo")
        self._sub_preferred_lang.setEditable(True)
        self._sub_preferred_lang.addItems([
            "sr", "srp", "serbian", "hr", "bs",
            "en", "eng", "english",
            "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "zh",
        ])
        g_load.add_row("Preferiran jezik", self._sub_preferred_lang,
                        "ISO 639 kod ili naziv jezika (mpv --slang)")

        self._sub_fallback_lang = QComboBox()
        self._sub_fallback_lang.setObjectName("settingsCombo")
        self._sub_fallback_lang.setEditable(True)
        self._sub_fallback_lang.addItems([
            "en", "eng", "english",
            "sr", "srp", "hr",
        ])
        g_load.add_row("Rezervni jezik", self._sub_fallback_lang,
                        "Koristi ako preferiran jezik nije dostupan")

        self._sub_auto_select = QCheckBox("Omogući")
        g_load.add_row("Auto-selekcija", self._sub_auto_select,
                        "Automatski odaberi prvi titl koji odgovara jeziku")

        self._sub_encoding = QComboBox()
        self._sub_encoding.setObjectName("settingsCombo")
        self._sub_encoding.addItems([
            "Auto-detect",
            "UTF-8",
            "UTF-8-BOM",
            "Windows-1250 (Central European)",
            "Windows-1251 (Cyrillic)",
            "Windows-1252 (Western)",
            "ISO-8859-1 (Latin-1)",
            "ISO-8859-2 (Latin-2 / Central)",
            "ISO-8859-5 (Cyrillic)",
            "ISO-8859-9 (Turkish)",
            "ISO-8859-15 (Latin-9)",
            "ISO-8859-16 (Romanian)",
            "EUC-JP",
            "Shift_JIS",
            "EUC-KR",
            "Big5",
            "GB2312",
            "GBK",
            "GB18030",
            "KOI8-R",
            "KOI8-U",
        ])
        g_load.add_row("Enkodiranje", self._sub_encoding,
                        "Kodna strana za SRT/ASS tekstualne titlove")

        self._sub_fix_timing = QCheckBox("Omogući")
        g_load.add_row("Popravi tajming", self._sub_fix_timing,
                        "Pokušaj ispraviti neusklađen tajming titla (--sub-fix-timing)")

        layout.addWidget(g_load)

        # ── Font & tekst ──
        g_font = SettingsGroup("Font i tekst")

        self._sub_font_family = QComboBox()
        self._sub_font_family.setObjectName("settingsCombo")
        self._sub_font_family.setEditable(True)
        self._sub_font_family.addItems([
            "Sans-Serif",
            "Arial",
            "Helvetica",
            "Noto Sans",
            "Roboto",
            "Open Sans",
            "Liberation Sans",
            "DejaVu Sans",
            "Segoe UI",
            "SF Pro Display",
            "Verdana",
            "Tahoma",
            "Trebuchet MS",
            "Ubuntu",
            "Cantarell",
        ])
        g_font.add_row("Font", self._sub_font_family,
                        "Može biti bilo koji instalirani sistemski font")

        self._sub_font_size = QSpinBox()
        self._sub_font_size.setObjectName("settingsSpin")
        self._sub_font_size.setRange(12, 120)
        self._sub_font_size.setSuffix(" px")
        g_font.add_row("Veličina fonta", self._sub_font_size)

        self._sub_bold = QCheckBox("Omogući")
        g_font.add_row("Podebljano (Bold)", self._sub_bold)

        self._sub_italic = QCheckBox("Omogući")
        g_font.add_row("Kurziv (Italic)", self._sub_italic)

        layout.addWidget(g_font)

        # ── Boje ──
        g_colors = SettingsGroup("Boje")

        self._sub_color = QComboBox()
        self._sub_color.setObjectName("settingsCombo")
        self._sub_color.addItems([
            "Bela (#FFFFFF)",
            "Žuta (#FFFF00)",
            "Svetložuta (#FFFACD)",
            "Zelena (#00FF00)",
            "Svetloplava (#00FFFF)",
            "Svetlonarandžasta (#FFD700)",
            "Svetloružičasta (#FFB6C1)",
            "Prilagođena...",
        ])
        g_colors.add_row("Boja teksta", self._sub_color,
                          "Primarna boja titla")

        self._sub_border_color = QComboBox()
        self._sub_border_color.setObjectName("settingsCombo")
        self._sub_border_color.addItems([
            "Crna (#000000)",
            "Tamnosiva (#333333)",
            "Siva (#808080)",
            "Providna",
            "Prilagođena...",
        ])
        g_colors.add_row("Boja ivice", self._sub_border_color,
                          "Boja obruba oko teksta")

        self._sub_border_size = QDoubleSpinBox()
        self._sub_border_size.setObjectName("settingsSpin")
        self._sub_border_size.setRange(0.0, 10.0)
        self._sub_border_size.setSingleStep(0.5)
        self._sub_border_size.setDecimals(1)
        self._sub_border_size.setSuffix(" px")
        g_colors.add_row("Debljina ivice", self._sub_border_size,
                          "Debljina obruba oko slova (0 = bez)")

        self._sub_shadow_color = QComboBox()
        self._sub_shadow_color.setObjectName("settingsCombo")
        self._sub_shadow_color.addItems([
            "Crna (#000000)",
            "Tamnosiva (#222222)",
            "Providna (bez senke)",
            "Prilagođena...",
        ])
        g_colors.add_row("Boja senke", self._sub_shadow_color)

        self._sub_shadow_offset = QDoubleSpinBox()
        self._sub_shadow_offset.setObjectName("settingsSpin")
        self._sub_shadow_offset.setRange(0.0, 10.0)
        self._sub_shadow_offset.setSingleStep(0.5)
        self._sub_shadow_offset.setDecimals(1)
        self._sub_shadow_offset.setSuffix(" px")
        g_colors.add_row("Pomeraj senke", self._sub_shadow_offset,
                          "Rastojanje senke od teksta")

        self._sub_bg_enabled = QCheckBox("Omogući")
        g_colors.add_row("Pozadina iza teksta", self._sub_bg_enabled,
                          "Poluprovidni pravougaonik iza titla")

        self._sub_bg_color = QComboBox()
        self._sub_bg_color.setObjectName("settingsCombo")
        self._sub_bg_color.addItems([
            "Crna (80% providna)",
            "Crna (50% providna)",
            "Crna (potpuna)",
            "Tamnosiva",
            "Prilagođena...",
        ])
        g_colors.add_row("Boja pozadine", self._sub_bg_color)

        self._sub_bg_padding = QSpinBox()
        self._sub_bg_padding.setObjectName("settingsSpin")
        self._sub_bg_padding.setRange(0, 50)
        self._sub_bg_padding.setSuffix(" px")
        g_colors.add_row("Padding pozadine", self._sub_bg_padding,
                          "Prostor oko teksta unutar pozadine")

        layout.addWidget(g_colors)

        # ── Pozicija & layout ──
        g_pos = SettingsGroup("Pozicija i raspored")

        self._sub_position = QSlider(Qt.Orientation.Horizontal)
        self._sub_position.setObjectName("volumeSlider")
        self._sub_position.setRange(0, 100)
        self._sub_position.setFixedWidth(200)
        g_pos.add_row("Vertikalna pozicija", self._sub_position,
                       "0 = vrh ekrana, 100 = dno ekrana")

        self._sub_margin_v = QSpinBox()
        self._sub_margin_v.setObjectName("settingsSpin")
        self._sub_margin_v.setRange(0, 200)
        self._sub_margin_v.setSuffix(" px")
        g_pos.add_row("Donja margina", self._sub_margin_v,
                       "Razmak od dna videa do titla")

        self._sub_margin_h = QSpinBox()
        self._sub_margin_h.setObjectName("settingsSpin")
        self._sub_margin_h.setRange(0, 300)
        self._sub_margin_h.setSuffix(" px")
        g_pos.add_row("Bočna margina", self._sub_margin_h,
                       "Horizontalno ograničenje teksta")

        self._sub_alignment = QComboBox()
        self._sub_alignment.setObjectName("settingsCombo")
        self._sub_alignment.addItems([
            "Centar (dole)",
            "Centar (gore)",
            "Centar (sredina)",
            "Levo (dole)",
            "Desno (dole)",
        ])
        g_pos.add_row("Poravnanje", self._sub_alignment,
                       "Pozicija titla na ekranu")

        self._sub_scale_with_window = QCheckBox("Omogući")
        g_pos.add_row("Skaliraj sa prozorom", self._sub_scale_with_window,
                       "Veličina titla prati veličinu prozora")

        self._sub_justify = QComboBox()
        self._sub_justify.setObjectName("settingsCombo")
        self._sub_justify.addItems([
            "Auto",
            "Levo",
            "Centar",
            "Desno",
        ])
        g_pos.add_row("Poravnanje teksta", self._sub_justify,
                       "Horizontalno poravnanje višelinijskih titlova")

        layout.addWidget(g_pos)

        # ── Sinhronizacija ──
        g_sync = SettingsGroup("Sinhronizacija")

        self._sub_delay = QDoubleSpinBox()
        self._sub_delay.setObjectName("settingsSpin")
        self._sub_delay.setRange(-30.0, 30.0)
        self._sub_delay.setSingleStep(0.1)
        self._sub_delay.setDecimals(1)
        self._sub_delay.setSuffix(" sec")
        g_sync.add_row("Kašnjenje titla", self._sub_delay,
                        "Pomeri titl napred (+) ili nazad (-) u vremenu")

        self._sub_speed = QDoubleSpinBox()
        self._sub_speed.setObjectName("settingsSpin")
        self._sub_speed.setRange(0.1, 10.0)
        self._sub_speed.setSingleStep(0.01)
        self._sub_speed.setDecimals(2)
        self._sub_speed.setSuffix("x")
        g_sync.add_row("Brzina titla", self._sub_speed,
                        "Ubrzaj/uspori tajming (za film vs. TV verzije)")

        self._sub_fps_override = QComboBox()
        self._sub_fps_override.setObjectName("settingsCombo")
        self._sub_fps_override.setEditable(True)
        self._sub_fps_override.addItems([
            "Auto",
            "23.976",
            "24.000",
            "25.000",
            "29.970",
            "30.000",
        ])
        g_sync.add_row("FPS titla", self._sub_fps_override,
                        "Zameni frame rate za tajming MicroDVD titlova")

        layout.addWidget(g_sync)

        # ── ASS/SSA override ──
        g_ass = SettingsGroup("ASS / SSA stilovi")

        self._sub_ass_override = QComboBox()
        self._sub_ass_override.setObjectName("settingsCombo")
        self._sub_ass_override.addItems([
            "Poštuj originalni stil",
            "Zameni samo font",
            "Zameni sve stilove",
            "Forsiraj moja podešavanja",
        ])
        g_ass.add_row("ASS override", self._sub_ass_override,
                       "Koliko tvojih podešavanja primeni na ASS titlove")

        self._sub_ass_hinting = QComboBox()
        self._sub_ass_hinting.setObjectName("settingsCombo")
        self._sub_ass_hinting.addItems([
            "Bez (none)",
            "Lagan (light)",
            "Normalan (normal)",
            "Nativni (native)",
        ])
        g_ass.add_row("Font hinting", self._sub_ass_hinting,
                       "Način renderovanja ivica slova")

        self._sub_ass_shaping = QComboBox()
        self._sub_ass_shaping.setObjectName("settingsCombo")
        self._sub_ass_shaping.addItems([
            "Jednostavan (simple)",
            "Složen (complex / HarfBuzz)",
        ])
        g_ass.add_row("Text shaping", self._sub_ass_shaping,
                       "Complex je bolji za ne-latinska pisma")

        self._sub_vsfilter_compat = QCheckBox("Omogući")
        g_ass.add_row("VSFilter kompatibilnost", self._sub_vsfilter_compat,
                       "Skaliraj ASS stilove kao VSFilter (za stare titlove)")

        self._sub_ass_force_margins = QCheckBox("Omogući")
        g_ass.add_row("Forsiraj margine", self._sub_ass_force_margins,
                       "Primeni tvoje margine i na ASS titlove")

        self._sub_stretch_ass = QCheckBox("Omogući")
        g_ass.add_row("Razvuci za prikaz", self._sub_stretch_ass,
                       "Razvuci ASS titlove ako se aspect ratio razlikuje")

        layout.addWidget(g_ass)

        # ── Napredno ──
        g_adv = SettingsGroup("Napredne opcije")

        self._sub_secondary_enabled = QCheckBox("Omogući")
        g_adv.add_row("Dvojni titlovi", self._sub_secondary_enabled,
                       "Prikaži dva titla istovremeno (npr. original + prevod)")

        self._sub_secondary_lang = QComboBox()
        self._sub_secondary_lang.setObjectName("settingsCombo")
        self._sub_secondary_lang.setEditable(True)
        self._sub_secondary_lang.addItems([
            "en", "eng", "english",
            "sr", "srp", "hr",
            "de", "fr", "es", "ja",
        ])
        g_adv.add_row("Jezik drugog titla", self._sub_secondary_lang,
                       "Jezik za sekundarni titl (--secondary-sid)")

        self._sub_blend = QComboBox()
        self._sub_blend.setObjectName("settingsCombo")
        self._sub_blend.addItems([
            "Isključeno",
            "Da (video frame)",
            "Da (video + OSD)",
        ])
        g_adv.add_row("Blendovanje u video", self._sub_blend,
                       "Renderiši titl direktno u video frame")

        self._sub_clear_on_seek = QCheckBox("Omogući")
        g_adv.add_row("Obriši pri seek-u", self._sub_clear_on_seek,
                       "Ukloni trenutni titl pri preskakanju")

        self._sub_gray = QCheckBox("Omogući")
        g_adv.add_row("Crno-beli titlovi", self._sub_gray,
                       "Konvertuj obojene titlove u sive tonove")

        self._sub_filter_sdh = QCheckBox("Omogući")
        g_adv.add_row("Filtriraj SDH", self._sub_filter_sdh,
                       "Ukloni opise zvukova [music], (laughter) itd.")

        self._sub_filter_regex = QComboBox()
        self._sub_filter_regex.setObjectName("settingsCombo")
        self._sub_filter_regex.setEditable(True)
        self._sub_filter_regex.addItems([
            "",
            r"\[.*?\]",
            r"\(.*?\)",
            r"<[^>]+>",
            r"♪.*?♪",
        ])
        g_adv.add_row("Regex filter", self._sub_filter_regex,
                       "Custom regex za filtriranje teksta iz titlova")

        layout.addWidget(g_adv)
        layout.addStretch()
        return scroll

    # ── 6. Torrent ──

    def _create_torrent_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Streaming", "YouTube, torrent i mrežni streamovi")

        # ── YouTube ──
        g_yt = SettingsGroup("YouTube (yt-dlp)")

        self._yt_quality = QComboBox()
        self._yt_quality.setObjectName("settingsCombo")
        self._yt_quality.addItems([
            "Audio Only",
            "360p",
            "480p",
            "720p",
            "1080p",
            "Best",
        ])
        g_yt.add_row("Podrazumevani kvalitet", self._yt_quality,
                      "Default kvalitet za YouTube — može se promeniti i u YouTube dialogu")

        self._yt_max_playlist = QSpinBox()
        self._yt_max_playlist.setObjectName("settingsSpin")
        self._yt_max_playlist.setRange(10, 500)
        self._yt_max_playlist.setSingleStep(10)
        g_yt.add_row("Max stavki u playlisti", self._yt_max_playlist,
                      "Koliko stavki maksimalno izvući iz YouTube playliste")

        layout.addWidget(g_yt)

        # ── Download ──
        g_dl = SettingsGroup("Preuzimanje")

        self._torrent_dir = QComboBox()
        self._torrent_dir.setObjectName("settingsCombo")
        self._torrent_dir.setEditable(True)
        self._torrent_dir.addItems([
            "",
            os.path.expanduser("~/Downloads/WavePlayer"),
            os.path.expanduser("~/Downloads"),
            "/tmp/waveplayer",
        ])
        g_dl.add_row("Download folder", self._torrent_dir,
                      "Gde se čuvaju preuzeti fajlovi (prazno = ~/Downloads/WavePlayer)")

        self._torrent_buffer = QSpinBox()
        self._torrent_buffer.setObjectName("settingsSpin")
        self._torrent_buffer.setRange(50, 5000)
        self._torrent_buffer.setSingleStep(50)
        self._torrent_buffer.setSuffix(" MB")
        g_dl.add_row("Buffer pre reprodukcije", self._torrent_buffer,
                      "Koliko MB preuzeti pre nego što se video pokrene")

        self._torrent_prealloc = QCheckBox("Omogući")
        g_dl.add_row("Pre-alokacija diska", self._torrent_prealloc,
                      "Zauzmi prostor na disku unapred (sporije ali manje fragmentacije)")

        self._torrent_delete = QCheckBox("Omogući")
        g_dl.add_row("Obriši pri zatvaranju", self._torrent_delete,
                      "Obriši preuzete fajlove kad se player zatvori")

        layout.addWidget(g_dl)

        # ── Brzina ──
        g_speed = SettingsGroup("Ograničenja brzine")

        self._torrent_max_dl = QSpinBox()
        self._torrent_max_dl.setObjectName("settingsSpin")
        self._torrent_max_dl.setRange(0, 100000)
        self._torrent_max_dl.setSingleStep(100)
        self._torrent_max_dl.setSuffix(" KB/s")
        self._torrent_max_dl.setSpecialValueText("Neograničeno")
        g_speed.add_row("Max download", self._torrent_max_dl,
                         "0 = neograničeno")

        self._torrent_max_ul = QSpinBox()
        self._torrent_max_ul.setObjectName("settingsSpin")
        self._torrent_max_ul.setRange(0, 100000)
        self._torrent_max_ul.setSingleStep(100)
        self._torrent_max_ul.setSuffix(" KB/s")
        self._torrent_max_ul.setSpecialValueText("Neograničeno")
        g_speed.add_row("Max upload", self._torrent_max_ul,
                         "0 = neograničeno")

        self._torrent_connections = QSpinBox()
        self._torrent_connections.setObjectName("settingsSpin")
        self._torrent_connections.setRange(10, 1000)
        self._torrent_connections.setSingleStep(10)
        g_speed.add_row("Max konekcija", self._torrent_connections,
                         "Maksimalan broj istovremenih konekcija")

        layout.addWidget(g_speed)

        # ── Mreža ──
        g_net = SettingsGroup("Mreža")

        self._torrent_port_min = QSpinBox()
        self._torrent_port_min.setObjectName("settingsSpin")
        self._torrent_port_min.setRange(1024, 65535)
        g_net.add_row("Port (od)", self._torrent_port_min,
                       "Početni port za slušanje")

        self._torrent_port_max = QSpinBox()
        self._torrent_port_max.setObjectName("settingsSpin")
        self._torrent_port_max.setRange(1024, 65535)
        g_net.add_row("Port (do)", self._torrent_port_max)

        self._torrent_dht = QCheckBox("Omogući")
        g_net.add_row("DHT", self._torrent_dht,
                       "Distributed Hash Table za pronalaženje peer-ova")

        self._torrent_encryption = QComboBox()
        self._torrent_encryption.setObjectName("settingsCombo")
        self._torrent_encryption.addItems(["Isključeno", "Omogućeno", "Forsirano"])
        g_net.add_row("Enkripcija", self._torrent_encryption,
                       "Enkriptovana komunikacija sa peer-ovima")

        layout.addWidget(g_net)

        # ── Seeding ──
        g_seed = SettingsGroup("Seeding")

        self._torrent_seed = QCheckBox("Omogući")
        g_seed.add_row("Seed nakon preuzimanja", self._torrent_seed,
                        "Nastavi upload nakon kompletnog preuzimanja")

        self._torrent_ratio = QDoubleSpinBox()
        self._torrent_ratio.setObjectName("settingsSpin")
        self._torrent_ratio.setRange(0.0, 100.0)
        self._torrent_ratio.setSingleStep(0.1)
        self._torrent_ratio.setDecimals(1)
        self._torrent_ratio.setSuffix("x")
        g_seed.add_row("Seed ratio", self._torrent_ratio,
                        "Zaustavi seed kad dostigne ovaj ratio (0 = seed zauvek)")

        layout.addWidget(g_seed)
        layout.addStretch()
        return scroll

    # ── 7. Plugini ──

    def _create_plugins_page(self) -> QWidget:
        """Plugin stranica sa enable/configure opcijama."""
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Plugini", "Instalirani WavePlayer plugini")

        group = SettingsGroup("Instalirani plugini")

        if not self._plugin_mgr:
            group.add_widget(QLabel("Plugin manager nije dostupan"))
            layout.addWidget(group)
            return scroll

        for plugin in self._plugin_mgr.get_all_plugins():
            # Dohvati info — koristi get_info() ako postoji, inače atribute
            if hasattr(plugin, "get_info"):
                info = plugin.get_info()
                name = info.name
                version = info.version
                desc = info.description
                icon = info.icon
            else:
                name = getattr(plugin, "name", plugin.__class__.__name__)
                version = getattr(plugin, "version", "1.0")
                desc = getattr(plugin, "description", "")
                icon = "🧩"

            container = QFrame()
            container.setObjectName("pluginCard")
            container.setStyleSheet("""
                QFrame#pluginCard {
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 8px;
                    padding: 8px;
                    margin-bottom: 4px;
                }
            """)

            # Glavni layout: info levo | kontrole desno
            row = QHBoxLayout(container)
            row.setContentsMargins(10, 8, 10, 8)
            row.setSpacing(12)

            # ── Leva strana: ikona + ime + opis ──
            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)

            title_label = QLabel(f"{icon}  {name}")
            title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
            info_layout.addWidget(title_label)

            if desc:
                desc_label = QLabel(desc)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet("font-size: 11px; color: #888;")
                info_layout.addWidget(desc_label)

            version_label = QLabel(f"v{version}")
            version_label.setStyleSheet("font-size: 10px; color: #666;")
            info_layout.addWidget(version_label)

            row.addLayout(info_layout, 1)  # stretch=1 da uzme prostor

            # ── Desna strana: toggle + configure ──
            controls = QVBoxLayout()
            controls.setSpacing(6)
            controls.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            enabled_chk = QCheckBox("Aktivan")
            enabled_chk.setChecked(
                self._config.get_plugin_enabled(name, True)
            )
            enabled_chk.stateChanged.connect(
                lambda state, n=name: self._toggle_plugin(n, state)
            )
            controls.addWidget(enabled_chk)

            if hasattr(plugin, "configure"):
                config_btn = QPushButton("⚙ Podesi")
                config_btn.setFixedWidth(90)
                config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                config_btn.clicked.connect(
                    lambda _, p=plugin: self._configure_plugin(p)
                )
                controls.addWidget(config_btn)

            row.addLayout(controls)

            group.add_widget(container)

        layout.addWidget(group)

        # Reload dugme
        reload_layout = QHBoxLayout()
        reload_layout.addStretch()
        reload_btn = QPushButton("🔄 Ponovo učitaj plugine")
        reload_btn.clicked.connect(self._reload_plugins)
        reload_layout.addWidget(reload_btn)
        layout.addLayout(reload_layout)

        layout.addStretch()
        return scroll

    # ── 8. Interfejs ──

    def _create_interface_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Interfejs", "Podešavanja korisničkog interfejsa")

        group1 = SettingsGroup("Prozor")

        self._remember_size = QCheckBox("Omogući")
        group1.add_row("Pamti veličinu prozora", self._remember_size,
                        "Sačuvaj poziciju i veličinu pri zatvaranju")

        self._remember_pos = QCheckBox("Omogući")
        group1.add_row("Pamti poziciju", self._remember_pos)

        self._start_maximized = QCheckBox("Omogući")
        group1.add_row("Pokreni maksimizovano", self._start_maximized)

        layout.addWidget(group1)

        group2 = SettingsGroup("Auto-hide kontrola")

        self._auto_hide = QCheckBox("Omogući")
        group2.add_row("Auto-hide kontrole", self._auto_hide,
                        "Automatski sakrij kontrole tokom reprodukcije")

        self._auto_hide_delay = QSpinBox()
        self._auto_hide_delay.setObjectName("settingsSpin")
        self._auto_hide_delay.setRange(500, 10000)
        self._auto_hide_delay.setSingleStep(500)
        self._auto_hide_delay.setSuffix(" ms")
        group2.add_row("Kašnjenje sakrivanja", self._auto_hide_delay,
                        "Vreme pre nego što se kontrole sakriju")

        self._auto_hide_cursor = QCheckBox("Omogući")
        group2.add_row("Sakrij kursor", self._auto_hide_cursor,
                        "Sakrij kursor miša zajedno sa kontrolama")

        layout.addWidget(group2)

        group3 = SettingsGroup("Playlist panel")

        self._playlist_width = QSpinBox()
        self._playlist_width.setObjectName("settingsSpin")
        self._playlist_width.setRange(200, 600)
        self._playlist_width.setSingleStep(10)
        self._playlist_width.setSuffix(" px")
        group3.add_row("Širina panela", self._playlist_width)

        self._playlist_show_duration = QCheckBox("Omogući")
        group3.add_row("Prikaži trajanje", self._playlist_show_duration,
                        "Prikaži trajanje pored naziva stavke")

        layout.addWidget(group3)
        layout.addStretch()
        return scroll

    # ── 9. Prečice ──

    def _create_shortcuts_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Prečice", "Tastaturne prečice")

        shortcuts = [
            ("Play / Pause", "Space"),
            ("Stop", "S"),
            ("Fullscreen", "F / F11"),
            ("Izlaz iz fullscreen-a", "Escape"),
            ("Jačina zvuka +", "↑ (Up)"),
            ("Jačina zvuka -", "↓ (Down)"),
            ("Preskoči napred", "→ (Right)"),
            ("Preskoči nazad", "← (Left)"),
            ("Mute / Unmute", "M"),
            ("Otvori fajl", "Ctrl+O"),
            ("Mrežni stream", "Ctrl+U"),
            ("Torrent stream", "Ctrl+T"),
            ("Welcome screen", "Home"),
            ("Show / hide playlist", "L"),
            ("Sledeći u playlisti", "N"),
            ("Prethodni u playlisti", "P"),
            ("Podešavanja", "Ctrl+,"),
            ("Zatvori", "Ctrl+Q"),
        ]

        group = SettingsGroup("Tastaturne prečice")

        for action_name, key_text in shortcuts:
            key_label = QLabel(key_text)
            key_label.setObjectName("settingsValue")
            key_label.setStyleSheet("""
                padding: 4px 10px;
                border-radius: 4px;
                background-color: rgba(255,255,255,0.05);
            """)
            group.add_row(action_name, key_label)

        note = QLabel("⚡ Prilagođavanje prečica biće dostupno u budućoj verziji")
        note.setObjectName("settingsSubLabel")
        note.setStyleSheet("padding: 8px 0;")
        group.add_widget(note)

        layout.addWidget(group)
        layout.addStretch()
        return scroll

    # ── 10. Napredno ──

    def _create_advanced_page(self) -> QWidget:
        scroll, layout = self._make_scroll_page()
        self._add_page_header(layout, "Napredno", "Napredna podešavanja za iskusne korisnike")

        group1 = SettingsGroup("MPV opcije")

        self._mpv_log_level = QComboBox()
        self._mpv_log_level.setObjectName("settingsCombo")
        self._mpv_log_level.addItems(["no", "fatal", "error", "warn", "info", "v", "debug"])
        group1.add_row("Log nivo", self._mpv_log_level,
                        "Nivo logovanja za MPV engine")

        self._cache_size = QSpinBox()
        self._cache_size.setObjectName("settingsSpin")
        self._cache_size.setRange(0, 2048)
        self._cache_size.setSingleStep(64)
        self._cache_size.setSuffix(" MB")
        group1.add_row("Veličina keša", self._cache_size,
                        "Keš za mrežne streamove (0 = default)")

        self._demuxer_readahead = QDoubleSpinBox()
        self._demuxer_readahead.setObjectName("settingsSpin")
        self._demuxer_readahead.setRange(0.0, 60.0)
        self._demuxer_readahead.setSingleStep(1.0)
        self._demuxer_readahead.setSuffix(" sec")
        group1.add_row("Demuxer readahead", self._demuxer_readahead)

        layout.addWidget(group1)

        group2 = SettingsGroup("Podaci")

        self._clear_recent_btn = QPushButton("Obriši")
        self._clear_recent_btn.setObjectName("settingsSecondaryBtn")
        self._clear_recent_btn.setFixedWidth(100)
        self._clear_recent_btn.clicked.connect(self._on_clear_recent)
        group2.add_row("Nedavni fajlovi", self._clear_recent_btn,
                        "Obriši listu nedavno otvorenih fajlova")

        self._reset_all_btn = QPushButton("Reset")
        self._reset_all_btn.setObjectName("settingsSecondaryBtn")
        self._reset_all_btn.setFixedWidth(100)
        self._reset_all_btn.clicked.connect(self._on_reset)
        group2.add_row("Sva podešavanja", self._reset_all_btn,
                        "Vrati sva podešavanja na podrazumevane vrednosti")

        layout.addWidget(group2)

        group3 = SettingsGroup("Informacije")

        info_items = [
            ("Config putanja", str(self._config._config_path)),
            ("Engine", "MPV (libmpv)"),
            ("Qt verzija", "PyQt6"),
        ]
        for label, value in info_items:
            val_lbl = QLabel(value)
            val_lbl.setObjectName("settingsValue")
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            group3.add_row(label, val_lbl)

        layout.addWidget(group3)
        layout.addStretch()
        return scroll

    # ═══════════════════════════════════════════
    #  VREDNOSTI
    # ═══════════════════════════════════════════

    def _load_values(self) -> None:
        """Učitaj trenutne vrednosti iz config-a u widgete."""
        cfg = self._config

        # Teme - označi selektovane
        for key, card in self._theme_cards.items():
            card.set_selected(key == self._current_theme)

        # OSD
        self._osd_display_ms.setValue(cfg.get("ui.osd_display_ms", 1500))
        self._osd_show_check.setChecked(cfg.get("ui.show_osd", True))

        # Reprodukcija
        self._resume_check.setChecked(cfg.get("playback.resume_playback", True))
        self._default_speed.setValue(cfg.get("playback.speed", 1.0))
        self._auto_play_check.setChecked(cfg.get("playback.auto_play", True))
        self._seek_step.setValue(cfg.get("playback.seek_step", 10))
        self._precise_seek.setChecked(cfg.get("playback.precise_seek", False))
        loop_mode = cfg.get("playback.loop_mode", 0)
        self._loop_combo.setCurrentIndex(min(loop_mode, 2))
        self._shuffle_check.setChecked(cfg.get("playback.shuffle", False))

        # Audio
        self._default_volume.setValue(cfg.get("audio.volume", 100))
        self._volume_step.setValue(cfg.get("audio.volume_step", 5))
        self._volume_boost.setChecked(cfg.get("audio.volume_boost", False))
        audio_idx = ["default", "pulse", "alsa", "jack"].index(
            cfg.get("audio.device", "default")
        ) if cfg.get("audio.device", "default") in ["default", "pulse", "alsa", "jack"] else 0
        self._audio_device.setCurrentIndex(audio_idx)
        self._normalize_check.setChecked(cfg.get("audio.normalize", False))

        # Video
        hw_map = {"auto": 0, "vaapi": 1, "vdpau": 2, "nvdec": 3, "no": 4}
        self._hw_decode.setCurrentIndex(hw_map.get(cfg.get("engine.hardware_decoding", "auto"), 0))
        vo_map = {"gpu": 0, "gpu-next": 1, "x11": 2, "wayland": 3}
        self._vo_combo.setCurrentIndex(vo_map.get(cfg.get("engine.vo", "gpu"), 0))
        self._deinterlace.setChecked(cfg.get("engine.deinterlace", False))

        scale_map = {"bilinear": 0, "spline36": 1, "ewa_lanczos": 2, "ewa_lanczossharp": 3}
        self._scale_combo.setCurrentIndex(scale_map.get(cfg.get("engine.scale", "spline36"), 1))
        self._dither_check.setChecked(cfg.get("engine.dither", True))
        self._icc_check.setChecked(cfg.get("engine.icc_profile", False))

        # Titlovi - Učitavanje
        sub_auto_map = {"exact": 0, "contains": 1, "all": 2, "no": 3}
        self._sub_auto.setCurrentIndex(sub_auto_map.get(cfg.get("subtitles.auto_load", "exact"), 0))

        pref_lang = cfg.get("subtitles.preferred_lang", "sr")
        idx = self._sub_preferred_lang.findText(pref_lang)
        if idx >= 0:
            self._sub_preferred_lang.setCurrentIndex(idx)
        else:
            self._sub_preferred_lang.setEditText(pref_lang)

        fb_lang = cfg.get("subtitles.fallback_lang", "en")
        idx = self._sub_fallback_lang.findText(fb_lang)
        if idx >= 0:
            self._sub_fallback_lang.setCurrentIndex(idx)
        else:
            self._sub_fallback_lang.setEditText(fb_lang)

        self._sub_auto_select.setChecked(cfg.get("subtitles.auto_select", True))

        enc = cfg.get("subtitles.encoding", "Auto-detect")
        idx = self._sub_encoding.findText(enc, Qt.MatchFlag.MatchContains)
        self._sub_encoding.setCurrentIndex(max(idx, 0))

        self._sub_fix_timing.setChecked(cfg.get("subtitles.fix_timing", False))

        # Titlovi - Font
        font = cfg.get("subtitles.font_family", "Arial")
        idx = self._sub_font_family.findText(font)
        if idx >= 0:
            self._sub_font_family.setCurrentIndex(idx)
        else:
            self._sub_font_family.setEditText(font)

        self._sub_font_size.setValue(cfg.get("subtitles.font_size", 46))
        self._sub_bold.setChecked(cfg.get("subtitles.bold", True))
        self._sub_italic.setChecked(cfg.get("subtitles.italic", False))

        # Titlovi - Boje
        sub_color_map = {
            "#FFFFFF": 0, "#FFFF00": 1, "#FFFACD": 2, "#00FF00": 3,
            "#00FFFF": 4, "#FFD700": 5, "#FFB6C1": 6,
        }
        self._sub_color.setCurrentIndex(sub_color_map.get(cfg.get("subtitles.color", "#FFFFFF"), 0))

        border_map = {"#000000": 0, "#333333": 1, "#808080": 2, "transparent": 3}
        self._sub_border_color.setCurrentIndex(border_map.get(cfg.get("subtitles.border_color", "#000000"), 0))
        self._sub_border_size.setValue(cfg.get("subtitles.border_size", 3.0))

        shadow_map = {"#000000": 0, "#222222": 1, "transparent": 2}
        self._sub_shadow_color.setCurrentIndex(shadow_map.get(cfg.get("subtitles.shadow_color", "#000000"), 0))
        self._sub_shadow_offset.setValue(cfg.get("subtitles.shadow_offset", 1.0))

        self._sub_bg_enabled.setChecked(cfg.get("subtitles.bg_enabled", False))
        bg_map = {"80": 0, "50": 1, "100": 2, "darkgray": 3}
        self._sub_bg_color.setCurrentIndex(bg_map.get(str(cfg.get("subtitles.bg_opacity", "80")), 0))
        self._sub_bg_padding.setValue(cfg.get("subtitles.bg_padding", 8))

        # Titlovi - Pozicija
        self._sub_position.setValue(cfg.get("subtitles.position", 98))
        self._sub_margin_v.setValue(cfg.get("subtitles.margin_v", 20))
        self._sub_margin_h.setValue(cfg.get("subtitles.margin_h", 25))
        align_map = {"bottom_center": 0, "top_center": 1, "center": 2, "bottom_left": 3, "bottom_right": 4}
        self._sub_alignment.setCurrentIndex(align_map.get(cfg.get("subtitles.alignment", "bottom_center"), 0))
        self._sub_scale_with_window.setChecked(cfg.get("subtitles.scale_with_window", True))
        justify_map = {"auto": 0, "left": 1, "center": 2, "right": 3}
        self._sub_justify.setCurrentIndex(justify_map.get(cfg.get("subtitles.justify", "center"), 2))

        # Titlovi - Sinhronizacija
        self._sub_delay.setValue(cfg.get("subtitles.delay", 0.0))
        self._sub_speed.setValue(cfg.get("subtitles.speed", 1.0))
        fps_val = str(cfg.get("subtitles.fps_override", "Auto"))
        idx = self._sub_fps_override.findText(fps_val)
        if idx >= 0:
            self._sub_fps_override.setCurrentIndex(idx)
        else:
            self._sub_fps_override.setEditText(fps_val)

        # Titlovi - ASS
        ass_map = {"no": 0, "font": 1, "style": 2, "force": 3}
        self._sub_ass_override.setCurrentIndex(ass_map.get(cfg.get("subtitles.ass_override", "no"), 0))
        hint_map = {"none": 0, "light": 1, "normal": 2, "native": 3}
        self._sub_ass_hinting.setCurrentIndex(hint_map.get(cfg.get("subtitles.ass_hinting", "none"), 0))
        shaping_map = {"simple": 0, "complex": 1}
        self._sub_ass_shaping.setCurrentIndex(shaping_map.get(cfg.get("subtitles.ass_shaping", "complex"), 1))
        self._sub_vsfilter_compat.setChecked(cfg.get("subtitles.vsfilter_compat", True))
        self._sub_ass_force_margins.setChecked(cfg.get("subtitles.ass_force_margins", False))
        self._sub_stretch_ass.setChecked(cfg.get("subtitles.stretch_ass", False))

        # Titlovi - Napredno
        self._sub_secondary_enabled.setChecked(cfg.get("subtitles.secondary_enabled", False))
        sec_lang = cfg.get("subtitles.secondary_lang", "en")
        idx = self._sub_secondary_lang.findText(sec_lang)
        if idx >= 0:
            self._sub_secondary_lang.setCurrentIndex(idx)
        else:
            self._sub_secondary_lang.setEditText(sec_lang)

        blend_map = {"no": 0, "video": 1, "video_osd": 2}
        self._sub_blend.setCurrentIndex(blend_map.get(cfg.get("subtitles.blend", "no"), 0))
        self._sub_clear_on_seek.setChecked(cfg.get("subtitles.clear_on_seek", True))
        self._sub_gray.setChecked(cfg.get("subtitles.gray", False))
        self._sub_filter_sdh.setChecked(cfg.get("subtitles.filter_sdh", False))
        regex_val = cfg.get("subtitles.filter_regex", "")
        idx = self._sub_filter_regex.findText(regex_val)
        if idx >= 0:
            self._sub_filter_regex.setCurrentIndex(idx)
        else:
            self._sub_filter_regex.setEditText(regex_val)

        # YouTube
        self._yt_quality.setCurrentIndex(cfg.get("plugins.youtube.default_quality", 0))
        self._yt_max_playlist.setValue(cfg.get("plugins.youtube.max_playlist_items", 100))

        # Torrent
        dl_dir = cfg.get("torrent.download_dir", "")
        idx = self._torrent_dir.findText(dl_dir)
        if idx >= 0:
            self._torrent_dir.setCurrentIndex(idx)
        else:
            self._torrent_dir.setEditText(dl_dir)
        self._torrent_buffer.setValue(cfg.get("torrent.buffer_mb", 500))
        self._torrent_prealloc.setChecked(cfg.get("torrent.preallocate", False))
        self._torrent_delete.setChecked(cfg.get("torrent.delete_on_close", False))
        self._torrent_max_dl.setValue(cfg.get("torrent.max_download_kbps", 0))
        self._torrent_max_ul.setValue(cfg.get("torrent.max_upload_kbps", 0))
        self._torrent_connections.setValue(cfg.get("torrent.connections_limit", 200))
        self._torrent_port_min.setValue(cfg.get("torrent.port_min", 6881))
        self._torrent_port_max.setValue(cfg.get("torrent.port_max", 6891))
        self._torrent_dht.setChecked(cfg.get("torrent.dht_enabled", True))
        self._torrent_encryption.setCurrentIndex(cfg.get("torrent.encryption", 1))
        self._torrent_seed.setChecked(cfg.get("torrent.seed_after_download", True))
        self._torrent_ratio.setValue(cfg.get("torrent.seed_ratio", 1.0))

        # Interfejs
        self._remember_size.setChecked(cfg.get("ui.remember_size", True))
        self._remember_pos.setChecked(cfg.get("ui.remember_position", True))
        self._start_maximized.setChecked(cfg.get("ui.start_maximized", False))
        self._auto_hide.setChecked(cfg.get("ui.auto_hide", True))
        self._auto_hide_delay.setValue(cfg.get("ui.auto_hide_delay_ms", 3000))
        self._auto_hide_cursor.setChecked(cfg.get("ui.auto_hide_cursor", True))
        self._playlist_width.setValue(cfg.get("ui.playlist_width", 320))
        self._playlist_show_duration.setChecked(cfg.get("ui.playlist_show_duration", True))

        # Napredno
        log_map = {"no": 0, "fatal": 1, "error": 2, "warn": 3, "info": 4, "v": 5, "debug": 6}
        self._mpv_log_level.setCurrentIndex(log_map.get(cfg.get("engine.log_level", "warn"), 3))
        self._cache_size.setValue(cfg.get("engine.cache_size_mb", 128))
        self._demuxer_readahead.setValue(cfg.get("engine.demuxer_readahead", 5.0))

    def _save_values(self) -> None:
        """Sačuvaj vrednosti iz widgeta u config."""
        cfg = self._config

        # Teme
        cfg.set("ui.theme", self._current_theme)
        cfg.set("ui.osd_display_ms", self._osd_display_ms.value())
        cfg.set("ui.show_osd", self._osd_show_check.isChecked())

        # Reprodukcija
        cfg.set("playback.resume_playback", self._resume_check.isChecked())
        cfg.set("playback.speed", self._default_speed.value())
        cfg.set("playback.auto_play", self._auto_play_check.isChecked())
        cfg.set("playback.seek_step", self._seek_step.value())
        cfg.set("playback.precise_seek", self._precise_seek.isChecked())
        cfg.set("playback.loop_mode", self._loop_combo.currentIndex())
        cfg.set("playback.shuffle", self._shuffle_check.isChecked())

        # Audio
        cfg.set("audio.volume", self._default_volume.value())
        cfg.set("audio.volume_step", self._volume_step.value())
        cfg.set("audio.volume_boost", self._volume_boost.isChecked())
        devices = ["default", "pulse", "alsa", "jack"]
        cfg.set("audio.device", devices[self._audio_device.currentIndex()])
        cfg.set("audio.normalize", self._normalize_check.isChecked())

        # Video
        hw_values = ["auto", "vaapi", "vdpau", "nvdec", "no"]
        cfg.set("engine.hardware_decoding", hw_values[self._hw_decode.currentIndex()])
        vo_values = ["gpu", "gpu-next", "x11", "wayland"]
        cfg.set("engine.vo", vo_values[self._vo_combo.currentIndex()])
        cfg.set("engine.deinterlace", self._deinterlace.isChecked())
        scale_values = ["bilinear", "spline36", "ewa_lanczos", "ewa_lanczossharp"]
        cfg.set("engine.scale", scale_values[self._scale_combo.currentIndex()])
        cfg.set("engine.dither", self._dither_check.isChecked())
        cfg.set("engine.icc_profile", self._icc_check.isChecked())

        # Titlovi - Učitavanje
        sub_auto_values = ["exact", "contains", "all", "no"]
        cfg.set("subtitles.auto_load", sub_auto_values[self._sub_auto.currentIndex()])
        cfg.set("subtitles.preferred_lang", self._sub_preferred_lang.currentText())
        cfg.set("subtitles.fallback_lang", self._sub_fallback_lang.currentText())
        cfg.set("subtitles.auto_select", self._sub_auto_select.isChecked())
        cfg.set("subtitles.encoding", self._sub_encoding.currentText())
        cfg.set("subtitles.fix_timing", self._sub_fix_timing.isChecked())

        # Titlovi - Font
        cfg.set("subtitles.font_family", self._sub_font_family.currentText())
        cfg.set("subtitles.font_size", self._sub_font_size.value())
        cfg.set("subtitles.bold", self._sub_bold.isChecked())
        cfg.set("subtitles.italic", self._sub_italic.isChecked())

        # Titlovi - Boje
        color_values = ["#FFFFFF", "#FFFF00", "#FFFACD", "#00FF00", "#00FFFF", "#FFD700", "#FFB6C1", "custom"]
        cfg.set("subtitles.color", color_values[min(self._sub_color.currentIndex(), len(color_values) - 1)])
        border_values = ["#000000", "#333333", "#808080", "transparent", "custom"]
        cfg.set("subtitles.border_color", border_values[min(self._sub_border_color.currentIndex(), len(border_values) - 1)])
        cfg.set("subtitles.border_size", self._sub_border_size.value())
        shadow_values = ["#000000", "#222222", "transparent", "custom"]
        cfg.set("subtitles.shadow_color", shadow_values[min(self._sub_shadow_color.currentIndex(), len(shadow_values) - 1)])
        cfg.set("subtitles.shadow_offset", self._sub_shadow_offset.value())
        cfg.set("subtitles.bg_enabled", self._sub_bg_enabled.isChecked())
        bg_values = ["80", "50", "100", "darkgray", "custom"]
        cfg.set("subtitles.bg_opacity", bg_values[min(self._sub_bg_color.currentIndex(), len(bg_values) - 1)])
        cfg.set("subtitles.bg_padding", self._sub_bg_padding.value())

        # Titlovi - Pozicija
        cfg.set("subtitles.position", self._sub_position.value())
        cfg.set("subtitles.margin_v", self._sub_margin_v.value())
        cfg.set("subtitles.margin_h", self._sub_margin_h.value())
        align_values = ["bottom_center", "top_center", "center", "bottom_left", "bottom_right"]
        cfg.set("subtitles.alignment", align_values[self._sub_alignment.currentIndex()])
        cfg.set("subtitles.scale_with_window", self._sub_scale_with_window.isChecked())
        justify_values = ["auto", "left", "center", "right"]
        cfg.set("subtitles.justify", justify_values[self._sub_justify.currentIndex()])

        # Titlovi - Sinhronizacija
        cfg.set("subtitles.delay", self._sub_delay.value())
        cfg.set("subtitles.speed", self._sub_speed.value())
        fps_text = self._sub_fps_override.currentText()
        cfg.set("subtitles.fps_override", fps_text)

        # Titlovi - ASS
        ass_values = ["no", "font", "style", "force"]
        cfg.set("subtitles.ass_override", ass_values[self._sub_ass_override.currentIndex()])
        hint_values = ["none", "light", "normal", "native"]
        cfg.set("subtitles.ass_hinting", hint_values[self._sub_ass_hinting.currentIndex()])
        shaping_values = ["simple", "complex"]
        cfg.set("subtitles.ass_shaping", shaping_values[self._sub_ass_shaping.currentIndex()])
        cfg.set("subtitles.vsfilter_compat", self._sub_vsfilter_compat.isChecked())
        cfg.set("subtitles.ass_force_margins", self._sub_ass_force_margins.isChecked())
        cfg.set("subtitles.stretch_ass", self._sub_stretch_ass.isChecked())

        # Titlovi - Napredno
        cfg.set("subtitles.secondary_enabled", self._sub_secondary_enabled.isChecked())
        cfg.set("subtitles.secondary_lang", self._sub_secondary_lang.currentText())
        blend_values = ["no", "video", "video_osd"]
        cfg.set("subtitles.blend", blend_values[self._sub_blend.currentIndex()])
        cfg.set("subtitles.clear_on_seek", self._sub_clear_on_seek.isChecked())
        cfg.set("subtitles.gray", self._sub_gray.isChecked())
        cfg.set("subtitles.filter_sdh", self._sub_filter_sdh.isChecked())
        cfg.set("subtitles.filter_regex", self._sub_filter_regex.currentText())

        # YouTube
        cfg.set("plugins.youtube.default_quality", self._yt_quality.currentIndex())
        cfg.set("plugins.youtube.max_playlist_items", self._yt_max_playlist.value())

        # Torrent
        cfg.set("torrent.download_dir", self._torrent_dir.currentText())
        cfg.set("torrent.buffer_mb", self._torrent_buffer.value())
        cfg.set("torrent.preallocate", self._torrent_prealloc.isChecked())
        cfg.set("torrent.delete_on_close", self._torrent_delete.isChecked())
        cfg.set("torrent.max_download_kbps", self._torrent_max_dl.value())
        cfg.set("torrent.max_upload_kbps", self._torrent_max_ul.value())
        cfg.set("torrent.connections_limit", self._torrent_connections.value())
        cfg.set("torrent.port_min", self._torrent_port_min.value())
        cfg.set("torrent.port_max", self._torrent_port_max.value())
        cfg.set("torrent.dht_enabled", self._torrent_dht.isChecked())
        cfg.set("torrent.encryption", self._torrent_encryption.currentIndex())
        cfg.set("torrent.seed_after_download", self._torrent_seed.isChecked())
        cfg.set("torrent.seed_ratio", self._torrent_ratio.value())

        # Interfejs
        cfg.set("ui.remember_size", self._remember_size.isChecked())
        cfg.set("ui.remember_position", self._remember_pos.isChecked())
        cfg.set("ui.start_maximized", self._start_maximized.isChecked())
        cfg.set("ui.auto_hide", self._auto_hide.isChecked())
        cfg.set("ui.auto_hide_delay_ms", self._auto_hide_delay.value())
        cfg.set("ui.auto_hide_cursor", self._auto_hide_cursor.isChecked())
        cfg.set("ui.playlist_width", self._playlist_width.value())
        cfg.set("ui.playlist_show_duration", self._playlist_show_duration.isChecked())

        # Napredno
        log_values = ["no", "fatal", "error", "warn", "info", "v", "debug"]
        cfg.set("engine.log_level", log_values[self._mpv_log_level.currentIndex()])
        cfg.set("engine.cache_size_mb", self._cache_size.value())
        cfg.set("engine.demuxer_readahead", self._demuxer_readahead.value())

        cfg.save()

    # ═══════════════════════════════════════════
    #  EVENT HANDLERS
    # ═══════════════════════════════════════════

    def _on_theme_selected(self, key: str) -> None:
        """Korisnik je odabrao novu player temu."""
        self._current_theme = key
        for k, card in self._theme_cards.items():
            card.set_selected(k == key)
        # Emituj za live preview
        self.theme_changed.emit(key)

    def _on_apply(self) -> None:
        """Primeni i sačuvaj sva podešavanja."""
        self._save_values()
        self.settings_changed.emit()
        self.accept()

    def _on_reset(self) -> None:
        """Vrati na default vrednosti."""
        self._current_theme = "midnight_red"
        self._load_values()
        self.theme_changed.emit(self._current_theme)

    def _on_clear_recent(self) -> None:
        """Obriši nedavne fajlove."""
        self._config.clear_recent_files()
        self._config.save()

    # ═══════════════════════════════════════════
    #  PLUGIN FUNKCIJE (nove)
    # ═══════════════════════════════════════════

    def _toggle_plugin(self, name: str, state: int) -> None:
        """Omogući/onemogući plugin."""
        enabled = state == Qt.CheckState.Checked.value
        self._config.set_plugin_enabled(name, enabled)
        QMessageBox.information(
            self,
            "Plugin state changed",
            "Promena će biti primenjena nakon restartovanja playera."
        )

    def _reload_plugins(self) -> None:
        """Ponovo učitaj sve plugine."""
        if not self._plugin_mgr:
            return
        self._plugin_mgr.reload_all()
        QMessageBox.information(
            self,
            "Plugins reloaded",
            "Plugin sistem je ponovo učitan."
        )

    def _configure_plugin(self, plugin):
        """Pozovi configure metodu plugina sa error handlingom."""
        if not plugin:
            return

        try:
            plugin.configure(self)
        except Exception as e:
            print("Plugin configure error:", e)

    # ═══════════════════════════════════════════
    #  DRAG SUPPORT (frameless dialog)
    # ═══════════════════════════════════════════

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)