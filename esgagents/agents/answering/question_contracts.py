from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuestionContract:
    pillar: str
    required_facets: tuple[str, ...]
    expected_facets: tuple[str, ...] = ()


def build_question_contract(planned: Any) -> QuestionContract:
    pillar = _canonical_pillar(getattr(planned, "pillar", ""))
    question_text = " ".join(
        str(value or "")
        for value in (
            getattr(planned, "item_ko", ""),
            getattr(planned, "description_ko", ""),
        )
    ).casefold()
    if pillar == "metrics":
        return QuestionContract(pillar, ("metric_result", "reporting_period"))
    if pillar == "governance":
        return QuestionContract(pillar, ("accountable_body", "role"), ("oversight_cadence",))
    if pillar == "risk_management":
        return QuestionContract(pillar, ("risk_identification", "control_or_response"), ("monitoring_follow_up",))
    expected = ("target",) if any(term in question_text for term in ("목표", "target", "달성", "감축")) else ()
    return QuestionContract("strategy", ("policy_or_direction",), expected)


def _canonical_pillar(value: str) -> str:
    normalized = (value or "").strip().casefold().replace("-", " ").replace("_", " ")
    if "metric" in normalized or "지표" in normalized:
        return "metrics"
    if "govern" in normalized or "거버넌스" in normalized:
        return "governance"
    if "risk" in normalized or "리스크" in normalized or "위험" in normalized:
        return "risk_management"
    return "strategy"
