"""
Unit tests for Website Reader capability (trafilatura extraction, SSRF enforcement, truncation, summarization).
"""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException

from app.models import ReaderResponse
from app.reader import fetch_page_content, read_url, summarize_text
from app.security import SSRFProtectionError


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Quantum Computing Breakthrough</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <article>
    <h1>Quantum Computing Breakthrough Announced</h1>
    <p>Researchers at the National Physics Institute achieved quantum coherence for over 10 minutes.</p>
    <p>This achievement paves the way for scalable quantum error correction and practical supercomputing.</p>
  </article>
  <footer>Copyright 2026 Physics Daily</footer>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_read_url_clean_extraction():
    # Mock safe fetch
    with patch("app.reader.fetch_page_content", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("https://physicsdaily.org/quantum", SAMPLE_HTML)

        result = await read_url(
            url="https://physicsdaily.org/quantum",
            max_chars=5000,
            summarize=False,
            use_cache=False,
        )

        assert result.url == "https://physicsdaily.org/quantum"
        assert result.title == "Quantum Computing Breakthrough"
        assert "quantum coherence" in result.text.lower()
        assert "Copyright 2026" not in result.text  # trafilatura strips boilerplates
        assert result.truncated is False


@pytest.mark.asyncio
async def test_read_url_truncation():
    with patch("app.reader.fetch_page_content", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("https://example.com/long", SAMPLE_HTML)

        # Set max_chars low
        result = await read_url(
            url="https://example.com/long",
            max_chars=50,
            summarize=False,
            use_cache=False,
        )

        assert len(result.text) <= 50
        assert result.truncated is True


@pytest.mark.asyncio
async def test_read_url_with_summarize():
    with patch("app.reader.fetch_page_content", new_callable=AsyncMock) as mock_fetch, \
         patch("app.reader.complete", new_callable=AsyncMock) as mock_complete:

        mock_fetch.return_value = ("https://example.com/article", SAMPLE_HTML)
        mock_complete.return_value = "Physicists demonstrated record 10-minute quantum coherence."

        result = await read_url(
            url="https://example.com/article",
            max_chars=5000,
            summarize=True,
            use_cache=False,
        )

        assert result.summary == "Physicists demonstrated record 10-minute quantum coherence."
        mock_complete.assert_called_once()
        # Verify prompt-injection defense delimiters
        args, kwargs = mock_complete.call_args
        assert "<untrusted_web_content>" in kwargs["user"]


@pytest.mark.asyncio
async def test_ssrf_blocked_on_initial_url():
    with pytest.raises(SSRFProtectionError):
        await read_url(url="http://127.0.0.1:8080/secret", use_cache=False)


def test_reader_api_endpoint(client):
    with patch("app.main.read_url") as mock_read:
        mock_read.return_value = ReaderResponse(
            url="https://example.com/doc",
            title="Example Doc",
            text="Clean body text of the document.",
            truncated=False,
            char_count=31,
            summary=None,
            cached=False,
        )

        response = client.post("/read", json={"url": "https://example.com/doc", "max_chars": 2000})
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Example Doc"
        assert "Clean body text" in data["text"]
