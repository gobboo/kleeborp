# utils/logger.py
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_format: Optional[str] = None,
    log_file: Optional[str] = None,
    max_bytes: int = 10_485_760,  # 10MB
    backup_count: int = 5,
):
    """
    Setup logging configuration for Kleeborp.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Custom log format string
        log_file: Path to log file (if None, only console logging)
        max_bytes: Maximum size of each log file before rotation
        backup_count: Number of backup files to keep
    """
    # Default format with color support
    if log_format is None:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatters
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Colored formatter for console (optional but nice)
    colored_formatter = ColoredFormatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler (with colors)
    kleeborp_filter = KleeborgLogFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(colored_formatter)
    console_handler.addFilter(kleeborp_filter)

    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(kleeborp_filter)

        root_logger.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger("discord").setLevel(logging.ERROR)
    logging.getLogger("websockets").setLevel(logging.ERROR)

    root_logger.info(f"Logging initialized at {level} level")


class KleeborgLogFilter(logging.Filter):
    """Only allow logs from Kleeborp modules"""

    ALLOWED_PREFIXES = (
        "core.",
        "module.",
        "modules.",
        "events.",
        "services.",
        "utils.",
        "__main__",
        "discord",
        "root",  # Allow root logger messages
    )

    def filter(self, record):
        # Allow if logger name starts with any allowed prefix
        return any(record.name.startswith(prefix) for prefix in self.ALLOWED_PREFIXES)


class ColoredFormatter(logging.Formatter):
    """
    Colored log formatter for console output.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record):
        # Save original levelname
        levelname = record.levelname

        # Add color to levelname
        if levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[levelname]}{self.BOLD}{levelname:8s}{self.RESET}"
            )

        # Format the message
        result = super().format(record)

        # Restore original levelname
        record.levelname = levelname

        return result


# Context manager for temporary log level changes
class LogLevel:
    """
    Context manager to temporarily change log level.

    Usage:
        with LogLevel('module.name', logging.DEBUG):
            # Debug logging enabled for this block
            do_something()
    """

    def __init__(self, logger_name: str, level: int):
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.old_level = None

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.old_level)
