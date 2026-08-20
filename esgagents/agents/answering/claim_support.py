from __future__ import annotations

import re
import unicodedata
from typing import Any

from esgagents.schemas import ClaimSupport


DATA_GAP_TERMS = (
    "not disclosed",
    "not provided",
    "not available",
    "no quantitative figure",
    "quantitative figure was not",
    "공개되지",
    "제공되지",
    "명시되어 있지",
    "명시되지",
    "확인되지",
    "미공시",
    "자료가 없",
    "정보가 없",
)
TOKEN_RE = re.compile(r"[가-힣]{2,}|[a-z]{3,}", re.IGNORECASE)
NUMBER_RE = re.compile(r"\d+(?:[,.]\d+)*(?:\s*%)?")
PERIOD_RE = re.compile(r"\b(?:19|20)\d{2}\b|\bFY\s*\d{2,4}\b", re.IGNORECASE)
STOPWORDS = {
    "회사는",
    "대웅제약",
    "대웅그룹",
    "그리고",
    "또한",
    "대한",
    "관련",
    "이를",
    "the",
    "and",
    "for",
    "with",
    "company",
    "was",
    "were",
    "is",
    "are",
    "has",
    "have",
    "had",
    "reported",
    "recorded",
    "according",
}
INTENT_STEM_RE = re.compile(
    r"([가-힣]{2,12})(?:하고자\s*(?:합니다|하며|하고)|할\s*(?:계획|예정)(?:입니다|이며|이고)?)"
)
PRACTICE_ENDINGS = ("하며", "합니다", "하고 있습니다", "하고 있으며", "하여", "하였습니다", "한다")
EVIDENCE_PRACTICE_ENDINGS = (*PRACTICE_ENDINGS, "하고 있", "하였", "했")
TIER_RANK = {
    "tier_1_governing": 5,
    "tier_2_operational": 4,
    "tier_3_assessment": 3,
    "tier_4_draft": 2,
    "tier_unknown": 1,
}


def build_claim_support(answer: str, evidence_items: list[Any]) -> list[ClaimSupport]:
    claims = _split_claims(answer)
    result: list[ClaimSupport] = []
    for index, claim in enumerate(claims, start=1):
        lower = unicodedata.normalize("NFKC", claim).casefold()
        period_match = PERIOD_RE.search(lower)
        if any(term in lower for term in DATA_GAP_TERMS):
            result.append(
                ClaimSupport(
                    claim_id=f"c{index}",
                    claim_text=claim,
                    support_status="data_gap",
                    reporting_period=period_match.group(0) if period_match else "",
                )
            )
            continue

        matches = [item for item in evidence_items if _claim_matches_item(claim, item)]
        if not matches:
            result.append(
                ClaimSupport(
                    claim_id=f"c{index}",
                    claim_text=claim,
                    support_status="unsupported",
                    reporting_period=period_match.group(0) if period_match else "",
                )
            )
            continue

        strongest_tier = max(
            (str(getattr(item, "source_tier", "") or "tier_unknown") for item in matches),
            key=lambda tier: TIER_RANK.get(tier, 0),
        )
        strongest_rank = TIER_RANK.get(strongest_tier, 0)
        strongest = [
            item
            for item in matches
            if TIER_RANK.get(str(getattr(item, "source_tier", "") or "tier_unknown"), 0)
            == strongest_rank
        ]
        source_ids = list(
            dict.fromkeys(
                _source_id(item)
                for item in strongest
                if _source_id(item)
            )
        )
        result.append(
            ClaimSupport(
                claim_id=f"c{index}",
                claim_text=claim,
                source_ids=source_ids,
                support_tier=strongest_tier,
                support_status=(
                    "partial"
                    if overstates_evidence_intent(claim, evidence_items)
                    else "grounded"
                ),
                reporting_period=period_match.group(0) if period_match else "",
                attribution_required=False,
            )
        )
    return result


def overstates_evidence_intent(claim: str, evidence_items: list[Any]) -> bool:
    """Detect a claim stating as current practice what evidence only intends.

    Source text routinely commits to a future action (``적용하고자 합니다``,
    ``확대할 예정입니다``) and the writer renders it as an operating control
    (``적용하며``, ``확대하여``). For an ESG disclosure that difference is material,
    so the claim is only partially supported. Evidence that states the same action
    in a realis form somewhere clears it -- the plan is then also a practice.
    """

    claim_text = unicodedata.normalize("NFKC", claim or "")
    evidence_text = unicodedata.normalize(
        "NFKC",
        " ".join(_evidence_text(item) for item in evidence_items or []),
    )
    if not claim_text or not evidence_text:
        return False
    for match in INTENT_STEM_RE.finditer(evidence_text):
        stem = match.group(1)
        if not any(f"{stem}{ending}" in claim_text for ending in PRACTICE_ENDINGS):
            continue
        if any(f"{stem}{ending}" in evidence_text for ending in EVIDENCE_PRACTICE_ENDINGS):
            continue
        return True
    return False


def _evidence_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("raw_evidence_ko") or item.get("text") or "")
    return str(getattr(item, "raw_evidence_ko", "") or "")


def _split_claims(answer: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", answer or "")
    return [
        " ".join(part.split()).strip(" •·")
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+|\s*[•·]\s*", normalized)
        if part.strip(" •·")
    ]


def _claim_matches_item(claim: str, item: Any) -> bool:
    evidence = unicodedata.normalize("NFKC", str(getattr(item, "raw_evidence_ko", "") or ""))
    if not evidence:
        return False
    claim_numbers = {_number_body(match.group(0)) for match in NUMBER_RE.finditer(claim)}
    evidence_numbers = {_number_body(match.group(0)) for match in NUMBER_RE.finditer(evidence)}
    if claim_numbers and not claim_numbers.issubset(evidence_numbers):
        return False
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return bool(claim_numbers)
    evidence_tokens = _tokens(evidence)
    overlap = claim_tokens.intersection(evidence_tokens)
    threshold = min(3, max(1, len(claim_tokens) // 3))
    return len(overlap) >= threshold


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN_RE.findall(unicodedata.normalize("NFKC", value or ""))
        if token.casefold() not in STOPWORDS
    }


def _number_body(value: str) -> str:
    return value.replace(" ", "").replace(",", "").removesuffix("%")


def _source_id(item: Any) -> str:
    return str(
        getattr(item, "canonical_source_id", "")
        or getattr(item, "document_id", "")
        or getattr(item, "source_path", "")
        or ""
    ).strip()
