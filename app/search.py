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


def _make_cache_key(query: str, max_results: int, language: str, time_range: Optional[str], categories: Optional[str], engine: Optional[str] = None) -> str:
    raw = f"{query.lower().strip()}|{max_results}|{language}|{time_range or ''}|{categories or ''}|{engine or ''}"
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
    engine: Optional[str] = None,
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
    if engine:
        params["engines"] = engine

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


async def _query_ahmia_direct(
    client: httpx.AsyncClient,
    query: str,
    max_results: int = 8,
) -> List[SearchResultItem]:
    """Fallback query to Ahmia.fi dark web search engine directly."""
    logger.info("Executing direct Ahmia dark web search for query: '%s'", query)
    try:
        import re
        from html import unescape
        
        response = await client.get(
            "https://ahmia.fi/search/",
            params={"q": query},
            timeout=10.0,
        )
        response.raise_for_status()
        html = response.text

        items: List[SearchResultItem] = []
        pattern = re.compile(
            r'<li[^>]*class=["\']result["\'][^>]*>.*?<h4><a\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a></h4>.*?<p>(.*?)</p>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            raw_url, raw_title, raw_desc = match.groups()
            clean_url = raw_url.strip()
            if "redirect_url=" in clean_url:
                clean_url = clean_url.split("redirect_url=")[-1]
            title = re.sub(r"<[^>]+>", "", unescape(raw_title)).strip()
            snippet = re.sub(r"<[^>]+>", "", unescape(raw_desc)).strip()
            if clean_url and title:
                items.append(
                    SearchResultItem(
                        title=title,
                        url=clean_url,
                        snippet=snippet,
                        engine="ahmia",
                    )
                )
            if len(items) >= max_results:
                break
        return items
    except Exception as exc:
        logger.warning("Direct Ahmia search failed: %s", exc)
        return []


async def search(
    query: str,
    max_results: int = 8,
    language: str = "en",
    time_range: Optional[SearchTimeRange | str] = None,
    categories: Optional[str] = None,
    engine: Optional[str] = None,
    use_cache: bool = True,
) -> Tuple[List[SearchResultItem], bool]:
    """
    Searches the web using SearXNG with retry, URL deduplication,
    Ahmia dark-web engine support, in-memory caching, and Brave API fallback.

    :return: Tuple of (results_list, was_cached)
    """
    time_range_val = time_range.value if isinstance(time_range, SearchTimeRange) else time_range
    cache_key = _make_cache_key(query, max_results, language, time_range_val, categories, engine)

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

    # If dark web requested or ahmia engine specified
    is_darkweb = (categories == "darkweb" or engine == "ahmia" or ".onion" in query.lower())
    target_categories = "darkweb" if is_darkweb and not categories else categories
    target_engine = "ahmia" if is_darkweb and not engine else engine

    async with httpx.AsyncClient(headers=headers) as client:
        # Attempt 1: SearXNG
        try:
            raw_items = await _query_searxng(
                client=client,
                query=query,
                language=language,
                time_range=time_range_val,
                categories=target_categories,
                engine=target_engine,
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
                    categories=target_categories,
                    engine=target_engine,
                )
            except Exception as exc:
                logger.error("SearXNG attempt 2 failed for query '%s': %s", query, exc)

        # Attempt 3: If darkweb requested and SearXNG yielded no results, query Ahmia direct
        if not raw_items and is_darkweb:
            raw_items = await _query_ahmia_direct(client, query, max_results)

        # Fallback to Brave API if SearXNG returned nothing for clearweb queries
        if not raw_items and not is_darkweb and BRAVE_API_KEY:
            raw_items = await _query_brave_fallback(client, query, max_results)

    # Deduplicate by URL up to max_results
    final_items = deduplicate_results(raw_items, max_results)

    # Cache successful results
    if use_cache and final_items:
        _SEARCH_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, final_items)

    return final_items, False
