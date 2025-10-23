"""
Security utilities for Scout Agent - Input validation, sanitization, and security measures.
"""

import hashlib
import re
import time
from functools import wraps
from typing import Any
from urllib.parse import urlparse

from common.observability import get_logger

logger = get_logger(__name__)

# Security configuration
MAX_URL_LENGTH = 2048
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
MAX_REQUESTS_PER_MINUTE = 60
REQUEST_TIMEOUT = 30
ALLOWED_SCHEMES = {'http', 'https'}
BLOCKED_DOMAINS = {
    'localhost', '127.0.0.1', '0.0.0.0',
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',  # Private networks
    '169.254.0.0/16',  # Link-local
}

# Rate limiting storage (in production, use Redis or similar)
rate_limit_store: dict[str, list[float]] = {}

def validate_url(url: str) -> bool:
    """
    Comprehensive URL validation with security checks.

    Args:
        url: The URL to validate

    Returns:
        bool: True if URL is valid and safe, False otherwise
    """
    if not url or not isinstance(url, str):
        logger.warning("URL validation failed: empty or non-string input")
        return False

    # Length check
    if len(url) > MAX_URL_LENGTH:
        logger.warning(f"URL validation failed: URL too long ({len(url)} > {MAX_URL_LENGTH})")
        return False

    try:
        parsed = urlparse(url)

        # Scheme validation
        if parsed.scheme not in ALLOWED_SCHEMES:
            logger.warning(f"URL validation failed: invalid scheme '{parsed.scheme}'")
            return False

        # Domain validation
        if not parsed.netloc:
            logger.warning("URL validation failed: no domain specified")
            return False

        # Check for blocked domains
        domain = parsed.netloc.lower()
        if any(blocked in domain for blocked in BLOCKED_DOMAINS):
            logger.warning(f"URL validation failed: blocked domain '{domain}'")
            return False

        # Check for IP addresses in private ranges
        if _is_private_ip(domain):
            logger.warning(f"URL validation failed: private IP address '{domain}'")
            return False

        # Path traversal prevention
        if '..' in parsed.path or parsed.path.startswith('/../'):
            logger.warning(f"URL validation failed: path traversal attempt in '{parsed.path}'")
            return False

        # Query parameter validation (basic)
        if parsed.query:
            if _contains_malicious_query(parsed.query):
                logger.warning("URL validation failed: malicious query parameters")
                return False

        return True

    except Exception as e:
        logger.warning(f"URL validation failed: parsing error - {e}")
        return False

def _is_private_ip(domain: str) -> bool:
    """Check if domain is a private IP address."""
    try:
        import ipaddress
        ip = ipaddress.ip_address(domain)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except (ipaddress.AddressValueError, ValueError) as e:
        logger.debug(f"Failed to parse IP address {domain}: {e}")
        return False

def _contains_malicious_query(query: str) -> bool:
    """Check for potentially malicious query parameters."""
    malicious_patterns = [
        r'<script', r'javascript:', r'data:', r'vbscript:',
        r'on\w+\s*=', r'<\w+', r'%3C%73%63%72%69%70%74'  # URL-encoded <script
    ]

    query_lower = query.lower()
    for pattern in malicious_patterns:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return True
    return False

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

def rate_limit(identifier: str, max_requests: int = MAX_REQUESTS_PER_MINUTE) -> bool:
    """
    Check if request should be rate limited.

    Args:
        identifier: Unique identifier for the requester (e.g., IP address)
        max_requests: Maximum requests per minute

    Returns:
        bool: True if request should be allowed, False if rate limited
    """
    current_time = time.time()
    window_start = current_time - 60  # 1 minute window

    if identifier not in rate_limit_store:
        rate_limit_store[identifier] = []

    # Remove old requests outside the window
    rate_limit_store[identifier] = [
        req_time for req_time in rate_limit_store[identifier]
        if req_time > window_start
    ]

    # Check if under limit
    if len(rate_limit_store[identifier]) < max_requests:
        rate_limit_store[identifier].append(current_time)
        return True

    logger.warning(f"Rate limit exceeded for {identifier}")
    return False

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

def secure_request_params(url: str, **kwargs) -> dict[str, Any]:
    """
    Create secure request parameters with timeouts and security headers.

    Args:
        url: The URL being requested
        **kwargs: Additional parameters

    Returns:
        dict: Secure request parameters
    """
    secure_params = {
        'timeout': REQUEST_TIMEOUT,
        'headers': {
            'User-Agent': 'JustNewsAgent-Scout/1.0 (Security-Focused)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'close',
            'Upgrade-Insecure-Requests': '1',
        }
    }

    # Add any additional parameters
    secure_params.update(kwargs)

    return secure_params

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

def validate_batch_urls(urls: list[str]) -> list[str]:
    """
    Validate a batch of URLs and return only the valid ones.

    Args:
        urls: List of URLs to validate

    Returns:
        list: List of valid URLs
    """
    if not urls or not isinstance(urls, list):
        return []

    valid_urls = []
    for url in urls:
        if validate_url(url):
            valid_urls.append(url)
        else:
            log_security_event('invalid_url_in_batch', {'url': url[:100]})  # Truncate for logging

    if len(valid_urls) != len(urls):
        logger.warning(f"Batch URL validation: {len(urls)} input, {len(valid_urls)} valid")

    return valid_urls

def security_wrapper(func):
    """
    Decorator to add security checks to functions that handle URLs or content.

    Args:
        func: The function to wrap

    Returns:
        function: Wrapped function with security checks
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Extract URL from args or kwargs
            url = None
            if args and isinstance(args[0], str) and args[0].startswith(('http://', 'https://')):
                url = args[0]
            elif 'url' in kwargs:
                url = kwargs['url']

            # Validate URL if present
            if url and not validate_url(url):
                log_security_event('url_validation_failed', {'url': url[:100], 'function': func.__name__})
                raise ValueError(f"Invalid or unsafe URL: {url[:100]}")

            # Check content size if present
            content = kwargs.get('content') or kwargs.get('text_content')
            if content and not validate_content_size(content):
                log_security_event('content_size_exceeded', {'function': func.__name__})
                raise ValueError("Content size exceeds maximum allowed limit")

            # Rate limiting (using function name as identifier for now)
            if not rate_limit(func.__name__):
                log_security_event('rate_limit_exceeded', {'function': func.__name__})
                raise ValueError("Rate limit exceeded")

            return func(*args, **kwargs)

        except Exception as e:
            logger.error(f"Security wrapper error in {func.__name__}: {e}")
            raise

    return wrapper
