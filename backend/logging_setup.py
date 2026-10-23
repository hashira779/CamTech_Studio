"""
Sends every backend.* logger to the console and to logs/vida.log.

Without this, Python drops INFO messages and the aligner's timeouts and fallbacks leave no
trace, so a slow or failed sync cannot be diagnosed after the fact.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from backend.paths import BASE_DIR

LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "vida.log")


def setup_logging(level: int = logging.INFO) -> None:
    logger = logging.getLogger("backend")
    if logger.handlers:  # uvicorn --reload imports the app again
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        logger.addHandler(file_handler)
    except OSError as e:
        logger.warning(f"Logging to console only; cannot open {LOG_FILE}: {e}")

    logger.setLevel(level)
    logger.propagate = False
