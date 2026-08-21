from types import SimpleNamespace

from esgagents.agents.answering.attribution import (
    salvage_source_overstatement,
    salvage_supported_claims,
)
from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent
from esgagents.agents.evidence.evidence_normalizer import EvidenceNormalizerAgent
from esgagents.agents.evidence.metric_facts import resolve_metric_facts
from esgagents.default_config import load_config
from esgagents.schemas import EvidenceItem, RagQuestionResult, SkillDraft
from skills.agents.writer import SkillWriterAgent


def _planned(qid: str = "Q039") -> SimpleNamespace:
    return SimpleNamespace(
        id=qid,
        pillar="Metrics",
        item_ko="Metric performance",
        description_ko="Metric result and period",
        example_ko="",
    )


def _item(text: str, **updates) -> EvidenceItem:
    values = {
        "raw_evidence_ko": text,
        "source_name": "metrics.xlsx",
        "source_path": "ESG/metrics.xlsx",
        "semantic_label": "metric_row",
        "source_tier": "tier_2_operational",
        "document_status": "approved",
    }
    values.update(updates)
    return EvidenceItem(**values)


def test_optional_coverage_hints_do_not_change_eligibility():
    config = load_config({"agent_mode": "offline"})
    planned = _planned()
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        normalized_answer_ko="A supported answer.",
        items=[_item("Water use | t | 2025=10")],
        answerable=False,
        coverage_status="no_evidence",
        missing_facets=["metric_result"],
        is_v3_payload=True,
    )

    result = EvidenceGateAgent(config).run(
        {"planned_questions": [planned], "rag_results": {planned.id: rag}}
    )

    assert result["evidence_gate"][planned.id]["accepted"] is True
    assert result["upstream_coverage_mismatches"][planned.id] is True
    assert result["upstream_hints"][planned.id] == {
        "answerable": False,
        "coverage_status": "no_evidence",
        "missing_facets": ["metric_result"],
    }


def test_minimal_v3_result_without_coverage_hints_is_eligible():
    config = load_config({"agent_mode": "offline"})
    planned = _planned()
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        normalized_answer_ko="A supported answer.",
        items=[_item("Water use | t | 2025=10")],
        is_v3_payload=True,
    )

    result = EvidenceGateAgent(config).run(
        {"planned_questions": [planned], "rag_results": {planned.id: rag}}
    )

    assert result["evidence_gate"][planned.id]["accepted"] is True
    assert result["upstream_coverage_mismatches"][planned.id] is False


def test_provenance_fallback_is_preserved_without_fake_source_path():
    config = load_config({"agent_mode": "offline"})
    planned = _planned()
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        normalized_answer_ko="A supported answer.",
        items=[
            _item(
                "Water use | t | 2025=10",
                source_path="",
                canonical_source_id="src-water-2025",
            )
        ],
        is_v3_payload=True,
    )

    gate = EvidenceGateAgent(config).run(
        {"planned_questions": [planned], "rag_results": {planned.id: rag}}
    )["evidence_gate"][planned.id]
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {planned.id: rag}}
    )["normalized_evidence"][planned.id]

    assert gate["accepted"] is True
    assert normalized["sources"][0]["source_path"] == ""
    assert normalized["sources"][0]["provenance_method"] == "canonical_source_id"
    assert normalized["sources"][0]["provenance_fallback"] is True


def test_metric_parser_handles_numeric_forms_and_malformed_rows_independently():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        items=[
            _item("Water use | % | 2021=0 | 2022=-1.25% | 2023=1,234.50"),
            _item("Malformed metric row"),
        ],
    )

    audit = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]["metric_audit"]

    assert audit["metric_row_count"] == 2
    assert audit["parsed_metric_row_count"] == 1
    assert audit["malformed_metric_row_count"] == 1
    assert {fact["normalized_value"] for fact in audit["accepted_facts"]} == {
        "0",
        "-1.25",
        "1234.5",
    }


def test_metric_conflicts_are_isolated_and_safe_facts_remain():
    items = [
        _item("Water use | t | 2025=10", source_path="ESG/a.xlsx"),
        _item("Water use | t | 2025=11", source_path="ESG/b.xlsx"),
        _item("Water reuse | % | 2025=25", source_path="ESG/c.xlsx"),
    ]
    normalized_items = EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {
            "rag_results": {
                "Q039": RagQuestionResult(
                    question_id="Q039",
                    answer_status="medium_confidence",
                    items=items,
                )
            }
        }
    )["normalized_evidence"]["Q039"]["items"]

    audit = resolve_metric_facts(normalized_items)

    assert audit["conflict_count"] == 1
    assert audit["accepted_fact_count"] == 1
    assert audit["accepted_facts"][0]["metric"] == "Water reuse"
    assert audit["all_numeric_facts_conflicted"] is False


def test_writer_uses_non_conflicting_structured_facts_without_llm():
    context = {
        "metric_audit": {
            "accepted_facts": [
                {
                    "metric": "Water reuse",
                    "period": "2025",
                    "value": "25",
                    "normalized_value": "25",
                    "unit": "%",
                }
            ]
        },
        "output_language": "English",
    }
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        normalized_answer_ko="",
    )

    answer, flags = SkillWriterAgent({"agent_mode": "offline"}, None)._draft_answer(context, rag)

    assert "Water reuse" in answer
    assert "2025" in answer
    assert "25 %" in answer
    assert flags == ["structured_metric_fallback"]


def test_found_table_writer_replaces_stub_with_narrative_fallback():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(final_answer="1.", quality_flags=[])

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    context = {
        "system_prompt": "Write a grounded metric answer.",
        "user_prompt": "Use only accepted facts.",
        "metric_audit": {
            "accepted_facts": [
                {
                    "metric": "Water reuse",
                    "period": "2025",
                    "value": "25",
                    "normalized_value": "25",
                    "unit": "%",
                }
            ]
        },
        "question": "Water management approach",
        "description": "Describe the qualitative management approach.",
        "evidence_items": [
            _item(
                "The company manages water risks through site-level monitoring and governance.",
                semantic_label="useful",
            )
        ],
        "output_language": "English",
    }
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        metric_status="found_table",
    )

    answer, flags = SkillWriterAgent({}, LLM())._draft_answer(context, rag)

    assert answer == "The company manages water risks through site-level monitoring and governance."
    assert "non_substantive_llm_output" in flags
    assert "evidence_extract_fallback" in flags


def test_found_table_writer_keeps_supported_narrative_without_table_metric():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="The company manages water risks through site-level monitoring.",
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    context = {
        "system_prompt": "Write a grounded metric answer.",
        "user_prompt": "Use accepted facts and evidence.",
        "metric_audit": {
            "accepted_facts": [
                {
                    "metric": "Water reuse",
                    "period": "2025",
                    "value": "25",
                    "normalized_value": "25",
                    "unit": "%",
                }
            ]
        },
        "question": "Water use status",
        "description": "Describe water use and reuse rate.",
        "evidence_items": [
            _item(
                "The company manages water risks through site-level monitoring.",
                semantic_label="useful",
            )
        ],
        "output_language": "English",
    }
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        metric_status="found_table",
    )

    answer, flags = SkillWriterAgent({}, LLM())._draft_answer(context, rag)

    assert answer.startswith("The company manages water risks")
    assert "Water reuse" not in answer
    assert "25 %" not in answer
    assert "structured_metric_fallback" not in flags


def test_found_table_writer_removes_unsupported_numeric_claims_and_uses_narrative_only():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer=(
                    "In 2025, waste generation totaled 1,250 tons. "
                    "The company manages water risks through site-level monitoring."
                ),
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = _planned("Q039")
    context = {
        "system_prompt": "Write a grounded metric answer.",
        "user_prompt": "Use accepted facts and evidence.",
        "accepted": True,
        "metric_audit": {
            "metric_status": "found_table",
            "accepted_facts": [
                {
                    "metric": "Water reuse",
                    "period": "2025",
                    "value": "25",
                    "normalized_value": "25",
                    "unit": "%",
                }
            ],
        },
        "question": "Water use status",
        "description": "Describe water use and reuse rate.",
        "evidence_items": [
            _item(
                "The company manages water risks through site-level monitoring.",
                semantic_label="useful",
            )
        ],
        "output_language": "English",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        metric_status="found_table",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "1,250" not in answer
    assert "Water reuse" not in answer
    assert "25 %" not in answer
    assert answer == "The company manages water risks through site-level monitoring."
    assert "claim_salvage_applied" in result["quality_flags"][planned.id]


def test_writer_preserves_specific_follow_up_channel_even_when_monitoring_facet_present():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer=(
                    "회사는 위험요인을 평가하고 개선대책을 이행하며 "
                    "분기별 안전보건회의를 운영합니다."
                ),
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q006",
        pillar="Risk Management",
        item_ko="안전보건 리스크 관리",
        description_ko="위험성 평가와 개선 후 후속관리 현황",
        example_ko="",
    )
    context = {
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_expected", "accepted_facts": []},
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "위험성평가 개선활동 완료 후 안전보건관리책임자에게 경과를 "
                    "보고하고, 산업안전보건 게시판 공지 또는 개인 메일링을 통해 "
                    "안전보건활동을 임직원들에게 공유하고 있습니다."
                ),
                semantic_label="useful",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        metric_status="not_expected",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "안전보건관리책임자에게 경과를 보고" in answer
    assert "개인 메일링" in answer
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_writer_adds_supported_operating_organization_and_site_system_facets():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer=(
                    "대웅그룹은 대표이사를 포함한 이사회를 통해 환경안전 경영을 추진하고 "
                    "매년 경영방침과 KPI, 예산을 검토·승인합니다."
                ),
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q021",
        pillar="Governance",
        item_ko="환경경영 관리 조직 및 책임",
        description_ko="환경경영 거버넌스, 운영조직, 사업장 관리체계",
        example_ko="",
    )
    context = {
        "qid": planned.id,
        "pillar": planned.pillar,
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_expected", "accepted_facts": []},
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "대웅그룹 EHS 경영위원회 산하에는 각 그룹사 EHS 실무 담당자로 "
                    "구성된 EHS간사협의체를 운영하고 있습니다. 각 사업장은 "
                    "환경안전보건 지표를 관리하고 현장 실행을 점검합니다."
                ),
                semantic_label="useful",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        metric_status="not_expected",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "EHS간사협의체" in answer
    assert "각 사업장은 환경안전보건 지표를 관리" in answer
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_writer_preserves_inline_metric_claims_from_routed_narrative_evidence():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="회사는 환경 성과를 관리하고 있습니다.",
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q023",
        pillar="Metrics",
        item_ko="환경 성과 지표 및 환경 사고 현황",
        description_ko="용수 재사용률과 폐기물 재활용률 성과",
        example_ko="",
    )
    context = {
        "qid": planned.id,
        "pillar": planned.pillar,
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "found_table", "accepted_facts": []},
        "metric_dimensions": ["water_reuse_rate", "waste_recycling_rate"],
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "용수 재사용률은 2024년 7.23%, 2025년 9.34%를 달성하였고 "
                    "2026년 목표는 14.7%입니다."
                ),
                semantic_label="useful",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        metric_expected=True,
        metric_status="found_table",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "용수 재사용률은 2024년 7.23%, 2025년 9.34%" in answer
    assert "2026년 목표는 14.7%" in answer
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_writer_does_not_duplicate_existing_inline_metric_claim():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer=(
                    "2025년 내부 이해관계자로부터 접수된 인권 관련 고충처리는 "
                    "총 63건이며, 모두 처리가 완료되었습니다."
                ),
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q011",
        pillar="Metrics",
        item_ko="인권 관련 고충 및 처리 현황",
        description_ko="인권 관련 고충 건수와 처리 현황",
        example_ko="",
    )
    context = {
        "qid": planned.id,
        "pillar": planned.pillar,
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_found", "accepted_facts": []},
        "metric_dimensions": ["human_rights_grievances"],
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "2025년 내부 이해관계자 인권 관련 접수된 고충처리는 "
                    "63건으로 확인되었으며 63건 모두 처리가 완료되었습니다."
                ),
                semantic_label="useful",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        metric_expected=True,
        metric_status="not_found",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert answer.count("63건") == 1
    assert "facet_supported_evidence_added" not in result["quality_flags"][planned.id]


def test_writer_adds_draft_cadence_and_role_facets_when_draft_is_allowed():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="대웅제약은 전사 환경안전 관리 체계 내에서 생물다양성 관련 이슈를 검토하고 있습니다.",
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q041",
        pillar="Governance",
        item_ko="생물다양성 감독 및 의사결정 체계",
        description_ko="감독 주체, 역할, 운영 주기",
        example_ko="",
    )
    context = {
        "qid": planned.id,
        "pillar": planned.pillar,
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_expected", "accepted_facts": []},
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "상반기 EHS 위원회에서는 전년도 생물다양성 정책 논의 내용을 "
                    "이사회에 보고하였으며, 하반기 EHS 위원회에서는 정기적인 "
                    "생물다양성 보호활동 계획을 수립하였습니다."
                ),
                semantic_label="useful",
                source_tier="tier_4_draft",
                document_status="draft",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        metric_status="not_expected",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted_draft_evidence"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "상반기 EHS 위원회" in answer
    assert "이사회에 보고" in answer
    assert "하반기 EHS 위원회" in answer
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_writer_preserves_due_diligence_risk_claim_from_draft_without_customer_attribution():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer=(
                    "검토 중인 제안 자료상 회사는 협력회사에 ESG 전반의 "
                    "관리 기준을 적용하고 단계별 로드맵을 추진할 계획입니다."
                ),
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q066",
        pillar="Risk Management",
        item_ko="공급망 ESG 리스크 관리",
        description_ko="공급망 내 지속가능성 리스크 식별 및 관리",
        example_ko="",
    )
    context = {
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_expected", "accepted_facts": []},
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "공급망 내에서 발생할 수 있는 다양한 지속가능성 리스크를 "
                    "사전에 식별·관리하기 위해 실사 의무를 공급망 리스크 관리 "
                    "체계에 통합하고자 합니다."
                ),
                semantic_label="useful",
                source_tier="tier_4_draft",
                document_status="draft",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        metric_status="not_expected",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted_draft_evidence"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert not answer.startswith("검토 중인 제안 자료상")
    assert "검토 중인 제안 자료상" not in answer
    assert "실사 의무를 공급망 리스크 관리 체계에 통합" in answer
    assert "draft_based_answer" in result["quality_flags"][planned.id]
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_writer_preserves_distinct_financial_risk_claim():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="회사는 법규 리스크와 운영 리스크를 관리하고 있습니다.",
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q082",
        pillar="Risk Management",
        item_ko="ESG 운영 관련 리스크 관리",
        description_ko="주요 리스크 유형별 관리 정책 및 운영 현황",
        example_ko="",
    )
    context = {
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_expected", "accepted_facts": []},
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "법규 리스크 관리 대웅제약은 국내외 법규 및 규정을 준수하고 "
                    "중대재해 TFT를 구성하여 위험요소 도출 및 완화 조치를 이행하고 있습니다 "
                    "재무 리스크 관리 정책 및 운영 현황 대웅제약은 2025년 공시담당부서를 "
                    "기존 재무팀에서 IR팀으로 변경하여 공시 업무의 전문성과 대응 체계를 강화하였습니다."
                ),
                semantic_label="useful",
                source_tier="tier_4_draft",
                document_status="draft",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        metric_status="not_expected",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted_draft_evidence"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "공시담당부서를 기존 재무팀에서 IR팀으로 변경" in answer
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_writer_recovers_stakeholder_risk_scenario_claim_from_draft():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="검토 중인 제안 자료상 회사는 이해관계자 의견을 리스크 평가에 반영합니다.",
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q094",
        pillar="Risk Management",
        item_ko="이해관계자 관련 리스크 관리",
        description_ko="이해관계자 의견을 반영한 리스크 관리",
        example_ko="",
    )
    context = {
        "system_prompt": "Write a grounded answer.",
        "user_prompt": "Use evidence.",
        "accepted": True,
        "metric_audit": {"metric_status": "not_expected", "accepted_facts": []},
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "이중 중대성 평가 방법론 STEP 1 이슈 후보군 도출 STEP 2 환경 사회 영향 중대성 평가 "
                    "STEP 3 재무 중대성 평가 STEP 4 중대 이슈 선정 "
                    "내부 이해관계자 FGI는 주요 ESG 이슈가 매출·비용·자산 등 기업 재무에 "
                    "미치는 잠재적 영향을 논의하고, 리스크·기회 발생 시 재무 영향 시나리오를 검토합니다."
                ),
                semantic_label="useful",
                source_tier="tier_4_draft",
                document_status="draft",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        metric_status="not_expected",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted_draft_evidence"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert not answer.startswith("검토 중인 제안 자료상")
    assert "검토 중인 제안 자료상" not in answer
    assert "이해관계자 FGI" in answer
    assert "리스크·기회 발생 시 재무 영향 시나리오를 검토" in answer
    assert "draft_based_answer" in result["quality_flags"][planned.id]
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_found_table_writer_preserves_additional_activity_without_metric_values():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="회사는 의료 인프라가 부족한 도서 지역에서 건강검진을 실시하였습니다.",
                quality_flags=[],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q071",
        pillar="Metrics",
        item_ko="사회공헌 활동 및 투자 현황",
        description_ko="사회공헌 활동과 투자 현황",
        example_ko="",
    )
    context = {
        "system_prompt": "Write a grounded metric answer.",
        "user_prompt": "Use narrative evidence only.",
        "accepted": True,
        "metric_audit": {
            "metric_status": "found_table",
            "accepted_facts": [
                {
                    "metric": "사회공헌 투자 비율",
                    "period": "2025",
                    "value": "0.43",
                    "normalized_value": "0.43",
                    "unit": "%",
                }
            ],
        },
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "이번 검진은 의료 취약 지역을 지원하기 위한 사회공헌 활동입니다. "
                    "이번 지원은 지난 3월 발생한 대형 산불로 피해를 입은 "
                    "이재민들의 건강한 일상 복귀를 돕기 위한 사회공헌활동의 "
                    "일환으로 진행됐습니다."
                ),
                semantic_label="useful",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        metric_status="found_table",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "산불로 피해를 입은 이재민" in answer
    assert "이번 지원은 발생한" not in answer
    assert "0.43" not in answer
    assert "3월" in answer
    assert "facet_supported_evidence_added" in result["quality_flags"][planned.id]


def test_found_table_writer_keeps_meeting_dates_but_redacts_agenda_metric_counts():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(final_answer="1.", quality_flags=[])

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    planned = SimpleNamespace(
        id="Q075",
        pillar="Metrics",
        item_ko="위원회 활동 및 회의 현황",
        description_ko="위원회 회의 개최와 주요 안건",
        example_ko="",
    )
    context = {
        "qid": planned.id,
        "pillar": planned.pillar,
        "system_prompt": "Write a grounded metric answer.",
        "user_prompt": "Use narrative evidence only.",
        "accepted": True,
        "metric_audit": {
            "metric_status": "found_table",
            "accepted_facts": [
                {
                    "metric": "위원회 안건 수",
                    "period": "2025",
                    "value": "23",
                    "normalized_value": "23",
                    "unit": "개",
                }
            ],
        },
        "question": planned.item_ko,
        "description": planned.description_ko,
        "evidence_items": [
            _item(
                (
                    "2025년에는 상반기 3월 20일, 하반기 10월 22일에 진행하였습니다. "
                    "해당 위원회에서는 총 23개(상반기 11개, 하반기 12개)의 안건을 논의하였고, "
                    "주요 안건으로는 환경안전보건 사업계획, 거버넌스 현황, 탄소중립 및 "
                    "에너지절감 성과보고, 임직원 안전사고 재발방지 방안 등이 있었습니다."
                ),
                semantic_label="useful",
            )
        ],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        metric_status="found_table",
    )

    result = SkillWriterAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "skill_contexts": {planned.id: context},
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "rag_results": {planned.id: rag},
            "quality_flags": {},
            "revision_counts": {},
        }
    )

    answer = result["draft_answers"][planned.id]
    assert "3월 20일" in answer
    assert "10월 22일" in answer
    assert "총 23개" in answer
    assert "상반기 11개" in answer
    assert "하반기 12개" in answer


def test_found_table_writer_cleans_editorial_boilerplate_from_narrative_fallback():
    class Structured:
        def invoke(self, prompt):
            return SkillDraft(final_answer="1.", quality_flags=[])

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    question = "개인정보 침해 및 정보보안 사고 현황"
    raw = (
        f"{question} ◀ 왼쪽처럼 수직으로 체계 수정 가능한가요 "
        "상세프로세스는 오른쪽 그림 참고 ▶ 대웅제약 2025 지속가능경영보고서 "
        "64 COMPANY OVERVIEW ESG JOURNEY HUMAN RIGHTS IMPACT ESG PERFORMANCE APPENDIX "
        "정보보안 및 개인정보보호 보안사고 예방 및 대응 활동 "
        "디지털 전환이 빠르게 진행됨에 따라 정보보안 및 정보보호의 중요성이 증가함에 따라 "
        "대웅제약은 글로벌 수준의 강력한 보안 체계를 지속 강화하고 있습니다. "
        "정보보호 정책을 제정하고 매년 1회 이상 개정을 통해 보안 역량을 강화하고 있습니다."
    )
    context = {
        "system_prompt": "Write a grounded metric answer.",
        "user_prompt": "Use only narrative evidence.",
        "metric_audit": {"accepted_facts": []},
        "question": question,
        "description": "",
        "evidence_items": [_item(raw, semantic_label="useful")],
        "output_language": "Korean",
    }
    rag = RagQuestionResult(
        question_id="Q019",
        answer_status="medium_confidence",
        metric_status="found_table",
        metric_confidence="low",
    )

    answer, flags = SkillWriterAgent({}, LLM())._draft_answer(context, rag)

    assert answer.startswith("디지털 전환이 빠르게 진행되면서")
    assert "중요성이 증가함에 따라" not in answer
    assert "중요성이 커짐에 따라" in answer
    assert question not in answer
    assert "◀" not in answer
    assert "▶" not in answer
    assert "왼쪽처럼" not in answer
    assert "COMPANY OVERVIEW" not in answer
    assert "APPENDIX" not in answer
    assert "non_substantive_llm_output" in flags
    assert "evidence_extract_fallback" in flags


def test_evidence_fallback_prefers_question_relevant_claims():
    answer = SkillWriterAgent._evidence_fallback(
        {
            "question": "Stakeholder communication activities",
            "description": "Current stakeholder engagement activities",
            "evidence_items": [
                _item("Risk likelihood is assessed annually.", semantic_label="useful"),
                _item(
                    "The company conducted stakeholder communication through employee "
                    "surveys and external focus groups.",
                    semantic_label="useful",
                ),
            ],
        }
    )

    assert answer.startswith("The company conducted stakeholder communication")
    assert "Risk likelihood" not in answer


def test_evidence_fallback_boosts_accountable_body_for_organization_questions():
    answer = SkillWriterAgent._evidence_fallback(
        {
            "question": "컴플라이언스 관리 조직 및 체계",
            "description": "전담 조직과 역할을 설명합니다",
            "evidence_items": [
                _item(
                    "국가핵심기술 보호와 해외 법인 보안 체계 구축으로 글로벌 성장의 기반을 다지고 있습니다. "
                    "국제 표준 인증(ISO) 유지와 철저한 컴플라이언스 대응을 통해 신뢰를 확보하고 있습니다.",
                    semantic_label="useful",
                ),
                _item(
                    "대웅그룹 정보보호팀은 글로벌 사업과 영업·생산·연구 활동의 지속가능성을 "
                    "뒷받침하는 핵심 경영 인프라 조직입니다.",
                    semantic_label="useful",
                ),
            ],
        }
    )

    assert answer.startswith("대웅그룹 정보보호팀은")
    assert "컴플라이언스 대응" in answer


def test_writer_replaces_q033_style_navigation_dump_with_relevant_evidence():
    raw_dump = (
        "1) Recalculation disclosure Company Overview Company Profile "
        "ESG Framework ESG Highlight Sustainability Performance Appendix"
    )
    context = {
        "qid": "Q033",
        "question": "Waste reduction strategy",
        "description": "Waste reduction and resource circulation activities",
        "output_language": "English",
        "metric_audit": {"metric_status": "not_found", "accepted_facts": []},
        "evidence_items": [
            _item(
                "The company reduces waste by prioritizing qualified recycling providers.",
                semantic_label="useful",
            )
        ],
    }
    rag = SimpleNamespace(metric_status="not_found", normalized_answer_ko=raw_dump)

    answer, flags = SkillWriterAgent({"agent_mode": "offline"}, None)._draft_answer(
        context, rag
    )

    assert answer == (
        "The company reduces waste by prioritizing qualified recycling providers."
    )
    assert flags == ["evidence_extract_fallback"]


def test_claim_salvage_keeps_grounded_sentence_only():
    evidence = [
        _item(
            "In 2025, water reuse was 25%.",
            semantic_label="useful",
        )
    ]

    answer, actions = salvage_supported_claims(
        "In 2025, water reuse was 25%. The company was certified in 2025.",
        evidence,
    )

    assert answer == "In 2025, water reuse was 25%."
    assert actions == ["removed_claim:unsupported:c2"]


def test_structured_metric_fact_is_deterministic_claim_support():
    metric_audit = {
        "accepted_facts": [
            {
                "metric": "Water reuse",
                "period": "2025",
                "value": "25",
                "normalized_value": "25",
                "unit": "%",
                "source_id": "ESG/metrics.xlsx",
            }
        ]
    }

    answer, actions = salvage_supported_claims(
        "Water reuse was reported as 2025: 25 %.",
        [_item("Water reuse | % | 2025=25")],
        metric_audit,
    )

    assert answer == "Water reuse was reported as 2025: 25 %."
    assert actions == []


def test_source_overstatement_salvage_keeps_safe_attributed_claim():
    evidence = [
        _item(
            "The proposal describes an EHS committee. The company operates ISO 14001.",
            semantic_label="useful",
            source_tier="tier_4_draft",
            document_status="draft",
        )
    ]

    answer, actions = salvage_source_overstatement(
        "According to the draft proposal, the proposal describes an EHS committee. "
        "According to the draft proposal, the company operates ISO 14001.",
        evidence,
    )

    assert answer == (
        "According to the draft proposal, the proposal describes an EHS committee. "
        "According to the draft proposal, the company operates ISO 14001."
    )
    assert actions == []


def test_source_overstatement_salvage_keeps_attributed_draft_plan_claim():
    evidence = [
        _item(
            (
                "상반기 EHS 위원회에서는 생물다양성 정책 논의 내용을 이사회에 보고하였으며, "
                "하반기 EHS 위원회에서는 정기적인 생물다양성 보호활동 계획을 수립하였습니다."
            ),
            semantic_label="useful",
            source_tier="tier_4_draft",
            document_status="draft",
        )
    ]

    answer, actions = salvage_source_overstatement(
        "검토 중인 제안 자료상 상반기 EHS 위원회에서는 생물다양성 정책 논의 내용을 "
        "이사회에 보고하였으며, 하반기 EHS 위원회에서는 정기적인 생물다양성 보호활동 "
        "계획을 수립하였습니다.",
        evidence,
    )

    assert "하반기 EHS 위원회" in answer
    assert actions == []


def test_evidence_fallback_does_not_open_with_a_back_referencing_claim():
    """Regression for Q057: relevance ranking put "이러한 노력의 결과, ..." first, so
    the answer opened by referring back to efforts it had not yet described."""

    answer = SkillWriterAgent._evidence_fallback(
        {
            "question": "인적 자본 관리 조직 및 체계",
            "description": "인적 자본 관리 조직과 운영 체계를 기술",
            "evidence_items": [
                _item(
                    "대웅제약은 자율과 성장 중심의 조직문화를 기반으로 근무환경을 지속 강화하고 있습니다. "
                    "이러한 노력의 결과, 인적자원개발 우수기관(Best HRD) 등 다양한 대외 인증을 통해 "
                    "조직문화 및 근무환경 경쟁력을 인정받고 있습니다.",
                    semantic_label="useful",
                )
            ],
        }
    )

    assert not answer.startswith("이러한 노력의 결과")
    assert answer.index("자율과 성장") < answer.index("이러한 노력의 결과")
    assert "Best HRD" in answer


def test_evidence_fallback_keeps_ranked_order_when_the_lead_is_self_contained():
    answer = SkillWriterAgent._evidence_fallback(
        {
            "question": "컴플라이언스 관리 조직 및 체계",
            "description": "전담 조직과 역할을 설명합니다",
            "evidence_items": [
                _item("국제 표준 인증(ISO) 유지와 컴플라이언스 대응을 통해 신뢰를 확보하고 있습니다.", semantic_label="useful"),
                _item("대웅그룹 정보보호팀은 보안 기준과 원칙을 수립하는 전담 조직입니다.", semantic_label="useful"),
            ],
        }
    )

    assert answer.startswith("대웅그룹 정보보호팀은")


def test_same_excerpt_from_two_documents_is_collapsed_to_the_strongest_copy():
    # Team RAG dedupes only by canonical_source_id + chunk_id, so an excerpt that
    # exists in several source files returns once per file with its own chunk_id
    # and its own semantic label.
    shared_text = "대웅제약은 인권경영 정책을 수립하고 인권영향평가를 실시하고 있습니다."
    rag = RagQuestionResult(
        question_id="Q028",
        answer_status="thin_but_usable",
        coverage_status="partial",
        answerable=True,
        metric_expected=False,
        items=[
            _item(
                shared_text,
                semantic_label="partial",
                semantic_score=0.7,
                canonical_source_id="src_report",
                chunk_id="doc_report_c1",
                source_name="business_report.pdf",
                source_path="ESG/business_report.pdf",
            ),
            _item(
                shared_text,
                semantic_label="useful",
                semantic_score=0.9,
                canonical_source_id="src_ungc",
                chunk_id="doc_ungc_c7",
                source_name="ungc.xlsx",
                source_path="ESG/ungc.xlsx",
            ),
            _item(
                "인권 고충처리 채널을 운영하고 접수된 사안을 규정에 따라 조치합니다.",
                semantic_label="useful",
                semantic_score=0.85,
                canonical_source_id="src_policy",
                chunk_id="doc_policy_c2",
                source_name="policy.pdf",
                source_path="ESG/policy.pdf",
            ),
        ],
    )

    normalized = EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {"rag_results": {"Q028": rag}}
    )["normalized_evidence"]["Q028"]

    texts = [item.raw_evidence_ko for item in normalized["items"]]
    assert texts.count(shared_text) == 1
    assert len(normalized["items"]) == 2
    assert len(normalized["sources"]) == 2
    kept = next(item for item in normalized["items"] if item.raw_evidence_ko == shared_text)
    assert kept.semantic_label == "useful"
    assert kept.chunk_id == "doc_ungc_c7"
    assert [
        (entry["kept_chunk_id"], entry["dropped_chunk_id"])
        for entry in normalized["duplicate_evidence_dropped"]
    ] == [("doc_ungc_c7", "doc_report_c1")]


def test_metric_rows_are_not_collapsed_by_repeated_row_text():
    rag = RagQuestionResult(
        question_id="Q079",
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        items=[
            _item(
                "이사회 인원 | 명 | 2025=7.0",
                semantic_label="metric_row",
                canonical_source_id="metric_lane::governance.xlsx",
                chunk_id="b1::sheet::48",
            ),
            _item(
                "이사회 인원 | 명 | 2025=7.0",
                semantic_label="metric_row",
                canonical_source_id="metric_lane::governance.xlsx",
                chunk_id="b1::sheet::49",
            ),
        ],
    )

    normalized = EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {"rag_results": {"Q079": rag}}
    )["normalized_evidence"]["Q079"]

    # A primary row and a scope_variant row may carry the same text, so the
    # metric lane keeps its own dedup key instead of collapsing on text.
    assert len(normalized["items"]) == 2
    assert normalized["duplicate_evidence_dropped"] == []


def test_facet_augmentation_rejects_an_off_topic_source_repeating_the_facet_word():
    """Regression for Q036: a CEO New Year address filled the water-target facet
    because it says "높은 목표 설정". The facet keyword alone is not topical evidence."""

    from skills.agents.writer import FACET_AUGMENT_TERMS

    context = {
        "qid": "Q036",
        "question": "수자원 관리 정책 및 목표",
        "description": "수자원의 효율적 사용과 수질 보전을 위한 물 관리 정책 및 목표를 설명합니다.",
        "evidence_items": [
            _item(
                "대웅제약 신년사 직원 성장이 최우선 설레는 출근길과 디지털 헬스케어 비전 제시 "
                "기존 경험과 지식을 넘어선 높은 목표 설정 성장을 위한 학습 실천 3원칙 제시",
                semantic_label="useful",
            )
        ],
    }
    topic = SkillWriterAgent._question_topic_terms(
        context, "target", FACET_AUGMENT_TERMS["target"]
    )

    assert "수자원" in topic
    assert "목표" not in topic
    assert not SkillWriterAgent._mentions_topic(
        context["evidence_items"][0].raw_evidence_ko, topic
    )
    assert SkillWriterAgent._best_facet_claim(
        context, "target", "", [], allow_draft=True
    ) == ""


def test_facet_augmentation_keeps_a_source_on_the_questions_own_subject():
    from skills.agents.writer import FACET_AUGMENT_TERMS

    context = {
        "qid": "Q036",
        "question": "수자원 관리 정책 및 목표",
        "description": "수자원의 효율적 사용과 수질 보전을 위한 물 관리 정책 및 목표를 설명합니다.",
        "evidence_items": [
            _item(
                "대웅제약은 수자원 사용 효율을 높이기 위해 2026년 용수 재이용률 목표를 "
                "14.7%로 설정하였습니다.",
                semantic_label="useful",
            )
        ],
    }
    claim = SkillWriterAgent._best_facet_claim(
        context, "target", "", [], allow_draft=True
    )

    assert "14.7%" in claim


def test_domain_facet_keeps_its_own_vocabulary_as_a_topical_link():
    """A site-management question is *about* 사업장, so that word must still count."""

    from skills.agents.writer import FACET_AUGMENT_TERMS

    context = {
        "qid": "Q021",
        "question": "환경경영 관리 조직 및 책임",
        "description": "환경경영 거버넌스, 운영조직, 사업장 관리체계",
        "evidence_items": [],
    }
    topic = SkillWriterAgent._question_topic_terms(
        context, "site_management_system", FACET_AUGMENT_TERMS["site_management_system"]
    )

    assert "사업장" in topic


def test_dependent_clause_is_dropped_when_its_antecedent_was_rejected():
    """Regression for Q053: the statute clause "제26조(감사의 실시) ① ..." was rejected
    and its dependent tail "이 경우 피감사부서장은 ..." shipped alone, mixing an audit
    regulation into a product-responsibility answer."""

    answer = SkillWriterAgent._evidence_fallback(
        {
            "qid": "Q053",
            "question": "제품 책임 관리 조직 및 체계",
            "description": "제품 책임 관리 조직과 체계를 기술",
            "evidence_items": [
                _item(
                    "제26조(감사의 실시) ① 위원회는 감사직무를 수행함에 있어 피감사부서장에게 "
                    "소속 직원의 업무 지원을 요청할 수 있다. 이 경우 피감사부서장은 이에 협조하여야 한다.",
                    semantic_label="useful",
                ),
                _item(
                    "품질경영(QM), 품질보증(QA), 품질관리(QC) 조직은 SOP 문서화, 밸리데이션, "
                    "시험 감사 업무를 수행합니다.",
                    semantic_label="useful",
                ),
            ],
        }
    )

    assert "피감사부서장" not in answer
    assert "품질경영(QM)" in answer


def test_dependent_clause_is_kept_when_its_antecedent_is_kept():
    answer = SkillWriterAgent._evidence_fallback(
        {
            "qid": "Q057",
            "question": "인적 자본 관리 조직 및 체계",
            "description": "인적 자본 관리 조직과 운영 체계를 기술",
            "evidence_items": [
                _item(
                    "대웅제약은 자율과 성장 중심의 조직문화를 기반으로 근무환경을 지속 강화하고 있습니다. "
                    "이러한 노력의 결과, 인적자원개발 우수기관(Best HRD) 등 다양한 대외 인증을 통해 "
                    "경쟁력을 인정받고 있습니다.",
                    semantic_label="useful",
                )
            ],
        }
    )

    assert "Best HRD" in answer
    assert answer.index("자율과 성장") < answer.index("이러한 노력의 결과")


def test_additive_connective_claim_stays_eligible_without_an_antecedent():
    """"또한" only continues the discourse; it does not point at one clause, so the
    sentence stands on its own -- Q048's green-procurement commitment must survive."""

    answer = SkillWriterAgent._evidence_fallback(
        {
            "qid": "Q048",
            "question": "친환경 제품 개발 정책 및 목표",
            "description": "친환경 제품 개발 정책과 목표를 기술",
            "evidence_items": [
                _item(
                    "1. 목적 본 정책은 녹색제품 구매의무 이행에 필요한 사항을 규정한다. "
                    "또한, 공급망 내에 친환경성과 지속가능성이 확산될 수 있도록 협력업체의 "
                    "안정적 녹색제품 공급을 지원하는 방안을 검토 중에 있습니다.",
                    semantic_label="useful",
                )
            ],
        }
    )

    assert "녹색제품 공급을 지원하는 방안" in answer
