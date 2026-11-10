"""
Main FastAPI application entry point for the Internet & Live Information Plugin.
Exposes endpoints for Search, News, Website Reader, Research Assistant, and Fact Verification.
Includes rate limiting, error handlers, logging, and tool manifest discovery.
"""

from collections import defaultdict
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import time
from typing import Dict, List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load environment variables before importing app modules
load_dotenv()

from app.models import (
    ErrorResponse,
    FactVerificationRequest,
    FactVerificationResponse,
    NewsRequest,
    NewsResponse,
    ReaderRequest,
    ReaderResponse,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
)
from app.news import get_news
from app.reader import read_url
from app.research import conduct_research
from app.search import search
from app.security import SSRFProtectionError
from app.verify import verify_claim

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("live-info-plugin")

# Rate limiting settings
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
_IP_TIMESTAMPS: Dict[str, List[float]] = defaultdict(list)


def rate_limiter(request: Request):
    """Simple in-memory sliding-window rate limiter per client IP."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = 60.0

    # Prune old timestamps
    active = [t for t in _IP_TIMESTAMPS[client_ip] if now - t < window]
    if len(active) >= RATE_LIMIT_PER_MINUTE:
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_PER_MINUTE} requests per minute.",
        )
    active.append(now)
    _IP_TIMESTAMPS[client_ip] = active


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for initialization and cleanup."""
    logger.info("Initializing Live Information Plugin...")
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")
    llm_provider = os.getenv("LLM_PROVIDER", "anthropic")
    llm_model = os.getenv("LLM_MODEL", "(default)")
    logger.info("SearXNG Backend: %s", searxng_url)
    logger.info("LLM Provider: %s (Model: %s)", llm_provider, llm_model)
    yield
    logger.info("Shutting down Live Information Plugin.")


app = FastAPI(
    title="Internet & Live Information Plugin",
    description=(
        "Production-grade live internet access plugin for open-source and commercial LLMs. "
        "Provides web search, news briefings, website reader with SSRF protection, "
        "multi-step deep research, and rigorous fact verification."
    ),
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(rate_limiter)],
)

# Enable CORS for web and client integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Global Exception Handlers
# ==============================================================================

@app.exception_handler(SSRFProtectionError)
async def ssrf_exception_handler(request: Request, exc: SSRFProtectionError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "SecurityViolation", "detail": exc.detail},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HttpRequestError", "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "InternalServerError", "detail": str(exc)},
    )


# ==============================================================================
# Health & Discovery Endpoints
# ==============================================================================

@app.get("/health", tags=["System"])
async def health_check():
    """Returns service health status and configuration info."""
    return {
        "status": "ok",
        "service": "live-info-plugin",
        "searxng_url": os.getenv("SEARXNG_URL", "http://localhost:8080"),
        "llm_provider": os.getenv("LLM_PROVIDER", "anthropic"),
        "llm_model": os.getenv("LLM_MODEL", ""),
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
    }


@app.get("/tools", tags=["System"])
async def get_tool_manifest():
    """Returns OpenAI/Open-Source function calling schema definitions for all 5 capabilities."""
    manifest_path = Path(__file__).parent.parent / "tools_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Tools manifest file not found.")


# ==============================================================================
# 1. Internet Search Endpoint
# ==============================================================================

@app.post(
    "/search",
    response_model=SearchResponse,
    tags=["Capabilities"],
    summary="Search the internet using SearXNG backend",
)
async def endpoint_search(req: SearchRequest):
    """
    Executes a web search with SearXNG, URL deduplication, and optional Brave Search fallback.
    Returns clean titles, URLs, snippets, and source engines.
    """
    logger.info("Received /search request: query='%s' max_results=%d", req.query, req.max_results)
    results, was_cached = await search(
        query=req.query,
        max_results=req.max_results,
        language=req.language,
        time_range=req.time_range,
    )
    return SearchResponse(
        query=req.query,
        total=len(results),
        results=results,
        cached=was_cached,
    )


# ==============================================================================
# 2. News & World Events Endpoint
# ==============================================================================

@app.post(
    "/news",
    response_model=NewsResponse,
    tags=["Capabilities"],
    summary="Get recent news articles and an executive briefing with citations",
)
async def endpoint_news(req: NewsRequest):
    """
    Retrieves recent news for a topic and generates an executive briefing (<= 5 bullet points)
    citing each referenced article by number [n].
    """
    logger.info("Received /news request: topic='%s' time_range=%s", req.topic, req.time_range)
    return await get_news(
        topic=req.topic,
        time_range=req.time_range,
        max_results=req.max_results,
    )


# ==============================================================================
# 3. Website Reader Endpoint
# ==============================================================================

@app.post(
    "/read",
    response_model=ReaderResponse,
    tags=["Capabilities"],
    summary="Read and extract clean text from a web page with strict SSRF protection",
)
async def endpoint_read(req: ReaderRequest):
    """
    Fetches a web page with SSRF protection re-verified on every redirect hop, enforces a 5MB size cap,
    extracts main body text with trafilatura, and optionally generates an LLM summary.
    """
    logger.info("Received /read request: url='%s' max_chars=%d summarize=%s", req.url, req.max_chars, req.summarize)
    return await read_url(
        url=req.url,
        max_chars=req.max_chars,
        summarize=req.summarize,
    )


# ==============================================================================
# 4. Research Assistant Endpoint
# ==============================================================================

@app.post(
    "/research",
    response_model=ResearchResponse,
    tags=["Capabilities"],
    summary="Multi-step deep research across parallel searches and web pages",
)
async def endpoint_research(req: ResearchRequest):
    """
    Deconstructs a research question into sub-queries, executes parallel searches,
    reads top pages across diverse domains, and synthesizes a structured report with [n] citations.
    """
    logger.info("Received /research request: question='%s' depth=%s", req.question, req.depth)
    return await conduct_research(
        question=req.question,
        depth=req.depth,
    )


# ==============================================================================
# 5. Fact Verification Endpoint
# ==============================================================================

@app.post(
    "/verify",
    response_model=FactVerificationResponse,
    tags=["Capabilities"],
    summary="Rigorous fact verification of claims against retrieved evidence",
)
async def endpoint_verify(req: FactVerificationRequest):
    """
    Generates supporting and contradicting queries, gathers evidence from both sides,
    and returns a definitive verdict (TRUE, MOSTLY_TRUE, MIXED, MOSTLY_FALSE, FALSE, UNVERIFIABLE)
    with confidence and structured quote summaries.
    """
    logger.info("Received /verify request: claim='%s'", req.claim)
    return await verify_claim(claim=req.claim)
