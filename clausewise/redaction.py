"""PII redaction — the feature that unblocks the first bank conversation.

Every enterprise buyer asks the same question first: "can contract text leave
our environment?" The honest answer is "only what the review needs, with
personal data stripped." This module is that answer, and it is applied before
any provider call.

Design constraints:
- **Reversible within the process only.** The mapping never leaves memory, so a
leaked prompt cannot be re-identified from stored state.
- **Deterministic.** Same input -> same placeholders, so caching by content hash
still works and two runs of the same document are comparable.
- **Conservative.** When unsure, redact. A redaction costs a little context; a
leaked IBAN costs the account.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Ordered: longer/more specific patterns first so they win.
#
# FLAGS MATTER. Patterns that describe uppercase identifiers (IBAN, SWIFT,
# CRYPTO) must NOT be case-insensitive: with re.IGNORECASE, the SWIFT pattern
# matches any 8-11 character lowercase English word, which silently redacts
# "interest", "invoice" and "examplebank" out of the contract. That destroys the
# Shari'ah analysis and swallows the email address before the EMAIL pattern can
# see it. Case-insensitivity is granted per pattern, deliberately.
_I = re.IGNORECASE

PATTERNS: list[tuple[str, str, int]] = [
    ("IBAN", r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", 0),
    ("SWIFT", r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", 0),
    ("EMAIL", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", _I),
    ("PHONE", r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}", 0),
    ("NATIONAL_ID", r"\b\d{3}-\d{2}-\d{4}\b|\b[A-Z]{1,2}\d{6,9}[A-Z]?\b", 0),
    ("CRYPTO", r"\b(?:0x[a-fA-F0-9]{40}|bc1[a-z0-9]{25,62})\b", 0),
    ("CARD", r"\b(?:\d[ -]?){13,19}\b", 0),
    ("ACCOUNT_NO", r"\b(?:account|a/c|acct)\s*(?:no\.?|number|#)?\s*[:\-]?\s*\d{6,20}\b", _I),
    ("REG_NO", r"\b(?:company|registration|commercial)\s*(?:no\.?|number|#)\s*[:\-]?\s*[A-Z0-9\-]{5,15}\b", _I),
]

@dataclass
class RedactionResult:
    text: str
    redactions_count: int
    categories: dict[str, int] = field(default_factory=dict)
    vault: dict[str, str] = field(default_factory=dict)

def redact_text(text: str) -> RedactionResult:
    if not text:
        return RedactionResult(text="", redactions_count=0)

    vault: dict[str, str] = {}
    reverse_vault: dict[str, str] = {}
    counts: dict[str, int] = {}
    total = 0
    cleaned = text

    for cat, pattern, flags in PATTERNS:
        matches = list(re.finditer(pattern, cleaned, flags=flags))
        for match in reversed(matches):
            val = match.group(0)
            if val in reverse_vault:
                placeholder = reverse_vault[val]
            else:
                counts[cat] = counts.get(cat, 0) + 1
                placeholder = f"[{cat}_{counts[cat]}]"
                reverse_vault[val] = placeholder
                vault[placeholder] = val
                total += 1
            start, end = match.span()
            cleaned = cleaned[:start] + placeholder + cleaned[end:]

    return RedactionResult(
        text=cleaned,
        redactions_count=total,
        categories=counts,
        vault=vault,
    )

def restore_text(text: str, vault: dict[str, str]) -> str:
    if not text or not vault:
        return text
    restored = text
    for placeholder, original in vault.items():
        restored = restored.replace(placeholder, original)
    return restored
