"""Shari'ah standards registry, issue taxonomy and the deterministic pre-scan.

WHY THIS MODULE EXISTS
----------------------
A generic LLM can say something plausible about any contract. What makes this
defensible is that every finding must resolve to an entry in a registry the
client can inspect. `resolve_standard()` is therefore a gate, not a lookup:
if it returns None, the finding is downgraded to a referral item and is never
presented as a compliance conclusion.

COPYRIGHT AND ACCURACY — READ BEFORE SHIPPING
---------------------------------------------
- `requirement_summary` fields are OUR OWN paraphrases for navigation. Do not
paste AAOIFI standard text into this file. AAOIFI standards are a licensed,
copyrighted product; the client's own copy is authoritative.
- Every entry carries `verify_status`. Entries marked `confirm_before_use`
have an unconfirmed number or scope and are flagged as such in the report
appendix. Validate the whole registry against your licensed copy of the
standards before a client sees it, then flip the flag to `verified_title`.

ISSUE TAXONOMY
--------------
The taxonomy is closed. A model that invents a new category gets it coerced to
`OTHER`, which forces human review — which is the safe failure mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    ADVISORY = "advisory"
    REFERRED = "referred"  # could not be cited -> for the board, not a finding


SEVERITY_ORDER: dict[str, int] = {
    Severity.CRITICAL.value: 0,
    Severity.HIGH.value: 1,
    Severity.MEDIUM.value: 2,
    Severity.ADVISORY.value: 3,
    Severity.REFERRED.value: 4,
}

#: Deterministic risk weights used to compute an audit's numeric score.
SEVERITY_WEIGHT: dict[str, float] = {
    Severity.CRITICAL.value: 40.0,
    Severity.HIGH.value: 18.0,
    Severity.MEDIUM.value: 7.0,
    Severity.ADVISORY.value: 2.0,
    Severity.REFERRED.value: 1.0,
}


class IssueType(str, Enum):
    RIBA = "RIBA"
    GHARAR = "GHARAR"
    MAYSIR = "MAYSIR"
    RISK_TRANSFER = "RISK_TRANSFER"
    PENALTY_ROUTING = "PENALTY_ROUTING"
    GUARANTEE = "GUARANTEE"
    PROFIT_GUARANTEE = "PROFIT_GUARANTEE"
    ASSET_OWNERSHIP = "ASSET_OWNERSHIP"
    SEQUENCING = "SEQUENCING"
    PRICE_CERTAINTY = "PRICE_CERTAINTY"
    CURRENCY = "CURRENCY"
    SETOFF = "SETOFF"
    PURIFICATION = "PURIFICATION"
    TAKAFUL_SURPLUS = "TAKAFUL_SURPLUS"
    TERMINATION = "TERMINATION"
    OTHER = "OTHER"


ISSUE_TYPE_LABELS: dict[str, str] = {
    "RIBA": "Riba / interest-equivalent return",
    "GHARAR": "Gharar / excessive uncertainty",
    "MAYSIR": "Maysir / speculative element",
    "RISK_TRANSFER": "Improper risk transfer (Dhaman)",
    "PENALTY_ROUTING": "Late-payment penalty treatment",
    "GUARANTEE": "Guarantee of capital or return",
    "PROFIT_GUARANTEE": "Guaranteed or fixed profit",
    "ASSET_OWNERSHIP": "Asset ownership and possession",
    "SEQUENCING": "Contract execution sequence",
    "PRICE_CERTAINTY": "Price or asset certainty",
    "CURRENCY": "Currency and rate handling",
    "SETOFF": "Debt set-off",
    "PURIFICATION": "Income purification",
    "TAKAFUL_SURPLUS": "Takaful surplus treatment",
    "TERMINATION": "Termination and default mechanics",
    "OTHER": "Requires Shari'ah board review",
}

_BY_LABEL = {v.lower(): k for k, v in ISSUE_TYPE_LABELS.items()}
_BY_NAME = {k.lower(): k for k in ISSUE_TYPE_LABELS}

#: Free-text phrases the taxonomy absorbs. Models rarely return the exact enum
#: name; they return "Late Payment Penalty" or "guarantee of capital". Matching
#: by longest alias first means the specific phrase wins over the general one.
_ISSUE_ALIASES: dict[str, IssueType] = {
    "guarantee of capital": IssueType.GUARANTEE,
    "capital guarantee": IssueType.GUARANTEE,
    "capital protection": IssueType.GUARANTEE,
    "guaranteed minimum return": IssueType.PROFIT_GUARANTEE,
    "guaranteed profit": IssueType.PROFIT_GUARANTEE,
    "guaranteed return": IssueType.PROFIT_GUARANTEE,
    "fixed profit": IssueType.PROFIT_GUARANTEE,
    "fixed return": IssueType.PROFIT_GUARANTEE,
    "profit rate": IssueType.PROFIT_GUARANTEE,
    "late payment penalty": IssueType.PENALTY_ROUTING,
    "late payment charge": IssueType.PENALTY_ROUTING,
    "late payment": IssueType.PENALTY_ROUTING,
    "penalty": IssueType.PENALTY_ROUTING,
    "late fee": IssueType.PENALTY_ROUTING,
    "default interest": IssueType.RIBA,
    "interest": IssueType.RIBA,
    "riba": IssueType.RIBA,
    "usury": IssueType.RIBA,
    "risk transfer": IssueType.RISK_TRANSFER,
    "risk of loss": IssueType.RISK_TRANSFER,
    "dhaman": IssueType.RISK_TRANSFER,
    "uncertainty": IssueType.GHARAR,
    "ambiguity": IssueType.GHARAR,
    "gharar": IssueType.GHARAR,
    "gambling": IssueType.MAYSIR,
    "speculation": IssueType.MAYSIR,
    "maysir": IssueType.MAYSIR,
    "ownership": IssueType.ASSET_OWNERSHIP,
    "possession": IssueType.ASSET_OWNERSHIP,
    "sequencing": IssueType.SEQUENCING,
    "execution sequence": IssueType.SEQUENCING,
    "price certainty": IssueType.PRICE_CERTAINTY,
    "currency": IssueType.CURRENCY,
    "set off": IssueType.SETOFF,
    "set-off": IssueType.SETOFF,
    "setoff": IssueType.SETOFF,
    "purification": IssueType.PURIFICATION,
    "charity": IssueType.PURIFICATION,
    "takaful": IssueType.TAKAFUL_SURPLUS,
    "surplus": IssueType.TAKAFUL_SURPLUS,
    "termination": IssueType.TERMINATION,
    "guarantee": IssueType.GUARANTEE,
}

_ALIASES_BY_LENGTH = sorted(_ISSUE_ALIASES, key=len, reverse=True)


def coerce_issue_type(raw: str | None) -> tuple[IssueType, bool]:
    """Map free text to the closed taxonomy.

    Returns (issue_type, was_unrecognised). An unrecognised type is coerced to
    OTHER and flagged, which forces human review rather than silently filing a
    novel claim as a compliance finding.
    """
    if not raw:
        return IssueType.OTHER, True

    key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if key in _BY_NAME:
        return IssueType(_BY_NAME[key]), False
    if key in _BY_LABEL:
        return IssueType(_BY_LABEL[key]), False

    probe = key.replace("_", " ")
    for alias in _ALIASES_BY_LENGTH:
        if alias.replace("_", " ") in probe:
            return _ISSUE_ALIASES[alias], False

    for name, enum_value in _BY_NAME.items():
        if name in key or key in name:
            return IssueType(enum_value), False

    return IssueType.OTHER, True


def coerce_severity(raw: str | None, default: Severity = Severity.MEDIUM) -> Severity:
    if not raw:
        return default
    key = str(raw).strip().lower()
    for sev in Severity:
        if sev.value == key:
            return sev
    if key.startswith("crit") or key in {"fatal", "severe"}:
        return Severity.CRITICAL
    if key.startswith("hi") or key == "major":
        return Severity.HIGH
    if key.startswith("lo") or key in {"minor", "info", "informational"}:
        return Severity.ADVISORY
    if key.startswith("med") or key == "moderate":
        return Severity.MEDIUM
    return default


# ============================================================ registry entries
@dataclass(frozen=True)
class StandardSpec:
    standard_id: str
    title: str
    domain: str
    citation_ref: str
    requirement_summary: str
    common_breaches: str
    default_severity: Severity
    verify_status: str  # verified_title | confirm_before_use
    source_url: str = "https://aaoifi.com/shariaa-standards/?lang=en"
    detect_patterns: tuple[str, ...] = ()


_RE_OPT: dict[str, re.Pattern] = {}


def _compile(spec: StandardSpec) -> None:
    for pattern in spec.detect_patterns:
        _RE_OPT[f"{spec.standard_id}::{pattern}"] = re.compile(pattern, re.IGNORECASE)


# NOTE ON NUMBERING: the standard *numbers and titles* below marked
# `verified_title` were checked against a published AAOIFI standards listing.
# Everything marked `confirm_before_use` still needs validating against your
# licensed copy. Requirement summaries are paraphrases written for this product.
AAOIFI_STANDARDS: tuple[StandardSpec, ...] = (
    StandardSpec(
        standard_id="SS-1",
        title="Trading in Currencies",
        domain="currency",
        citation_ref="AAOIFI Shari'ah Standard 1",
        requirement_summary=(
            "Currency exchange must be executed hand-to-hand (spot) with full possession before "
            "the parties separate. Deferring either counter-value turns the transaction into Riba."
        ),
        common_breaches="Forward FX legs, deferred settlement of one currency, net-settled currency swaps.",
        default_severity=Severity.HIGH,
        verify_status="verified_title",
        detect_patterns=(
            r"forward\s+(foreign\s+exchange|fx)",
            r"currency\s+(swap|forward|option)",
            r"settle(?:ment)?\s+in\s+\d+\s+(?:days|months)\s+(?:for|in)\s+(?:the\s+)?(?:foreign|other)\s+currency",
        ),
    ),
    StandardSpec(
        standard_id="SS-2",
        title="Debit Card, Charge Card and Credit Card",
        domain="cards",
        citation_ref="AAOIFI Shari'ah Standard 2",
        requirement_summary=(
            "Card products must avoid charging fees that function as interest on a deferred "
            "balance, and the issuer may not profit from a customer's inability to pay."
        ),
        common_breaches="Interest on revolving balances, percentage-based late fees retained by the issuer.",
        default_severity=Severity.HIGH,
        verify_status="verified_title",
        detect_patterns=(r"credit\s+card.*\binterest\b", r"revolving\s+(balance|credit)"),
    ),
    StandardSpec(
        standard_id="SS-3",
        title="Default in Payment by a Debtor",
        domain="late payment",
        citation_ref="AAOIFI Shari'ah Standard 3",
        requirement_summary=(
            "A solvent debtor who delays payment may be made subject to a penalty, but that amount "
            "must be directed to charity and must not be recognised as income of the financing "
            "institution. Charitable distribution is not a revenue line."
        ),
        common_breaches=(
            "Late charges accruing as 'default interest at X% per annum' for the institution's own "
            "account; compounding; penalty treated as profit; no charity clause."
        ),
        default_severity=Severity.CRITICAL,
        verify_status="verified_title",
        detect_patterns=(
            r"default\s+interest",
            r"interest\s+at\s+(?:a\s+rate\s+of\s+)?\d+(?:\.\d+)?\s*%",
            r"late\s+(?:payment\s+)?(?:charge|fee|penalt)(?:y|ies|s)?[^.]{0,80}%",
            r"accrue[^.]{0,40}(?:interest|charge|penalt)",
            r"per\s+annum",
            r"compounded?\s+(?:monthly|daily|annually|quarterly)",
            r"\b(?:LIBOR|SOFR|EURIBOR|EIBOR)\b",
        ),
    ),
    StandardSpec(
        standard_id="SS-4",
        title="Settlement of Debt by Set-Off",
        domain="set-off",
        citation_ref="AAOIFI Shari'ah Standard 4",
        requirement_summary=(
            "Mutual debts may be set off, but set-off must not be used to circumvent the prohibition "
            "on trading debt at a discount or to convert a sale into a monetary exchange."
        ),
        common_breaches="Cross-default set-off clauses that net a discounted receivable against principal.",
        default_severity=Severity.MEDIUM,
        verify_status="verified_title",
        # "set off" (with a space) is the commonest drafting in real contracts and
        # was missed by an earlier hyphen-only pattern.
        detect_patterns=(r"set[\s-]?off", r"net\s+of\s+any\s+amounts\s+owed"),
    ),
    StandardSpec(
        standard_id="SS-5",
        title="Guarantees",
        domain="guarantee",
        citation_ref="AAOIFI Shari'ah Standard 5",
        requirement_summary=(
            "A third-party guarantee of a debt is generally permitted and may carry a fee, but a "
            "guarantee of a profit or of investment capital by the manager or partner is not. "
            "Guaranteeing capital in a profit-and-loss-sharing arrangement transfers the risk the "
            "structure is built on."
        ),
        common_breaches=(
            "Corporate or sponsor guarantee of investment capital; bank undertaking to cover "
            "Musharakah losses; third-party guarantee dressed as a 'purchase undertaking'."
        ),
        default_severity=Severity.CRITICAL,
        verify_status="verified_title",
        detect_patterns=(
            r"guarantee[^.]{0,60}(?:principal|capital|profit|return|losses)",
            r"capital\s+(?:protection|guarantee)",
            r"undertak(?:e|ing)\s+to\s+(?:purchase|buy)",
            r"buy-?back",
            r"promise\s+to\s+(?:purchase|buy\s+back)",
        ),
    ),
    StandardSpec(
        standard_id="SS-8",
        title="Murabaha to the Purchase Orderer",
        domain="murabahah",
        citation_ref="AAOIFI Shari'ah Standard 8",
        requirement_summary=(
            "In Murabaha the financier must acquire the asset and bear the ownership risk and "
            "liability for it before selling it on. Risk cannot be passed to the customer before "
            "the sale contract is executed, and the profit must be a fixed, disclosed mark-up on a "
            "known cost — not a time-based charge on money."
        ),
        common_breaches=(
            "Risk of asset loss passing to the client prior to execution of the sale contract; "
            "client bearing the asset before the bank owns it; profit expressed as a percentage "
            "per annum on the outstanding amount; rollover of an existing Murabaha into a new one."
        ),
        default_severity=Severity.CRITICAL,
        verify_status="verified_title",
        detect_patterns=(
            r"all\s+risk\s+of\s+(?:asset\s+)?loss",
            r"risk\s+of\s+(?:loss|damage|destruction)[^.]{0,60}(?:pass|transfer|bear)",
            r"prior\s+to\s+the\s+execution",
            r"before\s+(?:the\s+)?(?:execution|signing|conclusion)\s+of\s+the\s+(?:murabahah|sale)",
            r"mark-?up\s+of[^.]{0,40}(?:per\s+annum|%|percent)",
            r"profit\s+(?:rate|amount)[^.]{0,40}(?:per\s+annum|outstanding)",
        ),
    ),
    StandardSpec(
        standard_id="SS-9",
        title="Ijarah and Ijarah Muntahia Bittamleek",
        domain="ijarah",
        citation_ref="AAOIFI Shari'ah Standard 9",
        requirement_summary=(
            "In Ijarah the lessor retains ownership and major maintenance obligations throughout "
            "the lease. The transfer of ownership at the end must be a separate transaction, and "
            "the promise to transfer must remain distinct from the lease itself, contingent on "
            "full rental payment."
        ),
        common_breaches=(
            "Customer bearing insurance, ownership-related taxes and major maintenance; ownership "
            "transfer embedded in the lease contract rather than a separate sale; residual value "
            "guaranteed by the lessee."
        ),
        default_severity=Severity.HIGH,
        verify_status="verified_title",
        detect_patterns=(
            r"ijarah|ijara",
            # Drafters use "the Client", "the Customer" and "the Hirer" at least as
            # often as they use "the Lessee" for the party taking the usufruct.
            r"(?:lessee|customer|client|hirer|obligor)\s+(?:shall|will|agrees?\s+to)\s+"
            r"(?:bear|pay|be\s+responsible\s+for)[^.]{0,80}"
            r"(?:insurance|major\s+maintenance|structural|ownership[\s-]?related|all\s+taxes)",
            r"residual\s+value[^.]{0,40}guarantee",
            r"ownership\s+(?:shall\s+)?(?:transfer|pass)[^.]{0,40}(?:automatic|upon\s+completion)",
        ),
    ),
    StandardSpec(
        standard_id="SS-10",
        title="Salam and Parallel Salam",
        domain="salam",
        citation_ref="AAOIFI Shari'ah Standard 10",
        requirement_summary=(
            "Salam requires full payment of the price at the time of contract for a precisely "
            "described future deliverable. Parallel Salam must be a separate contract with a "
            "different counterparty and may not be made conditional on the first."
        ),
        common_breaches="Partial payment at inception; deliverable left unspecified; parallel Salam tied to the original.",
        default_severity=Severity.HIGH,
        verify_status="confirm_before_use",
        detect_patterns=(r"\bsalam\b", r"advance\s+payment\s+for\s+(?:future\s+)?delivery"),
    ),
    StandardSpec(
        standard_id="SS-11",
        title="Istisna'a and Parallel Istisna'a",
        domain="istisna",
        citation_ref="AAOIFI Shari'ah Standard 11",
        requirement_summary=(
            "Istisna'a is a manufacture-to-order contract where the specification must be defined. "
            "The price may be paid in instalments, but a parallel Istisna'a must not be made "
            "conditional on the original contract."
        ),
        common_breaches="Specification left open; penalty for delay retained as income; parallel contract linked.",
        default_severity=Severity.MEDIUM,
        verify_status="confirm_before_use",
        detect_patterns=(r"istisna", r"manufactur[^.]{0,40}to\s+order"),
    ),
    StandardSpec(
        standard_id="SS-12",
        title="Sharikah (Musharakah) and Modern Corporations",
        domain="musharakah",
        citation_ref="AAOIFI Shari'ah Standard 12",
        requirement_summary=(
            "Profit is shared in an agreed ratio while losses are borne strictly in proportion to "
            "capital contributed. A partner cannot be guaranteed a return, and no partner may be "
            "insulated from loss."
        ),
        common_breaches=(
            "Guaranteed minimum return to one partner; loss allocation that departs from capital "
            "ratio; one partner's capital protected by another."
        ),
        default_severity=Severity.CRITICAL,
        verify_status="confirm_before_use",
        detect_patterns=(
            r"musharakah|musharaka|shirkah",
            r"capital\s+(?:of\s+)?the\s+(?:bank|investor)[^.]{0,60}(?:guarantee|secured|protected)",
        ),
    ),
    StandardSpec(
        standard_id="SS-13",
        title="Mudarabah",
        domain="mudarabah",
        citation_ref="AAOIFI Shari'ah Standard 13",
        requirement_summary=(
            "The Rabb-ul-Mal supplies capital and the Mudarib supplies effort; financial loss falls "
            "on the capital provider unless the Mudarib was negligent. The Mudarib may not guarantee "
            "capital, and profit ratio must be stated as a proportion of actual profit."
        ),
        common_breaches=(
            "Fixed or guaranteed return to the investor; Manager guaranteeing capital; profit "
            "expressed as a percentage of invested amount rather than of realised profit; "
            "expenses of the Mudarib charged to capital beyond what is agreed."
        ),
        default_severity=Severity.CRITICAL,
        verify_status="confirm_before_use",
        detect_patterns=(
            r"mudarabah|mudaraba",
            r"guaranteed\s+(?:profit|return|rate)",
            r"fixed\s+(?:profit|return|rate\s+of\s+return)",
            r"minimum\s+return",
            r"investor[^.]{0,50}shall\s+(?:receive|be\s+paid)[^.]{0,30}(?:fixed|guaranteed)",
        ),
    ),
    StandardSpec(
        standard_id="SS-17",
        title="Investment Sukuk",
        domain="sukuk",
        citation_ref="AAOIFI Shari'ah Standard 17",
        requirement_summary=(
            "Sukuk holders must hold a real ownership interest in the underlying assets, usufruct or "
            "project. A purchase undertaking at face value on maturity, or a guarantee of the "
            "periodic distribution, converts the sukuk into a conventional bond."
        ),
        common_breaches=(
            "Originator undertaking to repurchase at par; guaranteed periodic distributions; assets "
            "not genuinely transferred; credit enhancement functioning as a guarantee."
        ),
        default_severity=Severity.CRITICAL,
        verify_status="confirm_before_use",
        detect_patterns=(
            r"sukuk",
            r"undertak(?:e|ing)[^.]{0,60}(?:repurchase|redemption)\s+at\s+(?:par|face|nominal)",
            r"guarantee[^.]{0,40}(?:periodic\s+)?distribut",
        ),
    ),
    StandardSpec(
        standard_id="SS-19",
        title="Qard (Loans)",
        domain="qard",
        citation_ref="AAOIFI Shari'ah Standard 19",
        requirement_summary=(
            "A Qard is a benevolent loan repaid in kind. Any condition that increases the amount "
            "repaid, or that grants the lender a benefit as a condition of the loan, is Riba."
        ),
        common_breaches="Service charges calculated on the amount or duration of the loan; benefits conditioned on lending.",
        default_severity=Severity.HIGH,
        verify_status="confirm_before_use",
        detect_patterns=(r"\bqard\b", r"benevolent\s+loan", r"interest-?free\s+loan[^.]{0,60}\bfee\b"),
    ),
    StandardSpec(
        standard_id="SS-45",
        title="Protection of Capital and Investments",
        domain="governance",
        citation_ref="AAOIFI Shari'ah Standard 45",
        requirement_summary=(
            "Sets out how the capital of investment account holders is protected and the limits on "
            "smoothing returns. Reserves and profit equalisation mechanisms must not create a "
            "guaranteed return to any class of account holder."
        ),
        common_breaches="Profit equalisation reserve used to guarantee a rate to investment account holders.",
        default_severity=Severity.HIGH,
        verify_status="verified_title",
        detect_patterns=(r"profit\s+equalisation", r"investment\s+risk\s+reserve", r"smoothing\s+of\s+returns"),
    ),
)

for _spec in AAOIFI_STANDARDS:
    _compile(_spec)

STANDARD_INDEX: dict[str, StandardSpec] = {s.standard_id: s for s in AAOIFI_STANDARDS}


def resolve_standard(standard_id: str | None, extra_entries: Optional[dict[str, StandardSpec]] = None) -> Optional[StandardSpec]:
    """Resolve a citation id to a registry entry, or None.

    Accepts 'SS-3', 'ss 3', 'SS3', 'AAOIFI SS 3'. A None return is meaningful:
    the caller must downgrade the finding to a referral item.
    """
    if not standard_id:
        return None
    key = str(standard_id).strip().upper().replace("AAOIFI", "").strip(" :")
    key = key.replace(" ", "").replace("_", "-")
    if not key.startswith("SS") and key.isdigit():
        key = f"SS-{key}"
    if key and not key.startswith("SS-") and key.startswith("SS"):
        key = f"SS-{key[2:].lstrip('-')}"
    # "SS-03" and "SS-3" are the same standard; normalise leading zeros.
    zero_padded = re.fullmatch(r"SS-0*(\d+)", key)
    if zero_padded:
        key = f"SS-{zero_padded.group(1)}"
    if extra_entries and key in extra_entries:
        return extra_entries[key]
    return STANDARD_INDEX.get(key)


def standards_needing_verification() -> list[StandardSpec]:
    """Entries whose numbering or scope still needs checking before client use."""
    return [s for s in AAOIFI_STANDARDS if s.verify_status != "verified_title"]


# ==================================================== deterministic pre-scan
@dataclass
class PreScanHit:
    standard_id: str
    issue_type: IssueType
    severity: Severity
    matched_pattern: str
    excerpt: str
    clause_ref: str = ""


# A numbered clause usually starts a line, but pasted text and two-column PDF
# extraction frequently put the next clause immediately after a full stop on the
# same line ("… per annum. 2.3 All risk …"). Without the [.;] alternative, every
# finding in the second clause is attributed to the first clause's number.
_CLAUSE_REF_RE = re.compile(
    r"(?:^|\n|[.;]\s)\s*(?:\(?((?:\d+\.)*\d+)\)?|[A-Z]\.|[IVX]{1,4}\.)\s+"
)


def _clause_refs(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1) or m.group(0).strip()) for m in _CLAUSE_REF_RE.finditer(text)]


def clause_ref_at(text: str, position: int) -> str:
    ref = ""
    for start, label in _clause_refs(text):
        if start <= position:
            ref = label
        else:
            break
    return ref


def _excerpt(text: str, start: int, end: int, radius: int = 140) -> str:
    """Quoted context around a match, snapped to word boundaries.

    The reviewer has to be able to see the clause in context, but an excerpt that
    begins "rred payment basis" or ends "…maintenance and ow" reads as a bug and
    undermines trust in the citation next to it. Snap outward/inward to spaces and
    mark truncation with an ellipsis.
    """
    lo = max(start - radius, 0)
    hi = min(end + radius, len(text))

    if lo > 0:
        space = text.find(" ", lo)
        if space != -1 and space < start:
            lo = space + 1
    if hi < len(text):
        space = text.rfind(" ", start, hi)
        if space != -1 and space > end:
            hi = space

    snippet = re.sub(r"\s+", " ", text[lo:hi]).strip()
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def prescan(text: str, active_standard_ids: Optional[Iterable[str]] = None) -> list[PreScanHit]:
    """Run the deterministic rule pass before any model call.

    Two jobs:
    1. Recall insurance. A rule match is forced into the result set even if the
    model missed it, so recall never depends on the model's mood.
    2. Demo mode. With no API key the product still produces real, citable
    findings — which is what makes a free-tier or offline sales demo work.
    """
    permitted = set(active_standard_ids) if active_standard_ids else None
    hits: list[PreScanHit] = []
    seen: set[tuple[str, str]] = set()

    for spec in AAOIFI_STANDARDS:
        if permitted is not None and spec.standard_id not in permitted:
            continue
        for pattern in spec.detect_patterns:
            compiled = _RE_OPT.get(f"{spec.standard_id}::{pattern}")
            if compiled is None:
                continue
            for match in compiled.finditer(text):
                excerpt = _excerpt(text, match.start(), match.end())
                dedupe_key = (spec.standard_id, excerpt[:80])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                hits.append(
                    PreScanHit(
                        standard_id=spec.standard_id,
                        issue_type=_issue_for(spec),
                        severity=spec.default_severity,
                        matched_pattern=pattern,
                        excerpt=excerpt,
                        clause_ref=clause_ref_at(text, match.start()),
                    )
                )
    hits.sort(key=lambda h: (SEVERITY_ORDER[h.severity.value], h.standard_id))
    return hits


_ISSUE_BY_STANDARD: dict[str, IssueType] = {
    "SS-1": IssueType.CURRENCY,
    "SS-2": IssueType.RIBA,
    "SS-3": IssueType.PENALTY_ROUTING,
    "SS-4": IssueType.SETOFF,
    "SS-5": IssueType.GUARANTEE,
    "SS-8": IssueType.RISK_TRANSFER,
    "SS-9": IssueType.ASSET_OWNERSHIP,
    "SS-10": IssueType.GHARAR,
    "SS-11": IssueType.GHARAR,
    "SS-12": IssueType.PROFIT_GUARANTEE,
    "SS-13": IssueType.PROFIT_GUARANTEE,
    "SS-17": IssueType.GUARANTEE,
    "SS-19": IssueType.RIBA,
    "SS-45": IssueType.PROFIT_GUARANTEE,
}


def _issue_for(spec: StandardSpec) -> IssueType:
    return _ISSUE_BY_STANDARD.get(spec.standard_id, IssueType.OTHER)


# ============================================================ jurisdiction packs
@dataclass(frozen=True)
class JurisdictionPack:
    code: str
    label: str
    extra_requirements: tuple[str, ...]
    standard_ids: tuple[str, ...]
    note: str
    source_url: str = ""


JURISDICTION_PACKS: dict[str, JurisdictionPack] = {
    "GLOBAL": JurisdictionPack(
        code="GLOBAL",
        label="AAOIFI baseline (global)",
        extra_requirements=(),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note="The AAOIFI Shari'ah Standards baseline. A safe default where no national rulebook is specified.",
        source_url="https://aaoifi.com/shariaa-standards/?lang=en",
    ),
    "AE-CBUAE": JurisdictionPack(
        code="AE-CBUAE",
        label="UAE — CBUAE Shari'ah governance",
        extra_requirements=(
            "Internal Shari'ah audit manual and an annual Shari'ah audit plan approved by the Internal "
            "Shari'ah Supervision Committee.",
            "Appointment of a specialised external firm for External Shari'ah Audit.",
        ),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note=(
            "The CBUAE rulebook requires Islamic Financial Institutions to maintain Shari'ah "
            "governance standards including internal Shari'ah audit and to appoint an external firm "
            "for External Shari'ah Audit — so review evidence has to be producible on demand."
        ),
        source_url="https://rulebook.centralbank.ae/en/rulebook/standard-re-shariah-governance-islamic-financial-institutions",
    ),
    "SA-SAMA": JurisdictionPack(
        code="SA-SAMA",
        label="Saudi Arabia — SAMA",
        extra_requirements=("Draft-specific Shari'ah review evidence retained for the supervisory cycle.",),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note="Add the specific SAMA circulars your client is subject to during the custom-library build.",
        source_url="",
    ),
    "MY-BNM": JurisdictionPack(
        code="MY-BNM",
        label="Malaysia — BNM Shariah Governance Policy Document",
        extra_requirements=("Shariah committee approval recorded per product and per document template.",),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note="Malaysia commonly layers SAC resolutions on top of AAOIFI; encode them in a tenant library.",
        source_url="",
    ),
    "BH-CBB": JurisdictionPack(
        code="BH-CBB",
        label="Bahrain — CBB",
        extra_requirements=("Annual Shari'ah audit report submitted to the Shari'ah board.",),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note="CBB requires an annual Shari'ah review; the annual audit pack add-on maps to this cycle.",
        source_url="",
    ),
    "PK-SBP": JurisdictionPack(
        code="PK-SBP",
        label="Pakistan — SBP",
        extra_requirements=("Shari'ah compliance certificate per product; SBP Shari'ah Governance Framework.",),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note="Add the SBP Shari'ah Governance Framework clauses during onboarding.",
        source_url="",
    ),
    "UK": JurisdictionPack(
        code="UK",
        label="United Kingdom — FCA-regulated Islamic finance",
        extra_requirements=("Shari'ah review evidence consistent with FCA consumer-duty documentation obligations.",),
        standard_ids=tuple(STANDARD_INDEX.keys()),
        note="Home to a mature Islamic fintech and home-finance market; advisors here are the fastest ICP to close.",
        source_url="",
    ),
    "IIFM-HEDGING": JurisdictionPack(
        code="IIFM-HEDGING",
        label="IIFM / ISDA Tahawwut master agreement",
        extra_requirements=("Hedging documentation executed on the ISDA/IIFM Tahawwut Master Agreement.",),
        standard_ids=("SS-1", "SS-3", "SS-4", "SS-5"),
        note=(
            "The first standard contract document for Shari'ah-compliant derivatives, published by "
            "ISDA and IIFM; relevant when reviewing any Islamic hedging or profit-rate swap."
        ),
        source_url="https://www.isda.org/book/isda-iifm-tahawwut-master-agreement/",
    ),
}


def get_pack(code: str) -> JurisdictionPack:
    return JURISDICTION_PACKS.get((code or "GLOBAL").upper(), JURISDICTION_PACKS["GLOBAL"])


# ============================================================== seed helpers
@dataclass
class SeedStats:
    libraries: int = 0
    entries: int = 0


def seed_global_library() -> SeedStats:
    """Idempotently create/refresh the global AAOIFI library.

    Safe to call on every boot: entries are upserted by (library, standard_id).
    """
    from .db import session_scope
    from .models import StandardEntry, StandardLibrary

    stats = SeedStats()
    with session_scope() as session:
        library = (
            session.query(StandardLibrary)
            .filter(StandardLibrary.tenant_id.is_(None), StandardLibrary.name == "AAOIFI Shari'ah Standards")
            .one_or_none()
        )
        if library is None:
            library = StandardLibrary(
                tenant_id=None,
                name="AAOIFI Shari'ah Standards",
                jurisdiction="GLOBAL",
                description=(
                    "Baseline AAOIFI-aligned ruleset for Islamic trade facilities, Murabahah, Ijarah "
                    "and investment agreements. Requirement summaries are paraphrases for navigation; "
                    "the institution's licensed copy of the standards is authoritative."
                ),
                version="2.0",
            )
            session.add(library)
            session.flush()
            stats.libraries += 1

        existing = {e.standard_id: e for e in library.entries}
        for spec in AAOIFI_STANDARDS:
            entry = existing.get(spec.standard_id)
            payload = dict(
                title=spec.title,
                domain=spec.domain,
                citation_ref=spec.citation_ref,
                requirement_summary=spec.requirement_summary,
                common_breaches=spec.common_breaches,
                default_severity=spec.default_severity.value,
                detect_hints={"patterns": list(spec.detect_patterns)},
                source_url=spec.source_url,
                verify_status=spec.verify_status,
                is_active=True,
            )
            if entry is None:
                session.add(StandardEntry(library_id=library.id, standard_id=spec.standard_id, **payload))
                stats.entries += 1
            else:
                for key, value in payload.items():
                    setattr(entry, key, value)
    return stats


def global_library_id() -> Optional[str]:
    from .db import session_scope
    from .models import StandardLibrary

    with session_scope() as session:
        library = (
            session.query(StandardLibrary)
            .filter(StandardLibrary.tenant_id.is_(None), StandardLibrary.name == "AAOIFI Shari'ah Standards")
            .one_or_none()
        )
        return library.id if library else None


def active_standard_ids_for_library(library_id: Optional[str]) -> Optional[list[str]]:
    """Return the standard ids a library restricts to, or None for 'use the registry'."""
    if not library_id:
        return None
    from .db import session_scope
    from .models import StandardEntry

    with session_scope() as session:
        rows = (
            session.query(StandardEntry.standard_id)
            .filter(StandardEntry.library_id == library_id, StandardEntry.is_active.is_(True))
            .all()
        )
        return [r[0] for r in rows] or None


def library_entries_by_standard_id(library_id: Optional[str]) -> dict[str, StandardSpec]:
    """Load a tenant's custom library so citations resolve against THEIR ruleset.

    This is what makes bring-your-own-standards real: `resolve_standard` is
    given these entries first, so a client-coded 'CLIENT-SSB-14' resolves and
    cites properly.
    """
    if not library_id:
        return {}
    from .db import session_scope
    from .models import StandardEntry

    out: dict[str, StandardSpec] = {}
    with session_scope() as session:
        rows = (
            session.query(StandardEntry)
            .filter(StandardEntry.library_id == library_id, StandardEntry.is_active.is_(True))
            .all()
        )
        for row in rows:
            patterns: tuple[str, ...] = ()
            if isinstance(row.detect_hints, dict):
                patterns = tuple(row.detect_hints.get("patterns") or ())
            out[row.standard_id] = StandardSpec(
                standard_id=row.standard_id,
                title=row.title,
                domain=row.domain or "custom",
                citation_ref=row.citation_ref or row.standard_id,
                requirement_summary=row.requirement_summary or "",
                common_breaches=row.common_breaches or "",
                default_severity=coerce_severity(row.default_severity),
                verify_status=row.verify_status or "confirm_before_use",
                source_url=row.source_url or "",
                detect_patterns=patterns,
            )
    return out
