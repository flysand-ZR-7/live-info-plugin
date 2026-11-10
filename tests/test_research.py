"""
Unit tests for Research Assistant capability.
"""

from unittest.mock import AsyncMock, patch
import pytest

from app.models import ReaderResponse, ResearchDepth, SearchResultItem
from app.research import conduct_research, generate_sub_queries, select_diverse_urls


@pytest.mark.asyncio
async def test_generate_sub_queries():
    mock_json = '["fusion energy progress", "ITER reactor timeline", "stellarator developments"]'

    with patch("app.research.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = mock_json

        queries = await generate_sub_queries("What is the state of nuclear fusion?", count=3)

        assert len(queries) == 3
        assert queries[0] == "fusion energy progress"
        assert queries[1] == "ITER reactor timeline"


def test_select_diverse_urls():
    candidates = [
        ("https://wikipedia.org/wiki/Fusion", "Wiki 1"),
        ("https://wikipedia.org/wiki/Tokamak", "Wiki 2"),
        ("https://wikipedia.org/wiki/ITER", "Wiki 3"),
        ("https://nature.com/articles/fusion", "Nature 1"),
        ("https://mit.edu/news/fusion", "MIT 1"),
    ]

    # Max 3 URLs: should not take 3 from wikipedia.org
    selected = select_diverse_urls(candidates, max_urls=3)

    assert len(selected) == 3
    domains = [url for url, _ in selected]
    # Check that diverse domains (nature.com or mit.edu) are included
    assert any("nature.com" in u or "mit.edu" in u for u in domains)


@pytest.mark.asyncio
async def test_conduct_research_pipeline():
    mock_subqueries_json = '["solid state battery timeline", "solid state battery commercialization"]'

    mock_search_results = (
        [
            SearchResultItem(
                title="Solid State Battery Market 2026",
                url="https://batteries.com/report",
                snippet="Automakers target 2027-2028 for mass adoption.",
                engine="bing",
            ),
            SearchResultItem(
                title="Technical Hurdles of Dendrites",
                url="https://sciencedirect.com/dendrites",
                snippet="Electrolyte interface degradation remains a primary challenge.",
                engine="duckduckgo",
            ),
        ],
        False,
    )

    mock_reader_response = ReaderResponse(
        url="https://batteries.com/report",
        title="Solid State Battery Market 2026",
        text="Solid-state batteries replace liquid electrolytes with solid ceramics, improving energy density by 50%.",
        truncated=False,
        char_count=107,
    )

    mock_llm_report = (
        "## Summary\n"
        "Solid state batteries offer significant energy density improvements [1].\n\n"
        "## Key Findings\n"
        "* Automotive commercialization is targeted for late decade [1].\n\n"
        "## Disagreements and Uncertainty\n"
        "* Interface stability and manufacturing yield remain uncertain.\n\n"
        "## Sources\n"
        "[1] Solid State Battery Market 2026 — https://batteries.com/report"
    )

    with patch("app.research.generate_sub_queries", new_callable=AsyncMock) as mock_sq, \
         patch("app.research.search", new_callable=AsyncMock) as mock_search, \
         patch("app.research.read_url", new_callable=AsyncMock) as mock_read, \
         patch("app.research.complete", new_callable=AsyncMock) as mock_complete:

        mock_sq.return_value = ["solid state battery timeline"]
        mock_search.return_value = mock_search_results
        mock_read.return_value = mock_reader_response
        mock_complete.return_value = mock_llm_report

        response = await conduct_research("When will solid state batteries ship?", depth=ResearchDepth.QUICK)

        assert response.question == "When will solid state batteries ship?"
        assert len(response.sources) >= 1
        assert "## Key Findings" in response.answer
        assert "[1]" in response.answer


def test_research_endpoint(client):
    with patch("app.main.conduct_research") as mock_research:
        from app.models import ResearchResponse, ResearchSource
        mock_research.return_value = ResearchResponse(
            question="AI agents",
            depth="quick",
            sub_queries=["ai agents 2026"],
            answer="## Summary\nAI agents are evolving rapidly [1].\n\n## Sources\n[1] Agent Overview — https://example.com/agents",
            sources=[ResearchSource(id=1, title="Agent Overview", url="https://example.com/agents", domain="example.com")],
        )

        response = client.post("/research", json={"question": "AI agents", "depth": "quick"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) == 1
        assert "AI agents are evolving" in data["answer"]
