"""
Recursive multi-page website crawler service inspired by Scrapy.
Features:
- Breadth-first crawl with depth control (max_depth) and page capping (max_pages).
- Domain-boundary filtering (stay_on_domain).
- Strict SSRF protection and multi-hop validation for every child link.
- Trafilatura clean content extraction.
- Optional executive multi-page knowledge summarization via LLM.
"""

import asyncio
from collections import deque
import logging
import os
import re
from typing import List, Optional, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

import trafilatura

from app.llm import complete
from app.models import CrawledPageItem, CrawlResponse
from app.reader import fetch_page_content
from app.security import SSRFProtectionError, validate_url

logger = logging.getLogger(__name__)

# Excluded extensions that do not contain readable HTML articles/docs
EXCLUDED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dmg", ".pkg", ".deb", ".rpm",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf",
)


def _extract_links(html: str, base_url: str, allowed_domain: Optional[str]) -> List[str]:
    """Extracts, normalizes, and filters valid HTTP(S) child links from HTML."""
    found_links: List[str] = []
    # Match href="..." or href='...'
    matches = re.findall(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']', html, re.IGNORECASE)

    for href in matches:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue

        try:
            full_url = urljoin(base_url, href)
            clean_url, _ = urldefrag(full_url)
            parsed = urlparse(clean_url)

            # Only http or https schemes
            if parsed.scheme.lower() not in ("http", "https"):
                continue

            # Check file extensions
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                continue

            # Enforce domain boundary if requested
            if allowed_domain:
                host = parsed.netloc.lower()
                if ":" in host:
                    host = host.split(":")[0]
                if host != allowed_domain and not host.endswith("." + allowed_domain):
                    continue

            found_links.append(clean_url)
        except Exception:
            continue

    return list(dict.fromkeys(found_links))


async def crawl_website(
    root_url: str,
    max_depth: int = 2,
    max_pages: int = 10,
    stay_on_domain: bool = True,
    summarize: bool = False,
    use_tor: bool = False,
) -> CrawlResponse:
    """
    Crawls a website breadth-first starting from root_url up to max_depth and max_pages.
    """
    logger.info("Starting website crawl on '%s' (max_depth=%d, max_pages=%d)", root_url, max_depth, max_pages)

    # Validate root URL
    validated_root = validate_url(root_url)
    parsed_root = urlparse(validated_root)
    allowed_domain = parsed_root.netloc.lower().split(":")[0] if stay_on_domain else None

    visited_urls: Set[str] = set()
    queue: deque[Tuple[str, int]] = deque([(validated_root, 1)])
    crawled_pages: List[CrawledPageItem] = []
    max_depth_reached = 1

    semaphore = asyncio.Semaphore(3)

    while queue and len(crawled_pages) < max_pages:
        current_url, current_depth = queue.popleft()

        clean_current, _ = urldefrag(current_url)
        if clean_current in visited_urls:
            continue
        visited_urls.add(clean_current)

        if current_depth > max_depth_reached:
            max_depth_reached = current_depth

        async with semaphore:
            try:
                # SSRF validation check for every child link before fetch
                safe_url = validate_url(clean_current)
                final_url, html = await fetch_page_content(safe_url)
            except (SSRFProtectionError, Exception) as exc:
                logger.warning("Skipping URL '%s' during crawl: %s", clean_current, exc)
                continue

        # Extract text via trafilatura
        extracted_text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        ) or ""

        # Extract title
        title = None
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            clean_t = re.sub(r"\s+", " ", match.group(1)).strip()
            title = clean_t[:200] if clean_t else None

        child_links = _extract_links(html, final_url, allowed_domain)

        crawled_pages.append(
            CrawledPageItem(
                url=final_url,
                title=title,
                text=extracted_text[:12000].strip(),
                depth=current_depth,
                word_count=len(extracted_text.split()),
                child_links_count=len(child_links),
            )
        )

        # Enqueue discovered links if within depth limit and quota remains
        if current_depth < max_depth and len(crawled_pages) + len(queue) < max_pages * 2:
            for child in child_links:
                child_clean, _ = urldefrag(child)
                if child_clean not in visited_urls:
                    queue.append((child_clean, current_depth + 1))

    # Optional multi-page executive knowledge synthesis via LLM
    knowledge_summary = None
    if summarize and crawled_pages:
        try:
            combined_snippets = []
            for i, p in enumerate(crawled_pages[:8], 1):
                preview = p.text[:1500].replace("\n", " ")
                combined_snippets.append(f"[{i}] {p.title or p.url}\nURL: {p.url}\nContent: {preview}")

            corpus = "\n\n".join(combined_snippets)
            prompt = (
                f"You are a research synthesis agent. Below are excerpts from {len(crawled_pages)} crawled pages "
                f"from {root_url}.\n\n"
                f"{corpus}\n\n"
                f"Generate an executive knowledge summary synthesizing the key concepts, main topics, and architecture "
                f"described across these pages. Use bullet points and cite source URLs."
            )
            knowledge_summary = await complete(
                prompt=prompt,
                system_prompt="You are an expert technical documentation synthesizer. Be direct, factual, and clear.",
                max_tokens=800,
            )
        except Exception as exc:
            logger.warning("Failed to generate knowledge summary for crawl: %s", exc)

    return CrawlResponse(
        root_url=root_url,
        total_pages_crawled=len(crawled_pages),
        depth_reached=max_depth_reached,
        pages=crawled_pages,
        knowledge_summary=knowledge_summary,
    )
