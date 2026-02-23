"""Tests for URL scraper.

Tests use mocked HTTP responses to verify chunk extraction.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("bs4")

from cadforge_engine.vault.scraper import scrape_url, scrape_documentation


SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Test Docs</title></head>
<body>
<nav><a href="/">Home</a></nav>
<article>
<h1>Getting Started</h1>
<p>Welcome to the documentation. This is an introduction paragraph with enough text.</p>
<h2>Installation</h2>
<p>Install the package using pip install mylib. This section explains installation steps.</p>
<h2>Quick Start</h2>
<p>Create your first model with the following code example and instructions for beginners.</p>
<h3>Advanced Usage</h3>
<p>For advanced users, here are more detailed instructions and patterns for complex models.</p>
</article>
<footer><p>Copyright 2025</p></footer>
</body>
</html>
"""


def _mock_get(url: str, **kwargs) -> MagicMock:
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.text = SAMPLE_HTML
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


class TestScrapeUrl:
    """Test single URL scraping."""

    @patch("httpx.get", side_effect=_mock_get)
    def test_extracts_chunks(self, mock_get: MagicMock) -> None:
        chunks = scrape_url("https://example.com/docs", source_name="test-docs")
        assert len(chunks) > 0

    @patch("httpx.get", side_effect=_mock_get)
    def test_chunk_sections(self, mock_get: MagicMock) -> None:
        chunks = scrape_url("https://example.com/docs", source_name="test-docs")
        sections = [c.section for c in chunks]
        assert "Installation" in sections
        assert "Quick Start" in sections

    @patch("httpx.get", side_effect=_mock_get)
    def test_chunk_has_tags(self, mock_get: MagicMock) -> None:
        chunks = scrape_url("https://example.com/docs", source_name="test-docs")
        for chunk in chunks:
            assert "test-docs" in chunk.tags
            assert "scraped" in chunk.tags

    @patch("httpx.get", side_effect=_mock_get)
    def test_chunk_has_source_url(self, mock_get: MagicMock) -> None:
        chunks = scrape_url("https://example.com/docs", source_name="test-docs")
        for chunk in chunks:
            assert chunk.metadata["source_url"] == "https://example.com/docs"

    @patch("httpx.get", side_effect=_mock_get)
    def test_nav_footer_stripped(self, mock_get: MagicMock) -> None:
        chunks = scrape_url("https://example.com/docs", source_name="test-docs")
        all_content = " ".join(c.content for c in chunks)
        assert "Home" not in all_content  # nav stripped
        assert "Copyright" not in all_content  # footer stripped

    @patch("httpx.get", side_effect=Exception("Network error"))
    def test_handles_fetch_error(self, mock_get: MagicMock) -> None:
        chunks = scrape_url("https://example.com/broken", source_name="test")
        assert chunks == []


class TestScrapeDocumentation:
    """Test batch scraping."""

    @patch("httpx.get", side_effect=_mock_get)
    def test_batch_scrape(self, mock_get: MagicMock) -> None:
        chunks = scrape_documentation(
            ["https://example.com/page1", "https://example.com/page2"],
            source_name="docs",
        )
        # Should have chunks from both pages
        assert len(chunks) > 0
        assert mock_get.call_count == 2
