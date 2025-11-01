"""Profile registry for Crawl4AI-backed crawling.

This module centralises the logic for loading per-domain Crawl4AI profiles
from ``config/crawl_profiles.yaml``.  The scheduler imports these helpers to
attach the resolved profile payload to each crawler submission so runtime
behaviour stays configuration-driven.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

__all__ = [
    "CrawlProfile",
    "CrawlProfileError",
    "CrawlProfileRegistry",
    "load_crawl_profiles",
]


class CrawlProfileError(RuntimeError):
    """Raised when the Crawl4AI profile configuration cannot be parsed."""


def _normalise_domain(candidate: str) -> str:
    """Normalise a domain or URL string to its lower-case hostname."""
    value = (candidate or "").strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc or parsed.path
    return host.lower().strip()


def _expand_placeholders(value: Any, domain: str) -> Any:
    """Recursive helper that replaces ``{domain}`` tokens."""
    if isinstance(value, str):
        return value.replace("{domain}", domain)
    if isinstance(value, list):
        return [_expand_placeholders(item, domain) for item in value]
    if isinstance(value, dict):
        return {key: _expand_placeholders(item, domain) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class CrawlProfile:
    """Immutable representation of a single profile entry."""

    slug: str
    engine: str = "crawl4ai"
    mode: str = "landing"
    follow_internal_links: bool = True
    max_pages: int | None = None
    start_urls: list[str] = field(default_factory=list)
    run_config: dict[str, Any] = field(default_factory=dict)
    link_preview: dict[str, Any] = field(default_factory=dict)
    browser_config: dict[str, Any] = field(default_factory=dict)
    adaptive: dict[str, Any] = field(default_factory=dict)
    js_code: list[str] = field(default_factory=list)
    wait_for: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    description: str | None = None

    def payload_for_domain(self, domain: str) -> dict[str, Any]:
        """Return a serialisable payload expanded for ``domain``."""
        expanded = {
            "profile_slug": self.slug,
            "engine": self.engine,
            "mode": self.mode,
            "follow_internal_links": self.follow_internal_links,
            "max_pages": self.max_pages,
            "start_urls": _expand_placeholders(self.start_urls, domain),
            "run_config": _expand_placeholders(self.run_config, domain),
            "link_preview": _expand_placeholders(self.link_preview, domain),
            "browser_config": _expand_placeholders(self.browser_config, domain),
            "adaptive": _expand_placeholders(self.adaptive, domain),
            "js_code": _expand_placeholders(self.js_code, domain),
            "wait_for": _expand_placeholders(self.wait_for, domain),
            "extra": _expand_placeholders(self.extra, domain),
        }
        return {key: value for key, value in expanded.items() if value not in (None, [], {}, "")}


@dataclass(frozen=True)
class CrawlProfileRegistry:
    """Resolved view of the profile configuration."""

    profiles: Mapping[str, CrawlProfile]
    domain_assignments: Mapping[str, str]
    default_slug: str | None

    def for_domain(self, domain: str) -> CrawlProfile | None:
        key = _normalise_domain(domain)
        slug = self.domain_assignments.get(key)
        if not slug and key.startswith("www."):
            slug = self.domain_assignments.get(key[4:])
        if not slug and not key.startswith("www."):
            slug = self.domain_assignments.get(f"www.{key}")
        if not slug:
            slug = self.default_slug
        if not slug:
            return None
        return self.profiles.get(slug)

    def build_overrides(self, domains: Iterable[str]) -> dict[str, dict[str, Any]]:
        overrides: dict[str, dict[str, Any]] = {}
        for domain in domains:
            profile = self.for_domain(domain)
            if not profile:
                continue
            normalised = _normalise_domain(domain)
            if not normalised:
                continue
            overrides[normalised] = profile.payload_for_domain(normalised)

            if normalised.startswith("www."):
                bare = normalised[4:]
                if bare and bare not in overrides:
                    overrides[bare] = profile.payload_for_domain(bare)
            else:
                www_variant = f"www.{normalised}"
                if www_variant not in overrides:
                    overrides[www_variant] = profile.payload_for_domain(www_variant)
        return overrides


def _coerce_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise CrawlProfileError(f"{context} must be a mapping")
    return dict(value)


def load_crawl_profiles(path: Path) -> CrawlProfileRegistry:
    """Load the Crawl4AI profile configuration from YAML."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise exc
    except OSError as exc:  # pragma: no cover - surfaced to caller
        raise CrawlProfileError(f"Unable to read crawl profiles: {path}") from exc
    except yaml.YAMLError as exc:  # pragma: no cover
        raise CrawlProfileError(f"Invalid crawl profile YAML: {path}") from exc

    profiles_section = _coerce_mapping(raw.get("profiles"), context="profiles")
    if not profiles_section:
        raise CrawlProfileError("profiles section cannot be empty")

    default_slug = raw.get("defaults", {}).get("profile")

    profiles: dict[str, CrawlProfile] = {}
    domain_assignments: dict[str, str] = {}

    for slug, body in profiles_section.items():
        if not isinstance(body, Mapping):
            raise CrawlProfileError(f"Profile '{slug}' must be a mapping")
        data = dict(body)
        engine = str(data.get("engine", "crawl4ai")).strip().lower() or "crawl4ai"
        mode = str(data.get("mode", "landing")).strip().lower() or "landing"
        follow_internal = bool(data.get("follow_internal_links", True))
        max_pages = data.get("max_pages")
        if max_pages is not None:
            max_pages = int(max_pages)
        start_urls = data.get("start_urls") or []
        if isinstance(start_urls, str):
            start_urls = [start_urls]
        start_urls = [str(item).strip() for item in start_urls if str(item).strip()]
        run_config = _coerce_mapping(data.get("run_config"), context=f"profile '{slug}' run_config")
        link_preview = _coerce_mapping(data.get("link_preview"), context=f"profile '{slug}' link_preview")
        browser_config = _coerce_mapping(data.get("browser_config"), context=f"profile '{slug}' browser_config")
        adaptive = _coerce_mapping(data.get("adaptive"), context=f"profile '{slug}' adaptive")
        extra = _coerce_mapping(data.get("extra"), context=f"profile '{slug}' extra")
        description = data.get("description")
        js_code = data.get("js_code") or []
        if isinstance(js_code, str):
            js_code = [js_code]
        js_code = [str(item) for item in js_code if str(item)]
        wait_for = data.get("wait_for")
        if wait_for is not None:
            wait_for = str(wait_for)

        profile = CrawlProfile(
            slug=slug,
            engine=engine,
            mode=mode,
            follow_internal_links=follow_internal,
            max_pages=max_pages,
            start_urls=start_urls,
            run_config=run_config,
            link_preview=link_preview,
            browser_config=browser_config,
            adaptive=adaptive,
            js_code=js_code,
            wait_for=wait_for,
            extra=extra,
            description=description,
        )
        profiles[slug] = profile

        assignments = data.get("domains") or []
        if isinstance(assignments, str):
            assignments = [assignments]
        for domain in assignments:
            normalised = _normalise_domain(str(domain))
            if not normalised:
                continue
            domain_assignments[normalised] = slug

    if default_slug and default_slug not in profiles:
        raise CrawlProfileError(f"Default profile '{default_slug}' is not defined")

    return CrawlProfileRegistry(
        profiles=profiles,
        domain_assignments=domain_assignments,
        default_slug=default_slug,
    )
