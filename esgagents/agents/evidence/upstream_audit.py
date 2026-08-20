"""Client-side checks for guarantees the v3 producer no longer enforces.

Team RAG's sealed v3 index returns labels and statuses but stops there: its own
``retrieval_notes`` say "no overlay/dedupe/noise-drop, labels/status only". Two
of the spec guarantees therefore have to be re-checked by the consumer:

* §13 topic isolation - an excerpt about a mutually exclusive topic must not be
  substituted for the requested one (GHG for air pollutants, water use for
  wastewater discharge, shareholder structure for related-party transactions).
* §7/§8 facet coverage - ``covered_facets`` is a producer claim, so it is
  verified against the excerpts that actually came back.

Neither check needs the corpus. Topic isolation uses the question contract that
already exists locally, and facet grounding uses the returned evidence text.

The patterns below are deliberately local to this module even though
``answering.semantic_critic`` carries a similar lexicon: that one runs on a
drafted answer and has no ``metric_result``/``reporting_period`` detector, and
importing it here would pull the LLM critic into the evidence layer. The
dimension names are kept in step with ``question_contracts`` by a drift test.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from esgagents.schemas import EvidenceItem


_GHG_DIMENSIONS = frozenset(
    {"scope_1_emissions", "scope_2_emissions", "scope_3_emissions", "energy_use"}
)
_POLLUTANT_DIMENSIONS = frozenset({"air_pollutant_emissions", "water_pollutant_emissions"})
_WATER_USE_DIMENSIONS = frozenset({"water_consumption", "water_reuse_rate"})
_WASTEWATER_DIMENSIONS = frozenset({"wastewater_discharge"})
_SHAREHOLDER_DIMENSIONS = frozenset(
    {"shareholder_composition", "dividend_policy", "shareholder_meeting"}
)
_RELATED_PARTY_DIMENSIONS = frozenset({"related_party_transactions"})

# Spec §13: topic A must not be answered with topic B. Only the pairs that can
# be told apart from the excerpt text alone are listed; the metric-versus-policy
# rows of that table are already covered by the metric_result facet requirement.
TOPIC_EXCLUSIONS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (_GHG_DIMENSIONS, _POLLUTANT_DIMENSIONS),
    (_WATER_USE_DIMENSIONS, _WASTEWATER_DIMENSIONS),
    (_SHAREHOLDER_DIMENSIONS, _RELATED_PARTY_DIMENSIONS),
)

TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "scope_1_emissions": (r"scope\s*1", r"스코프\s*1", r"직접\s*배출"),
    "scope_2_emissions": (r"scope\s*2", r"스코프\s*2", r"간접\s*배출"),
    "scope_3_emissions": (r"scope\s*3", r"스코프\s*3"),
    "energy_use": (r"에너지.{0,8}(?:사용|소비)", r"energy (?:use|consumption)"),
    "air_pollutant_emissions": (
        r"대기\s*오염\s*물질",
        r"질소산화물",
        r"황산화물",
        r"\bnox\b",
        r"\bsox\b",
        r"\bvoc\b",
        r"먼지",
        r"air pollutant",
    ),
    "water_pollutant_emissions": (r"수질\s*오염\s*물질", r"water[-\s]*pollutant"),
    "water_consumption": (
        r"용수.{0,5}(?:사용|취수|소비)",
        r"취수량",
        r"water (?:use|consumption|withdrawal)",
    ),
    "water_reuse_rate": (r"용수.{0,5}(?:재사용|재이용)", r"water reuse"),
    "wastewater_discharge": (r"폐수", r"방류", r"wastewater", r"effluent"),
    "shareholder_composition": (r"주주.{0,8}(?:구성|현황|비율)", r"지분\s*율", r"shareholder"),
    "dividend_policy": (r"배당", r"dividend"),
    "shareholder_meeting": (r"주주총회", r"shareholder meeting"),
    "related_party_transactions": (
        r"특수\s*관계\s*자",
        r"관계사.{0,6}거래",
        r"내부\s*거래",
        r"related[-\s]*party",
    ),
}

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_PERIOD_RE = re.compile(
    r"(?:(?:19|20)\d{2}\s*년?|\bFY\s*\d{2,4}\b|\bQ[1-4]\b|\d{1,2}\s*분기|반기|보고\s*기간|reporting\s+period)",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"(?:%|퍼센트|명|건|회|시간|일|톤|t(?:co2(?:eq)?)?|kg|kwh|mwh|tj|㎥|m3|원|억원|만원|백만원|krw|usd)",
    re.IGNORECASE,
)
# The metric lane serializes a table row as "label | unit | 2024=6.0 | 2025=7.0",
# where no number sits next to its unit.
_METRIC_ROW_VALUE_RE = re.compile(r"(?:19|20)\d{2}\s*=\s*-?[\d.,]+")
# "반기 1회", "연 2회" are a reporting cadence, not a metric result.
_CADENCE_RE = re.compile(r"(?:연|매년|반기|분기|매월|월|주)\s*\d*\s*$")
_CADENCE_UNITS = ("회", "시간", "일")

# Evidence-level facet detectors. Every facet used by
# ``question_contracts.QuestionContract`` is covered so an over-claim on any
# required or expected facet can be checked.
FACET_EVIDENCE_TERMS: dict[str, tuple[str, ...]] = {
    "policy_or_direction": ("정책", "방침", "원칙", "전략", "방향", "policy", "principle", "strategy"),
    "target": ("목표", "감축", "달성", "target", "goal"),
    "accountable_body": ("이사회", "위원회", "협의체", "팀", "부서", "담당", "책임자", "board", "committee", "department"),
    "role": ("역할", "책임", "담당", "승인", "검토", "보고", "심의", "role", "responsib", "approve", "review"),
    "oversight_cadence": ("정기", "매년", "연 1회", "반기", "분기", "월", "수시", "annual", "quarter", "semi-annual"),
    "risk_identification": ("리스크", "위험", "식별", "평가", "진단", "risk", "identify", "assess"),
    "control_or_response": ("통제", "대응", "조치", "완화", "개선", "실사", "control", "response", "mitigat"),
    "monitoring_follow_up": ("모니터링", "점검", "추적", "후속", "사후", "monitor", "follow-up", "track"),
    "operating_organization": ("환경경영팀", "ehs팀", "간사협의체", "실무", "운영 조직", "operating organization"),
    "site_management_system": ("사업장", "공장", "현장", "site", "facility", "plant"),
}


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())


def excluded_topic_dimensions(own_dimensions: Iterable[str]) -> frozenset[str]:
    """Dimensions that must not be substituted for this question's own topic."""
    own = {str(dimension) for dimension in own_dimensions}
    if not own:
        return frozenset()
    excluded: set[str] = set()
    for left, right in TOPIC_EXCLUSIONS:
        # A question that legitimately spans both sides of a pair (Q039 asks for
        # water use and wastewater discharge together) excludes neither side.
        if own & left and not own & right:
            excluded |= right
        elif own & right and not own & left:
            excluded |= left
    return frozenset(excluded - own)


def matches_topic_dimension(text: str, dimension: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in TOPIC_PATTERNS.get(dimension, ())
    )


def substituted_topic_dimensions(
    text: str,
    own_dimensions: Iterable[str],
    excluded_dimensions: Iterable[str],
) -> tuple[str, ...]:
    """Excluded dimensions an excerpt talks about while saying nothing on topic.

    An excerpt that covers both the requested topic and an excluded one is kept:
    that is context, not substitution.
    """
    matched = tuple(
        dimension
        for dimension in sorted(excluded_dimensions)
        if matches_topic_dimension(text, dimension)
    )
    if not matched:
        return ()
    if any(matches_topic_dimension(text, dimension) for dimension in own_dimensions):
        return ()
    return matched


def has_grounded_facet(text: str, facet: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    if facet == "reporting_period":
        return bool(_PERIOD_RE.search(normalized))
    if facet == "metric_result":
        if _METRIC_ROW_VALUE_RE.search(normalized):
            return True
        for match in _NUMBER_RE.finditer(normalized):
            tail = normalized[match.end() : match.end() + 12].strip()
            unit = _UNIT_RE.match(tail)
            if not unit:
                continue
            if unit.group(0) in _CADENCE_UNITS and _CADENCE_RE.search(
                normalized[max(0, match.start() - 8) : match.start()]
            ):
                continue
            return True
        return False
    return any(term in normalized for term in FACET_EVIDENCE_TERMS.get(facet, ()))


def grounded_facets(items: Iterable[EvidenceItem], facets: Iterable[str]) -> tuple[str, ...]:
    texts = [str(getattr(item, "raw_evidence_ko", "") or "") for item in items]
    return tuple(
        facet
        for facet in sorted(set(facets))
        if any(has_grounded_facet(text, facet) for text in texts)
    )


def verify_upstream_facets(
    *,
    covered_facets: Iterable[str],
    missing_facets: Iterable[str],
    contract_facets: Iterable[str],
    items: Iterable[EvidenceItem],
) -> dict[str, Any]:
    """Compare the producer's facet claims against the returned excerpts.

    Only facets this question actually requires are checked, and only when
    evidence came back at all - a question with no evidence has nothing to
    ground a claim in and is already reported as ``no_evidence``.
    """
    evidence = list(items)
    checked = sorted({str(facet) for facet in contract_facets})
    if not evidence or not checked:
        return {}
    claimed = {str(facet) for facet in covered_facets}
    declared_missing = {str(facet) for facet in missing_facets}
    grounded = set(grounded_facets(evidence, checked))
    overclaimed = sorted((claimed & set(checked)) - grounded)
    understated = sorted((declared_missing & set(checked)) & grounded)
    ungrounded_required = sorted(facet for facet in checked if facet not in grounded)
    verification: dict[str, Any] = {
        "checked_facets": checked,
        "grounded_facets": sorted(grounded),
        "ungrounded_facets": ungrounded_required,
    }
    if overclaimed:
        verification["overclaimed_facets"] = overclaimed
    if understated:
        verification["understated_facets"] = understated
    return verification
