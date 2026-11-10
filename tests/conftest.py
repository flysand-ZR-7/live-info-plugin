"""
Pytest configuration and shared fixtures.
"""

import os
import pytest
from fastapi.testclient import TestClient

# Set testing environment variables before importing the app
os.environ["SEARXNG_URL"] = "http://localhost:8080"
os.environ["LLM_PROVIDER"] = "anthropic"
os.environ["LLM_API_KEY"] = "test-mock-key"
os.environ["LLM_MODEL"] = "claude-3-5-sonnet-20241022"
os.environ["CACHE_TTL_SECONDS"] = "0"  # Disable caching in tests

from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as test_client:
        yield test_client
