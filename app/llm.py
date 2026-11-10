"""
LLM abstraction provider.
Exposes a single async function: complete(system: str, user: str) -> str.
Supports Anthropic, OpenAI, and any OpenAI-compatible open-source model endpoint
(vLLM, Ollama, Groq, OpenRouter, LM Studio, etc.) configured via environment variables.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Provider configuration read from environment
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip() or None

# Set sensible model defaults if omitted
if not LLM_MODEL:
    if LLM_PROVIDER == "anthropic":
        LLM_MODEL = "claude-3-5-sonnet-20241022"
    elif LLM_PROVIDER in ("openai", "openai-compatible"):
        LLM_MODEL = "gpt-4o-mini"
    else:
        LLM_MODEL = "default"

_anthropic_client = None
_openai_client = None


def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic
            _anthropic_client = anthropic.AsyncAnthropic(api_key=LLM_API_KEY)
        except Exception as exc:
            logger.error("Failed to initialize Anthropic client: %s", exc)
            raise RuntimeError(f"Anthropic initialization failed: {exc}")
    return _anthropic_client


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            import openai
            # apiKey can be empty or a dummy string for local Ollama/vLLM instances
            api_key = LLM_API_KEY or "not-needed"
            _openai_client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=LLM_BASE_URL,
            )
        except Exception as exc:
            logger.error("Failed to initialize OpenAI/OpenAI-compatible client: %s", exc)
            raise RuntimeError(f"OpenAI-compatible client initialization failed: {exc}")
    return _openai_client


async def complete(system: str, user: str, max_tokens: int = 4096, temperature: float = 0.2) -> str:
    """
    Executes a chat completion call with the configured LLM provider.

    :param system: System prompt setting role, instructions, and safety rules.
    :param user: User prompt containing the task and data.
    :param max_tokens: Maximum tokens in response.
    :param temperature: Generation temperature (low default for factual consistency).
    :return: Generated string completion.
    """
    provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower()
    model = os.getenv("LLM_MODEL", LLM_MODEL).strip()

    logger.debug("Dispatching completion to provider '%s' with model '%s'", provider, model)

    if provider == "anthropic":
        client = get_anthropic_client()
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Extract text from Anthropic content blocks
        text_parts = [
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ]
        return "".join(text_parts).strip()

    elif provider in ("openai", "openai-compatible", "ollama", "vllm"):
        client = get_openai_client()
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Supported: 'anthropic', 'openai', 'openai-compatible'."
        )
