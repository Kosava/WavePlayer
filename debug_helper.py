"""Debug helper za praćenje torrent flow-a."""

import logging
import os
import time
import traceback
from functools import wraps

logger = logging.getLogger(__name__)

def debug_trace(func):
    """Dekorator koji loguje ulaz/izlaz iz funkcije."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"→ {func.__name__} pozvana")
        start = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = (time.time() - start) * 1000
            logger.debug(f"← {func.__name__} završena za {elapsed:.1f}ms, result: {result}")
            return result
        except Exception as e:
            logger.error(f"✗ {func.__name__} izazvala grešku: {e}")
            traceback.print_exc()
            raise
    return wrapper

def log_file_operation(path, operation):
    """Loguj fajl operaciju."""
    if os.path.exists(path):
        size = os.path.getsize(path) / (1024 * 1024)
        logger.debug(f"FILE {operation}: {path} (postoji, {size:.1f} MB)")
    else:
        logger.debug(f"FILE {operation}: {path} (NE POSTOJI)")