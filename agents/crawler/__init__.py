"""
Crawler Agent

Unified production crawling agent for JustNewsAgent.
Provides intelligent multi-strategy crawling with AI analysis.
"""

import sys
import os

# Add project root to path for version import
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from common.version_utils import get_version
    __version__ = get_version()
except ImportError:
    # Fallback version
    __version__ = "0.8.0"

from .unified_production_crawler import UnifiedProductionCrawler

__all__ = ["UnifiedProductionCrawler"]
