"""
Pydantic v2 data models for all requests and responses in the Live Information Plugin.
"""

from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, HttpUrl


# ==============================================================================
# 1. Search Models
# ==============================================================================

class SearchTimeRange(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query terms")
    max_results: int = Field(default=8, ge=1, le=50, description="Maximum number of search results to return")
    language: str = Field(default="en", max_length=10, description="Search language code (e.g., 'en', 'es', 'de')")
    time_range: Optional[SearchTimeRange] = Field(default=None, description="Optional time range filter")


class SearchResultItem(BaseModel):
    title: str = Field(..., description="Title of the search result")
    url: str = Field(..., description="Destination URL")
    snippet: str = Field(..., description="Snippet/excerpt text from the result")
    engine: str = Field(..., description="Search backend engine that found this result (e.g., duckduckgo, bing)")


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResultItem]
    cached: bool = False


# ==============================================================================
# 2. News Models
# ==============================================================================

class NewsRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="News topic or headline subject")
    time_range: SearchTimeRange = Field(default=SearchTimeRange.DAY, description="Recency filter (default: day)")
    max_results: int = Field(default=8, ge=1, le=30, description="Max number of news articles")


class NewsArticleItem(BaseModel):
    title: str
    url: str
    source: str
    published_date: Optional[str] = None
    snippet: str


class NewsResponse(BaseModel):
    topic: str
    time_range: str
    total: int
    articles: List[NewsArticleItem]
    briefing: str = Field(..., description="Executive briefing with 5 bullet points max and numbered source citations [n]")
    cached: bool = False


# ==============================================================================
# 3. Reader Models
# ==============================================================================

class ReaderRequest(BaseModel):
    url: str = Field(..., description="Web page URL to fetch and extract main text from")
    max_chars: int = Field(default=8000, ge=500, le=50000, description="Maximum extracted text characters before truncation")
    summarize: bool = Field(default=False, description="Whether to also generate an LLM summary of the page")


class ReaderResponse(BaseModel):
    url: str
    title: Optional[str] = None
    text: str = Field(..., description="Main clean extracted body text (HTML, ads, headers stripped)")
    truncated: bool = Field(..., description="True if text exceeded max_chars and was truncated")
    char_count: int
    summary: Optional[str] = None
    cached: bool = False


# ==============================================================================
# 4. Research Models
# ==============================================================================

class ResearchDepth(str, Enum):
    QUICK = "quick"        # 3 sub-queries
    STANDARD = "standard"  # 5 sub-queries
    DEEP = "deep"          # 8 sub-queries


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000, description="Research question or topic to investigate")
    depth: ResearchDepth = Field(default=ResearchDepth.STANDARD, description="Depth level: quick=3 sub-queries, standard=5, deep=8")


class ResearchSource(BaseModel):
    id: int = Field(..., description="Citation number [n]")
    title: str
    url: str
    domain: str


class ResearchResponse(BaseModel):
    question: str
    depth: str
    sub_queries: List[str]
    answer: str = Field(..., description="Structured report: Summary, Key Findings, Disagreements/Uncertainty with [n] citations")
    sources: List[ResearchSource]


# ==============================================================================
# 5. Fact Verification Models
# ==============================================================================

class VerdictEnum(str, Enum):
    TRUE = "TRUE"
    MOSTLY_TRUE = "MOSTLY_TRUE"
    MIXED = "MIXED"
    MOSTLY_FALSE = "MOSTLY_FALSE"
    FALSE = "FALSE"
    UNVERIFIABLE = "UNVERIFIABLE"


class FactVerificationRequest(BaseModel):
    claim: str = Field(..., min_length=3, max_length=1000, description="The specific factual claim to verify")


class EvidenceItem(BaseModel):
    url: str
    title: str
    quote_summary: str = Field(..., description="Concise paraphrase or short phrase of evidence from the page")


class FactVerificationResponse(BaseModel):
    claim: str
    verdict: VerdictEnum
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    explanation: str = Field(..., description="Reasoning based strictly on retrieved evidence")
    supporting: List[EvidenceItem] = Field(default_factory=list, description="Evidence supporting the claim")
    contradicting: List[EvidenceItem] = Field(default_factory=list, description="Evidence contradicting the claim")


# ==============================================================================
# Error Models
# ==============================================================================

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
