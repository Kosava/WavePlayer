"""Application stylesheet generator.

Generates Qt stylesheets from ThemeColors dataclass.
Supports multiple themes with runtime switching.

PORTABILITY NOTES:
  - C++: identical Qt stylesheet syntax, string formatting
  - Rust/egui: convert to egui::Style via theme colors
"""

from .themes import ThemeColors, get_theme


def generate_stylesheet(colors: ThemeColors) -> str:
    """Generiši kompletan stylesheet iz ThemeColors."""
    return f"""
/* ════════════════════════════════════════════
   WavePlayer Generated Theme
   ════════════════════════════════════════════ */

/* === Glavni prozor === */
QMainWindow {{
    background-color: {colors.bg_primary};
    border: none;
}}

#centralFrame {{
    background-color: {colors.bg_primary};
    border: 1px solid {colors.border};
    border-radius: 8px;
}}

/* === Title Bar === */
#titleBar {{
    background-color: {colors.bg_secondary};
    border-bottom: 1px solid {colors.border};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

#titleIcon {{
    font-size: 16px;
}}

#titleLabel {{
    color: {colors.text_primary};
    font-size: 13px;
    font-weight: 500;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#windowBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: none;
    border-radius: 4px;
    font-size: 14px;
}}

#windowBtn:hover {{
    background-color: {colors.bg_tertiary};
    color: {colors.text_accent};
}}

#closeBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: none;
    border-radius: 4px;
    font-size: 14px;
}}

#closeBtn:hover {{
    background-color: {colors.close_hover};
    color: #ffffff;
}}

/* === Video Widget === */
#videoWidget {{
    background-color: #000000;
    border: none;
}}

#dropZone {{
    color: {colors.text_muted};
    font-size: 16px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
    background-color: {colors.bg_tertiary};
    border: 2px dashed {colors.bg_tertiary};
    border-radius: 12px;
    padding: 48px;
    min-width: 300px;
    min-height: 120px;
}}

#dropZone[dragOver="true"] {{
    background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    border-color: {colors.accent};
    color: {colors.accent};
}}

/* === Control Bar === */
#controlBar {{
    background-color: rgba({_hex_to_rgb_str(colors.bg_secondary)}, 0.95);
    border-top: 1px solid {colors.border};
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}}

/* === Slider-i === */
QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background-color: {colors.slider_groove};
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background-color: {colors.accent};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {colors.slider_handle};
    border: none;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {colors.accent};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

/* Progress slider */
#progressSlider::groove:horizontal {{
    height: 5px;
}}

#progressSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {colors.progress_gradient_start}, stop:1 {colors.progress_gradient_end});
}}

#progressSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    border: 2px solid {colors.handle_border};
    background-color: {colors.slider_handle};
}}

/* Volume slider */
#volumeSlider::groove:horizontal {{
    height: 3px;
}}

#volumeSlider::handle:horizontal {{
    width: 10px;
    height: 10px;
    margin: -4px 0;
    border-radius: 5px;
}}

/* === Dugmad === */
#playPauseBtn {{
    background-color: {colors.accent};
    color: white;
    border: none;
    border-radius: 22px;
    font-size: 16px;
}}

#playPauseBtn:hover {{
    background-color: {colors.accent_hover};
}}

#playPauseBtn:pressed {{
    background-color: {colors.accent_pressed};
}}

#controlBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: none;
    border-radius: 16px;
    font-size: 14px;
}}

#controlBtn:hover {{
    background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    color: {colors.text_accent};
}}

#controlBtn:checked {{
    background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    color: {colors.accent};
}}

#textBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: 1px solid {colors.border_hover};
    border-radius: 4px;
    font-size: 11px;
    font-family: 'Consolas', 'SF Mono', monospace;
}}

#textBtn:hover {{
    background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    color: {colors.text_accent};
    border-color: {colors.text_muted};
}}

/* === Vremenske oznake === */
#timeLabel, #durationLabel {{
    color: {colors.text_secondary};
    font-size: 12px;
    font-family: 'Consolas', 'SF Mono', monospace;
}}

/* === Side Panel (Playlist) === */
#sidePanel {{
    background-color: {colors.bg_secondary};
    border-left: 1px solid {colors.border};
}}

#panelHeader {{
    color: {colors.text_primary};
    font-size: 15px;
    font-weight: bold;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#panelBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: 1px solid {colors.border_hover};
    border-radius: 4px;
    font-size: 14px;
}}

#panelBtn:hover {{
    background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    color: {colors.text_accent};
}}

#searchEdit {{
    background-color: {colors.bg_input};
    color: {colors.text_primary};
    border: 1px solid {colors.bg_tertiary};
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 13px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
    selection-background-color: {colors.accent};
}}

#searchEdit:focus {{
    border-color: {colors.border_focus};
}}

/* Playlist lista */
#playlistWidget {{
    background-color: transparent;
    color: {colors.text_primary};
    border: none;
    outline: none;
    font-size: 13px;
}}

#playlistWidget::item {{
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 2px;
}}

#playlistWidget::item:selected {{
    background-color: {colors.accent};
    color: white;
}}

#playlistWidget::item:hover:!selected {{
    background-color: {colors.bg_tertiary};
}}

#infoLabel {{
    color: {colors.text_muted};
    font-size: 11px;
}}

/* === Tooltip === */
QToolTip {{
    background-color: {colors.tooltip_bg};
    color: {colors.text_primary};
    border: 1px solid {colors.border_hover};
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 12px;
}}

/* === Settings Dialog === */
#settingsDialog {{
    background-color: {colors.bg_primary};
    border: 1px solid {colors.border};
    border-radius: 12px;
}}

#settingsSidebar {{
    background-color: {colors.bg_secondary};
    border-right: 1px solid {colors.border};
    border-top-left-radius: 12px;
    border-bottom-left-radius: 12px;
}}

#settingsContent {{
    background-color: {colors.bg_primary};
    border-top-right-radius: 12px;
    border-bottom-right-radius: 12px;
}}

#settingsNavBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#settingsNavBtn:hover {{
    background-color: {colors.bg_tertiary};
    color: {colors.text_primary};
}}

#settingsNavBtn:checked {{
    background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    color: {colors.accent};
    font-weight: bold;
}}

#settingsSectionTitle {{
    color: {colors.text_primary};
    font-size: 18px;
    font-weight: bold;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#settingsSectionDesc {{
    color: {colors.text_muted};
    font-size: 12px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#settingsGroup {{
    background-color: {colors.bg_secondary};
    border: 1px solid {colors.border};
    border-radius: 10px;
    padding: 16px;
}}

#settingsGroupTitle {{
    color: {colors.text_primary};
    font-size: 14px;
    font-weight: 600;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#settingsLabel {{
    color: {colors.text_primary};
    font-size: 13px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#settingsSubLabel {{
    color: {colors.text_muted};
    font-size: 11px;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

#settingsValue {{
    color: {colors.text_secondary};
    font-size: 12px;
    font-family: 'Consolas', 'SF Mono', monospace;
}}

/* Settings combo box */
#settingsCombo {{
    background-color: {colors.bg_input};
    color: {colors.text_primary};
    border: 1px solid {colors.border};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 160px;
}}

#settingsCombo:hover {{
    border-color: {colors.border_hover};
}}

#settingsCombo::drop-down {{
    border: none;
    width: 24px;
}}

#settingsCombo QAbstractItemView {{
    background-color: {colors.bg_secondary};
    color: {colors.text_primary};
    border: 1px solid {colors.border};
    border-radius: 6px;
    selection-background-color: {_argb_hex_to_rgba(colors.accent_subtle)};
    selection-color: {colors.accent};
    outline: none;
}}

/* Settings spin box */
#settingsSpin {{
    background-color: {colors.bg_input};
    color: {colors.text_primary};
    border: 1px solid {colors.border};
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 13px;
    min-width: 80px;
}}

#settingsSpin:hover {{
    border-color: {colors.border_hover};
}}

/* Settings checkbox / toggle */
QCheckBox {{
    color: {colors.text_primary};
    font-size: 13px;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {colors.border_hover};
    background-color: {colors.bg_input};
}}

QCheckBox::indicator:checked {{
    background-color: {colors.accent};
    border-color: {colors.accent};
}}

QCheckBox::indicator:hover {{
    border-color: {colors.accent};
}}

/* Theme preview card */
#themeCard {{
    background-color: {colors.bg_secondary};
    border: 2px solid {colors.border};
    border-radius: 10px;
    padding: 8px;
}}

#themeCard:hover {{
    border-color: {colors.border_hover};
}}

#themeCard[selected="true"] {{
    border-color: {colors.accent};
}}

#themeCardName {{
    color: {colors.text_primary};
    font-size: 11px;
    font-weight: 600;
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}

/* Scrollbar styling */
QScrollBar:vertical {{
    background-color: {colors.scrollbar_bg};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {colors.scrollbar_handle};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {colors.text_muted};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* Settings action buttons */
#settingsPrimaryBtn {{
    background-color: {colors.accent};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}}

#settingsPrimaryBtn:hover {{
    background-color: {colors.accent_hover};
}}

#settingsSecondaryBtn {{
    background-color: transparent;
    color: {colors.text_secondary};
    border: 1px solid {colors.border_hover};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
}}

#settingsSecondaryBtn:hover {{
    background-color: {colors.bg_tertiary};
    color: {colors.text_primary};
}}

/* Separator */
#settingsSeparator {{
    background-color: {colors.border};
    max-height: 1px;
}}
"""


def _hex_to_rgb_str(hex_color: str) -> str:
    """Konvertuj hex boju u 'r, g, b' string za rgba()."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"
    return "20, 20, 20"


def _argb_hex_to_rgba(hex_color: str) -> str:
    """Konvertuj #AARRGGBB hex u rgba(r, g, b, a) string za Qt CSS.

    Qt stylesheet parser ne podržava pouzdano 8-cifarski hex format.
    Ova funkcija konvertuje u rgba() koji radi svuda.
    Podržava i standardni 6-cifarski hex (#RRGGBB) i rgba() passthrough.
    """
    if hex_color.startswith("rgba"):
        return hex_color
    h = hex_color.lstrip("#")
    if len(h) == 8:
        a = int(h[0:2], 16)
        r = int(h[2:4], 16)
        g = int(h[4:6], 16)
        b = int(h[6:8], 16)
        alpha = round(a / 255, 3)
        return f"rgba({r}, {g}, {b}, {alpha})"
    if len(h) == 6:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return f"rgba({r}, {g}, {b}, 1.0)"
    return hex_color


def get_stylesheet(theme_name: str = "midnight_red") -> str:
    """Vrati stylesheet za zadatu temu."""
    from .welcome_widget import get_welcome_stylesheet
    colors = get_theme(theme_name)
    return generate_stylesheet(colors) + get_welcome_stylesheet(colors)
