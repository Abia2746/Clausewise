"""Validation schemas for model output.

The model is treated as an untrusted input source. Everything it returns is
validated, coerced into the closed taxonomy, and citation-checked. A schema
violation is a first-class domain event, not an exception to swallow: the engine
either repairs once or refuses the audit.

`parse_audit_output` is deliberately tolerant about *how* the response arrives.
Providers differ: one returns raw text with Markdown fences and conversational
padding, another returns an already-decoded mapping. Both land on the same
validated shape here, so `audit_engine` never has to care which provider spoke.

Parsing raw text is delegated to `providers.extract_json_object`, which is the
single tested implementation of the fence/prose tolerance rules. A bare JSON
array is also accepted, because some models answer with a list of findings and
no envelope.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_FINDINGS_PER_CHUNK = 40
MAX_EXCERPT_CHARS = 800


class FindingSchema(BaseModel):
    """One flagged clause, before citation enforcement and scoring.

    Every field is total: a missing or malformed value is coerced, never raised.
    A model that omits a severity must not be able to crash a paid review.
    """

    clause_ref: str = ""
    clause_excerpt: str = ""
    issue_type: str = "OTHER"
    severity: str = "medium"
    standard_id: Optional[str] = None
    rationale: str = ""
    remedial_wording: str = ""
    confidence: float = 0.5

    model_config = {"extra": "ignore"}

    @field_validator("clause_ref", "issue_type", "severity", mode="before")
    @classmethod
    def _stringify(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("clause_excerpt", mode="before")
    @classmethod
    def _trim_excerpt(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()[:MAX_EXCERPT_CHARS]

    @field_validator("rationale", "remedial_wording", mode="before")
    @classmethod
    def _clean_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        if number > 1.0:  # some models answer 0-100
            number = number / 100.0
        return max(0.0, min(1.0, number))

    @field_validator("standard_id", mode="before")
    @classmethod
    def _clean_standard(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


# Retained so `audit_engine` (and anything else written against the original
# name) keeps importing. `FindingSchema` is the canonical spelling.
Modelfinding = FindingSchema


class ModelAuditOutput(BaseModel):
    """One chunk's worth of model output, validated."""

    summary: str = ""
    findings: list[FindingSchema] = Field(default_factory=list)
    overall_confidence: float = 0.0
    needs_human_review: bool = True
    review_reason: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("findings", mode="before")
    @classmethod
    def _cap_findings(cls, value: Any) -> list:
        if not value:
            return []
        if not isinstance(value, list):
            return []
        return value[:MAX_FINDINGS_PER_CHUNK]

    @field_validator("overall_confidence", mode="before")
    @classmethod
    def _coerce_overall(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        if number > 1.0:
            number = number / 100.0
        return max(0.0, min(1.0, number))

    @field_validator("needs_human_review", mode="before")
    @classmethod
    def _coerce_bool(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        return str(value).strip().lower() not in {"false", "0", "no", "none"}

    @model_validator(mode="after")
    def _derive_confidence(self) -> "ModelAuditOutput":
        # If the model did not state an overall confidence, infer it from the
        # findings rather than defaulting to a number that looks authoritative.
        if self.overall_confidence <= 0.0 and self.findings:
            self.overall_confidence = round(
                sum(f.confidence for f in self.findings) / len(self.findings), 3
            )
        return self


def _looks_like_array(text: str) -> bool:
    """True when the first JSON structure in the text is a list, not an object."""
    first_bracket = text.find("[")
    if first_bracket == -1:
        return False
    first_brace = text.find("{")
    return first_brace == -1 or first_bracket < first_brace


def _decode_raw_text(raw_text: str) -> Any:
    """Clean a raw model response and decode it into a JSON value.

    Delegates to the provider layer's extractor, which handles ```json fences and
    prose padding and is covered by its own tests.

    Arrays are resolved *before* that delegation, because the extractor slices
    the first `{...}` out of an array and would silently discard the surrounding
    list — turning a bare list of findings into a single unrecognised object.
    """
    from .providers import extract_json_object

    text = raw_text if isinstance(raw_text, str) else str(raw_text)
    stripped = text.strip()

    if _looks_like_array(stripped):
        first_bracket, last_bracket = stripped.find("["), stripped.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            try:
                decoded = json.loads(stripped[first_bracket : last_bracket + 1])
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                return {"findings": decoded}

    return extract_json_object(text)


def parse_audit_output(payload: "str | dict[str, Any] | list[Any]") -> ModelAuditOutput:
    """Validate a provider response into the domain shape.

    Accepts either raw model text (fences, prose padding and all) or an
    already-decoded mapping. Text is cleaned and decoded first, via
    `_decode_raw_text`; a response containing no JSON object at all raises
    `InvalidModelOutput` so the caller can treat that section as unreadable
    rather than silently analyse nothing.

    Accepts a few common envelope shapes because models drift: a bare list of
    findings, or an object nested under 'result' / 'audit'.
    """
    if isinstance(payload, str):
        payload = _decode_raw_text(payload)

    if isinstance(payload, list):
        payload = {"findings": payload}

    if not isinstance(payload, dict):
        return ModelAuditOutput()

    if "findings" not in payload and isinstance(payload.get("result"), dict):
        payload = payload["result"]
    if "findings" not in payload and isinstance(payload.get("audit"), dict):
        payload = payload["audit"]
    if "findings" not in payload:
        for key in ("issues", "observations", "risks", "items"):
            if isinstance(payload.get(key), list):
                payload = {**payload, "findings": payload[key]}
                break

    return ModelAuditOutput.model_validate(payload)
