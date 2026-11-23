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
_POLL_REQUESTS = {("GET", "/api/dev/mtime"), ("POST", "/api/system/heartbeat")}


class _QuietPolls(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn access records carry method, path and status as message arguments.
        args = record.args
        if record.levelno != logging.INFO or not isinstance(args, tuple) or len(args) != 5:
            return True
        _, method, path, _, status = args
        if not isinstance(path, str) or not isinstance(status, int):
            return True
        successful_poll = 200 <= status < 300 and (method, path.partition("?")[0]) in _POLL_REQUESTS
        return not successful_poll


def setup_logging(level: int = logging.INFO) -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(log_filter, _QuietPolls) for log_filter in access.filters):
        access.addFilter(_QuietPolls())

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
