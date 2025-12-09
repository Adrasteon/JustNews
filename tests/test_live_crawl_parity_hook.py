import asyncio
import os
from unittest.mock import patch, MagicMock

import live_crawl_test


class FakeCrawler:
    def __init__(self, result=None):
        self._result = result or {}

    async def run_unified_crawl(self, *args, **kwargs):
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@patch.dict(os.environ, {"PARITY_CHECK_ON_CRAWL": "1"})
@patch("scripts.dev.verify_chroma_parity.main")
@patch("live_crawl_test.CrawlerEngine", return_value=FakeCrawler({ 'sites_crawled': 1, 'total_articles': 0, 'total_ingest_candidates': 0 }))
def test_parity_invoked_after_crawl(mock_crawler, mock_parity):
    mock_parity.return_value = 0

    asyncio.run(live_crawl_test.run_crawl_test())

    assert mock_parity.called


@patch.dict(os.environ, {"PARITY_CHECK_ON_CRAWL": "0"})
@patch("scripts.dev.verify_chroma_parity.main")
@patch("live_crawl_test.CrawlerEngine", return_value=FakeCrawler({ 'sites_crawled': 1, 'total_articles': 0, 'total_ingest_candidates': 0 }))
def test_parity_skipped_when_disabled(mock_crawler, mock_parity):
    asyncio.run(live_crawl_test.run_crawl_test())

    assert not mock_parity.called


@patch.dict(os.environ, {"PARITY_CHECK_ON_CRAWL": "1", "PARITY_REPAIR_ON_CRAWL": "1", "PARITY_REPAIR_CONFIRM_BYPASS": "1", "PARITY_BATCH": "123"})
@patch("scripts.dev.verify_chroma_parity.main")
@patch("live_crawl_test.CrawlerEngine", return_value=FakeCrawler({ 'sites_crawled': 1, 'total_articles': 0, 'total_ingest_candidates': 0 }))
def test_parity_repair_with_confirm(mock_crawler, mock_parity):
    mock_parity.return_value = 0

    asyncio.run(live_crawl_test.run_crawl_test())

    assert mock_parity.called
    # ensure args included --repair and --confirm and batch 123
    called_args = mock_parity.call_args[0][0]
    assert "--repair" in called_args
    assert "--confirm" in called_args
    assert "123" in called_args or "--batch" in called_args
