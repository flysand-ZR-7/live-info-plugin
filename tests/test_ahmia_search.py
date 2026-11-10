"""
Tests for Ahmia dark web search integration and fallback.
"""

import pytest
import respx
from httpx import Response

from app.search import search, _query_ahmia_direct


@pytest.mark.asyncio
@respx.mock
async def test_ahmia_direct_query_parses_html():
    ahmia_html = """
    <html>
      <body>
        <ol class="searchResults">
          <li class="result">
            <h4><a href="http://darkexamplexyz1234.onion/forum">Tor Threat Intelligence Forum</a></h4>
            <p>Database of vulnerability disclosures and cyber security discussions on hidden services.</p>
          </li>
          <li class="result">
            <h4><a href="http://anothertor789.onion/leak">Security Disclosures</a></h4>
            <p>Public security disclosures and reports.</p>
          </li>
        </ol>
      </body>
    </html>
    """
    respx.get("https://ahmia.fi/search/?q=cybersecurity").mock(return_value=Response(200, text=ahmia_html))

    results, _ = await search(
        query="cybersecurity",
        max_results=5,
        engine="ahmia",
        use_cache=False,
    )

    assert len(results) == 2
    assert results[0].engine == "ahmia"
    assert "darkexamplexyz1234.onion" in results[0].url
    assert "Tor Threat Intelligence" in results[0].title
