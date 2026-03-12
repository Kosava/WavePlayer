"""WavePlayer plugin system.

plugins/
├── __init__.py          # Ovaj fajl
├── plugin_api.py        # Bazni interfejsi (WavePlugin, SubtitlePlugin...)
├── plugin_manager.py    # Manager koji otkriva i učitava plugine
└── subtitle_search.py   # Subtitle search plugin (OpenSubtitles + Podnapisi)
"""

from .plugin_api import (
    WavePlugin,
    SubtitlePlugin,
    PluginContext,
    PluginInfo,
    PluginType,
    SubtitleResult,
)
from .plugin_manager import PluginManager

__all__ = [
    "WavePlugin",
    "SubtitlePlugin",
    "PluginContext",
    "PluginInfo",
    "PluginType",
    "SubtitleResult",
    "PluginManager",
]
