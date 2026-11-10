"""
Tests for Scrapy-style recursive multi-page crawler.
"""

import pytest
import respx
from httpx import Response

from app.crawler import crawl_website, _extract_links


def test_extract_links_filters_domain_and_extensions():
    html = """
    <html>
      <body>
        <a href="/docs/intro">Intro</a>
        <a href="https://example.com/api">API Reference</a>
        <a href="https://external.com/page">External</a>
        <a href="/downloads/manual.pdf">PDF Manual</a>
        <a href="/assets/image.png">Logo</a>
        <a href="javascript:void(0)">JS Action</a>
        <a href="#section">Anchor</a>
      </body>
    </html>
    """
    links = _extract_links(html, "https://example.com/start", allowed_domain="example.com")
    assert "https://example.com/docs/intro" in links
    assert "https://example.com/api" in links
    assert "https://external.com/page" not in links
    assert not any(l.endswith(".pdf") for l in links)
    assert not any(l.endswith(".png") for l in links)


@pytest.mark.asyncio
@respx.mock
async def test_crawl_website_success():
    root_html = """
    <html>
      <head><title>Docs Home</title></head>
      <body>
        <h1>Welcome to Example Docs</h1>
        <p>Main content for the first page.</p>
        <a href="https://example.com/page2">Go to Page 2</a>
      </body>
    </html>
    """
    page2_html = """
    <html>
      <head><title>Docs Page 2</title></head>
      <body>
        <h2>Second Page</h2>
        <p>This is deep documentation text.</p>
      </body>
    </html>
    """

    respx.get("https://example.com/docs").mock(return_value=Response(200, text=root_html))
    respx.get("https://example.com/page2").mock(return_value=Response(200, text=page2_html))

    res = await crawl_website(
        root_url="https://example.com/docs",
        max_depth=2,
        max_pages=5,
        stay_on_domain=True,
        summarize=False,
    )

    assert res.total_pages_crawled >= 1
    assert res.pages[0].url == "https://example.com/docs"
    assert res.pages[0].title == "Docs Home"


@pytest.mark.asyncio
@respx.mock
async def test_crawl_blocks_ssrf_child_links():
    root_html = """
    <html>
      <head><title>Root Site</title></head>
      <body>
        <a href="http://169.254.169.254/latest/meta-data/">Cloud Metadata</a>
        <a href="http://127.0.0.1:8080/admin">Localhost Admin</a>
      </body>
    </html>
    """
    respx.get("https://example.com/index").mock(return_value=Response(200, text=root_html))

    res = await crawl_website(
        root_url="https://example.com/index",
        max_depth=2,
        max_pages=5,
        stay_on_domain=False,  # Allow external links to test SSRF filtering
    )

    assert res.total_pages_crawled == 1
    # Ensure internal IPs were blocked and not crawled
    visited = [p.url for p in res.pages]
    assert not any("169.254.169.254" in u for u in visited)
    assert not any("127.0.0.1" in u for u in visited)
