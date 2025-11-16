"""
Common observability utilities for JustNewsAgent
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Ensure LOG_DIR is defined
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'logs'))
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance for the given name.
    This function now creates a logger that writes to a dedicated, rotating file.

    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    # Derive a log file name from the logger name. Use the last component
    # after any dots so callers like "test.module" map to "module.log" as
    # expected by tests.
    log_file_name = name.split('.')[-1] if name else 'app'
    log_file_path = os.path.join(LOG_DIR, f'{log_file_name}.log')

    logger = logging.getLogger(name)

    # Always ensure the logger has our expected configuration. Do not early-return
    # just because handlers exist; tests rely on specific handlers and levels.
    logger.setLevel(logging.DEBUG)

    # Create or attach a rotating file handler if none present
    has_file = any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
    if not has_file:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Ensure a console handler exists. File handlers are also StreamHandlers, so
    # we explicitly ensure we don't treat file handlers as console handlers.
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def setup_logging(level: int = logging.INFO, format_string: str | None = None) -> None:
    """
    Setup basic logging configuration for the application.
    This function is now a compatibility wrapper and the main configuration
    is handled by get_logger to ensure file-based logging.
    
    Args:
        level: Logging level (default: INFO)
        format_string: Custom format string (optional)
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # This basicConfig will apply to any loggers that don't get configured
    # by get_logger, but our goal is to use get_logger everywhere.
    # Configure the root logger to the requested level when requested
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format=format_string,
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler()],  # Default to console
        )
