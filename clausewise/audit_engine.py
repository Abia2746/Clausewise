"""The review engine.

Pipeline
--------
extract -> redact -> chunk -> provider -> validate -> enforce citations
-> merge with deterministic pre-scan -> score -> refuse-or-return

Three product rules are implemented here rather than described in a policy
document, because a rule that lives only in prose is a rule that gets bypassed
under deadline:

1. `enforce_citations` — a finding whose `standard_id` does not resolve in the
client's library is downgraded to a REFERRED item. It is shown as "for your
Shari'ah board," never as a compliance conclusion. This is what stops the
product from confidently inventing a standard number.
2. `should_refuse` — below the confidence floor, or when too much of the
document failed to process, the audit refuses and routes to the client's
board. Refusal is a feature that enterprise buyers test for.
3. `merge_prescan` — the deterministic rule pass is unioned with the model
output, so recall never depends on the model's mood. It also means the
product produces genuine findings when no model is configured.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .config import DISCLAIMER_TEXT, PROMPT_VERSION, STANDARDS_REGISTRY_VERSION, get_settings
from .entitlements import Plan, get_plan
from .errors import AuditRefused
from .extraction import Chunk, chunk_document
from .providers import LLMProvider, ProviderError, ProviderUsage
from .redaction import redact_with_vault
from .schemas import ModelAuditOutput, Modelfinding, parse_audit_output
from .standards import (
    ISSUE_TYPE_LABELS,
    SEVERITY_ORDER,
    SEVERITY_WEIGHT,
    IssueType,
    Severity,
    StandardSpec,
    active_standard_ids_for_library,
    coerce_issue_type,
    coerce_severity,
    library_entries_by_standard_id,
    prescan,
    resolve_standard,
)

_MIN_CHUNK_SUCCESS_RATIO = 0.6
_MAX_EXCERPT = 700
_EXCERPT_WHITESPACE = re.compile(r"\s+")
_OTHER_ISSUE_LABEL = ISSUE_TYPE_LABELS.get(IssueType.OTHER.value, "Requires Shari'ah board review")


# ======================================================================= prompts
SYSTEM_PROMPT = """You are a Shari'ah compliance review assistant working for an Islamic financial institution.

Your output is a FIRST-PASS REVIEW for a qualified Shari'ah reviewer. It is not a
fatwa, not a ruling, and not legal advice. A human always decides.

HOW TO WORK
1. Read the contract extract and identify clauses that conflict with the Shari'ah
standards supplied to you, or that create a Shari'ah risk needing a ruling.
2. For every finding you MUST cite the standard_id of the standard it breaches,
using ONLY ids from the SUPPLIED STANDARDS list.
3. If no supplied standard fits, set "standard_id" to null. Never invent a
standard number, never cite a standard that is not in the list, and never
guess at a paragraph reference.
4. Quote the offending language verbatim in "clause_excerpt" (maximum 400
characters). Never paraphrase the quote.
5. Write "rationale" as the reviewer's reasoning: what the clause does, and why
it conflicts with the cited requirement. Two to four sentences.
6. Write "remedial_wording" as replacement clause language the institution could
actually adopt. Be specific and conservative.
7. Set "confidence" honestly, between 0 and 1. If the extract is ambiguous, or
you are inferring missing context, keep it below 0.6 and explain why in the
rationale. Low confidence is useful; false confidence is dangerous.
8. Do not report stylistic, commercial or purely legal issues. Only Shari'ah
compliance matters. If the extract contains nothing relevant, return an empty
findings array. An empty result is a valid, correct answer.

Severity definitions
critical : the structure is likely non-compliant as drafted (Riba, improper
risk transfer, guarantee of capital or return).
high : a material Shari'ah risk that needs a ruling or a material redraft.
medium : a defect that should be corrected but does not by itself break the
structure.
advisory : drafting improvement that reduces future Shari'ah risk.

OUTPUT
Return JSON only, matching this schema exactly:
{
  "summary": "string - 2 to 4 sentences on the overall Shari'ah risk posture of this extract",
  "findings": [
    {
      "clause_ref": "string - the clause number as it appears, e.g. 2.3",
      "clause_excerpt": "string - verbatim quote, max 400 chars",
      "issue_type": "RIBA | GHARAR | MAYSIR | RISK_TRANSFER | PENALTY_ROUTING | GUARANTEE | PROFIT_GUARANTEE | ASSET_OWNERSHIP | SEQUENCING | PRICE_CERTAINTY | CURRENCY | SETOFF | PURIFICATION | TAKAFUL_SURPLUS | TERMINATION | OTHER",
      "severity": "critical | high | medium | advisory",
      "standard_id": "string from the supplied list, or null",
      "rationale": "string",
      "remedial_wording": "string",
      "confidence": 0.0
    }
  ],
  "overall_confidence": 0.0,
  "needs_human_review": true,
  "review_reason": "string or null"
}
"""


def _standards_block(entries: Iterable[StandardSpec], *, limit: int = 60) -> str:
    lines: list[str] = []
    for spec in list(entries)[:limit]:
        lines.append(
            f"- id: {spec.standard_id}\n"
            f"  title: {spec.title}\n"
            f"  requirement: {spec.requirement_summary}\n"
            f"  commonly breached by: {spec.common_breaches or 'n/a'}"
        )
    return "\n".join(lines)


def build_chunk_prompt(
    *,
    chunk: Chunk,
    document_type: str,
    standards: Iterable[StandardSpec],
    jurisdiction_label: str,
    extra_requirements: Iterable[str] = (),
    redaction_note: str = "",
) -> str:
    extras = "\n".join(f"- {item}" for item in extra_requirements) or "- none on record"
    clause_hint = ", ".join(chunk.clause_refs[:20]) or "none detected"
    return f"""DOCUMENT CONTEXT
instrument type : {document_type}
jurisdiction : {jurisdiction_label}
extract {chunk.index + 1}, characters {chunk.start}-{chunk.end}
clause numbering visible in this extract: {clause_hint}
privacy note: {redaction_note or "no personal data was present"}

SUPPLIED STANDARDS (cite only these ids)
{_standards_block(standards)}

ADDITIONAL LOCAL REQUIREMENTS
{extras}

CONTRACT EXTRACT
--- BEGIN EXTRACT ---
{chunk.text}
--- END EXTRACT ---

Review this extract and return the JSON object described in your instructions."""


# ======================================================================= outcome
@dataclass
class EngineFinding:
    clause_ref: str = ""
    clause_excerpt: str = ""
    issue_type: str = IssueType.OTHER.value
    severity: str = Severity.MEDIUM.value
    standard_id: Optional[str] = None
    standard_title: str = ""
    citation_ref: str = ""
    citation_status: str = "uncited"  # cited | uncited | unresolved
    rationale: str = ""
    remedial_wording: str = ""
    confidence: float = 0.5
    needs_human_review: bool = True
    detected_by: str = "model"

    def dedupe_key(self) -> tuple[str, str]:
        standard = (self.standard_id or "none").upper()
        clause = (self.clause_ref or "").strip().lower()
        if clause:
            return (standard, f"clause:{clause}")
        excerpt = _EXCERPT_WHITESPACE.sub(" ", (self.clause_excerpt or "")[:120]).strip().lower()
        return (standard, excerpt)


@dataclass
class AuditOutcome:
    status: str  # succeeded | refused | failed
    summary: str = ""
    findings: list[EngineFinding] = field(default_factory=list)
    risk_status: str = "Low"
    risk_score: float = 0.0
    counts: dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0
    needs_human_review: bool = True
    review_reason: str = ""
    refusal_reason: Optional[str] = None
    chunks_total: int = 0
    chunks_failed: int = 0
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    provider: str = ""
    model: str = ""
    redaction_note: str = ""
    warnings: list[str] = field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    standards_version: str = STANDARDS_REGISTRY_VERSION

    @property
    def findings_critical(self) -> int:
        return self.counts.get(Severity.CRITICAL.value, 0)

    @property
    def findings_high(self) -> int:
        return self.counts.get(Severity.HIGH.value, 0)

    @property
    def findings_medium(self) -> int:
        return self.counts.get(Severity.MEDIUM.value, 0)

    @property
    def findings_advisory(self) -> int:
        return self.counts.get(Severity.ADVISORY.value, 0)

    @property
    def findings_referred(self) -> int:
        return self.counts.get(Severity.REFERRED.value, 0)

    @property
    def findings_total(self) -> int:
        return self.findings_critical + self.findings_high + self.findings_medium + self.findings_advisory


def enforce_citations(
    findings: list[EngineFinding],
    extra_entries: Optional[dict[str, StandardSpec]] = None,
) -> list[EngineFinding]:
    for finding in findings:
        spec = resolve_standard(finding.standard_id, extra_entries)
        if spec is None:
            finding.standard_id = finding.standard_id or None
            finding.citation_status = "unresolved" if finding.standard_id else "uncited"
            finding.standard_title = ""
            finding.citation_ref = ""
            finding.severity = Severity.REFERRED.value
            finding.needs_human_review = True
            note = (
                f"Cited standard '{finding.standard_id}' is not in the active library."
                if finding.standard_id
                else "No standard citation was provided."
            )
            finding.rationale = f"{finding.rationale} [{note} Referred to the Shari'ah board.]".strip()
        else:
            finding.standard_id = spec.standard_id
            finding.standard_title = spec.title
            finding.citation_ref = spec.citation_ref
            finding.citation_status = "cited"
    return findings


def merge_prescan(findings: list[EngineFinding], hits: list[Any]) -> list[EngineFinding]:
    existing = {f.dedupe_key() for f in findings}
    for hit in hits:
        candidate = EngineFinding(
            clause_ref=hit.clause_ref,
            clause_excerpt=hit.excerpt[:_MAX_EXCERPT],
            issue_type=hit.issue_type.value,
            severity=hit.severity.value,
            standard_id=hit.standard_id,
            rationale=(
                f"Deterministic rule match on the pattern \"{hit.matched_pattern}\". "
                f"{ISSUE_TYPE_LABELS.get(hit.issue_type.value, _OTHER_ISSUE_LABEL)}. "
                "Flagged by the rule engine, so it is not dependent on model recall."
            ),
            remedial_wording=_prescan_remedy(hit.issue_type.value),
            confidence=0.7,
            needs_human_review=True,
            detected_by="rule",
        )
        key = candidate.dedupe_key()
        if key in existing:
            continue
        existing.add(key)
        findings.append(candidate)
    return findings


def _prescan_remedy(issue_type: str) -> str:
    from .providers import _REMEDIES

    return _REMEDIES.get(issue_type, _REMEDIES["OTHER"])


def _rank(finding: EngineFinding) -> tuple[int, float, int]:
    return (
        SEVERITY_ORDER[finding.severity],
        -finding.confidence,
        0 if finding.citation_status == "cited" else 1,
    )


def dedupe_findings(findings: list[EngineFinding]) -> list[EngineFinding]:
    best: dict[tuple[str, str], EngineFinding] = {}
    merged_counts: dict[tuple[str, str], int] = {}

    for finding in findings:
        key = finding.dedupe_key()
        merged_counts[key] = merged_counts.get(key, 0) + 1
        current = best.get(key)
        if current is None or _rank(finding) < _rank(current):
            best[key] = finding

    result: list[EngineFinding] = []
    for key, finding in best.items():
        collapsed = merged_counts.get(key, 1)
        if collapsed > 1:
            finding.rationale = (
                f"{finding.rationale} [{collapsed} rule/model observations collapsed into this "
                "single finding for this clause.]"
            ).strip()
        result.append(finding)

    result.sort(key=lambda f: (SEVERITY_ORDER[f.severity], -f.confidence, f.clause_ref or "zzz"))
    return result


def score_findings(findings: list[EngineFinding]) -> tuple[str, float, dict[str, int]]:
    counts = {severity.value: 0 for severity in Severity}
    score = 0.0
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
        score += SEVERITY_WEIGHT.get(finding.severity, 0.0)

    score = min(round(score, 1), 100.0)

    if counts.get(Severity.CRITICAL.value, 0) > 0 or score >= 60.0:
        status = "High"
    elif score >= 22.0:
        status = "Medium"
    else:
        status = "Low"
    return status, score, counts


def should_refuse(
    *,
    confidence: float,
    chunks_total: int,
    chunks_failed: int,
    findings: list[EngineFinding],
    truncated: bool = False,
) -> tuple[bool, Optional[str], str]:
    settings = get_settings()

    if chunks_total == 0:
        return True, "no_content", "No analysable content was found in this document."

    if chunks_failed / max(chunks_total, 1) > (1 - _MIN_CHUNK_SUCCESS_RATIO):
        return (
            True,
            "extraction_incomplete",
            f"Only {chunks_total - chunks_failed} of {chunks_total} sections could be analysed.",
        )

    if truncated:
        return (
            True,
            "truncated_document",
            "The document exceeded the configured size limit and was truncated.",
        )

    if confidence < settings.llm_min_confidence:
        return (
            True,
            "low_confidence",
            f"The engine's confidence ({confidence:.0%}) was below the threshold ({settings.llm_min_confidence:.0%}).",
        )

    critical_unresolved = [
        f for f in findings if f.citation_status == "unresolved" and f.severity == Severity.CRITICAL.value
    ]
    if len(critical_unresolved) >= 3:
        return (
            True,
            "citation_unresolved",
            "Several critical items could not be matched to a standard in your active library.",
        )

    return False, None, ""


def run_audit(
    text: str,
    *,
    provider: LLMProvider,
    document_type: str = "general",
    library_id: Optional[str] = None,
    jurisdiction: str = "GLOBAL",
    truncated: bool = False,
) -> AuditOutcome:
    """Execute standard pipeline."""
    from .redaction import redact_text
    from .standards import load_library_entries

    settings = get_settings()
    redaction = redact_text(text) if settings.redaction_enabled else None
    working_text = redaction.text if redaction else text

    entries = load_library_entries(library_id)
    chunks = chunk_document(working_text, target_chars=settings.chunk_target_chars)

    all_raw_findings: list[EngineFinding] = []
    total_tokens_in = 0
    total_tokens_out = 0
    chunks_failed = 0

    for chunk in chunks:
        prompt = build_chunk_prompt(
            chunk=chunk,
            document_type=document_type,
            standards=entries,
            jurisdiction_label=jurisdiction,
            redaction_note=f"{redaction.redactions_count} items masked" if redaction else "",
        )
        try:
            model_out: ModelAuditOutput = provider.analyze(SYSTEM_PROMPT, prompt)
            for raw in model_out.findings:
                all_raw_findings.append(
                    EngineFinding(
                        clause_ref=raw.clause_ref,
                        clause_excerpt=raw.clause_excerpt,
                        issue_type=raw.issue_type,
                        severity=raw.severity,
                        standard_id=raw.standard_id,
                        rationale=raw.rationale,
                        remedial_wording=raw.remedial_wording,
                        confidence=raw.confidence,
                        detected_by="model",
                    )
                )
        except Exception:
            chunks_failed += 1

    prescan_hits = prescan(working_text, document_type=document_type)
    merged = merge_prescan(all_raw_findings, prescan_hits)
    cited = enforce_citations(merged, {e.standard_id: e for e in entries})
    deduped = dedupe_findings(cited)

    risk_status, risk_score, counts = score_findings(deduped)
    avg_conf = (
        round(sum(f.confidence for f in deduped) / len(deduped), 2) if deduped else 0.95
    )

    refused, refusal_reason, refusal_msg = should_refuse(
        confidence=avg_conf,
        chunks_total=len(chunks),
        chunks_failed=chunks_failed,
        findings=deduped,
        truncated=truncated,
    )

    return AuditOutcome(
        status="refused" if refused else "succeeded",
        summary=refusal_msg if refused else "Contract review completed.",
        findings=[] if refused else deduped,
        risk_status="High" if refused else risk_status,
        risk_score=100.0 if refused else risk_score,
        counts=counts,
        confidence=avg_conf,
        refusal_reason=refusal_reason,
        chunks_total=len(chunks),
        chunks_failed=chunks_failed,
        provider=provider.name,
        model=settings.active_model,
        redaction_note=f"{redaction.redactions_count} items masked" if redaction else "",
    )
