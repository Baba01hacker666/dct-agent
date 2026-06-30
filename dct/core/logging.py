"""
dct.core.logging
Structured file logging for DCT Agent.
Writes to ~/.config/dct/dct.log with automatic rotation at 1MB.
"""

from __future__ import annotations
import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.expanduser("~"), ".config", "dct")
_LOG_FILE = os.path.join(_LOG_DIR, "dct.log")
_MAX_BYTES = 1_048_576  # 1 MB
_BACKUP_COUNT = 2

_log_initialized = False


def _init_logging() -> None:
    """Configure the root DCT logger (idempotent)."""
    global _log_initialized
    if _log_initialized:
        return

    os.makedirs(_LOG_DIR, exist_ok=True)

    logger = logging.getLogger("dct")
    logger.setLevel(logging.DEBUG)

    # File handler with rotation
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(name)s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(fh)

    # Prevent propagation to root logger (avoids console noise)
    logger.propagate = False

    _log_initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name (e.g. 'dct.core.registry')."""
    _init_logging()
    return logging.getLogger(name)
