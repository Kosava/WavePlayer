"""WavePlayer - Modern video player application.

Entry point for the application.
Initializes logging, creates QApplication and main window.

Usage:
    python app.py
    python app.py /path/to/video.mp4

PORTABILITY NOTES:
  - C++: main.cpp with QApplication setup
  - Rust: fn main() with qt6-rs Application
"""

import sys
import logging
import os
import locale

# MPV/libmpv zahteva C locale za numeričke vrednosti.
# Mora biti pre BILO KAKVOG importa koji učita libmpv.
# Bez ovoga -> SEGFAULT na non-English sistemima.
locale.setlocale(locale.LC_ALL, "C")
os.environ["LC_NUMERIC"] = "C"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow


def setup_logging() -> None:
    """Postavi logging konfiguraciju."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    """Glavna funkcija - entry point aplikacije."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("WavePlayer pokrenut")

    # Kreiraj Qt aplikaciju
    app = QApplication(sys.argv)
    app.setApplicationName("WavePlayer")
    app.setOrganizationName("WavePlayer")

    # Omogući high DPI
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Kreiraj i prikaži glavni prozor
    window = MainWindow()
    window.show()

    # Ako je prosleđen fajl kao argument, učitaj ga
    args = app.arguments()
    if len(args) > 1:
        file_path = args[1]
        if os.path.isfile(file_path):
            logger.info(f"Učitavam fajl iz argumenta: {file_path}")
            window._load_file(file_path)

    logger.info("Ulazim u event loop")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())