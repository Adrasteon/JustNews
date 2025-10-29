"""Crawl4AI adapter used by the unified crawler engine.

The crawler engine delegates to this module when a profile explicitly requests
Crawl4AI-backed crawling.  The adapter translates profile dictionaries into
``crawl4ai`` configuration objects and converts the resulting pages back into
articles using the existing extraction pipeline so downstream ingestion logic
remains unchanged.
"""
from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

from agents.sites.generic_site_crawler import GenericSiteCrawler, SiteConfig
from common.observability import get_logger

logger = get_logger(__name__)

try:  # Optional dependency, resolved at runtime when available
    crawl4ai = importlib.import_module("crawl4ai")  # type: ignore
except ImportError:  # pragma: no cover - missing optional dependency
    crawl4ai = None  # type: ignore

# Narrow allow-lists keep the translated run configuration maintainable and
# avoid surprising ``crawl4ai`` keyword errors when new options are introduced.
_ALLOWED_BROWSER_KEYS = {
    "browser_type",
    "headless",
    "viewport_width",
    "viewport_height",
    "user_agent",
    "user_agent_mode",
    "proxy",
    "cookies",
    "headers",
    "text_mode",
    "verbose",
    "extra_args",
    "ignore_https_errors",
}

_ALLOWED_RUN_CONFIG_KEYS = {
    "word_count_threshold",
    "exclude_external_links",
    "remove_overlay_elements",
    "process_iframes",
    "target_elements",
    "excluded_tags",
    "only_text",
    "score_links",
    "wait_for",
    "wait_for_timeout",
    "js_code",
    "screenshot",
    "pdf",
    "capture_mhtml",
    "exclude_all_images",
    "exclude_external_images",
    "image_score_threshold",
    "table_score_threshold",
}

_ALLOWED_LINK_PREVIEW_KEYS = {
    "include_internal",
    "include_external",
    "include_patterns",
    "exclude_patterns",
    "max_links",
    "concurrency",
    "timeout",
    "query",
    "score_threshold",
    "verbose",
}


@dataclass
class CrawlContext:
    site_config: SiteConfig
    profile: dict[str, Any]
    max_articles: int
    follow_internal_links: bool
    page_budget: int


def _ensure_absolute(url: str, base: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return urljoin(base, url)


def _normalise_url_for_site(url: str, site_config: SiteConfig) -> str:
    if not url:
        return ""
    base = site_config.start_url or f"https://{site_config.domain}" if site_config.domain else ""
    if not base:
        return url
    return _ensure_absolute(url, base)


def _build_browser_config(settings: dict[str, Any] | None):
    if not settings:
        return None
    if crawl4ai is None:  # pragma: no cover - optional dependency missing
        return None

    BrowserConfig = getattr(crawl4ai, "BrowserConfig", None)
    if BrowserConfig is None:
        return None

    kwargs = {key: settings[key] for key in _ALLOWED_BROWSER_KEYS if key in settings}
    if not kwargs:
        return None
    return BrowserConfig(**kwargs)


def _build_link_preview_config(settings: dict[str, Any] | None):
    if not settings:
        return None

    LinkPreviewConfig = None
    if crawl4ai is not None:
        LinkPreviewConfig = getattr(crawl4ai, "LinkPreviewConfig", None)
        if LinkPreviewConfig is None:
            try:
                adaptive = importlib.import_module("crawl4ai.adaptive_crawler")
                LinkPreviewConfig = getattr(adaptive, "LinkPreviewConfig", None)
            except ImportError:  # pragma: no cover - optional
                LinkPreviewConfig = None
    if LinkPreviewConfig is None:
        return None

    kwargs = {key: settings[key] for key in _ALLOWED_LINK_PREVIEW_KEYS if key in settings}
    if not kwargs:
        return None
    for pattern_key in ("include_patterns", "exclude_patterns"):
        if pattern_key in kwargs and isinstance(kwargs[pattern_key], str):
            kwargs[pattern_key] = [kwargs[pattern_key]]
    return LinkPreviewConfig(**kwargs)


def _build_run_config(profile: dict[str, Any]):
    run_config_def: dict[str, Any] = dict(profile.get("run_config") or {})
    if profile.get("wait_for") and "wait_for" not in run_config_def:
        run_config_def["wait_for"] = profile["wait_for"]
    if profile.get("js_code") and "js_code" not in run_config_def:
        run_config_def["js_code"] = profile["js_code"]

    kwargs = {key: run_config_def[key] for key in _ALLOWED_RUN_CONFIG_KEYS if key in run_config_def}

    for list_key in ("js_code", "target_elements", "excluded_tags"):
        if list_key in kwargs and isinstance(kwargs[list_key], str):
            kwargs[list_key] = [kwargs[list_key]]

    link_preview_cfg = _build_link_preview_config(profile.get("link_preview"))
    if link_preview_cfg:
        kwargs["link_preview_config"] = link_preview_cfg

    if crawl4ai is None:  # pragma: no cover - surfaced to caller fallback
        raise ImportError("crawl4ai is not installed")

    CacheMode = getattr(crawl4ai, "CacheMode", None)
    CrawlerRunConfig = getattr(crawl4ai, "CrawlerRunConfig", None)
    if CacheMode is None or CrawlerRunConfig is None:
        raise ImportError("crawl4ai CacheMode or CrawlerRunConfig missing")

    cache_mode = profile.get("run_config", {}).get("cache_mode", "bypass")
    cache_mode_enum = getattr(CacheMode, str(cache_mode).upper(), CacheMode.BYPASS)

    return CrawlerRunConfig(cache_mode=cache_mode_enum, **kwargs)


def _select_link_candidates(
    links: Sequence[dict[str, Any]],
    context: CrawlContext,
    visited: set[str],
    remaining_budget: int,
) -> list[str]:
    if not links or remaining_budget <= 0:
        return []

    include_patterns = context.profile.get("link_preview", {}).get("include_patterns") or []
    exclude_patterns = context.profile.get("link_preview", {}).get("exclude_patterns") or []
    include_patterns = include_patterns if isinstance(include_patterns, list) else [include_patterns]
    exclude_patterns = exclude_patterns if isinstance(exclude_patterns, list) else [exclude_patterns]

    def _score(entry: dict[str, Any]) -> float:
        for key in ("total_score", "contextual_score", "intrinsic_score"):
            value = entry.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    filtered: list[tuple[float, str]] = []
    for item in links:
        href = item.get("href")
        if not href:
            continue
        absolute = _normalise_url_for_site(href, context.site_config)
        if not absolute or absolute in visited:
            continue
        parsed = urlparse(absolute)
        if context.site_config.domain and parsed.netloc and context.site_config.domain not in parsed.netloc:
            continue
        if include_patterns and not any(pattern in absolute for pattern in include_patterns):
            continue
        if exclude_patterns and any(pattern in absolute for pattern in exclude_patterns):
            continue
        filtered.append((_score(item), absolute))

    filtered.sort(key=lambda entry: entry[0], reverse=True)
    return [url for _, url in filtered[:remaining_budget]]


def _build_article_from_result(
    builder: GenericSiteCrawler,
    target_url: str,
    result: Any,
    profile: dict[str, Any],
    links_followed: int,
) -> dict[str, Any] | None:
    html = getattr(result, "cleaned_html", None) or getattr(result, "html", None)
    if not html:
        markdown_obj = getattr(result, "markdown", None)
        raw_markdown = getattr(markdown_obj, "raw_markdown", None) if markdown_obj else None
        if raw_markdown:
            html = f"<article>{raw_markdown}</article>"
    if not html:
        return None

    article = builder._build_article(target_url, html)
    if not article:
        return None

    metadata = article.setdefault("extraction_metadata", {})
    crawl_meta = metadata.setdefault("crawl4ai", {})
    crawl_meta.update(
        {
            "profile_slug": profile.get("profile_slug"),
            "mode": profile.get("mode"),
            "source_url": getattr(result, "url", target_url),
            "links_followed": links_followed,
            "link_preview_count": len(getattr(result, "links", {}).get("internal", [])) if getattr(result, "links", None) else 0,
        }
    )
    page_metadata = getattr(result, "metadata", None)
    if page_metadata:
        crawl_meta["page_metadata"] = page_metadata
    return article


async def crawl_site_with_crawl4ai(
    site_config: SiteConfig,
    profile: dict[str, Any],
    max_articles: int,
) -> list[dict[str, Any]]:
    """Execute a Crawl4AI-backed crawl using the provided profile."""
    if crawl4ai is None:  # pragma: no cover - handled by caller fallback
        raise ImportError("crawl4ai is not installed")

    AsyncWebCrawler = getattr(crawl4ai, "AsyncWebCrawler", None)
    if AsyncWebCrawler is None:
        raise ImportError("crawl4ai AsyncWebCrawler not available")

    article_limit = max(1, int(max_articles or 1))
    browser_config = _build_browser_config(profile.get("browser_config"))
    run_config = _build_run_config(profile)

    start_urls = profile.get("start_urls") or []
    if not start_urls:
        inferred = site_config.start_url
        if inferred:
            start_urls = [inferred]
    if not start_urls:
        logger.warning("Crawl4AI profile for %s did not provide any start URLs", site_config.name)
        return []

    unique_urls: list[str] = []
    for candidate in start_urls:
        normalised = _normalise_url_for_site(str(candidate), site_config)
        if normalised and normalised not in unique_urls:
            unique_urls.append(normalised)

    if not unique_urls:
        return []

    follow_internal_links = bool(profile.get("follow_internal_links", True))
    page_budget = int(profile.get("max_pages") or article_limit or len(unique_urls))
    page_budget = max(page_budget, len(unique_urls))
    context = CrawlContext(
        site_config=site_config,
        profile=profile,
        max_articles=article_limit,
        follow_internal_links=follow_internal_links,
        page_budget=page_budget,
    )

    builder = GenericSiteCrawler(site_config, enable_http_fetch=False)
    articles: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: list[str] = list(unique_urls)
    pages_fetched = 0

    crawler_factory = AsyncWebCrawler(config=browser_config) if browser_config else AsyncWebCrawler()
    async with crawler_factory as crawler:
        while queue and pages_fetched < context.page_budget and len(articles) < context.max_articles:
            current_url = queue.pop(0)
            if not current_url or current_url in visited:
                continue
            visited.add(current_url)
            try:
                result = await crawler.arun(current_url, config=run_config)
            except Exception as exc:  # noqa: BLE001 - robustness first
                logger.warning("Crawl4AI failed for %s: %s", current_url, exc)
                continue

            pages_fetched += 1
            if not getattr(result, "success", True):
                logger.debug("Crawl4AI returned unsuccessful result for %s", current_url)
                continue

            article = _build_article_from_result(
                builder,
                current_url,
                result,
                profile,
                links_followed=max(0, len(visited) - len(unique_urls)),
            )
            if article:
                articles.append(article)
                if len(articles) >= context.max_articles:
                    break

            if (
                context.follow_internal_links
                and len(articles) < context.max_articles
                and getattr(result, "links", None)
            ):
                remaining_pages = context.page_budget - pages_fetched
                candidates = result.links.get("internal", []) if result.links else []
                next_urls = _select_link_candidates(candidates, context, visited, remaining_pages)
                for url in next_urls:
                    if url not in queue and url not in visited:
                        queue.append(url)

    return articles[: context.max_articles]
