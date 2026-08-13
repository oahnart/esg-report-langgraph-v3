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


def test_found_table_writer_replaces_stub_with_narrative_evidence_fallback():
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

    assert answer.startswith("The company manages water risks")
    assert "Water reuse" not in answer
    assert "25 %" not in answer
    assert "non_substantive_llm_output" in flags
    assert "evidence_extract_fallback" in flags


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

    assert answer == "According to the draft proposal, the proposal describes an EHS committee."
    assert actions == ["removed_claim:source_overstatement:c2"]
