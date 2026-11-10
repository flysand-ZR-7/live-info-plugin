"""
Unit tests for Fact Verification capability.
"""

from unittest.mock import AsyncMock, patch
import pytest

from app.models import FactVerificationResponse, VerdictEnum
from app.verify import generate_verification_queries, verify_claim


@pytest.mark.asyncio
async def test_generate_verification_queries():
    mock_json = (
        '{"supporting": ["Great Wall space seen evidence", "astronauts visible Great Wall"], '
        '"contradicting": ["Great Wall space myth debunked", "NASA visible human structures space"]}'
    )

    with patch("app.verify.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = mock_json

        sup, con = await generate_verification_queries("The Great Wall of China is visible from the Moon with naked eyes")

        assert len(sup) == 2
        assert len(con) == 2
        assert "Great Wall" in sup[0]
        assert "debunked" in con[0]


@pytest.mark.asyncio
async def test_verify_claim_verdict():
    mock_docs = [
        {
            "url": "https://nasa.gov/great-wall-myth",
            "title": "NASA Fact Sheet: Earth Viewing",
            "text": "The Great Wall is barely visible from low Earth orbit and completely invisible from the Moon without optical aid.",
        }
    ]

    mock_adjudication_json = """
    {
      "verdict": "FALSE",
      "confidence": 0.98,
      "explanation": "Astronauts and orbital imagery confirm that the Great Wall cannot be distinguished from the Moon without high-powered optics.",
      "supporting": [],
      "contradicting": [
        {
          "url": "https://nasa.gov/great-wall-myth",
          "title": "NASA Fact Sheet: Earth Viewing",
          "quote_summary": "The wall is completely invisible from the Moon without optical aid."
        }
      ]
    }
    """

    with patch("app.verify.generate_verification_queries", new_callable=AsyncMock) as mock_queries, \
         patch("app.verify.fetch_evidence_documents", new_callable=AsyncMock) as mock_fetch_docs, \
         patch("app.verify.complete", new_callable=AsyncMock) as mock_complete:

        mock_queries.return_value = (["support query"], ["debunk query"])
        mock_fetch_docs.return_value = mock_docs
        mock_complete.return_value = mock_adjudication_json

        result = await verify_claim("The Great Wall of China is visible from the Moon with naked eyes")

        assert result.verdict == VerdictEnum.FALSE
        assert result.confidence >= 0.95
        assert len(result.contradicting) == 1
        assert "invisible from the Moon" in result.contradicting[0].quote_summary


def test_verify_endpoint(client):
    with patch("app.main.verify_claim") as mock_verify:
        mock_verify.return_value = FactVerificationResponse(
            claim="Water boils at 100C at standard atmospheric pressure",
            verdict=VerdictEnum.TRUE,
            confidence=0.99,
            explanation="Thermodynamic physics and empirical chemistry confirm standard boiling point of water at 1 atm is 100 degrees Celsius.",
            supporting=[],
            contradicting=[],
        )

        response = client.post("/verify", json={"claim": "Water boils at 100C at 1 atm"})
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "TRUE"
        assert data["confidence"] == 0.99
