"""Logging configuration for Laqta backend."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure structured, clean console logging for Laqta."""
    logger = logging.getLogger("qatta")
    logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()
