"""Theme engine for WavePlayer.

Multiple curated themes for the player UI and OSD overlay.
Each theme is a complete visual identity with coordinated colors.

PORTABILITY NOTES:
  - C++: identical Qt stylesheet with string replacement
  - Rust: theme struct -> egui::Style conversion
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ThemeColors:
    """Boje jedne teme. Sve boje su hex stringovi."""
    # Osnova
    bg_primary: str = "#0f0f0f"
    bg_secondary: str = "#141414"
    bg_tertiary: str = "#1e1e1e"
    bg_input: str = "#1e1e1e"

    # Tekst
    text_primary: str = "#e0e0e0"
    text_secondary: str = "#999999"
    text_muted: str = "#666666"
    text_accent: str = "#ffffff"

    # Akcent
    accent: str = "#e50914"
    accent_hover: str = "#f40612"
    accent_pressed: str = "#c00812"
    accent_subtle: str = "#26e50914"

    # Granice
    border: str = "#1e1e1e"
    border_hover: str = "#333333"
    border_focus: str = "#e50914"

    # Kontrole
    slider_groove: str = "#2a2a2a"
    slider_handle: str = "#ffffff"
    handle_border: str = "#e50914"

    # Posebni
    close_hover: str = "#e81123"
    scrollbar_bg: str = "#1a1a1a"
    scrollbar_handle: str = "#333333"
    tooltip_bg: str = "#1a1a1a"

    # OSD
    osd_bg: str = "rgba(0, 0, 0, 180)"
    osd_text: str = "#ffffff"
    osd_subtext: str = "#e0e0e0"
    osd_progress_bg: str = "rgba(255, 255, 255, 0.2)"
    osd_progress_fill: str = "#e50914"

    # Gradient za progress
    progress_gradient_start: str = "#e50914"
    progress_gradient_end: str = "#ff4444"
    buffer_color: str = "rgba(255, 255, 255, 0.15)"  # torrent buffer traka


@dataclass
class OsdTheme:
    """Vizuelni stil za OSD overlay."""
    name: str = "Default"
    bg: str = "rgba(0, 0, 0, 180)"
    text_color: str = "#ffffff"
    subtext_color: str = "#e0e0e0"
    progress_bg: str = "rgba(255, 255, 255, 0.2)"
    progress_fill: str = "#e50914"
    border_radius: int = 12
    icon_size: int = 32
    text_size: int = 14
    blur: bool = False
    border: str = "none"
    shadow: str = "none"
    padding_h: int = 24
    padding_v: int = 16


# ═══════════════════════════════════════════
#  PLAYER TEME
# ═══════════════════════════════════════════

THEMES: Dict[str, ThemeColors] = {
    # ── Midnight Red (Default - Netflix inspired) ──
    "midnight_red": ThemeColors(),

    # ── Abyss Blue ──
    "abyss_blue": ThemeColors(
        bg_primary="#080c14",
        bg_secondary="#0d1320",
        bg_tertiary="#141c2e",
        bg_input="#141c2e",
        text_primary="#c8d6e5",
        text_secondary="#6b7f99",
        text_muted="#4a5568",
        text_accent="#e2e8f0",
        accent="#2d7ff9",
        accent_hover="#4a94ff",
        accent_pressed="#1a6ae0",
        accent_subtle="#262d7ff9",
        border="#141c2e",
        border_hover="#1e2d47",
        border_focus="#2d7ff9",
        slider_groove="#1a2640",
        slider_handle="#e2e8f0",
        handle_border="#2d7ff9",
        close_hover="#ff4757",
        tooltip_bg="#0d1320",
        scrollbar_bg="#0d1320",
        scrollbar_handle="#1e2d47",
        osd_bg="rgba(8, 12, 20, 200)",
        osd_text="#e2e8f0",
        osd_subtext="#8da0b8",
        osd_progress_bg="rgba(45, 127, 249, 0.2)",
        osd_progress_fill="#2d7ff9",
        progress_gradient_start="#2d7ff9",
        progress_gradient_end="#56a0ff",
    ),

    # ── Emerald Night ──
    "emerald_night": ThemeColors(
        bg_primary="#0a0f0d",
        bg_secondary="#0f1a15",
        bg_tertiary="#15241d",
        bg_input="#15241d",
        text_primary="#b8d4c8",
        text_secondary="#5e8a74",
        text_muted="#3d6652",
        text_accent="#d4f0e0",
        accent="#10b981",
        accent_hover="#34d399",
        accent_pressed="#059669",
        accent_subtle="#2610b981",
        border="#15241d",
        border_hover="#1e3529",
        border_focus="#10b981",
        slider_groove="#162920",
        slider_handle="#d4f0e0",
        handle_border="#10b981",
        close_hover="#ef4444",
        tooltip_bg="#0f1a15",
        scrollbar_bg="#0f1a15",
        scrollbar_handle="#1e3529",
        osd_bg="rgba(10, 15, 13, 200)",
        osd_text="#d4f0e0",
        osd_subtext="#7aaa92",
        osd_progress_bg="rgba(16, 185, 129, 0.2)",
        osd_progress_fill="#10b981",
        progress_gradient_start="#10b981",
        progress_gradient_end="#34d399",
    ),

    # ── Sunset Amber ──
    "sunset_amber": ThemeColors(
        bg_primary="#12100c",
        bg_secondary="#1a1610",
        bg_tertiary="#241e16",
        bg_input="#241e16",
        text_primary="#d4c4a8",
        text_secondary="#8a7a60",
        text_muted="#6a5a42",
        text_accent="#f0e0c8",
        accent="#f59e0b",
        accent_hover="#fbbf24",
        accent_pressed="#d97706",
        accent_subtle="#26f59e0b",
        border="#241e16",
        border_hover="#352c1e",
        border_focus="#f59e0b",
        slider_groove="#2a2218",
        slider_handle="#f0e0c8",
        handle_border="#f59e0b",
        close_hover="#ef4444",
        tooltip_bg="#1a1610",
        scrollbar_bg="#1a1610",
        scrollbar_handle="#352c1e",
        osd_bg="rgba(18, 16, 12, 200)",
        osd_text="#f0e0c8",
        osd_subtext="#b8a880",
        osd_progress_bg="rgba(245, 158, 11, 0.2)",
        osd_progress_fill="#f59e0b",
        progress_gradient_start="#f59e0b",
        progress_gradient_end="#fbbf24",
    ),

    # ── Violet Haze ──
    "violet_haze": ThemeColors(
        bg_primary="#0e0a14",
        bg_secondary="#14101e",
        bg_tertiary="#1e1630",
        bg_input="#1e1630",
        text_primary="#c8b8e0",
        text_secondary="#7a6899",
        text_muted="#5a4878",
        text_accent="#e0d4f0",
        accent="#8b5cf6",
        accent_hover="#a78bfa",
        accent_pressed="#7c3aed",
        accent_subtle="#268b5cf6",
        border="#1e1630",
        border_hover="#2a2044",
        border_focus="#8b5cf6",
        slider_groove="#1e1835",
        slider_handle="#e0d4f0",
        handle_border="#8b5cf6",
        close_hover="#ef4444",
        tooltip_bg="#14101e",
        scrollbar_bg="#14101e",
        scrollbar_handle="#2a2044",
        osd_bg="rgba(14, 10, 20, 200)",
        osd_text="#e0d4f0",
        osd_subtext="#9a88b8",
        osd_progress_bg="rgba(139, 92, 246, 0.2)",
        osd_progress_fill="#8b5cf6",
        progress_gradient_start="#8b5cf6",
        progress_gradient_end="#a78bfa",
    ),

    # ── Rose Gold ──
    "rose_gold": ThemeColors(
        bg_primary="#120e0e",
        bg_secondary="#1a1414",
        bg_tertiary="#261c1c",
        bg_input="#261c1c",
        text_primary="#d4b8b8",
        text_secondary="#996e6e",
        text_muted="#784e4e",
        text_accent="#f0d4d4",
        accent="#f43f5e",
        accent_hover="#fb7185",
        accent_pressed="#e11d48",
        accent_subtle="#26f43f5e",
        border="#261c1c",
        border_hover="#382828",
        border_focus="#f43f5e",
        slider_groove="#2a1e1e",
        slider_handle="#f0d4d4",
        handle_border="#f43f5e",
        close_hover="#ef4444",
        tooltip_bg="#1a1414",
        scrollbar_bg="#1a1414",
        scrollbar_handle="#382828",
        osd_bg="rgba(18, 14, 14, 200)",
        osd_text="#f0d4d4",
        osd_subtext="#b88888",
        osd_progress_bg="rgba(244, 63, 94, 0.2)",
        osd_progress_fill="#f43f5e",
        progress_gradient_start="#f43f5e",
        progress_gradient_end="#fb7185",
    ),

    # ── Arctic Silver ──
    "arctic_silver": ThemeColors(
        bg_primary="#111315",
        bg_secondary="#171b1f",
        bg_tertiary="#1e2328",
        bg_input="#1e2328",
        text_primary="#c0c8d0",
        text_secondary="#6b7785",
        text_muted="#4a545f",
        text_accent="#e0e8f0",
        accent="#64748b",
        accent_hover="#94a3b8",
        accent_pressed="#475569",
        accent_subtle="#2664748b",
        border="#1e2328",
        border_hover="#2c3238",
        border_focus="#94a3b8",
        slider_groove="#242a30",
        slider_handle="#e0e8f0",
        handle_border="#94a3b8",
        close_hover="#ef4444",
        tooltip_bg="#171b1f",
        scrollbar_bg="#171b1f",
        scrollbar_handle="#2c3238",
        osd_bg="rgba(17, 19, 21, 210)",
        osd_text="#e0e8f0",
        osd_subtext="#8898a8",
        osd_progress_bg="rgba(148, 163, 184, 0.2)",
        osd_progress_fill="#94a3b8",
        progress_gradient_start="#64748b",
        progress_gradient_end="#94a3b8",
    ),

    # ── Cyber Teal ──
    "cyber_teal": ThemeColors(
        bg_primary="#080d0e",
        bg_secondary="#0c1416",
        bg_tertiary="#121f22",
        bg_input="#121f22",
        text_primary="#a8d4d0",
        text_secondary="#5a8a84",
        text_muted="#3a6660",
        text_accent="#c8f0ec",
        accent="#14b8a6",
        accent_hover="#2dd4bf",
        accent_pressed="#0d9488",
        accent_subtle="#2614b8a6",
        border="#121f22",
        border_hover="#1a2e32",
        border_focus="#14b8a6",
        slider_groove="#142428",
        slider_handle="#c8f0ec",
        handle_border="#14b8a6",
        close_hover="#ef4444",
        tooltip_bg="#0c1416",
        scrollbar_bg="#0c1416",
        scrollbar_handle="#1a2e32",
        osd_bg="rgba(8, 13, 14, 200)",
        osd_text="#c8f0ec",
        osd_subtext="#6eaaa4",
        osd_progress_bg="rgba(20, 184, 166, 0.2)",
        osd_progress_fill="#14b8a6",
        progress_gradient_start="#14b8a6",
        progress_gradient_end="#2dd4bf",
    ),

    # ── OLED Pure ──
    "oled_pure": ThemeColors(
        bg_primary="#000000",
        bg_secondary="#0a0a0a",
        bg_tertiary="#141414",
        bg_input="#141414",
        text_primary="#d0d0d0",
        text_secondary="#707070",
        text_muted="#484848",
        text_accent="#ffffff",
        accent="#ffffff",
        accent_hover="#e0e0e0",
        accent_pressed="#c0c0c0",
        accent_subtle="#14ffffff",
        border="#1a1a1a",
        border_hover="#2a2a2a",
        border_focus="#ffffff",
        slider_groove="#1a1a1a",
        slider_handle="#ffffff",
        handle_border="#ffffff",
        close_hover="#e81123",
        tooltip_bg="#0a0a0a",
        scrollbar_bg="#000000",
        scrollbar_handle="#1a1a1a",
        osd_bg="rgba(0, 0, 0, 220)",
        osd_text="#ffffff",
        osd_subtext="#aaaaaa",
        osd_progress_bg="rgba(255, 255, 255, 0.12)",
        osd_progress_fill="#ffffff",
        progress_gradient_start="#808080",
        progress_gradient_end="#ffffff",
    ),

    # ═══════════════════════════════════════
    #  SVETLE TEME
    # ═══════════════════════════════════════

    # ── Polar Light ──
    # Čist beli kao skandinavski sneg, sa ledeno plavim akcentom
    "polar_light": ThemeColors(
        bg_primary="#f5f7fa",
        bg_secondary="#edf0f5",
        bg_tertiary="#e2e6ed",
        bg_input="#e8ecf2",
        text_primary="#1a1f2e",
        text_secondary="#5a6478",
        text_muted="#8892a4",
        text_accent="#0d1220",
        accent="#1e6cf0",
        accent_hover="#3d82f5",
        accent_pressed="#1558cc",
        accent_subtle="#1a1e6cf0",
        border="#d8dde6",
        border_hover="#c0c8d5",
        border_focus="#1e6cf0",
        slider_groove="#d0d6e0",
        slider_handle="#1e6cf0",
        handle_border="#1e6cf0",
        close_hover="#e81123",
        scrollbar_bg="#edf0f5",
        scrollbar_handle="#c0c8d5",
        tooltip_bg="#1a1f2e",
        osd_bg="rgba(245, 247, 250, 210)",
        osd_text="#1a1f2e",
        osd_subtext="#5a6478",
        osd_progress_bg="rgba(30, 108, 240, 0.15)",
        osd_progress_fill="#1e6cf0",
        progress_gradient_start="#1e6cf0",
        progress_gradient_end="#5a9aff",
    ),

    # ── Sakura Bloom ──
    # Japanski trešnjin cvet — topli roze na krem pozadini
    "sakura_bloom": ThemeColors(
        bg_primary="#fdf6f4",
        bg_secondary="#f8ecea",
        bg_tertiary="#f0ddd8",
        bg_input="#f4e4e0",
        text_primary="#3a1f22",
        text_secondary="#7a5558",
        text_muted="#a88488",
        text_accent="#2a0e12",
        accent="#d84060",
        accent_hover="#e85a78",
        accent_pressed="#c03050",
        accent_subtle="#1ad84060",
        border="#ecd4d0",
        border_hover="#ddbcb8",
        border_focus="#d84060",
        slider_groove="#e8ccc8",
        slider_handle="#d84060",
        handle_border="#d84060",
        close_hover="#c03050",
        scrollbar_bg="#f8ecea",
        scrollbar_handle="#ddbcb8",
        tooltip_bg="#3a1f22",
        osd_bg="rgba(253, 246, 244, 210)",
        osd_text="#3a1f22",
        osd_subtext="#7a5558",
        osd_progress_bg="rgba(216, 64, 96, 0.15)",
        osd_progress_fill="#d84060",
        progress_gradient_start="#d84060",
        progress_gradient_end="#f07898",
    ),

    # ── Sol Dorado ──
    # Mediteranski sunčan dan — topla zlatna na peščanoj bazi
    "sol_dorado": ThemeColors(
        bg_primary="#faf6ee",
        bg_secondary="#f2ecdf",
        bg_tertiary="#e8dfd0",
        bg_input="#ede5d6",
        text_primary="#2e2518",
        text_secondary="#6e5e48",
        text_muted="#9a8a72",
        text_accent="#1a1408",
        accent="#d48a0a",
        accent_hover="#e8a020",
        accent_pressed="#b87008",
        accent_subtle="#1ad48a0a",
        border="#e0d6c4",
        border_hover="#ccbfa8",
        border_focus="#d48a0a",
        slider_groove="#d8ccb8",
        slider_handle="#d48a0a",
        handle_border="#d48a0a",
        close_hover="#e81123",
        scrollbar_bg="#f2ecdf",
        scrollbar_handle="#ccbfa8",
        tooltip_bg="#2e2518",
        osd_bg="rgba(250, 246, 238, 210)",
        osd_text="#2e2518",
        osd_subtext="#6e5e48",
        osd_progress_bg="rgba(212, 138, 10, 0.15)",
        osd_progress_fill="#d48a0a",
        progress_gradient_start="#d48a0a",
        progress_gradient_end="#f0b840",
    ),

    # ── Mint Breeze ──
    # Svež mentol — hladan zelen na svetloj podlozi
    "mint_breeze": ThemeColors(
        bg_primary="#f2faf7",
        bg_secondary="#e6f4ef",
        bg_tertiary="#d4ebe3",
        bg_input="#ddf0e8",
        text_primary="#142e24",
        text_secondary="#4a6e5e",
        text_muted="#78a090",
        text_accent="#0a2018",
        accent="#0da06a",
        accent_hover="#20b880",
        accent_pressed="#088a58",
        accent_subtle="#1a0da06a",
        border="#c8e2d8",
        border_hover="#a8d0c0",
        border_focus="#0da06a",
        slider_groove="#c0d8ce",
        slider_handle="#0da06a",
        handle_border="#0da06a",
        close_hover="#e81123",
        scrollbar_bg="#e6f4ef",
        scrollbar_handle="#a8d0c0",
        tooltip_bg="#142e24",
        osd_bg="rgba(242, 250, 247, 210)",
        osd_text="#142e24",
        osd_subtext="#4a6e5e",
        osd_progress_bg="rgba(13, 160, 106, 0.15)",
        osd_progress_fill="#0da06a",
        progress_gradient_start="#0da06a",
        progress_gradient_end="#30d890",
    ),

    # ── Lavender Mist ──
    # Provansalska lavanda — nežni ljubičasti tonovi na sivkastoj bazi
    "lavender_mist": ThemeColors(
        bg_primary="#f6f4fa",
        bg_secondary="#edeaf4",
        bg_tertiary="#dfd8ec",
        bg_input="#e5e0f0",
        text_primary="#221a32",
        text_secondary="#5e5078",
        text_muted="#8a7ea8",
        text_accent="#150e24",
        accent="#7c4ddb",
        accent_hover="#9468f0",
        accent_pressed="#6838c0",
        accent_subtle="#1a7c4ddb",
        border="#d4cce4",
        border_hover="#bab0d4",
        border_focus="#7c4ddb",
        slider_groove="#ccc4dc",
        slider_handle="#7c4ddb",
        handle_border="#7c4ddb",
        close_hover="#e81123",
        scrollbar_bg="#edeaf4",
        scrollbar_handle="#bab0d4",
        tooltip_bg="#221a32",
        osd_bg="rgba(246, 244, 250, 210)",
        osd_text="#221a32",
        osd_subtext="#5e5078",
        osd_progress_bg="rgba(124, 77, 219, 0.15)",
        osd_progress_fill="#7c4ddb",
        progress_gradient_start="#7c4ddb",
        progress_gradient_end="#a880f0",
    ),

    # ── Coral Reef ──
    # Tropski koralni greben — živi koralj na plavkasto-belom
    "coral_reef": ThemeColors(
        bg_primary="#faf5f3",
        bg_secondary="#f4ece8",
        bg_tertiary="#eaddd6",
        bg_input="#efe3dc",
        text_primary="#32201a",
        text_secondary="#7a5448",
        text_muted="#a48076",
        text_accent="#22100a",
        accent="#e8553a",
        accent_hover="#f06e55",
        accent_pressed="#cc4430",
        accent_subtle="#1ae8553a",
        border="#e2d2ca",
        border_hover="#d0b8ae",
        border_focus="#e8553a",
        slider_groove="#d8c6bc",
        slider_handle="#e8553a",
        handle_border="#e8553a",
        close_hover="#cc4430",
        scrollbar_bg="#f4ece8",
        scrollbar_handle="#d0b8ae",
        tooltip_bg="#32201a",
        osd_bg="rgba(250, 245, 243, 210)",
        osd_text="#32201a",
        osd_subtext="#7a5448",
        osd_progress_bg="rgba(232, 85, 58, 0.15)",
        osd_progress_fill="#e8553a",
        progress_gradient_start="#e8553a",
        progress_gradient_end="#f08868",
    ),

    # ── Ocean Foam ──
    # Pena na talasima — svetloplava sa dubokim ocean akcentom
    "ocean_foam": ThemeColors(
        bg_primary="#f0f7fb",
        bg_secondary="#e4eff7",
        bg_tertiary="#d0e2f0",
        bg_input="#d8e8f4",
        text_primary="#12283a",
        text_secondary="#3e6480",
        text_muted="#6a90aa",
        text_accent="#081c2c",
        accent="#0870b8",
        accent_hover="#1a8ad6",
        accent_pressed="#065a96",
        accent_subtle="#1a0870b8",
        border="#c4d8e8",
        border_hover="#a6c4da",
        border_focus="#0870b8",
        slider_groove="#bcd0e2",
        slider_handle="#0870b8",
        handle_border="#0870b8",
        close_hover="#e81123",
        scrollbar_bg="#e4eff7",
        scrollbar_handle="#a6c4da",
        tooltip_bg="#12283a",
        osd_bg="rgba(240, 247, 251, 210)",
        osd_text="#12283a",
        osd_subtext="#3e6480",
        osd_progress_bg="rgba(8, 112, 184, 0.15)",
        osd_progress_fill="#0870b8",
        progress_gradient_start="#0870b8",
        progress_gradient_end="#30a0e8",
    ),

    # ── Linen & Ink ──
    # Starinski papir i mastilo — elegantna retro-moderna estetika
    "linen_ink": ThemeColors(
        bg_primary="#f5f0ea",
        bg_secondary="#ece5dc",
        bg_tertiary="#dfd6ca",
        bg_input="#e4dbd0",
        text_primary="#1e1814",
        text_secondary="#5c4e42",
        text_muted="#8a7c70",
        text_accent="#0e0a06",
        accent="#2c2420",
        accent_hover="#443830",
        accent_pressed="#1a1410",
        accent_subtle="#1a2c2420",
        border="#d6ccc0",
        border_hover="#c0b4a6",
        border_focus="#2c2420",
        slider_groove="#ccc0b2",
        slider_handle="#2c2420",
        handle_border="#2c2420",
        close_hover="#b03020",
        scrollbar_bg="#ece5dc",
        scrollbar_handle="#c0b4a6",
        tooltip_bg="#1e1814",
        osd_bg="rgba(245, 240, 234, 215)",
        osd_text="#1e1814",
        osd_subtext="#5c4e42",
        osd_progress_bg="rgba(44, 36, 32, 0.15)",
        osd_progress_fill="#2c2420",
        progress_gradient_start="#2c2420",
        progress_gradient_end="#6a5a4e",
    ),

    # ── Electric Lime ──
    # Puna energija — neon zeleno-žuta na čistoj beloj bazi
    "electric_lime": ThemeColors(
        bg_primary="#f6faf2",
        bg_secondary="#ecf4e4",
        bg_tertiary="#daeaca",
        bg_input="#e2f0d4",
        text_primary="#1a2e10",
        text_secondary="#4a6a34",
        text_muted="#72944e",
        text_accent="#102006",
        accent="#4a9e10",
        accent_hover="#5cb820",
        accent_pressed="#3a8408",
        accent_subtle="#1a4a9e10",
        border="#cce2b8",
        border_hover="#b0d098",
        border_focus="#4a9e10",
        slider_groove="#c0d6a8",
        slider_handle="#4a9e10",
        handle_border="#4a9e10",
        close_hover="#e81123",
        scrollbar_bg="#ecf4e4",
        scrollbar_handle="#b0d098",
        tooltip_bg="#1a2e10",
        osd_bg="rgba(246, 250, 242, 210)",
        osd_text="#1a2e10",
        osd_subtext="#4a6a34",
        osd_progress_bg="rgba(74, 158, 16, 0.15)",
        osd_progress_fill="#4a9e10",
        progress_gradient_start="#4a9e10",
        progress_gradient_end="#78d040",
    ),

    # ── Blush Copper ──
    # Luksuzna mešavina — roze-bakarna na slonovači
    "blush_copper": ThemeColors(
        bg_primary="#faf5f2",
        bg_secondary="#f2eae4",
        bg_tertiary="#e6d8d0",
        bg_input="#ecddd4",
        text_primary="#30201c",
        text_secondary="#725448",
        text_muted="#9a7e72",
        text_accent="#20100a",
        accent="#c06840",
        accent_hover="#d88058",
        accent_pressed="#a45530",
        accent_subtle="#1ac06840",
        border="#dec8bc",
        border_hover="#ccb0a2",
        border_focus="#c06840",
        slider_groove="#d4beb0",
        slider_handle="#c06840",
        handle_border="#c06840",
        close_hover="#a03020",
        scrollbar_bg="#f2eae4",
        scrollbar_handle="#ccb0a2",
        tooltip_bg="#30201c",
        osd_bg="rgba(250, 245, 242, 210)",
        osd_text="#30201c",
        osd_subtext="#725448",
        osd_progress_bg="rgba(192, 104, 64, 0.15)",
        osd_progress_fill="#c06840",
        progress_gradient_start="#c06840",
        progress_gradient_end="#e09070",
    ),
}


# ═══════════════════════════════════════════
#  OSD TEME
# ═══════════════════════════════════════════

OSD_THEMES: Dict[str, OsdTheme] = {
    "minimal": OsdTheme(
        name="Minimal",
        bg="rgba(0, 0, 0, 160)",
        text_color="#ffffff",
        subtext_color="#cccccc",
        progress_bg="rgba(255, 255, 255, 0.15)",
        progress_fill="#ffffff",
        border_radius=8,
        icon_size=28,
        text_size=13,
        padding_h=20,
        padding_v=12,
    ),
    "glass": OsdTheme(
        name="Glass",
        bg="rgba(30, 30, 30, 140)",
        text_color="#ffffff",
        subtext_color="#d0d0d0",
        progress_bg="rgba(255, 255, 255, 0.18)",
        progress_fill="rgba(255, 255, 255, 0.85)",
        border_radius=16,
        icon_size=32,
        text_size=14,
        blur=True,
        border="1px solid #1affffff",
        padding_h=28,
        padding_v=18,
    ),
    "neon": OsdTheme(
        name="Neon",
        bg="rgba(0, 0, 0, 200)",
        text_color="#00ff88",
        subtext_color="#00cc66",
        progress_bg="rgba(0, 255, 136, 0.15)",
        progress_fill="#00ff88",
        border_radius=4,
        icon_size=30,
        text_size=14,
        border="1px solid #4d00ff88",
        shadow="0 0 20px rgba(0, 255, 136, 0.2)",
        padding_h=24,
        padding_v=14,
    ),
    "cinema": OsdTheme(
        name="Cinema",
        bg="rgba(10, 10, 10, 220)",
        text_color="#f5c518",
        subtext_color="#c8a010",
        progress_bg="rgba(245, 197, 24, 0.15)",
        progress_fill="#f5c518",
        border_radius=2,
        icon_size=36,
        text_size=15,
        padding_h=32,
        padding_v=20,
    ),
    "frosted": OsdTheme(
        name="Frosted",
        bg="rgba(40, 40, 50, 120)",
        text_color="#e8e8f0",
        subtext_color="#a0a0b0",
        progress_bg="rgba(255, 255, 255, 0.12)",
        progress_fill="rgba(200, 200, 220, 0.8)",
        border_radius=20,
        icon_size=30,
        text_size=13,
        blur=True,
        border="1px solid #0fffffff",
        padding_h=26,
        padding_v=16,
    ),
    "vibrant": OsdTheme(
        name="Vibrant",
        bg="rgba(20, 0, 40, 190)",
        text_color="#ff6bff",
        subtext_color="#cc55cc",
        progress_bg="rgba(255, 107, 255, 0.15)",
        progress_fill="linear-gradient(90deg, #ff6bff, #6baaff)",
        border_radius=14,
        icon_size=34,
        text_size=14,
        border="1px solid #33ff6bff",
        shadow="0 4px 30px rgba(255, 107, 255, 0.15)",
        padding_h=26,
        padding_v=16,
    ),
}


# ═══════════════════════════════════════════
#  THEME META (za prikaz u settings-u)
# ═══════════════════════════════════════════

THEME_META: Dict[str, Dict[str, str]] = {
    "midnight_red": {
        "name": "Midnight Red",
        "description": "Klasična tamna tema sa crvenim akcentom",
        "icon": "🔴",
        "preview_colors": "#0f0f0f,#e50914,#1e1e1e",
    },
    "abyss_blue": {
        "name": "Abyss Blue",
        "description": "Duboki ocean sa plavim sjajem",
        "icon": "🔵",
        "preview_colors": "#080c14,#2d7ff9,#141c2e",
    },
    "emerald_night": {
        "name": "Emerald Night",
        "description": "Smaragdna noć u šumi",
        "icon": "🟢",
        "preview_colors": "#0a0f0d,#10b981,#15241d",
    },
    "sunset_amber": {
        "name": "Sunset Amber",
        "description": "Topla svetlost zalaska sunca",
        "icon": "🟡",
        "preview_colors": "#12100c,#f59e0b,#241e16",
    },
    "violet_haze": {
        "name": "Violet Haze",
        "description": "Misteriozna ljubičasta izmaglica",
        "icon": "🟣",
        "preview_colors": "#0e0a14,#8b5cf6,#1e1630",
    },
    "rose_gold": {
        "name": "Rose Gold",
        "description": "Elegantan ruža-zlato sjaj",
        "icon": "🩷",
        "preview_colors": "#120e0e,#f43f5e,#261c1c",
    },
    "arctic_silver": {
        "name": "Arctic Silver",
        "description": "Hladan i čist arktički sivi",
        "icon": "⚪",
        "preview_colors": "#111315,#94a3b8,#1e2328",
    },
    "cyber_teal": {
        "name": "Cyber Teal",
        "description": "Futuristička tirkizna energija",
        "icon": "🩵",
        "preview_colors": "#080d0e,#14b8a6,#121f22",
    },
    "oled_pure": {
        "name": "OLED Pure",
        "description": "Čista crna za OLED ekrane",
        "icon": "⚫",
        "preview_colors": "#000000,#ffffff,#141414",
    },
    "polar_light": {
        "name": "Polar Light",
        "description": "Skandinavski sneg sa ledenim plavim",
        "icon": "🏔️",
        "preview_colors": "#f5f7fa,#1e6cf0,#e2e6ed",
    },
    "sakura_bloom": {
        "name": "Sakura Bloom",
        "description": "Japanski trešnjin cvet na kremu",
        "icon": "🌸",
        "preview_colors": "#fdf6f4,#d84060,#f0ddd8",
    },
    "sol_dorado": {
        "name": "Sol Dorado",
        "description": "Mediteransko sunce i zlatni pesak",
        "icon": "☀️",
        "preview_colors": "#faf6ee,#d48a0a,#e8dfd0",
    },
    "mint_breeze": {
        "name": "Mint Breeze",
        "description": "Svež mentol vetar kroz baštu",
        "icon": "🍃",
        "preview_colors": "#f2faf7,#0da06a,#d4ebe3",
    },
    "lavender_mist": {
        "name": "Lavender Mist",
        "description": "Provansalska lavanda u izmaglici",
        "icon": "💜",
        "preview_colors": "#f6f4fa,#7c4ddb,#dfd8ec",
    },
    "coral_reef": {
        "name": "Coral Reef",
        "description": "Tropski koralni greben u toplom moru",
        "icon": "🪸",
        "preview_colors": "#faf5f3,#e8553a,#eaddd6",
    },
    "ocean_foam": {
        "name": "Ocean Foam",
        "description": "Pena na talasima atlantskog okeana",
        "icon": "🌊",
        "preview_colors": "#f0f7fb,#0870b8,#d0e2f0",
    },
    "linen_ink": {
        "name": "Linen & Ink",
        "description": "Starinski papir i kaligrafsko mastilo",
        "icon": "📜",
        "preview_colors": "#f5f0ea,#2c2420,#dfd6ca",
    },
    "electric_lime": {
        "name": "Electric Lime",
        "description": "Eksplozija energije u neon zelenoj",
        "icon": "⚡",
        "preview_colors": "#f6faf2,#4a9e10,#daeaca",
    },
    "blush_copper": {
        "name": "Blush Copper",
        "description": "Luksuzna bakarna toplina na slonovači",
        "icon": "🥉",
        "preview_colors": "#faf5f2,#c06840,#e6d8d0",
    },
}

OSD_THEME_META: Dict[str, Dict[str, str]] = {
    "minimal": {"name": "Minimal", "description": "Čist i diskretan", "icon": "◻️"},
    "glass": {"name": "Glass", "description": "Stakleni efekat sa blur-om", "icon": "🪟"},
    "neon": {"name": "Neon", "description": "Svetleći neonski stil", "icon": "💚"},
    "cinema": {"name": "Cinema", "description": "Bioskopski zlatni prikaz", "icon": "🎬"},
    "frosted": {"name": "Frosted", "description": "Zaleđeno staklo", "icon": "❄️"},
    "vibrant": {"name": "Vibrant", "description": "Živi pink-plavi gradijent", "icon": "💜"},
}


def get_theme(name: str) -> ThemeColors:
    """Vrati temu po imenu, ili default.

    Podržava alias 'dark' -> 'midnight_red' za kompatibilnost
    sa starim config fajlovima.
    """
    aliases = {"dark": "midnight_red"}
    key = aliases.get(name, name)
    return THEMES.get(key, THEMES["midnight_red"])


def get_osd_theme(name: str) -> OsdTheme:
    """Vrati OSD temu po imenu, ili default."""
    return OSD_THEMES.get(name, OSD_THEMES["minimal"])


def get_theme_names() -> List[str]:
    """Vrati listu svih dostupnih tema."""
    return list(THEMES.keys())


def get_osd_theme_names() -> List[str]:
    """Vrati listu svih OSD tema."""
    return list(OSD_THEMES.keys())