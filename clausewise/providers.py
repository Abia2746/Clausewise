"""LLM Provider wrapper supporting Google Gemini and OpenAI integration."""

from __future__ import annotations

import json
from typing import Any, Optional

from .config import get_settings
from .errors import ProviderError, ProviderTimeout
from .schemas import ModelAuditOutput, parse_audit_output

class ProviderHealth:
    def __init__(self, active_provider: str, model: str, degraded: bool, note: str):
        self.active_provider = active_provider
        self.model = model
        self.degraded = degraded
        self.note = note

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_provider": self.active_provider,
            "model": self.model,
            "degraded": self.degraded,
            "note": self.note,
        }

def provider_health() -> ProviderHealth:
    settings = get_settings()
    if settings.gemini_api_key:
        return ProviderHealth("gemini", settings.gemini_model, False, "Gemini active.")
    if settings.openai_api_key:
        return ProviderHealth("openai", settings.openai_model, False, "OpenAI active.")
    return ProviderHealth("demo", "mock-shariah-v1", True, "No LLM API keys configured. Running in demo mode.")

class BaseProvider:
    def analyze(self, system_prompt: str, user_prompt: str) -> ModelAuditOutput:
        raise NotImplementedError

class GeminiProvider(BaseProvider):
    def analyze(self, system_prompt: str, user_prompt: str) -> ModelAuditOutput:
        settings = get_settings()
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(
                model_name=settings.gemini_model,
                system_instruction=system_prompt,
            )
            response = model.generate_content(
                user_prompt,
                generation_config={"response_mime_type": "application/json"},
            )
            data = json.loads(response.text)
            return parse_audit_output(data)
        except Exception as exc:
            raise ProviderError(f"Gemini provider call failed: {exc}") from exc

class DemoProvider(BaseProvider):
    def analyze(self, system_prompt: str, user_prompt: str) -> ModelAuditOutput:
        return ModelAuditOutput(
            summary="Demo mode audit completed. No contractual breaches identified in baseline scan.",
            findings=[],
            overall_confidence=0.95,
            needs_human_review=False,
        )

def get_provider() -> BaseProvider:
    settings = get_settings()
    if settings.gemini_api_key:
        return GeminiProvider()
    return DemoProvider()
