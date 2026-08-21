from types import SimpleNamespace

import pytest

from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent
from esgagents.agents.evidence.evidence_normalizer import EvidenceNormalizerAgent
from esgagents.agents.evidence.metric_facts import (
    format_metric_number,
    metric_numbers_equivalent,
    resolve_metric_facts,
    salvage_conflicting_metric_claims,
    salvage_metric_narrative_without_values,
    salvage_unsupported_numeric_metric_claims,
)
from esgagents.default_config import load_config
from esgagents.schemas import (
    EvidenceItem,
    EvidenceFact,
    MetricEvidenceItem,
    RagQuestionResult,
    model_to_dict,
)
from skills.agents.writer import SkillWriterAgent


def _narrative(text: str) -> EvidenceItem:
    return EvidenceItem(
        raw_evidence_ko=text,
        source_name="report.pdf",
        source_path="ESG/report.pdf",
        semantic_label="useful",
        source_tier="tier_2_operational",
        document_status="approved",
    )


def _metric(
    text: str,
    *,
    block: str,
    role: str = "primary",
    entity: str = "Daewoong Pharm",
    entity_class: str = "daewoong_pharm",
    rank: int = 1,
) -> MetricEvidenceItem:
    return MetricEvidenceItem(
        raw_evidence_ko=text,
        source_name="metrics.xlsx",
        source_path="ESG/metrics.xlsx",
        semantic_label="metric_row",
        source_tier="tier_2_operational",
        source_type="operational_record",
        document_status="approved",
        table_block=block,
        block_rank=rank,
        block_role=role,
        entity=entity,
        entity_class=entity_class,
    )


def _planned(qid: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=qid,
        pillar="Metrics",
        item_ko="Metric disclosure",
        description_ko="Metric result and narrative",
        example_ko="",
    )


def test_decimal_rounding_uses_answer_precision():
    assert metric_numbers_equivalent("12,771.822", "12771.822287491")
    assert not metric_numbers_equivalent("12,771.821", "12771.822287491")


def test_metric_not_found_salvage_removes_values_but_keeps_years_and_iso_identifiers():
    answer = (
        "The company has operated ISO 14001 since 2022. "
        "In 2025, the water reuse rate was 9.34%."
    )

    salvaged, actions = salvage_unsupported_numeric_metric_claims(
        answer,
        {"metric_status": "not_found", "accepted_facts": []},
    )

    assert "ISO 14001" in salvaged
    assert "2022" in salvaged
    assert "9.34%" not in salvaged
    assert actions == ["removed_claim:unsupported_metric:c2"]
    assert format_metric_number("12771.822287491") == "12,771.822"


def test_metric_final_narrative_redacts_values_but_keeps_full_and_short_years():
    answer = (
        "ISO 14001 절차에 따라 2025년 환경 활동을 운영했습니다. "
        "23년 CP 위반자는 중징계(감봉 3개월 이상) 절차에 회부했습니다. "
        "재활용률은 9.34%였습니다."
    )

    salvaged, actions = salvage_metric_narrative_without_values(
        answer,
        {"accepted_facts": [{"value": "9.34"}]},
    )

    assert "ISO 14001" in salvaged
    assert "2025년" in salvaged
    assert "23년" in salvaged
    assert "9.34" not in salvaged
    assert "3개월" not in salvaged
    assert actions


def test_metric_final_narrative_keeps_context_dates_and_cadence_without_metric_values():
    answer = (
        "2025년에는 상반기 3월 20일, 하반기 10월 22일에 진행하였습니다. "
        "해당 위원회에서는 총 23개(상반기 11개, 하반기 12개)의 안건을 논의하였습니다. "
        "용수 재사용률은 2025년 9.34%를 달성했습니다."
    )

    salvaged, actions = salvage_metric_narrative_without_values(
        answer,
        {"accepted_facts": [{"value": "23"}, {"value": "9.34"}]},
    )

    assert "3월 20일" in salvaged
    assert "10월 22일" in salvaged
    assert "상·하반기에 걸쳐 여러 안건" in salvaged
    assert "23개" not in salvaged
    assert "11개" not in salvaged
    assert "12개" not in salvaged
    assert "9.34" not in salvaged
    assert "여러 (" not in salvaged
    assert actions


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"scope": "Factory A"}, {"scope": "Factory B"}),
        ({"value_role": "actual"}, {"value_role": "target"}),
        ({"locator": {"section": "Scope 1"}}, {"locator": {"section": "Scope 2"}}),
    ],
)
def test_scope_role_and_locator_dimensions_do_not_create_false_conflicts(first, second):
    item = _metric("Metric table", block="Emissions")
    item.facts = [
        EvidenceFact(metric="Emissions", period="2025", value="10", unit="tCO2e", **first),
        EvidenceFact(metric="Emissions", period="2025", value="20", unit="tCO2e", **second),
    ]

    audit = resolve_metric_facts([item])

    assert audit["conflict_count"] == 0
    assert audit["accepted_fact_count"] == 2


def test_real_conflict_removes_only_the_related_metric_claim():
    item = _metric("Metric table", block="Emissions")
    item.facts = [
        EvidenceFact(metric="Scope 1", period="2025", value="10", unit="tCO2e", scope="Group"),
        EvidenceFact(metric="Scope 1", period="2025", value="20", unit="tCO2e", scope="Group"),
        EvidenceFact(metric="Energy use", period="2025", value="10", unit="MWh", scope="Group"),
    ]
    audit = resolve_metric_facts([item])

    revised, actions = salvage_conflicting_metric_claims(
        "Scope 1 was 10 tCO2e in 2025. Energy use was 10 MWh in 2025.",
        audit,
    )

    assert "Scope 1" not in revised
    assert "Energy use was 10 MWh" in revised
    assert actions == ["removed_claim:conflicting_metric:c1"]


def test_metric_contract_fields_and_unknown_metadata_survive_model_dump():
    result = RagQuestionResult.model_validate(
        {
            "question_id": "Q039",
            "metric_expected": True,
            "metric_status": "found_table",
            "metric_summary": {"n_rows": 1, "n_blocks": 1, "future_count": 7},
            "metric_confidence": None,
            "metric_evidence": [
                {
                    **model_to_dict(_metric("Water use | ton | 2025=10", block="Water")),
                    "future_metric_tag": "kept",
                }
            ],
            "narrative_evidence": [model_to_dict(_narrative("Boundary changed in 2024."))],
        }
    )

    dumped = model_to_dict(result)
    assert dumped["metric_status"] == "found_table"
    assert dumped["metric_summary"]["future_count"] == 7
    assert dumped["metric_evidence"][0]["future_metric_tag"] == "kept"
    assert dumped["narrative_evidence"][0]["raw_evidence_ko"] == "Boundary changed in 2024."


@pytest.mark.parametrize("metric_form", [None, "", "   "])
def test_empty_metric_form_uses_current_table_row_contract_default(metric_form):
    result = RagQuestionResult.model_validate(
        {
            "question_id": "Q039",
            "metric_expected": True,
            "metric_status": "found_table",
            "metric_evidence": [
                {
                    **model_to_dict(_metric("Water use | ton | 2025=10", block="Water")),
                    "metric_form": metric_form,
                }
            ],
        }
    )

    normalized = EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {"rag_results": {"Q039": result}}
    )["normalized_evidence"]["Q039"]

    assert result.metric_evidence[0].metric_form == "table_row"
    assert normalized["metric_audit"]["accepted_fact_count"] == 1
    assert not any(
        "unsupported metric_form" in warning
        for warning in normalized["metric_audit"]["metric_contract_warnings"]
    )


def test_found_table_uses_only_primary_rows_and_keeps_entities_separate():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            _metric("Water use | ton | 2025=10", block="Pharm water"),
            _metric(
                "Water use | ton | 2025=20",
                block="Group water",
                entity="Daewoong Group",
                entity_class="group_total",
                rank=2,
            ),
            _metric("Sales | KRW | 2025=100", block="Pharm water", role="denominator"),
            _metric(
                "Water use | ton | 2025=3",
                block="Factory water",
                role="scope_variant",
                entity="Factory A",
                entity_class="factory",
                rank=3,
            ),
        ],
        narrative_evidence=[_narrative("The reporting boundary changed in 2024.")],
    )

    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]
    audit = normalized["metric_audit"]

    assert audit["accepted_fact_count"] == 2
    assert audit["conflict_count"] == 0
    assert {fact["entity_class"] for fact in audit["accepted_facts"]} == {
        "daewoong_pharm",
        "group_total",
    }
    assert audit["denominator_row_count"] == 1
    assert audit["scope_variant_row_count"] == 1
    assert len(normalized["metric_items"]) == 2
    assert normalized["items"] == normalized["narrative_items"]
    assert all(
        item.semantic_label.casefold() != "metric_row"
        for item in normalized["items"]
    )


def test_normalizer_withholds_unanswered_assessment_checklist_from_writer_items():
    config = load_config({"agent_mode": "offline"})
    operational = _narrative(
        "대웅제약은 ISO14001 환경경영시스템에 따라 환경 관리 절차를 운영하고 있습니다."
    )
    checklist = EvidenceItem(
        raw_evidence_ko=(
            "9. 환경권 보장. 회사는 환경경영체제를 수립 및 유지하고 있다. "
            "환경개선을 위한 측정 가능한 목표를 설정하고 정기적으로 점검한다."
        ),
        source_name="(1차 평가完) 20260518 대웅제약 인권영향평가.xlsx",
        source_path="assessments/인권영향평가.xlsx",
        source_tier="tier_3_assessment",
        source_type="external_assessment",
        document_status="external_assessment",
        semantic_label="partial",
    )
    rag = RagQuestionResult(
        question_id="Q020",
        answer_status="high_confidence",
        metric_expected=False,
        metric_status="not_expected",
        items=[operational, checklist],
    )

    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q020": rag}}
    )["normalized_evidence"]["Q020"]

    assert [item.raw_evidence_ko for item in normalized["items"]] == [
        operational.raw_evidence_ko
    ]
    assert [item.raw_evidence_ko for item in normalized["narrative_items"]] == [
        operational.raw_evidence_ko
    ]
    assert [item.raw_evidence_ko for item in normalized["withheld_assessment_criteria"]] == [
        checklist.raw_evidence_ko
    ]


def test_q039_full_fixture_preserves_23_rows_and_five_primary_blocks():
    config = load_config({"agent_mode": "offline"})
    primary_rows = []
    row_number = 1
    for block_rank, block_size in enumerate((5, 4, 3, 3, 2), start=1):
        entity_class = "daewoong_pharm" if block_rank % 2 else "group_total"
        entity = "Daewoong Pharm" if block_rank % 2 else "Daewoong Group"
        for _ in range(block_size):
            primary_rows.append(
                _metric(
                    f"Water metric {row_number} | ton | 2025={row_number}",
                    block=f"Water block {block_rank}",
                    entity=entity,
                    entity_class=entity_class,
                    rank=block_rank,
                )
            )
            row_number += 1
    scope_rows = [
        _metric(
            f"Factory metric {index} | ton | 2025={index}",
            block=f"Water block {index}",
            role="scope_variant",
            entity=f"Factory {index}",
            entity_class="factory",
            rank=index,
        )
        for index in range(1, 5)
    ]
    denominator_rows = [
        _metric(
            f"Sales denominator {index} | KRW | 2025={index * 100}",
            block=f"Water block {index}",
            role="denominator",
            rank=index,
        )
        for index in range(1, 3)
    ]
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="found_table",
        metric_summary={
            "n_rows": 23,
            "n_blocks": 5,
            "n_primary": 17,
            "n_scope_variant": 4,
            "n_denominator": 2,
        },
        metric_evidence=[*primary_rows, *scope_rows, *denominator_rows],
        narrative_evidence=[_narrative("The reporting boundary changed in 2024.")],
    )

    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]
    audit = normalized["metric_audit"]

    assert len(normalized["metric_evidence"]) == 23
    assert audit["accepted_fact_count"] == 17
    assert audit["primary_row_count"] == 17
    assert audit["scope_variant_row_count"] == 4
    assert audit["denominator_row_count"] == 2
    assert len({fact["table_block"] for fact in audit["accepted_facts"]}) == 5


def test_found_table_invalid_primary_identity_is_warned_and_excluded():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            _metric(
                "Water use | ton | 2025=10",
                block="Unknown",
                entity="",
                entity_class="",
            )
        ],
    )
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]
    assert normalized["metric_audit"]["accepted_fact_count"] == 0
    assert any(
        "missing entity identity" in warning
        for warning in normalized["metric_audit"]["metric_contract_warnings"]
    )


def test_metric_summary_mismatch_uses_actual_evidence_counts_and_requests_warning():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        metric_summary={
            "n_rows": 99,
            "n_blocks": 3,
            "n_primary": 2,
            "n_scope_variant": 0,
            "n_denominator": 0,
        },
        metric_evidence=[
            _metric("Water use | ton | 2025=10", block="Water"),
        ],
    )

    audit = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]["metric_audit"]

    assert audit["metric_summary_actual"] == {
        "n_rows": 1,
        "n_blocks": 1,
        "n_primary": 1,
        "n_scope_variant": 0,
        "n_denominator": 0,
    }
    assert audit["metric_summary_mismatches"] == {
        "n_rows": {"expected": 99, "actual": 1},
        "n_blocks": {"expected": 3, "actual": 1},
        "n_primary": {"expected": 2, "actual": 1},
    }
    assert any(
        warning.startswith("metric_summary_mismatch:n_rows:")
        for warning in audit["metric_contract_warnings"]
    )

    planned = _planned("Q039")
    result = SkillWriterAgent({"agent_mode": "offline"}, None).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {
                "Q039": {
                    "accepted": True,
                    "metric_audit": audit,
                    "metric_absence": {},
                    "evidence_items": [],
                    "output_language": "English",
                }
            },
            "evidence_gate": {"Q039": {"accepted": True, "reason": "accepted"}},
            "rag_results": {"Q039": rag},
            "normalized_evidence": {"Q039": {"metric_audit": audit}},
        }
    )
    assert "metric_summary_mismatch" in result["quality_flags"]["Q039"]
    assert "human_review_required" in result["quality_flags"]["Q039"]


def test_metric_summary_block_count_uses_only_primary_blocks():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        metric_summary={
            "n_rows": 3,
            "n_blocks": 1,
            "n_primary": 1,
            "n_scope_variant": 1,
            "n_denominator": 1,
        },
        metric_evidence=[
            _metric("Water use | ton | 2025=10", block="Primary water"),
            _metric(
                "Factory water | ton | 2025=3",
                block="Factory water",
                role="scope_variant",
            ),
            _metric(
                "Sales | KRW | 2025=100",
                block="Sales denominator",
                role="denominator",
            ),
        ],
    )

    audit = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]["metric_audit"]

    assert audit["metric_summary_actual"]["n_blocks"] == 1
    assert audit["metric_summary_mismatches"] == {}


@pytest.mark.parametrize(
    ("updates", "warning_fragment"),
    [
        ({"table_block": ""}, "missing table_block"),
        ({"metric_form": "inline_figure"}, "unsupported metric_form"),
    ],
)
def test_primary_metric_row_outside_table_contract_is_audit_only(
    updates, warning_fragment
):
    config = load_config({"agent_mode": "offline"})
    item = _metric("Water use | ton | 2025=10", block="Water")
    item = item.model_copy(update=updates)
    rag = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[item],
    )

    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]

    assert normalized["metric_items"] == []
    assert normalized["metric_audit"]["accepted_facts"] == []
    assert len(normalized["metric_evidence"]) == 1
    assert any(
        warning_fragment in warning
        for warning in normalized["metric_audit"]["metric_contract_warnings"]
    )


@pytest.mark.parametrize("reason", ["no_candidate", "below_threshold", "blocked_by_gate"])
def test_not_found_with_insufficient_status_is_blocked_by_evidence_gate(reason):
    config = load_config({"agent_mode": "offline"})
    qid = "Q095"
    narrative = _narrative("The company operates stakeholder communication channels.")
    rag = RagQuestionResult.model_validate(
        {
            "question_id": qid,
            "answer_status": "insufficient",
            "metric_expected": True,
            "metric_status": "not_found",
            "metric_absence": {"reason": reason, "n_candidates_seen": 4},
            "items": [model_to_dict(narrative)],
        }
    )
    planned = _planned(qid)

    gate = EvidenceGateAgent(config).run(
        {"planned_questions": [planned], "rag_results": {qid: rag}}
    )["evidence_gate"][qid]
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {qid: rag}}
    )["normalized_evidence"][qid]
    context = {
        "accepted": gate["accepted"],
        "metric_audit": normalized["metric_audit"],
        "metric_absence": normalized["metric_audit"]["metric_absence"],
        "evidence_items": normalized["narrative_items"],
        "output_language": "English",
    }
    writer = SkillWriterAgent({"agent_mode": "offline"}, None)
    result = writer.run(
        {
            "planned_questions": [planned],
            "skill_contexts": {qid: context},
            "evidence_gate": {qid: gate},
            "rag_results": {qid: rag},
            "normalized_evidence": {qid: normalized},
        }
    )

    assert gate["accepted"] is False
    assert normalized["metric_audit"]["accepted_facts"] == []
    assert result["final_answers"][qid] == ""
    assert gate["reason"] in result["quality_flags"][qid]


def test_low_metric_confidence_withholds_numeric_facts_and_requests_review():
    config = load_config({"agent_mode": "offline"})
    qid = "Q019"
    rag = RagQuestionResult(
        question_id=qid,
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="found_table",
        metric_confidence="low",
        metric_evidence=[_metric("Incidents | count | 2025=4", block="Incidents")],
        narrative_evidence=[_narrative("The company maintains an incident response process.")],
    )
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {qid: rag}}
    )["normalized_evidence"][qid]
    audit = normalized["metric_audit"]
    assert audit["accepted_facts"] == []
    assert audit["withheld_facts"]
    assert audit["numeric_withheld"] is True

    planned = _planned(qid)
    writer = SkillWriterAgent({"agent_mode": "offline"}, None)
    result = writer.run(
        {
            "planned_questions": [planned],
            "skill_contexts": {
                qid: {
                    "accepted": True,
                    "metric_audit": audit,
                    "metric_absence": {},
                    "evidence_items": normalized["narrative_items"],
                    "output_language": "English",
                }
            },
            "evidence_gate": {qid: {"accepted": True, "reason": "accepted"}},
            "rag_results": {qid: rag},
            "normalized_evidence": {qid: normalized},
        }
    )
    assert "2025=4" not in result["final_answers"][qid]
    assert result["final_answers"][qid].startswith(
        "The company maintains an incident response process"
    )
    assert "metric_low_confidence" in result["quality_flags"][qid]
    assert "human_review_required" in result["quality_flags"][qid]


def test_metric_expected_and_status_route_final_answer_sources_separately():
    config = load_config({"agent_mode": "offline"})
    narrative = _narrative("The company monitors water risks and reporting boundaries.")
    legacy = _narrative("The company maintains a legacy qualitative policy.")
    results = {
        "Q001": RagQuestionResult(
            question_id="Q001",
            metric_expected=False,
            metric_status="not_expected",
            items=[legacy],
        ),
        "Q039": RagQuestionResult(
            question_id="Q039",
            metric_expected=True,
            metric_status="found_table",
            metric_evidence=[
                _metric("Water use | ton | 2025=10", block="Water")
            ],
            narrative_evidence=[narrative],
            items=[
                _metric("Water use | ton | 2025=10", block="Water"),
                narrative,
            ],
        ),
        "Q095": RagQuestionResult(
            question_id="Q095",
            metric_expected=True,
            metric_status="not_found",
            metric_absence={"reason": "below_threshold"},
            items=[legacy],
            narrative_evidence=[narrative],
        ),
    }

    normalized = EvidenceNormalizerAgent(config).run({"rag_results": results})[
        "normalized_evidence"
    ]

    assert [item.raw_evidence_ko for item in normalized["Q001"]["items"]] == [
        legacy.raw_evidence_ko
    ]
    assert [item.raw_evidence_ko for item in normalized["Q039"]["items"]] == [
        narrative.raw_evidence_ko
    ]
    assert normalized["Q039"]["metric_audit"]["accepted_facts"]
    assert [item.raw_evidence_ko for item in normalized["Q095"]["items"]] == [
        legacy.raw_evidence_ko
    ]
    assert [
        item.raw_evidence_ko
        for item in normalized["Q095"]["narrative_evidence"]
    ] == [narrative.raw_evidence_ko]
    assert normalized["Q095"]["metric_audit"]["accepted_facts"] == []


def test_not_found_writer_uses_items_and_ignores_narrative_evidence():
    config = load_config({"agent_mode": "offline"})
    qid = "Q095"
    item_evidence = _narrative(
        "The company engages stakeholders through employee surveys."
    )
    forbidden_narrative = _narrative(
        "Narrative evidence says 37 stakeholder meetings were held."
    )
    rag = RagQuestionResult(
        question_id=qid,
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="not_found",
        metric_absence={"reason": "below_threshold"},
        items=[item_evidence],
        narrative_evidence=[forbidden_narrative],
    )
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {qid: rag}}
    )["normalized_evidence"][qid]
    planned = _planned(qid)

    result = SkillWriterAgent({"agent_mode": "offline"}, None).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {
                qid: {
                    "accepted": True,
                    "metric_audit": normalized["metric_audit"],
                    "metric_absence": normalized["metric_audit"]["metric_absence"],
                    "evidence_items": normalized["narrative_items"],
                    "output_language": "English",
                }
            },
            "evidence_gate": {qid: {"accepted": True, "reason": "accepted"}},
            "rag_results": {qid: rag},
            "normalized_evidence": {qid: normalized},
        }
    )

    assert result["final_answers"][qid] == item_evidence.raw_evidence_ko
    assert "37" not in result["final_answers"][qid]
    assert "metric_not_found" in result["quality_flags"][qid]


def test_not_found_writer_preserves_inline_number_from_items_prose():
    config = load_config({"agent_mode": "offline"})
    qid = "Q011"
    item_evidence = _narrative(
        "2025년 내부 이해관계자 인권 관련 접수된 고충처리는 "
        "63건으로 확인되었으며 63건 모두 처리가 완료되었습니다."
    )
    rag = RagQuestionResult(
        question_id=qid,
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="not_found",
        metric_absence={"reason": "below_threshold"},
        items=[item_evidence],
    )
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {qid: rag}}
    )["normalized_evidence"][qid]
    planned = _planned(qid)

    result = SkillWriterAgent({"agent_mode": "offline"}, None).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {
                qid: {
                    "accepted": True,
                    "metric_audit": normalized["metric_audit"],
                    "metric_absence": normalized["metric_audit"]["metric_absence"],
                    "evidence_items": normalized["narrative_items"],
                    "output_language": "Korean",
                }
            },
            "evidence_gate": {qid: {"accepted": True, "reason": "accepted"}},
            "rag_results": {qid: rag},
            "normalized_evidence": {qid: normalized},
        }
    )

    assert "63건" in result["final_answers"][qid]
    assert "처리가 완료" in result["final_answers"][qid]
    assert "metric_not_found" in result["quality_flags"][qid]


def test_metric_narrative_drops_redaction_artifacts_but_keeps_qualitative_context():
    answer = (
        "대웅그룹은 ISO 14001 환경경영시스템 인증을 취득하여 표준 절차에 따라 환경보호를 추진하고 있습니다. "
        "용수 재사용률은 2024년 7.23%, 2025년 9.34%를 달성하였습니다. "
        "매년 재사용률 향상과 대기 및 수질오염 물질 원단위 감소를 목표로 관리하고 있습니다."
    )

    result, actions = salvage_metric_narrative_without_values(answer, {"accepted_facts": []})

    assert "ISO 14001" in result
    assert "해당 비율" not in result
    assert "7.23" not in result
    assert "9.34" not in result
    assert "용수 재사용률" not in result
    assert any(action.startswith("removed_claim:unsupported_metric") for action in actions)


def test_metric_narrative_drops_related_cases_redaction_artifact():
    answer = (
        "2025년 내부 이해관계자로부터 접수된 인권 관련 고충처리는 63건이며, "
        "해당 건 모두 처리가 완료되었습니다."
    )

    result, actions = salvage_metric_narrative_without_values(answer, {"accepted_facts": []})

    assert "관련 건" not in result
    assert "63" not in result
    assert result == ""
    assert actions == ["removed_claim:unsupported_metric:c1"]


def test_metric_narrative_rewrites_grievance_case_count_as_qualitative_completion():
    answer = (
        "2025년 내부 이해관계자 인권 관련 접수된 고충처리는 "
        "63건으로 확인되었으며 63건 모두 처리가 완료되었습니다."
    )

    result, actions = salvage_metric_narrative_without_values(answer, {"accepted_facts": []})

    assert result == "2025년 내부 이해관계자 인권 관련 고충이 접수되었으며 접수된 고충은 모두 처리 완료되었습니다."
    assert "63" not in result
    assert "접수 건" not in result
    assert actions == ["redacted_claim:unsupported_metric:c1"]


def test_metric_narrative_rewrites_board_count_placeholders_naturally():
    answer = (
        "대웅그룹의 이사회는 대표이사를 포함하여 6인으로 구성되어 있으며, "
        "정관에 따라 이사회는 3명 이상 9명 이내로 구성하며, "
        "독립이사는 이사 총수의 3분의 1 이상으로 유지하도록 규정하고 있습니다."
    )

    result, _ = salvage_metric_narrative_without_values(answer, {"accepted_facts": []})

    assert "복수의 인원으로 구성" not in result
    assert "복수의 인원 이상 복수의 인원 이내" not in result
    assert "일정 비율" not in result
    assert "대웅그룹은 대표이사를 포함한 이사회를 운영" in result
    assert "정관상 정해진 범위" in result
    assert "정관상 최소 비율 이상" in result


def test_metric_narrative_rewrites_repeated_area_placeholder():
    answer = "평가는 운영, 환경, 인권 노동의 3개 영역, 총 26개 세부 항목으로 구성됩니다."

    result, _ = salvage_metric_narrative_without_values(answer, {"accepted_facts": []})

    assert "여러 영역 여러 세부 항목" not in result
    assert "운영, 환경, 인권·노동의 여러 영역의 세부 항목" in result


def test_prose_figure_belonging_to_another_legal_entity_is_removed():
    """Regression for Q023: source documents carry one paragraph per legal entity,
    identical but for the subject and the numbers. The answer named the subsidiary
    and quoted the group's recycling rate."""

    from esgagents.agents.evidence.metric_facts import (
        entity_misattributed_numeric_claims,
        salvage_entity_misattributed_claims,
    )

    evidence = [
        {
            "raw_evidence_ko": (
                "환경경영 성과 ㈜ 대웅그룹은 ISO14001 인증 취득 후 환경보호를 위해 노력하고 있습니다. "
                "폐기물 배출량 대비 재활용률은 2024년 89.2%, 2025년 89.1%를 달성하였습니다."
            )
        },
        {
            "raw_evidence_ko": (
                "환경경영 성과 ㈜ 대웅제약은 ISO14001 인증 취득 후 환경보호를 위해 노력하고 있습니다. "
                "폐기물 배출량 대비 재활용률은 2023년 34.1%, 2024년 50.9%를 달성하였습니다."
            )
        },
    ]
    answer = (
        "대웅제약은 ISO 14001 환경경영시스템 인증을 통해 환경 보호를 추진하고 있습니다. "
        "폐기물 재활용률: 2024년 89.2%에서 2025년 89.1%를 달성하였습니다."
    )

    misattributed = entity_misattributed_numeric_claims(answer, evidence)
    cleaned, actions = salvage_entity_misattributed_claims(answer, evidence)

    assert len(misattributed) == 1
    assert "89.2%" in misattributed[0]
    assert "89.2%" not in cleaned
    assert "89.1%" not in cleaned
    assert cleaned.startswith("대웅제약은 ISO 14001")
    assert any("entity_misattributed_metric" in action for action in actions)


def test_prose_figure_matching_the_named_entity_is_kept():
    from esgagents.agents.evidence.metric_facts import (
        entity_misattributed_numeric_claims,
        salvage_entity_misattributed_claims,
    )

    evidence = [
        {
            "raw_evidence_ko": (
                "환경경영 성과 ㈜ 대웅그룹은 재활용률은 2024년 89.2%를 달성하였습니다."
            )
        },
        {
            "raw_evidence_ko": (
                "환경경영 성과 ㈜ 대웅제약은 재활용률은 2024년 50.9%를 달성하였습니다."
            )
        },
    ]
    answer = "대웅제약은 폐기물 재활용률 2024년 50.9%를 달성하였습니다."

    assert entity_misattributed_numeric_claims(answer, evidence) == []
    assert salvage_entity_misattributed_claims(answer, evidence) == (answer, [])


def test_answer_without_a_named_entity_is_not_flagged():
    from esgagents.agents.evidence.metric_facts import entity_misattributed_numeric_claims

    evidence = [{"raw_evidence_ko": "㈜ 대웅그룹은 재활용률은 2024년 89.2%를 달성하였습니다."}]

    assert entity_misattributed_numeric_claims("재활용률은 2024년 89.2%입니다.", evidence) == []
