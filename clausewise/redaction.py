"""PII redaction — the feature that unblocks the first bank conversation.

Every enterprise buyer asks the same question first: "can contract text leave
our environment?" The honest answer is "only what the review needs, with
personal data stripped." This module is that answer, and it is applied before
any provider call.

Design constraints:
* **Reversible within the process only.** The mapping never leaves memory, so a
  leaked prompt cannot be re-identified from stored state.
* **Deterministic.** Same input -> same placeholders, so caching by content hash
  still works and two runs of the same document are comparable.
* **Conservative.** When unsure, redact. A redaction costs a little context; a
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
    ("REG_NO", r"\b(?:company|registration|commercial)\s*(?:no\.?|number|#)\s*[:\-]?\s*[\w\-/]{4,20}\b", _I),
]

_COMPILED: list[tuple[str, re.Pattern]] = [
    (name, re.compile(rx, flags)) for name, rx, flags in PATTERNS
]

# Deliberately NOT redacted: amounts, dates, clause numbers, rates and standard
# references — the Shari'ah analysis depends on them, and they are not personal
# data. Over-redaction is as damaging as under-redaction here.

@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def applied(self) -> bool:
        return self.total > 0

    def summary(self) -> str:
        if not self.applied:
            return "No personal data detected."
        parts = [f"{count} {name.lower().replace('_', ' ')}" for name, count in sorted(self.counts.items())]
        return "Redacted " + ", ".join(parts) + " before analysis."

class _Vault:
    """Process-local, per-redaction placeholder vault. Never persisted."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def placeholder(self, kind: str, original: str) -> str:
        key = f"{kind}:{original}"
        if key in self._map:
            return self._map[key]
        self._counters[kind] = self._counters.get(kind, 0) + 1
        token = f"[{kind}_{self._counters[kind]}]"
        self._map[key] = token
        return token

    def restore(self, text: str) -> str:
        out = text
        for key, token in self._map.items():
            kind, original = key.split(":", 1)
            out = out.replace(token, original)
        return out

    def __len__(self) -> int:
        return len(self._map)

def redact(text: str) -> RedactionResult:
    if not text:
        return RedactionResult(text="", counts={})

    vault = _Vault()
    counts: dict[str, int] = {}
    working = text

    for name, pattern in _COMPILED:
        def _sub(match: re.Match, _name: str = name) -> str:
            counts[_name] = counts.get(_name, 0) + 1
            return vault.placeholder(_name, match.group(0))

        working = pattern.sub(_sub, working)

    return RedactionResult(text=working, counts=counts)

def redact_with_vault(text: str) -> tuple[RedactionResult, _Vault]:
    """Same as `redact` but returns the vault, for restoring model output.

    The engine redacts before the model call and restores the original values in
    the returned findings, so a consultant sees real counterparty names while
    the provider never did.
    """
    if not text:
        return RedactionResult(text="", counts={}), _Vault()

    vault = _Vault()
    counts: dict[str, int] = {}
    working = text
    for name, pattern in _COMPILED:
        def _sub(match: re.Match, _name: str = name) -> str:
            counts[_name] = counts.get(_name, 0) + 1
            return vault.placeholder(_name, match.group(0))

        working = pattern.sub(_sub, working)

    return RedactionResult(text=working, counts=counts), vault
