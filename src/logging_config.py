"""
Centralized logging configuration for YT News Generator.

Usage:
    from logging_config import get_logger
    logger = get_logger(__name__)

    logger.info("Processing started")
    logger.error("Something failed", exc_info=True)
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ==========================================
# Configuration
# ==========================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotation settings
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
BACKUP_COUNT = 5  # Keep 5 backup files

# ==========================================
# Setup
# ==========================================

_initialized = False


def setup_logging():
    """Initialize the logging system. Called automatically on first get_logger()."""
    global _initialized
    if _initialized:
        return

    # Create logs directory
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # ==========================================
    # Console Handler (stdout)
    # ==========================================
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ==========================================
    # Rotating File Handler - All logs
    # ==========================================
    all_log_path = LOG_DIR / "app.log"
    file_handler = RotatingFileHandler(
        all_log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # ==========================================
    # Rotating File Handler - Errors only
    # ==========================================
    error_log_path = LOG_DIR / "error.log"
    error_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    # ==========================================
    # Suppress noisy third-party loggers
    # ==========================================
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _initialized = True

    # Log startup
    startup_logger = logging.getLogger("logging_config")
    startup_logger.info(f"Logging initialized - level={LOG_LEVEL}, log_dir={LOG_DIR}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given module name.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Starting process")
        logger.debug("Debug details: %s", data)
        logger.error("Failed!", exc_info=True)
    """
    setup_logging()
    return logging.getLogger(name)


# ==========================================
# Convenience functions for CLI scripts
# ==========================================

def log_section(logger: logging.Logger, title: str):
    """Log a section header for visual separation."""
    logger.info("=" * 50)
    logger.info(title)
    logger.info("=" * 50)


def log_step(logger: logging.Logger, step_num: int, total: int, description: str):
    """Log a numbered step in a process."""
    logger.info(f"Step {step_num}/{total}: {description}")


def log_success(logger: logging.Logger, message: str):
    """Log a success message."""
    logger.info(f"SUCCESS: {message}")


def log_timing(logger: logging.Logger, operation: str, seconds: float):
    """Log operation timing."""
    logger.info(f"{operation} completed in {seconds:.2f}s")
