from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any


SOURCE_TIERS = {
    "tier_1_governing",
    "tier_2_operational",
    "tier_3_assessment",
    "tier_4_draft",
    "tier_unknown",
}
DRAFT_KEYWORDS = (
    "초안",
    "검토 안",
    "검토안",
    "구성안",
    "제안",
    "proposal",
    "draft",
    "consultant",
    "consulting",
    "컨설팅",
    "요구사항",
    "대응방안",
)
DRAFT_ATTRIBUTION_TERMS = (
    "초안",
    "제안",
    "검토 자료",
    "검토안",
    "자료에 따르면",
    "draft",
    "proposal",
    "proposed",
    "under review",
)

TIER_RANK = {
    "tier_1_governing": 5,
    "tier_2_operational": 4,
    "tier_3_assessment": 3,
    "tier_unknown": 2,
    "tier_4_draft": 1,
}


@dataclass(frozen=True)
class SourceClassification:
    canonical_source_id: str
    source_tier: str
    source_type: str
    document_status: str
    classification_reason: str


def canonical_filename(source_name: str, source_path: str) -> str:
    candidate = (source_name or "").strip()
    if not candidate:
        normalized_path = (source_path or "").replace("\\", "/").rstrip("/")
        candidate = PurePath(normalized_path).name
    value = unicodedata.normalize("NFKC", candidate).casefold()
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "unknown-source"


def evidence_fingerprint(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def classify_source(item: Any) -> SourceClassification:
    source_name = _field(item, "source_name")
    source_path = _field(item, "source_path")
    canonical = canonical_filename(source_name, source_path)
    canonical_id = _field(item, "canonical_source_id") or f"src_{hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:16]}"

    explicit_tier = _field(item, "source_tier").lower()
    explicit_type = _field(item, "source_type").lower()
    explicit_status = _field(item, "document_status").lower()
    haystack = unicodedata.normalize("NFKC", f"{source_name} {source_path}").casefold()
    draft_match = next((keyword for keyword in DRAFT_KEYWORDS if keyword in haystack), None)
    if draft_match and explicit_status in {"", "unknown"}:
        return SourceClassification(
            canonical_source_id=canonical_id,
            source_tier="tier_4_draft",
            source_type="draft_or_proposal",
            document_status="draft",
            classification_reason=f"rag_metadata_refined;inferred_keyword:{draft_match}",
        )
    if explicit_tier in SOURCE_TIERS:
        return SourceClassification(
            canonical_source_id=canonical_id,
            source_tier=explicit_tier,
            source_type=explicit_type or _default_type(explicit_tier),
            document_status=explicit_status or _default_status(explicit_tier),
            classification_reason=_field(item, "classification_reason") or "rag_metadata",
        )

    rules = (
        (
            "tier_4_draft",
            "draft_or_proposal",
            "draft",
            DRAFT_KEYWORDS,
        ),
        (
            "tier_3_assessment",
            "external_assessment",
            "assessed",
            ("평가결과", "서면평가", "ecovadis", "audit", "assessment", "on-site", "onsite", "고객사 esg", "현대차"),
        ),
        (
            "tier_1_governing",
            "official_filing",
            "governing",
            ("dart", "사업보고서", "공시", "official filing"),
        ),
        (
            "tier_1_governing",
            "policy_procedure",
            "governing",
            ("정책", "방침", "절차", "지침", "규정", "매뉴얼", "manual", "policy", "procedure", "원본문서"),
        ),
        (
            "tier_2_operational",
            "operational_record",
            "operational",
            ("회의 결과", "회의결과", "사용량", "배출량", "실적", "kpi", "data report", "company report", "sustainability report", "usage", "emission", "operational", "운영", "목표", "기안", "보고서"),
        ),
    )
    for tier, source_type, status, keywords in rules:
        matched = next((keyword for keyword in keywords if keyword in haystack), None)
        if matched:
            return SourceClassification(
                canonical_source_id=canonical_id,
                source_tier=tier,
                source_type=explicit_type or source_type,
                document_status=explicit_status or status,
                classification_reason=(
                    f"rag_metadata_partial;inferred_keyword:{matched}"
                    if explicit_type or explicit_status
                    else f"inferred_keyword:{matched}"
                ),
            )
    return SourceClassification(
        canonical_source_id=canonical_id,
        source_tier="tier_unknown",
        source_type=explicit_type or "unknown",
        document_status=explicit_status or "unknown",
        classification_reason="rag_metadata_partial;insufficient_tier" if explicit_type or explicit_status else "insufficient_metadata",
    )


def relevance_band(label: str) -> int:
    normalized = (label or "").strip().casefold()
    if normalized == "metric_row":
        return 4
    if normalized in {"strong", "high", "high_confidence", "useful", "keep"}:
        return 3
    if normalized in {"medium", "medium_confidence", "partial", "keep_supportive"}:
        return 2
    return 1


def _field(item: Any, field: str) -> str:
    if isinstance(item, dict):
        return str(item.get(field, "") or "").strip()
    return str(getattr(item, field, "") or "").strip()


def _default_type(tier: str) -> str:
    return {
        "tier_1_governing": "policy_procedure",
        "tier_2_operational": "operational_record",
        "tier_3_assessment": "external_assessment",
        "tier_4_draft": "draft_or_proposal",
    }.get(tier, "unknown")


def _default_status(tier: str) -> str:
    return {
        "tier_1_governing": "governing",
        "tier_2_operational": "operational",
        "tier_3_assessment": "assessed",
        "tier_4_draft": "draft",
    }.get(tier, "unknown")


def has_draft_attribution(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return any(term in normalized for term in DRAFT_ATTRIBUTION_TERMS)


def attribute_draft_statement(text: str, output_language: str = "") -> str:
    value = " ".join((text or "").split())
    if not value or has_draft_attribution(value):
        return value
    language = (output_language or "").strip().casefold()
    if language in {"ko", "kor", "korean", "한국어"} or language.startswith("ko-"):
        return f"제안/검토 자료에 따르면, {value}"
    return f"According to the draft proposal, {value}"


def attribute_assessment_statement(text: str, output_language: str = "") -> str:
    value = " ".join((text or "").split())
    if not value:
        return value
    lower = unicodedata.normalize("NFKC", value).casefold()
    if any(
        term in lower
        for term in (
            "평가에 따르면",
            "평가 자료에 따르면",
            "평가 결과",
            "assessment",
            "assessed",
        )
    ):
        return value
    language = (output_language or "").strip().casefold()
    if language in {"ko", "kor", "korean", "한국어"} or language.startswith("ko-"):
        return f"평가 자료에 따르면, {value}"
    return f"According to the assessment, {value}"
