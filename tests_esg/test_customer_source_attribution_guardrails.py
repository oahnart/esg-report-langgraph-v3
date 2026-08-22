from pathlib import Path
from types import SimpleNamespace

import pytest

from esgagents.agents.answering.output_hygiene import OutputHygieneAgent
from esgagents.agents.answering.semantic_critic import SemanticCompletenessCriticAgent
from esgagents.agents.evidence.source_policy import (
    attribute_assessment_statement,
    attribute_draft_statement,
)
from esgagents.schemas import EvidenceItem, QAResult


ROOT = Path(__file__).resolve().parents[1]


def _planned(qid: str = "Q999"):
    return SimpleNamespace(
        id=qid,
        pillar="Strategy",
        item_ko="Policy status",
        description_ko="Describe the supported policy status",
    )


def _semantic_state(planned, answer: str, *, tier: str, evidence_text: str):
    item = EvidenceItem(
        raw_evidence_ko=evidence_text,
        source_name="assessment.xlsx" if tier == "tier_3_assessment" else "proposal.docx",
        source_path="ESG/source",
        source_tier=tier,
        document_status="assessed" if tier == "tier_3_assessment" else "draft",
    )
    return {
        "planned_questions": [planned],
        "draft_answers": {planned.id: answer},
        "final_answers": {planned.id: answer},
        "qa_results": {planned.id: QAResult(status="passed", notes=["grounded"])},
        "normalized_evidence": {
            planned.id: {
                "items": [item],
                "sources": [
                    {
                        "source_name": item.source_name,
                        "source_path": item.source_path,
                        "source_tier": item.source_tier,
                        "document_status": item.document_status,
                    }
                ],
            }
        },
        "quality_flags": {planned.id: []},
        "skill_checks": {planned.id: ["claims_grounded: passed"]},
    }


def test_source_attribution_helpers_never_prepend_customer_prose():
    assert attribute_draft_statement("The company operates ISO 14001.", "English") == (
        "The company operates ISO 14001."
    )
    assert attribute_draft_statement("회사는 안전보건 체계를 운영하고 있습니다.", "Korean") == (
        "회사는 안전보건 체계를 운영하고 있습니다."
    )
    assert attribute_assessment_statement("Safety criteria were partially met.", "English") == (
        "Safety criteria were partially met."
    )
    assert attribute_assessment_statement("일부 항목이 충족되었습니다.", "Korean") == "일부 항목이 충족되었습니다."


def test_answering_pipeline_does_not_call_source_attribution_helpers_for_final_answer():
    production_files = [
        ROOT / "skills" / "agents" / "writer.py",
        ROOT / "esgagents" / "agents" / "answering" / "revision.py",
        ROOT / "esgagents" / "agents" / "answering" / "attribution.py",
    ]

    for path in production_files:
        text = path.read_text(encoding="utf-8")
        assert "attribute_draft_statement" not in text
        assert "attribute_assessment_statement" not in text
        assert "draft_attributed" not in text
        assert "assessment_attributed" not in text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Theo đề xuất đang được xem xét, công ty vận hành hệ thống EHS.", "Công ty vận hành hệ thống EHS."),
        ("According to the draft proposal, the company operates ISO 14001.", "The company operates ISO 14001."),
        ("The proposal under review describes the company operates ISO 14001.", "The company operates ISO 14001."),
        ("검토 중인 제안 자료상 위원회가 운영됩니다.", "위원회가 운영됩니다."),
        ("외부 평가 자료상 일부 항목이 충족되었습니다.", "일부 항목이 충족되었습니다."),
        ("The external assessment records: safety policy items were partially met.", "Safety policy items were partially met."),
    ],
)
def test_output_hygiene_removes_customer_source_attribution_phrases(raw, expected):
    qid = "Q999"
    result = OutputHygieneAgent({"output_hygiene_enabled": True}).run(
        {
            "planned_questions": [_planned(qid)],
            "final_answers": {qid: raw},
            "quality_flags": {qid: []},
            "qa_results": {qid: QAResult(status="passed")},
        }
    )

    assert result["final_answers"][qid] == expected
    assert "removed_source_attribution" in result["sanitizer_actions"][qid]


def test_output_hygiene_blocks_source_limited_rewrite_residue():
    qid = "Q999"
    result = OutputHygieneAgent({"output_hygiene_enabled": True}).run(
        {
            "planned_questions": [_planned(qid)],
            "final_answers": {qid: "회사는 안전관리 체계 구축 방안으로 제시하고 있습니다."},
            "quality_flags": {qid: ["draft_based_answer"]},
            "qa_results": {qid: QAResult(status="passed")},
        }
    )

    assert result["final_answers"][qid] == ""
    assert "source_limitation_rewrite_output" in result["hard_failures"][qid]


def test_assessment_checklist_overclaim_fails_instead_of_rewriting_final_answer():
    planned = _planned()
    answer = "The company operates an approved safety policy and monitors safety targets."
    result = SemanticCompletenessCriticAgent({"semantic_qa_enabled": True}, None).run(
        _semantic_state(
            planned,
            answer,
            tier="tier_3_assessment",
            evidence_text="The assessment checklist marks safety policy items as partially met.",
        )
    )

    assert result["qa_results"][planned.id].status == "failed"
    assert result["final_answers"][planned.id] == answer
    assert "source usage overstated" in result["qa_results"][planned.id].notes
