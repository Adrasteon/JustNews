"""
Security utilities for Analyst Agent - Input validation and sanitization.
"""

import hashlib
import re
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)

# Security configuration
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

def sanitize_content(content: str) -> str:
    """
    Sanitize content by removing potentially dangerous elements.

    Args:
        content: The content to sanitize

    Returns:
        str: Sanitized content
    """
    if not content or not isinstance(content, str):
        return ""

    # Length limit
    if len(content) > MAX_CONTENT_LENGTH:
        logger.warning(f"Content truncated: {len(content)} > {MAX_CONTENT_LENGTH}")
        content = content[:MAX_CONTENT_LENGTH]

    # Remove potentially dangerous HTML/script content
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'<iframe[^>]*>.*?</iframe>',  # Iframes
        r'<object[^>]*>.*?</object>',  # Object tags
        r'<embed[^>]*>.*?</embed>',    # Embed tags
        r'javascript:',                # JavaScript URLs
        r'vbscript:',                  # VBScript URLs
        r'data:',                      # Data URLs
        r'on\w+\s*=',                  # Event handlers
    ]

    for pattern in dangerous_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)

    return content

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks.

    Args:
        filename: The filename to sanitize

    Returns:
        str: Sanitized filename
    """
    if not filename or not isinstance(filename, str):
        return "unknown_file"

    # Remove path separators and dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)

    # Remove path traversal attempts
    filename = re.sub(r'\.\.', '', filename)

    # Limit length
    if len(filename) > 255:
        filename = filename[:255]

    # Ensure it's not empty
    if not filename.strip():
        filename = "unknown_file"

    return filename

def validate_content_size(content: str, max_size: int = MAX_CONTENT_LENGTH) -> bool:
    """
    Validate content size.

    Args:
        content: The content to check
        max_size: Maximum allowed size in bytes

    Returns:
        bool: True if content size is acceptable
    """
    if not content:
        return True

    size = len(content.encode('utf-8'))
    if size > max_size:
        logger.warning(f"Content size validation failed: {size} > {max_size}")
        return False

    return True

def log_security_event(event_type: str, details: dict[str, Any], level: str = 'warning'):
    """
    Log security-related events.

    Args:
        event_type: Type of security event
        details: Event details
        level: Log level (debug, info, warning, error)
    """
    message = f"SECURITY EVENT [{event_type}]: {details}"

    if level == 'debug':
        logger.debug(message)
    elif level == 'info':
        logger.info(message)
    elif level == 'warning':
        logger.warning(message)
    elif level == 'error':
        logger.error(message)

def hash_content(content: str) -> str:
    """
    Create a hash of content for integrity checking.

    Args:
        content: The content to hash

    Returns:
        str: SHA256 hash of the content
    """
    if not content:
        return ""

    return hashlib.sha256(content.encode('utf-8')).hexdigest()
