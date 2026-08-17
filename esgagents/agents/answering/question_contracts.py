from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuestionContract:
    pillar: str
    required_facets: tuple[str, ...]
    expected_facets: tuple[str, ...] = ()
    metric_dimensions: tuple[str, ...] = ()


METRIC_DIMENSIONS_BY_QID: dict[str, tuple[str, ...]] = {
    "Q007": ("occupational_accident_count", "ltifr", "safety_training"),
    "Q011": ("human_rights_grievances",),
    "Q015": ("product_recall_count", "product_safety_incident_count", "quality_complaint_count"),
    "Q019": ("privacy_breach_count", "data_leak_incident_count", "security_violation_count"),
    "Q023": (
        "water_reuse_rate",
        "waste_recycling_rate",
        "environmental_violation_count",
        "environmental_accident_count",
    ),
    "Q027": ("ethics_violation_reports", "corruption_incidents", "whistleblowing_cases_resolved"),
    "Q031": ("scope_1_emissions", "scope_2_emissions", "scope_3_emissions", "energy_use"),
    "Q035": ("waste_generation", "waste_recycling_rate"),
    "Q039": ("water_consumption", "water_reuse_rate", "wastewater_discharge"),
    "Q043": ("habitat_protection_activity", "ecosystem_restoration_activity"),
    "Q047": ("air_pollutant_emissions", "water_pollutant_emissions"),
    "Q051": ("eco_friendly_product_count", "environmental_certification_count"),
    "Q055": ("product_recovery_recycling", "environmental_regulatory_response"),
    "Q059": ("employee_training_hours", "training_investment", "turnover_rate"),
    "Q063": ("workforce_gender_mix", "workforce_age_mix", "female_manager_ratio"),
    "Q067": (
        "managed_supplier_count",
        "supplier_esg_assessment_count",
        "supplier_improvement_support",
    ),
    "Q071": ("community_investment", "volunteer_participation"),
    "Q075": ("committee_meeting_count", "committee_activity_count"),
    "Q079": (
        "board_composition",
        "independent_director_ratio",
        "board_meeting_count",
        "board_attendance_rate",
    ),
    "Q083": ("esg_target", "esg_target_progress"),
    "Q087": ("compliance_violation_cases", "fine_amount", "compliance_training"),
    "Q091": ("shareholder_composition", "dividend_policy", "shareholder_meeting"),
    "Q095": ("stakeholder_communication_activity",),
}


QUESTION_CONTRACTS_BY_QID: dict[str, QuestionContract] = {
    "Q021": QuestionContract(
        "governance",
        (
            "accountable_body",
            "role",
            "operating_organization",
            "site_management_system",
        ),
        ("oversight_cadence",),
    ),
    "Q074": QuestionContract(
        "risk_management",
        ("risk_identification", "control_or_response"),
        ("monitoring_follow_up",),
    ),
}


def build_question_contract(planned: Any) -> QuestionContract:
    qid = str(getattr(planned, "id", ""))
    if qid in QUESTION_CONTRACTS_BY_QID:
        return QUESTION_CONTRACTS_BY_QID[qid]
    pillar = _canonical_pillar(getattr(planned, "pillar", ""))
    question_text = " ".join(
        str(value or "")
        for value in (
            getattr(planned, "item_ko", ""),
            getattr(planned, "description_ko", ""),
        )
    ).casefold()
    if pillar == "metrics":
        return QuestionContract(
            pillar,
            ("metric_result", "reporting_period"),
            metric_dimensions=METRIC_DIMENSIONS_BY_QID.get(qid, ()),
        )
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
