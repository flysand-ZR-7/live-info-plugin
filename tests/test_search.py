"""
Unit tests for Search capability (SearXNG client, deduplication, retry, and fallback).
"""

from unittest.mock import AsyncMock, patch
import pytest
import respx
import httpx

from app.models import SearchResultItem
from app.search import deduplicate_results, search


def test_deduplicate_results():
    items = [
        SearchResultItem(title="A", url="https://example.com/page", snippet="a", engine="ddg"),
        SearchResultItem(title="A duplicate", url="https://example.com/page/", snippet="a dup", engine="bing"),
        SearchResultItem(title="B", url="https://example.com/other", snippet="b", engine="ddg"),
        SearchResultItem(title="C", url="https://news.org/story", snippet="c", engine="brave"),
    ]
    deduped = deduplicate_results(items, max_results=2)
    assert len(deduped) == 2
    assert deduped[0].url == "https://example.com/page"
    assert deduped[1].url == "https://example.com/other"


@pytest.mark.asyncio
@respx.mock
async def test_searxng_search_success():
    searx_endpoint = "http://localhost:8080/search"
    mock_payload = {
        "results": [
            {
                "title": "FastAPI Framework",
                "url": "https://fastapi.tiangolo.com/",
                "content": "FastAPI is a modern, fast web framework for building APIs with Python.",
                "engine": "duckduckgo",
            },
            {
                "title": "FastAPI Tutorial",
                "url": "https://fastapi.tiangolo.com/tutorial/",
                "content": "Step by step tutorial.",
                "engine": "bing",
            },
        ]
    }
    respx.get(searx_endpoint).respond(200, json=mock_payload)

    results, was_cached = await search(query="fastapi", max_results=5, use_cache=False)

    assert len(results) == 2
    assert results[0].title == "FastAPI Framework"
    assert results[0].url == "https://fastapi.tiangolo.com/"
    assert results[0].engine == "duckduckgo"
    assert was_cached is False


@pytest.mark.asyncio
@respx.mock
async def test_searxng_retry_on_initial_failure():
    searx_endpoint = "http://localhost:8080/search"
    # First attempt fails with 500, second attempt succeeds
    route = respx.get(searx_endpoint)
    route.side_effect = [
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Recovered Result",
                        "url": "https://example.com/recovered",
                        "content": "Recovered snippet on retry.",
                        "engine": "duckduckgo",
                    }
                ]
            },
        ),
    ]

    results, _ = await search(query="test retry", max_results=5, use_cache=False)
    assert len(results) == 1
    assert results[0].title == "Recovered Result"


@pytest.mark.asyncio
@respx.mock
async def test_brave_fallback_when_searxng_down():
    searx_endpoint = "http://localhost:8080/search"
    respx.get(searx_endpoint).respond(503, text="Service Unavailable")

    brave_endpoint = "https://api.search.brave.com/res/v1/web/search"
    respx.get(brave_endpoint).respond(
        200,
        json={
            "web": {
                "results": [
                    {
                        "title": "Brave Fallback Result",
                        "url": "https://brave.com/search",
                        "description": "Found via Brave search fallback API.",
                    }
                ]
            }
        },
    )

    with patch("app.search.BRAVE_API_KEY", "mock-brave-key"):
        results, _ = await search(query="fallback test", max_results=5, use_cache=False)

    assert len(results) == 1
    assert results[0].title == "Brave Fallback Result"
    assert results[0].engine == "brave-fallback"


def test_search_api_endpoint(client):
    with patch("app.main.search") as mock_search:
        mock_search.return_value = (
            [
                SearchResultItem(
                    title="Mocked Search",
                    url="https://example.com/mock",
                    snippet="Mock snippet text",
                    engine="duckduckgo",
                )
            ],
            False,
        )

        response = client.post("/search", json={"query": "test query", "max_results": 4})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "test query"
        assert data["total"] == 1
        assert data["results"][0]["title"] == "Mocked Search"
