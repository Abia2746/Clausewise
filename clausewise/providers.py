"""Model providers behind one interface.

Three implementations, one contract:

* `GeminiProvider`            — the default; Google Gemini via google-genai.
* `OpenAICompatibleProvider`  — anything exposing /v1/chat/completions: Azure
                                OpenAI, Bedrock proxies, vLLM, Ollama. This is
                                the in-region and on-prem path, and the answer to
                                "what happens if we can't send data to Google?"
* `HeuristicProvider`         — no model call at all. Runs the deterministic
                                rule registry. Powers demo mode, offline sales
                                demos and the entire test suite.

The interface is `complete_json(system, user, schema_hint) -> ProviderResponse`.
Adding a fourth provider means implementing one method.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .config import get_settings
from .errors import InvalidModelOutput, ProviderError, ProviderTimeout


@dataclass
class ProviderUsage:
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    latency_ms: int = 0
    calls: int = 0


@dataclass
class ProviderResponse:
    data: dict[str, Any]
    raw_text: str = ""
    usage: ProviderUsage = field(default_factory=ProviderUsage)


class LLMProvider(Protocol):
    name: str

    def complete_json(self, *, system: str, user: str, schema_hint: str) -> ProviderResponse: ...


# ------------------------------------------------------------------- utilities
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_EXTRACT_BLOCK = re.compile(
    r"---\s*BEGIN EXTRACT\s*---(.*?)---\s*END EXTRACT\s*---", re.DOTALL | re.IGNORECASE
)


def contract_text_from_prompt(prompt: str) -> str:
    """Recover the contract extract from a composed chunk prompt.

    The heuristic provider must scan the *document*, never the whole prompt: the
    prompt embeds the standards catalogue, whose own wording ("default interest
    at X% per annum", "compounding") would otherwise match the rule patterns and
    report findings against the standards list itself.
    """
    if not prompt:
        return ""
    match = _EXTRACT_BLOCK.search(prompt)
    if match:
        return match.group(1).strip()
    return prompt


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse JSON out of a model response, tolerating fences and prose padding."""
    if not text or not text.strip():
        raise InvalidModelOutput("The review engine returned an empty response.")

    candidates: list[str] = []
    stripped = text.strip()
    candidates.append(stripped)

    for match in _JSON_FENCE.finditer(text):
        candidates.append(match.group(1).strip())

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(stripped[first_brace : last_brace + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    raise InvalidModelOutput("The review engine returned a response that was not valid JSON.")


def _backoff_seconds(attempt: int) -> float:
    return min(2 ** attempt * 0.8, 12.0)


def _is_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    retryable_markers = (
        "timeout", "timed out", "deadline", "429", "rate limit", "resource_exhausted",
        "500", "502", "503", "504", "unavailable", "overloaded", "internal error", "connection",
    )
    return any(marker in message for marker in retryable_markers)


# ====================================================================== Gemini
class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.llm_model_override or settings.gemini_model
        self.settings = settings
        if not self.api_key:
            raise ProviderError(
                "No model API key is configured for this deployment. Ask your administrator to set "
                "GEMINI_API_KEY, or use demo mode (LLM_PROVIDER=heuristic)."
            )
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise ProviderError("The google-genai package is not installed in this deployment.") from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def complete_json(self, *, system: str, user: str, schema_hint: str) -> ProviderResponse:
        from google.genai import types

        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=self.settings.llm_temperature,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

        started = time.perf_counter()
        last_error: Optional[Exception] = None

        for attempt in range(self.settings.llm_max_retries):
            try:
                response = client.models.generate_content(model=self.model, contents=user, config=config)
                text = getattr(response, "text", "") or ""
                usage_meta = getattr(response, "usage_metadata", None)
                tokens_in = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                tokens_out = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                data = extract_json_object(text)
                return ProviderResponse(
                    data=data,
                    raw_text=text,
                    usage=ProviderUsage(
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        model=self.model,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        calls=1,
                    ),
                )
            except InvalidModelOutput:
                raise
            except Exception as exc:
                last_error = exc
                if not _is_retryable(exc) or attempt == self.settings.llm_max_retries - 1:
                    break
                time.sleep(_backoff_seconds(attempt))

        message = str(last_error) if last_error else "unknown error"
        if "timeout" in message.lower() or "deadline" in message.lower():
            raise ProviderTimeout(f"The review engine timed out after {self.settings.llm_timeout_seconds}s.")
        raise ProviderError(f"The review engine could not complete the request: {message}")


# ========================================================= OpenAI-compatible API
class OpenAICompatibleProvider:
    """Any Chat Completions endpoint. Used for in-region and on-prem deployments."""

    name = "openai_compatible"

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.llm_model_override or settings.openai_model or "gpt-4o-mini"
        self.settings = settings
        if not self.base_url:
            raise ProviderError("OPENAI_BASE_URL is not configured for this deployment.")

    def complete_json(self, *, system: str, user: str, schema_hint: str) -> ProviderResponse:
        import httpx

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        started = time.perf_counter()
        last_error: Optional[Exception] = None

        for attempt in range(self.settings.llm_max_retries):
            try:
                with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                    response = client.post(url, json=payload, headers=headers)
                if response.status_code >= 400:
                    raise ProviderError(f"Upstream model returned HTTP {response.status_code}.")
                body = response.json()
                text = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {}) or {}
                return ProviderResponse(
                    data=extract_json_object(text),
                    raw_text=text,
                    usage=ProviderUsage(
                        tokens_in=int(usage.get("prompt_tokens", 0) or 0),
                        tokens_out=int(usage.get("completion_tokens", 0) or 0),
                        model=self.model,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        calls=1,
                    ),
                )
            except InvalidModelOutput:
                raise
            except Exception as exc:
                last_error = exc
                if not _is_retryable(exc) or attempt == self.settings.llm_max_retries - 1:
                    break
                time.sleep(_backoff_seconds(attempt))

        raise ProviderError(f"Upstream model call failed: {last_error}")


# =================================================================== heuristic
class HeuristicProvider:
    """Deterministic provider. No network, no key, no cost.

    This exists for three reasons, all commercial rather than technical:
      1. The free tier and every sales demo work with zero model spend.
      2. The test suite can assert on real behaviour instead of mocks.
      3. A prospect can see genuine, citable findings before you ever spend
         money on their document.
    """

    name = "heuristic"

    def __init__(self, model: str = "heuristic") -> None:
        self.model = model
        self.settings = get_settings()

    def complete_json(self, *, system: str, user: str, schema_hint: str) -> ProviderResponse:
        started = time.perf_counter()
        from .standards import ISSUE_TYPE_LABELS, prescan

        document = contract_text_from_prompt(user)
        hits = prescan(document)
        findings: list[dict[str, Any]] = []
        for hit in hits:
            findings.append(
                {
                    "clause_ref": hit.clause_ref,
                    "clause_excerpt": hit.excerpt[:600],
                    "issue_type": hit.issue_type.value,
                    "severity": hit.severity.value,
                    "standard_id": hit.standard_id,
                    "rationale": (
                        f"Rule-matched language: \"{hit.matched_pattern}\". "
                        f"{ISSUE_TYPE_LABELS.get(hit.issue_type.value, 'Requires Shari\'ah board review')}."
                    ),
                    "remedial_wording": _generic_remedy(hit.issue_type.value),
                    "confidence": 0.62,
                }
            )

        # Deliberately report raw observations, not a final count: several patterns
        # usually match the same clause, so this number is larger than the
        # consolidated finding total. Saying so here stops the two figures from
        # looking like a contradiction in the report.
        summary = (
            f"Deterministic rule pass returned {len(findings)} raw observation(s) in this section. "
            "Overlapping observations are collapsed to one finding per clause and standard in the "
            "consolidated result."
            if findings
            else "Deterministic rule pass returned no observation for this section."
        )

        data = {
            "summary": summary,
            "findings": findings,
            "overall_confidence": 0.6 if findings else 0.75,
            "needs_human_review": True,
            "review_reason": "Demo/rule-based pass — always validated by a qualified reviewer.",
        }
        return ProviderResponse(
            data=data,
            raw_text=json.dumps(data),
            usage=ProviderUsage(
                tokens_in=len(user) // 4,
                tokens_out=len(json.dumps(data)) // 4,
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                calls=0,  # no billable model call was made
            ),
        )


_REMEDIES: dict[str, str] = {
    "RIBA": (
        "Replace the interest-based charge with a fixed, disclosed mark-up on a known cost, or an "
        "agreed profit share proportional to capital contributed."
    ),
    "PENALTY_ROUTING": (
        "The customer undertakes to donate [X]% of the overdue amount to a charity nominated by the "
        "institution. The amount is recognised as a payable to charitable causes, not as income of "
        "the institution, and is applied without compounding."
    ),
    "RISK_TRANSFER": (
        "Ownership of and risk in the asset shall remain with the institution until the Murabahah "
        "sale contract for that asset is executed by both parties, after which risk passes to the "
        "customer in accordance with the sale."
    ),
    "GUARANTEE": (
        "Remove any undertaking to guarantee principal, capital or a minimum return. Where a "
        "third-party guarantee of a debt is required, state it as a separate, fee-based guarantee "
        "contract in accordance with the relevant standard."
    ),
    "PROFIT_GUARANTEE": (
        "Express the return as a share of actual realised profit, stated as a ratio, with losses "
        "borne in proportion to capital contributed. Delete references to a fixed or guaranteed rate."
    ),
    "ASSET_OWNERSHIP": (
        "State that major maintenance, insurance and ownership-related liabilities rest with the "
        "lessor, and move any transfer of ownership into a separate sale or gift undertaking to be "
        "executed at the end of the term."
    ),
    "GHARAR": (
        "Specify the asset, price, delivery date and payment mechanics precisely. Replace "
        "'to be determined' and 'as agreed' with ascertainable terms, and attach the specification "
        "as a schedule."
    ),
    "SEQUENCING": (
        "Sequence the contracts explicitly: the acquisition is completed before the sale contract is "
        "executed, and the documents record each step separately."
    ),
    "CURRENCY": (
        "Execute the exchange of currencies on a spot basis with full possession before the parties "
        "separate, or restructure so that a single currency is used throughout."
    ),
    "SETOFF": (
        "Restrict set-off to genuine mutual monetary debts and exclude any netting that would "
        "discount a receivable or convert a sale into an exchange of money for money."
    ),
    "PURIFICATION": (
        "Add a mechanism identifying any non-compliant income received, and route it to a charitable "
        "purpose under the supervision of the Shari'ah board."
    ),
    "TAKAFUL_SURPLUS": (
        "State that any surplus is distributed to participants or to charitable causes in accordance "
        "with the participants' fund arrangements, and is not retained as operator income."
    ),
    "PRICE_CERTAINTY": (
        "State the cost price, the agreed mark-up and the resulting sale price as fixed ascertainable "
        "amounts, and confirm that neither changes after execution."
    ),
    "MAYSIR": (
        "Remove speculative or wagering mechanics and replace them with a definite commercial "
        "exchange of an identified asset, usufruct or service."
    ),
    "TERMINATION": (
        "Align default and termination mechanics with the applicable standard, including the treatment "
        "of any outstanding instalments and the routing of penalties to charity."
    ),
    "OTHER": "Refer this clause to the Shari'ah board for a determination before execution.",
}


def _generic_remedy(issue_type: str) -> str:
    return _REMEDIES.get(issue_type, _REMEDIES["OTHER"])


# ===================================================================== factory
def get_provider(name: Optional[str] = None) -> LLMProvider:
    settings = get_settings()
    key = (name or settings.llm_provider or "gemini").strip().lower()

    def _fallback(reason: str) -> LLMProvider:
        # Degrade to the deterministic engine rather than showing the user a
        # blank screen. A degraded review is a demo; an error page is a lost deal.
        return HeuristicProvider()

    if key == "gemini":
        try:
            return GeminiProvider()
        except ProviderError:
            return _fallback("no gemini key")
    if key in {"openai_compatible", "openai", "azure", "vllm", "ollama"}:
        try:
            return OpenAICompatibleProvider()
        except ProviderError:
            return _fallback("no openai-compatible endpoint")
    if key == "heuristic":
        return HeuristicProvider()
    return HeuristicProvider()


def provider_health() -> dict[str, Any]:
    """Cheap status probe for the admin page and the /health endpoint."""
    settings = get_settings()
    provider = get_provider()
    return {
        "configured_provider": settings.llm_provider,
        "active_provider": provider.name,
        "model": settings.active_model,
        "live_model_available": provider.name != "heuristic",
        "degraded": provider.name == "heuristic" and settings.llm_provider != "heuristic",
        "note": (
            "Running the deterministic rule engine. Findings are real but narrower than a live model pass."
            if provider.name == "heuristic"
            else "Live model configured."
        ),
    }
