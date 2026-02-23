"""URL scraper for ingesting documentation into the vault.

Uses httpx + beautifulsoup4 to fetch and parse documentation pages,
then splits them into VaultChunk objects for indexing.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from cadforge_engine.vault.schema import VaultChunk

logger = logging.getLogger(__name__)


def scrape_url(url: str, source_name: str = "") -> list[VaultChunk]:
    """Fetch a URL and extract content as VaultChunk objects.

    Args:
        url: The URL to scrape.
        source_name: Name for the source (used in tags and file_path).

    Returns:
        List of VaultChunk objects extracted from the page.
    """
    import httpx
    from bs4 import BeautifulSoup

    try:
        response = httpx.get(url, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove nav, sidebar, footer, etc.
    for tag in soup.find_all(["nav", "footer", "script", "style", "aside"]):
        tag.decompose()

    # Find main content area
    main = (
        soup.find(role="main")
        or soup.find("article")
        or soup.find("main")
        or soup.find("body")
    )

    if main is None:
        return []

    # Extract text, split by headings
    sections = _split_by_headings(main)

    if not source_name:
        title = soup.find("title")
        source_name = title.get_text(strip=True) if title else url

    chunks = []
    for section_title, section_text in sections:
        content = section_text.strip()
        if not content or len(content) < 20:
            continue

        chunk_id = _make_url_chunk_id(url, section_title)
        chunks.append(VaultChunk(
            id=chunk_id,
            file_path=f"url:{source_name}",
            section=section_title,
            content=content,
            tags=[source_name, "scraped"],
            metadata={"source_url": url},
        ))

    return chunks


def scrape_documentation(
    urls: list[str],
    source_name: str,
) -> list[VaultChunk]:
    """Batch scrape multiple URLs from the same documentation source.

    Args:
        urls: List of URLs to scrape.
        source_name: Name identifying this documentation source.

    Returns:
        List of VaultChunk objects from all pages.
    """
    all_chunks: list[VaultChunk] = []
    for url in urls:
        try:
            chunks = scrape_url(url, source_name=source_name)
            all_chunks.extend(chunks)
            logger.info("Scraped %d chunks from %s", len(chunks), url)
        except Exception as e:
            logger.warning("Error scraping %s: %s", url, e)
    return all_chunks


def compute_url_hash(url: str, content: str) -> str:
    """Compute a content hash for URL deduplication."""
    raw = f"{url}:{content}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _split_by_headings(element: Any) -> list[tuple[str, str]]:
    """Split HTML content by heading tags into (title, text) pairs."""
    sections: list[tuple[str, str]] = []
    current_title = "Overview"
    current_parts: list[str] = []

    for child in element.children:
        tag_name = getattr(child, "name", None)
        if tag_name in ("h1", "h2", "h3", "h4"):
            # Save previous section
            text = "\n".join(current_parts).strip()
            if text:
                sections.append((current_title, text))
            current_title = child.get_text(strip=True)
            current_parts = []
        else:
            text = child.get_text(separator="\n", strip=True) if hasattr(child, "get_text") else str(child).strip()
            if text:
                current_parts.append(text)

    # Save last section
    text = "\n".join(current_parts).strip()
    if text:
        sections.append((current_title, text))

    return sections


def _make_url_chunk_id(url: str, section: str) -> str:
    """Generate a deterministic chunk ID from URL and section."""
    raw = f"{url}::{section}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
