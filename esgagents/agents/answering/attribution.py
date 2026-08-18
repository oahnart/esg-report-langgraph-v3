from __future__ import annotations

import re
import unicodedata
from typing import Any

from .claim_support import build_claim_support
from esgagents.agents.evidence.metric_facts import metric_facts_supporting_claim


DEFINITIVE_SOURCE_TERMS = (
    "승인",
    "시행",
    "운영하고",
    "구축하고",
    "수립",
    "유지",
    "모니터링",
    "점검",
    "제공하고",
    "평가하고",
    "수행하고",
    "달성 목표",
    "commitment",
    "committed",
    "approved",
    "implemented",
    "has established",
    "establishes",
    "maintains",
    "monitors",
    "checks",
    "provides",
    "evaluates",
    "operates",
)


def attribute_supported_claims(
    answer: str,
    evidence_items: list[Any],
    output_language: str,
) -> tuple[str, list[str]]:
    if not answer:
        return "", []
    supports = build_claim_support(answer, evidence_items)
    if not supports:
        return answer, []
    claims: list[str] = []
    flags: list[str] = []
    for support in supports:
        claim = support.claim_text
        if support.support_status in {"grounded", "partial"}:
            if support.support_tier == "tier_4_draft":
                claim = support.claim_text
                flags.append("draft_based_answer")
            elif support.support_tier == "tier_3_assessment":
                claim = support.claim_text
                flags.append("assessment_based_answer")
        claims.append(claim)
    return " ".join(claims), sorted(set(flags))


def salvage_supported_claims(
    answer: str,
    evidence_items: list[Any],
    metric_audit: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """Keep only claims that deterministic evidence matching can ground."""
    if not answer:
        return "", []
    supports = build_claim_support(answer, evidence_items)
    if not supports:
        return "", ["removed_claim:unsupported_claim"]
    kept = []
    actions = []
    for support in supports:
        metric_support = metric_facts_supporting_claim(
            support.claim_text,
            metric_audit or {},
        )
        if support.support_status in {"grounded", "partial", "data_gap"} or metric_support:
            kept.append(support.claim_text)
        else:
            actions.append(
                f"removed_claim:{support.support_status}:{support.claim_id}"
            )
    return " ".join(kept), actions


def has_definitive_source_claim(claim: str) -> bool:
    lower = unicodedata.normalize("NFKC", claim or "").casefold()
    lower = re.sub(
        r"\b(?:is|are|was|were|has|have|does|do)?\s*not\s+(?:an?\s+)?"
        r"(?:approved|implemented|operating|operate|established|committed)\b",
        "",
        lower,
    )
    return any(term in lower for term in DEFINITIVE_SOURCE_TERMS)


def salvage_source_overstatement(
    answer: str,
    evidence_items: list[Any],
) -> tuple[str, list[str]]:
    supports = build_claim_support(answer, evidence_items)
    kept: list[str] = []
    actions: list[str] = []
    for support in supports:
        source_limited = support.support_tier in {
            "tier_3_assessment",
            "tier_4_draft",
        }
        if (
            source_limited
            and support.support_status in {"grounded", "partial"}
            and has_definitive_source_claim(support.claim_text)
        ):
            if support.support_tier == "tier_4_draft":
                kept.append(support.claim_text)
                continue
            actions.append(f"removed_claim:source_overstatement:{support.claim_id}")
        else:
            kept.append(support.claim_text)
    return " ".join(kept), actions
