"""Optional crawler enhancement modules.

Each module in this package provides an opt-in helper that augments the
existing crawler without changing its default behaviour.  The crawler engine
imports these lazily so deployments can enable the enhancements
incrementally via configuration overrides.
"""

from .paywall_detector import PaywallDetectionResult, PaywallDetector  # noqa: F401
from .proxy_manager import ProxyManager, PIASocks5Manager  # noqa: F401
from .stealth_browser import StealthProfile, StealthBrowserFactory  # noqa: F401
from .ua_rotation import UserAgentProvider  # noqa: F401
from .modal_handler import ModalHandlingResult, ModalHandler  # noqa: F401
