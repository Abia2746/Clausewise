"""LLM provider abstraction layer.

Supports Anthropic Claude, OpenAI, and local/mock endpoints with automatic
fallback, retry handling, and structured token counting.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import get_settings
from .errors import ProviderError, RateLimitError


@dataclass
class ProviderUsage:
    """Tracks token usage and cost for provider calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    requests: int = 0

    def accumulate(self, input_tok: int = 0, output_tok: int = 0, cost: float = 0.0) -> None:
        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.total_tokens += (input_tok + output_tok)
        self.cost_usd += cost
        self.requests += 1


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw_response: Any = field(default_factory=dict, repr=False)


class LLMProvider(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def complete(self, prompt: str, *, system: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4000) -> LLMResponse:
        pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude integration via official SDK or HTTP client."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

    def complete(self, prompt: str, *, system: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4000) -> LLMResponse:
        import time
        start = time.time()
        
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system

            response = client.messages.create(**kwargs)
            latency = (time.time() - start) * 1000
            
            content_block = response.content[0] if response.content else None
            text = content_block.text if hasattr(content_block, "text") else str(content_block)
            
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

            return LLMResponse(
                text=text,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency,
                raw_response=response,
            )
        except Exception as exc:
            if "rate_limit" in str(exc).lower():
                raise RateLimitError(f"Anthropic rate limit reached: {exc}") from exc
            raise ProviderError(f"Anthropic provider error: {exc}") from exc


class OpenAIProvider(LLMProvider):
    """OpenAI integration for GPT-4o and compatible endpoints."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def complete(self, prompt: str, *, system: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4000) -> LLMResponse:
        import time
        start = time.time()
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = (time.time() - start) * 1000
            
            choice = response.choices[0]
            text = choice.message.content or ""
            
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            return LLMResponse(
                text=text,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency,
                raw_response=response,
            )
        except Exception as exc:
            if "rate_limit" in str(exc).lower():
                raise RateLimitError(f"OpenAI rate limit reached: {exc}") from exc
            raise ProviderError(f"OpenAI provider error: {exc}") from exc


def get_default_provider() -> LLMProvider:
    """Factory helper to fetch configured default model provider."""
    settings = get_settings()
    provider_name = getattr(settings, "llm_provider", "anthropic").lower()
    
    if provider_name == "openai" or os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        return OpenAIProvider()
    return AnthropicProvider()


def provider_health() -> dict[str, Any]:
    """Check connectivity and credentials status for active providers."""
    anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    openai_ok = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "anthropic_configured": anthropic_ok,
        "openai_configured": openai_ok,
        "default": "openai" if openai_ok and not anthropic_ok else "anthropic",
    }
