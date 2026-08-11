from esgagents.agents.answering.text_quality import non_narrative_reason
from esgagents.agents.evidence.source_policy import (
    attribute_assessment_statement,
    attribute_draft_statement,
)


def test_numbered_document_navigation_dump_is_not_customer_prose():
    answer = (
        "1) Recalculation disclosure Company Overview Company Profile "
        "ESG Framework ESG Highlight Sustainability Performance Appendix"
    )

    assert non_narrative_reason(answer) == "numbered_block_output"


def test_document_navigation_dump_is_rejected_without_numbered_prefix():
    answer = (
        "Company Overview Company Profile ESG Framework ESG Highlight "
        "Sustainability Performance Appendix"
    )

    assert non_narrative_reason(answer) == "document_navigation_dump_output"


def test_draft_and_assessment_attribution_are_distinct_and_natural():
    draft = attribute_draft_statement("회사는 감축 방안을 마련했습니다.", "Korean")
    assessment = attribute_assessment_statement("일부 항목이 충족되었습니다.", "Korean")

    assert draft.startswith("검토 중인 제안 자료상 ")
    assert "제안/검토 자료에 따르면" not in draft
    assert assessment.startswith("외부 평가 자료상 ")
    assert "평가 자료에 따르면" not in assessment
