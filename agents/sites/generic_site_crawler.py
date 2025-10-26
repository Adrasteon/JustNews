"""Lightweight generic crawler primitives used by the crawler agent.

The previous production implementation pulled in a large dependency tree that was
removed during the repository clean-up.  These stubs provide the minimum surface
area required by the crawler engine so the service can start successfully.  They
support simple HTTP fetching when explicitly enabled via environment variable
and fall back to no-op behaviour in offline environments.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

import requests

from agents.crawler.extraction import ExtractionOutcome, extract_article_content
from common.observability import get_logger

logger = get_logger(__name__)


def _bool_from_env(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean-ish environment flags."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(init=False)
class SiteConfig:
    """Normalized site configuration wrapper used by crawler components."""

    source_id: Optional[int] = None
    name: str = ""
    domain: str = ""
    url: str = ""
    crawling_strategy: str = "generic"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, source: Any):
        data = self._normalise_source(source)

        self.source_id = data.get("id")
        self.name = data.get("name") or data.get("domain") or data.get("url") or "unknown"

        raw_domain = data.get("domain")
        raw_url = data.get("url")

        if raw_domain:
            domain = raw_domain.strip()
        elif raw_url:
            parsed = urlparse(raw_url)
            domain = parsed.netloc or parsed.path
        else:
            domain = ""

        url = raw_url or ""

        if domain and "://" in domain:
            parsed = urlparse(domain)
            if parsed.netloc:
                if not url:
                    url = domain
                domain = parsed.netloc

        if not url and domain:
            scheme = "https" if not domain.startswith("http") else ""
            url = f"{scheme}://{domain}" if scheme else domain

        self.domain = domain
        self.url = url

        metadata = data.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        self.metadata = dict(metadata)

        self.crawling_strategy = (
            self.metadata.get("crawling_strategy")
            or data.get("crawling_strategy")
            or "generic"
        )

    @staticmethod
    def _normalise_source(source: Any) -> Dict[str, Any]:
        if isinstance(source, SiteConfig):
            return source.to_dict()
        if isinstance(source, Mapping):
            return dict(source)
        if hasattr(source, "_mapping"):
            return dict(source._mapping)  # e.g. SQLAlchemy Row
        if hasattr(source, "_asdict"):
            return dict(source._asdict())  # e.g. namedtuple
        if hasattr(source, "__dict__"):
            return {k: v for k, v in vars(source).items() if not k.startswith("_")}
        raise TypeError(f"Unsupported source type for SiteConfig: {type(source)!r}")

    @property
    def start_url(self) -> str:
        return self.url or (f"https://{self.domain}" if self.domain else "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.name,
            "domain": self.domain,
            "url": self.url,
            "metadata": dict(self.metadata),
            "crawling_strategy": self.crawling_strategy,
        }


class GenericSiteCrawler:
    """Basic crawler that fetches the landing page for a site.

    The implementation intentionally keeps network access optional so the agent
    can operate in restricted environments.  Set
    ``UNIFIED_CRAWLER_ENABLE_HTTP_FETCH=true`` to allow HTTP requests.
    """

    def __init__(
        self,
        site_config: SiteConfig,
        concurrent_browsers: int = 2,
        batch_size: int = 8,
        *,
        enable_http_fetch: Optional[bool] = None,
        session: Optional[requests.Session] = None,
    ):
        self.site_config = site_config
        self.concurrent_browsers = concurrent_browsers
        self.batch_size = batch_size
        resolved = enable_http_fetch if enable_http_fetch is not None else _bool_from_env(
            os.environ.get("UNIFIED_CRAWLER_ENABLE_HTTP_FETCH"),
            default=False,
        )
        self.enable_http_fetch = resolved
        self.session = session or requests.Session()

    async def crawl_site(self, max_articles: int = 25) -> List[Dict[str, Any]]:
        if not self.enable_http_fetch:
            logger.debug(
                "HTTP fetching disabled via UNIFIED_CRAWLER_ENABLE_HTTP_FETCH; skipping %s",
                self.site_config.domain or self.site_config.name,
            )
            return []

        target_url = self._normalise_target_url(self.site_config.start_url)
        if not target_url:
            # Attempt to unwrap simple list-like values passed through JSON args
            if isinstance(self.site_config.name, list) and self.site_config.name:
                target_url = self._normalise_target_url(self.site_config.name[0])
            elif isinstance(self.site_config.domain, list) and self.site_config.domain:
                target_url = self._normalise_target_url(self.site_config.domain[0])
            elif isinstance(self.site_config.metadata.get("start_url"), list):
                candidate = self.site_config.metadata["start_url"]
                if candidate:
                    target_url = self._normalise_target_url(candidate[0])
            elif isinstance(self.site_config.metadata.get("start_url"), str):
                target_url = self._normalise_target_url(self.site_config.metadata["start_url"])
        if not target_url:
            logger.warning("No URL configured for site %s; skipping", self.site_config.name)
            return []

        logger.debug("Generic crawler fetching %s", target_url)

        try:
            html = await asyncio.to_thread(self._fetch_url, target_url)
        except Exception as exc:  # noqa: BLE001 - we keep the crawler resilient
            logger.warning("Failed to fetch %s: %s", target_url, exc)
            return []

        if not html:
            return []

        article = self._build_article(target_url, html)
        return [article] if article else []

    def _normalise_target_url(self, candidate: Any) -> str:
        """Best-effort URL normaliser that strips duplicate schemes and fills defaults."""
        if candidate is None:
            return ""
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            candidate = next((item for item in candidate if item), "")
        candidate = str(candidate).strip()
        if not candidate:
            return ""

        # Avoid common double scheme artefacts such as https://https://example.com
        parsed = urlparse(candidate)
        if parsed.scheme and not parsed.netloc and "://" in parsed.path:
            parsed = urlparse(parsed.path)

        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        path = parsed.path
        params = parsed.params
        query = parsed.query
        fragment = parsed.fragment

        if not netloc:
            fallback = (self.site_config.domain or "").strip()
            if fallback and "://" in fallback:
                fallback = urlparse(fallback).netloc or fallback
            if fallback:
                netloc = fallback
            else:
                # Treat bare domains or paths as implicit netloc values
                if path and not path.startswith("/"):
                    derived = urlparse(f"https://{path}")
                    netloc = derived.netloc or netloc
                    # Preserve sub-path when present after the hostname
                    if derived.path and derived.netloc:
                        path = derived.path

        netloc = netloc.lstrip("/")
        if not netloc:
            return ""

        normalised = urlunparse((scheme, netloc, path, params, query, fragment))
        return normalised.rstrip("/") or normalised

    def _fetch_url(self, url: str) -> str:
        response = self.session.get(url, timeout=10, headers={"User-Agent": "JustNewsCrawler/1.0"})
        response.raise_for_status()
        return response.text

    def _build_article(self, url: str, html: str) -> Optional[Dict[str, Any]]:
        extraction: ExtractionOutcome = extract_article_content(html, url)
        if not extraction.text:
            logger.debug("Extraction pipeline returned no content for %s", url)
            return None

        canonical_url = extraction.canonical_url or url
        url_hash = hashlib.sha256(canonical_url.encode("utf-8", errors="ignore")).hexdigest()
        timestamp = datetime.now(timezone.utc).isoformat()

        extraction_metadata: Dict[str, Any] = {
            "strategy": self.site_config.crawling_strategy,
            "extractor": extraction.extractor_used,
            "fallbacks_attempted": extraction.fallbacks_attempted,
            "word_count": extraction.word_count,
            "boilerplate_ratio": extraction.boilerplate_ratio,
            "needs_review": extraction.needs_review,
            "review_reasons": extraction.review_reasons,
            "raw_html_path": extraction.raw_html_path,
        }
        if extraction.metadata:
            extraction_metadata["extracted_primary"] = extraction.metadata

        article = {
            "url": url,
            "canonical": canonical_url,
            "title": extraction.title or self.site_config.name,
            "content": extraction.text[:10_000],
            "domain": self.site_config.domain,
            "source_name": self.site_config.name,
            "publisher_meta": self.site_config.metadata,
            "extracted_metadata": extraction.metadata,
            "structured_metadata": extraction.structured_metadata,
            "language": extraction.language,
            "authors": extraction.authors,
            "section": extraction.section,
            "tags": extraction.tags,
            "publication_date": extraction.publication_date,
            "confidence": 0.75 if not extraction.needs_review else 0.35,
            "paywall_flag": False,
            "needs_review": extraction.needs_review,
            "extraction_metadata": extraction_metadata,
            "raw_html_ref": extraction.raw_html_path,
            "timestamp": timestamp,
            "url_hash": url_hash,
        }

        return article


class MultiSiteCrawler:
    """Coordinator that uses the generic crawler for multiple sites."""

    def __init__(self, *, enable_http_fetch: Optional[bool] = None):
        self.enable_http_fetch = enable_http_fetch

    async def crawl_sites(
        self,
        site_configs: Iterable[SiteConfig],
        *,
        max_articles_per_site: int = 25,
        concurrent_sites: int = 3,
    ) -> Dict[str, List[Dict[str, Any]]]:
        results: Dict[str, List[Dict[str, Any]]] = {}
        semaphore = asyncio.Semaphore(max(1, concurrent_sites))

        async def _crawl_single(config: SiteConfig) -> None:
            async with semaphore:
                crawler = GenericSiteCrawler(
                    config,
                    enable_http_fetch=self.enable_http_fetch,
                )
                articles = await crawler.crawl_site(max_articles=max_articles_per_site)
                results[config.domain or config.name] = articles

        tasks = [asyncio.create_task(_crawl_single(config)) for config in site_configs]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return results
