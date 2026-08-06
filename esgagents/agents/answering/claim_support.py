from __future__ import annotations

import re
import unicodedata
from typing import Any

from esgagents.schemas import ClaimSupport


DATA_GAP_TERMS = (
    "not disclosed",
    "not provided",
    "not available",
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
}
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
                support_status="grounded",
                reporting_period=period_match.group(0) if period_match else "",
                attribution_required=strongest_tier in {"tier_3_assessment", "tier_4_draft"},
            )
        )
    return result


def _split_claims(answer: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", answer or "")
    return [
        " ".join(part.split()).strip(" •")
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+|\s*•\s*", normalized)
        if part.strip(" •")
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
