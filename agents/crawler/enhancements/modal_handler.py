"""Cookie/consent modal heuristics for the crawler."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

try:  # Optional dependency, aligns with GenericSiteCrawler behaviour
    from lxml import html as lxml_html  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled gracefully at runtime
    lxml_html = None

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ModalHandlingResult:
    """Outcome of running :class:`ModalHandler` on a HTML document."""

    cleaned_html: str
    modals_detected: bool
    applied_cookies: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class ModalHandler:
    """Detect and mitigate soft-consent modals with minimal dependencies."""

    CONSENT_KEYWORDS = (
        "cookie",
        "consent",
        "gdpr",
        "preferences",
        "privacy",
        "tracking",
    )

    def __init__(
        self,
        *,
        enable_cookie_injection: bool = True,
        consent_cookie_name: str = "justnews_cookie_consent",
        consent_cookie_value: str = "1",
    ) -> None:
        self.enable_cookie_injection = enable_cookie_injection
        self.consent_cookie_name = consent_cookie_name
        self.consent_cookie_value = consent_cookie_value

    def process(self, html: str) -> ModalHandlingResult:
        """Attempt to detect and remove consent overlays.

        Args:
            html: Raw HTML string returned by the upstream request.

        Returns:
            :class:`ModalHandlingResult` describing whether any remediation took
            place.  The caller can decide how to use the cleaned HTML and
            optional cookies.
        """

        notes: List[str] = []
        detected = False
        cleaned_html = html

        if self._contains_consent_keywords(html):
            detected = True
            notes.append("Consent keywords detected in HTML")

        if lxml_html is not None and detected:
            try:
                tree = lxml_html.fromstring(html)
                removed = self._remove_overlay_nodes(tree)
                if removed:
                    cleaned_html = lxml_html.tostring(tree, encoding="unicode")
                    notes.append(f"Removed {removed} overlay nodes")
            except Exception as exc:  # noqa: BLE001 - resilience first
                logger.debug("ModalHandler failed to parse HTML: %s", exc)
                notes.append("Overlay removal failed; original HTML preserved")

        cookies: Dict[str, str] = {}
        if detected and self.enable_cookie_injection:
            cookies[self.consent_cookie_name] = self.consent_cookie_value
            notes.append("Generated synthetic consent cookie")

        return ModalHandlingResult(
            cleaned_html=cleaned_html,
            modals_detected=detected,
            applied_cookies=cookies,
            notes=notes,
        )

    def _contains_consent_keywords(self, html: str) -> bool:
        lowered = html.lower()
        return any(keyword in lowered for keyword in self.CONSENT_KEYWORDS)

    def _remove_overlay_nodes(self, tree: "lxml_html.HtmlElement") -> int:
        """Heuristically remove modal containers from an lxml tree."""

        patterns: Iterable[str] = (
            "//div[contains(@class, 'cookie')]",
            "//div[contains(@class, 'consent')]",
            "//div[contains(@class, 'modal')]",
            "//div[contains(@id, 'cookie')]",
            "//div[contains(@id, 'consent')]",
            "//section[contains(@class, 'cookie')]",
            "//section[contains(@id, 'cookie')]",
        )
        removed = 0
        for xpath in patterns:
            for node in tree.xpath(xpath):  # type: ignore[attr-defined]
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                    removed += 1
        return removed
