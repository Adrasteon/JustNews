"""
Common observability utilities for JustNewsAgent
"""

import os
import logging
from typing import Optional
from logging.handlers import RotatingFileHandler

# Ensure LOG_DIR is defined
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'logs')
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
    # Derive a log file name from the logger name
    log_file_name = name.split('.')[1] if '.' in name else 'app'
    log_file_path = os.path.join(LOG_DIR, f'{log_file_name}.log')

    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers if logger is already configured
    if logger.hasHandlers():
        return logger

    # Set logging level to DEBUG for detailed information
    logger.setLevel(logging.DEBUG)
    
    # Create a rotating file handler
    handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Also add a console handler for immediate feedback during development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def setup_logging(level: int = logging.INFO, format_string: Optional[str] = None) -> None:
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
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler()] # Default to console
    )
