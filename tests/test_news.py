"""
Unit tests for News & World Events capability.
"""

from unittest.mock import AsyncMock, patch
import pytest

from app.models import NewsArticleItem, SearchResultItem
from app.news import generate_news_briefing, get_news


@pytest.mark.asyncio
async def test_generate_news_briefing_with_citations():
    articles = [
        NewsArticleItem(
            title="James Webb Telescope Discovers New Exoplanet",
            url="https://space.org/exoplanet",
            source="SpaceNews",
            snippet="Astronomers discovered an Earth-sized exoplanet in the habitable zone.",
        ),
        NewsArticleItem(
            title="Atmospheric Analysis of Exoplanet Confirmed",
            url="https://nature.org/atmosphere",
            source="Nature",
            snippet="Spectroscopy confirmed water vapor and carbon dioxide.",
        ),
    ]

    mock_llm_response = (
        "* James Webb Space Telescope identified a temperate exoplanet in habitable zone [1].\n"
        "* Atmospheric spectral analysis detected signatures of carbon dioxide and water vapor [2]."
    )

    with patch("app.news.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = mock_llm_response

        briefing = await generate_news_briefing("James Webb exoplanet", articles)

        assert "[1]" in briefing
        assert "[2]" in briefing
        assert "exoplanet" in briefing.lower()
        mock_complete.assert_called_once()


@pytest.mark.asyncio
async def test_get_news_orchestration():
    mock_search_results = [
        SearchResultItem(
            title="Global AI Summit Concludes in Paris",
            url="https://reuters.com/world/ai-summit",
            snippet="World leaders agreed on safety testing standards.",
            engine="bing news",
        ),
        SearchResultItem(
            title="New AI Treaty Drafted",
            url="https://apnews.com/article/ai-treaty",
            snippet="The framework establishes international oversight.",
            engine="duckduckgo news",
        ),
    ]

    mock_briefing = "* International delegates concluded AI safety treaty [1, 2]."

    with patch("app.news.search", new_callable=AsyncMock) as mock_search, \
         patch("app.news.complete", new_callable=AsyncMock) as mock_complete:

        mock_search.return_value = (mock_search_results, False)
        mock_complete.return_value = mock_briefing

        response = await get_news(topic="AI Summit", max_results=2)

        assert response.total == 2
        assert response.articles[0].source == "Reuters"
        assert response.articles[1].source == "Apnews"
        assert "[1, 2]" in response.briefing


def test_news_endpoint(client):
    with patch("app.main.get_news") as mock_get_news:
        from app.models import NewsResponse
        mock_get_news.return_value = NewsResponse(
            topic="Space",
            time_range="day",
            total=1,
            articles=[
                NewsArticleItem(
                    title="Rocket Launch Successful",
                    url="https://example.com/rocket",
                    source="Example",
                    snippet="Falcon launched safely.",
                )
            ],
            briefing="* Rocket launched safely into orbit [1].",
            cached=False,
        )

        response = client.post("/news", json={"topic": "Space", "time_range": "day"})
        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "Space"
        assert len(data["articles"]) == 1
        assert "[1]" in data["briefing"]
