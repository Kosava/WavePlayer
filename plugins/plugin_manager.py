"""Plugin Manager za WavePlayer.

Otkriva, učitava i upravlja pluginima.
Plugini su Python moduli u plugins/ direktorijumu koji sadrže
klasu koja nasleđuje WavePlugin ili SubtitlePlugin.

PORTABILITY NOTES:
  - C++: dlopen/LoadLibrary za shared libraries
  - Rust: libloading crate za dynamic loading
"""

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

from .plugin_api import (
    WavePlugin,
    SubtitlePlugin,
    PluginContext,
    PluginInfo,
    PluginType,
    SubtitleResult,
)

logger = logging.getLogger(__name__)


class PluginManager:
    """Upravlja svim pluginima u sistemu.

    Lifecycle:
      1. discover_plugins() — skenira direktorijum za plugine
      2. load_plugin(name) — instancira plugin
      3. initialize_all(context) — inicijalizuje sve učitane plugine
      4. shutdown_all() — gasi sve plugine
    """

    def __init__(self, plugin_dir: Optional[str] = None) -> None:
        # Direktorijum za plugine — default je plugins/ pored ovog fajla
        if plugin_dir:
            self._plugin_dir = Path(plugin_dir)
        else:
            self._plugin_dir = Path(__file__).parent

        self._plugins: Dict[str, WavePlugin] = {}
        self._plugin_classes: Dict[str, Type[WavePlugin]] = {}
        self._context: Optional[PluginContext] = None

        logger.info(f"PluginManager: dir={self._plugin_dir}")

    @property
    def plugins(self) -> Dict[str, WavePlugin]:
        """Svi učitani plugini."""
        return self._plugins

    def get_all_plugins(self) -> List[WavePlugin]:
        """Vrati listu svih učitanih plugina."""
        return list(self._plugins.values())

    def get_subtitle_plugins(self) -> List[SubtitlePlugin]:
        """Vrati samo subtitle plugine."""
        return [
            p for p in self._plugins.values()
            if isinstance(p, SubtitlePlugin) and p.enabled
        ]

    def get_plugin(self, name: str) -> Optional[WavePlugin]:
        """Vrati plugin po imenu."""
        return self._plugins.get(name)

    # --- Discovery & Loading ---

    def discover_plugins(self) -> List[str]:
        """Skeniraj plugin direktorijum i vrati imena pronađenih plugina."""
        found = []

        if not self._plugin_dir.exists():
            logger.warning(f"Plugin dir ne postoji: {self._plugin_dir}")
            return found

        for item in self._plugin_dir.iterdir():
            # Preskoči __pycache__, __init__, plugin_api, plugin_manager
            if item.name.startswith("_"):
                continue
            if item.name in ("plugin_api.py", "plugin_manager.py"):
                continue

            if item.is_file() and item.suffix == ".py":
                name = item.stem
                found.append(name)
                logger.debug(f"Plugin otkriven: {name}")

            elif item.is_dir() and (item / "__init__.py").exists():
                name = item.name
                found.append(name)
                logger.debug(f"Plugin paket otkriven: {name}")

        logger.info(f"Otkriveno {len(found)} plugina: {found}")
        return found

    def load_plugin(self, name: str) -> bool:
        """Učitaj plugin po imenu. Vrati True ako uspešno."""
        if name in self._plugins:
            logger.debug(f"Plugin '{name}' već učitan")
            return True

        try:
            # Pokušaj import kao submodul paketa
            module_path = self._plugin_dir / f"{name}.py"
            package_path = self._plugin_dir / name / "__init__.py"

            if module_path.exists():
                spec = importlib.util.spec_from_file_location(
                    f"plugins.{name}", str(module_path)
                )
            elif package_path.exists():
                spec = importlib.util.spec_from_file_location(
                    f"plugins.{name}", str(package_path),
                    submodule_search_locations=[str(self._plugin_dir / name)]
                )
            else:
                logger.error(f"Plugin '{name}' nije pronađen")
                return False

            if spec is None or spec.loader is None:
                logger.error(f"Plugin '{name}': spec je None")
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # Pronađi klasu koja nasleđuje WavePlugin
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, WavePlugin)
                        and attr is not WavePlugin
                        and attr is not SubtitlePlugin):
                    plugin_class = attr
                    break

            if plugin_class is None:
                logger.error(f"Plugin '{name}': nema WavePlugin klasu")
                return False

            # Instanciraj
            instance = plugin_class()
            info = instance.get_info()
            self._plugins[info.name] = instance
            self._plugin_classes[info.name] = plugin_class

            logger.info(f"Plugin učitan: {info.name} v{info.version} ({info.description})")
            return True

        except Exception as e:
            logger.error(f"Greška pri učitavanju plugina '{name}': {e}", exc_info=True)
            return False

    def load_all(self) -> int:
        """Otkrij i učitaj sve plugine. Vrati broj uspešno učitanih."""
        names = self.discover_plugins()
        loaded = 0
        for name in names:
            if self.load_plugin(name):
                loaded += 1
        return loaded

    # --- Initialization ---

    def initialize_all(self, context: PluginContext) -> None:
        """Inicijalizuj sve učitane plugine sa kontekstom."""
        self._context = context
        for name, plugin in self._plugins.items():
            try:
                if plugin.initialize(context):
                    logger.info(f"Plugin inicijalizovan: {name}")
                else:
                    logger.warning(f"Plugin inicijalizacija neuspešna: {name}")
                    plugin.enabled = False
            except Exception as e:
                logger.error(f"Greška pri inicijalizaciji plugina '{name}': {e}")
                plugin.enabled = False

    def shutdown_all(self) -> None:
        """Ugasi sve plugine."""
        for name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
                logger.debug(f"Plugin ugašen: {name}")
            except Exception as e:
                logger.error(f"Greška pri gašenju plugina '{name}': {e}")
        self._plugins.clear()

    def reload_all(self) -> None:
        """Ponovo učitaj sve plugine (gašenje, čišćenje, ponovno učitavanje i inicijalizacija)."""
        for plugin in self._plugins.values():
            if hasattr(plugin, "shutdown"):
                plugin.shutdown()

        self._plugins.clear()
        self.load_all()
        if self._context:
            self.initialize_all(self._context)

    # --- Subtitle convenience ---

    def search_subtitles(
        self,
        query: str,
        languages: List[str],
        file_hash: str = "",
        file_path: str = "",
    ) -> List[SubtitleResult]:
        """Pretraži titlove kroz SVE subtitle plugine."""
        all_results = []
        for plugin in self.get_subtitle_plugins():
            try:
                info = plugin.get_info()
                logger.debug(f"Pretraga titlova: {info.name}...")
                results = plugin.search(query, languages, file_hash, file_path)
                all_results.extend(results)
                logger.info(f"{info.name}: {len(results)} rezultata")
            except Exception as e:
                logger.error(f"Greška pri pretrazi ({plugin.get_info().name}): {e}")
        return all_results

    def download_subtitle(
        self, result: SubtitleResult, dest_dir: str
    ) -> Optional[str]:
        """Download titl koristeći odgovarajući plugin."""
        for plugin in self.get_subtitle_plugins():
            if plugin.get_info().name == result.provider:
                try:
                    return plugin.download(result, dest_dir)
                except Exception as e:
                    logger.error(f"Download greška ({result.provider}): {e}")
                    return None

        logger.error(f"Plugin '{result.provider}' nije pronađen za download")
        return None