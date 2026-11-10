"""
Search service handling SearXNG queries, retry logic, URL deduplication,
Brave Search API fallback, and in-memory TTL caching.
"""

import asyncio
import hashlib
import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.models import SearchResultItem, SearchTimeRange

logger = logging.getLogger(__name__)

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))

# Simple in-memory cache: cache_key -> (expiry_monotonic, list_of_items)
_SEARCH_CACHE: Dict[str, Tuple[float, List[SearchResultItem]]] = {}


def _make_cache_key(query: str, max_results: int, language: str, time_range: Optional[str], categories: Optional[str]) -> str:
    raw = f"{query.lower().strip()}|{max_results}|{language}|{time_range or ''}|{categories or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_url(raw_url: str) -> str:
    """Normalizes URL for deduplication."""
    try:
        parsed = urlparse(raw_url.strip())
        # Lowercase scheme and host, remove trailing slash from path if present
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        normalized = f"{scheme}://{netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized
    except Exception:
        return raw_url.strip()


def deduplicate_results(items: List[SearchResultItem], max_results: int) -> List[SearchResultItem]:
    """Deduplicates search results by normalized URL while preserving ranking order."""
    seen_urls = set()
    deduped = []
    for item in items:
        norm = _normalize_url(item.url)
        if norm not in seen_urls:
            seen_urls.add(norm)
            deduped.append(item)
            if len(deduped) >= max_results:
                break
    return deduped


async def _query_searxng(
    client: httpx.AsyncClient,
    query: str,
    language: str,
    time_range: Optional[str],
    categories: Optional[str],
) -> List[SearchResultItem]:
    """Queries SearXNG JSON endpoint."""
    params = {
        "q": query,
        "format": "json",
        "language": language,
    }
    if time_range:
        params["time_range"] = time_range
    if categories:
        params["categories"] = categories

    endpoint = f"{SEARXNG_URL}/search"
    response = await client.get(endpoint, params=params, timeout=8.0)
    response.raise_for_status()

    data = response.json()
    raw_results = data.get("results", [])

    items = []
    for r in raw_results:
        url = r.get("url")
        title = r.get("title", "").strip()
        snippet = r.get("content", "") or r.get("snippet", "")
        engine = r.get("engine", "searxng")

        if url and title:
            items.append(
                SearchResultItem(
                    title=title,
                    url=url,
                    snippet=snippet.strip(),
                    engine=engine,
                )
            )

    return items


async def _query_brave_fallback(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
) -> List[SearchResultItem]:
    """Fallback search using Brave Search API if configured."""
    if not BRAVE_API_KEY:
        logger.warning("Brave fallback requested but BRAVE_API_KEY is not configured.")
        return []

    logger.info("Executing Brave Search fallback for query: '%s'", query)
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": min(max_results, 20),
    }

    try:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("web", {}).get("results", [])

        items = []
        for r in results:
            url = r.get("url")
            title = r.get("title", "").strip()
            snippet = r.get("description", "").strip()
            if url and title:
                items.append(
                    SearchResultItem(
                        title=title,
                        url=url,
                        snippet=snippet,
                        engine="brave-fallback",
                    )
                )
        return items
    except Exception as exc:
        logger.error("Brave search fallback failed: %s", exc)
        return []


async def search(
    query: str,
    max_results: int = 8,
    language: str = "en",
    time_range: Optional[SearchTimeRange | str] = None,
    categories: Optional[str] = None,
    use_cache: bool = True,
) -> Tuple[List[SearchResultItem], bool]:
    """
    Searches the web using SearXNG with retry, URL deduplication,
    in-memory caching, and Brave API fallback.

    :return: Tuple of (results_list, was_cached)
    """
    time_range_val = time_range.value if isinstance(time_range, SearchTimeRange) else time_range
    cache_key = _make_cache_key(query, max_results, language, time_range_val, categories)

    now = time.monotonic()
    if use_cache and cache_key in _SEARCH_CACHE:
        expiry, cached_items = _SEARCH_CACHE[cache_key]
        if now < expiry:
            logger.debug("Cache hit for query: '%s'", query)
            return cached_items, True
        else:
            del _SEARCH_CACHE[cache_key]

    raw_items: List[SearchResultItem] = []
    headers = {"User-Agent": "LiveInfoPlugin/1.0 (Mozilla/5.0 AppleWebKit/537.36)"}

    async with httpx.AsyncClient(headers=headers) as client:
        # Attempt 1: SearXNG
        try:
            raw_items = await _query_searxng(
                client=client,
                query=query,
                language=language,
                time_range=time_range_val,
                categories=categories,
            )
        except Exception as exc:
            logger.warning("SearXNG attempt 1 failed for query '%s': %s", query, exc)

        # Attempt 2: SearXNG Retry if empty or failed
        if not raw_items:
            logger.info("Retrying SearXNG query '%s'...", query)
            await asyncio.sleep(0.5)
            try:
                raw_items = await _query_searxng(
                    client=client,
                    query=query,
                    language=language,
                    time_range=time_range_val,
                    categories=categories,
                )
            except Exception as exc:
                logger.error("SearXNG attempt 2 failed for query '%s': %s", query, exc)

        # Fallback to Brave API if SearXNG returned nothing
        if not raw_items and BRAVE_API_KEY:
            raw_items = await _query_brave_fallback(client, query, max_results)

    # Deduplicate by URL up to max_results
    final_items = deduplicate_results(raw_items, max_results)

    # Cache successful results
    if use_cache and final_items:
        _SEARCH_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, final_items)

    return final_items, False
