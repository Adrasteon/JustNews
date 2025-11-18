import os
from pathlib import Path


def test_public_website_template_exists_and_contains_pages():
    path = Path(__file__).parents[2] / "agents" / "dashboard" / "public_website.html"
    assert path.exists(), f"public_website.html not found at {path}"
    content = path.read_text(encoding="utf-8")
    assert 'dropdown' in content
    assert '/api/crawl/status' in content
    assert '/gpu/dashboard' in content
