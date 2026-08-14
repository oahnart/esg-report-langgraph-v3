import pytest

from esgagents.agents.answering.text_quality import (
    clean_final_answer_for_customer,
    final_answer_block_reason,
    non_narrative_reason,
)
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


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (
            "자원선순환 재활용 원재료 관리 3. 물 관리 용수 사용량 저감 4. 생물다양성 보호",
            "list_dump_output",
        ),
        (
            "(이상행위 분석 및 모니터링) 산업기술보호관리자는 보안사고 예방 활동을 수행한다.",
            "parenthetical_heading_output",
        ),
        (
            "() 기업 소유권/운영 배당정책 경영지원실 경영관리팀 부장.",
            "parenthetical_heading_output",
        ),
        (
            "불공정거래 방지 투명경영 및 반부패 윤리경영시스템 구축 ※ 핵심지표란?",
            "symbol_marker_output",
        ),
        (
            "기업이 구성원의 비윤리 행위를 관리 감독하고 있는지 확인 /.",
            "question_context_output",
        ),
        (
            "컴플라이언스 윤리경영 리스크 관리 체계 부장 19. 기업 소유권 정책 • 기업일반 재무 정보",
            "list_fragment_output",
        ),
        (
            "기업 소유권/운영 배당정책, 경영진의 자사주 매입 등 정책 경영지원실 경영관리팀 부장.",
            "korean_fragment_output",
        ),
        (
            "환경측면 파악 및 영향평가 업무 절차 ) 각 팀장은 환경영향평가 시점으로 파악하고 조치한다.",
            "procedure_heading_fragment_output",
        ),
        (
            "ECO-FRIENDLY MOBILITY SOLUTIONS 일진하이솔루스 ESG DATA REPORT 보고서 개요 일진하이솔루스 ESG Data Report는 회사와 이해관계자가 함께 지속가능한 미래를 만들어 가는 우리의 꿈과 활동을 담은 첫 보고서입니다.",
            "document_boilerplate_output",
        ),
    ],
)
def test_final_answer_contract_rejects_structural_and_symbol_noise(answer, reason):
    assert final_answer_block_reason(answer) == reason


def test_final_answer_normalizer_removes_unknown_unicode_noise_without_named_rules():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "회사는 정보보안 정책을 운영합니다." + chr(0xD800) + " " + chr(0xE000) + " " + chr(0x2060)
    )

    assert cleaned == "회사는 정보보안 정책을 운영합니다."
    assert reason == ""
    assert "removed_control_unicode" in actions


def test_final_answer_salvages_narrative_after_leading_list_fragments():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "1. 목차 2. 주요 내용 회사는 정보보안 정책을 운영합니다."
    )

    assert cleaned == "회사는 정보보안 정책을 운영합니다."
    assert reason == ""
    assert "salvaged_narrative_after_list_or_heading" in actions


def test_final_answer_keeps_pure_list_dump_blocked_when_no_narrative_remains():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "1. 물 관리 용수 사용량 저감 2. 생물다양성 보호 3. 친환경 제품 개발"
    )

    assert cleaned
    assert reason == "numbered_block_output"
    assert "salvaged_narrative_after_list_or_heading" not in actions


def test_draft_and_assessment_attribution_are_distinct_and_natural():
    draft = attribute_draft_statement("회사는 감축 방안을 마련했습니다.", "Korean")
    assessment = attribute_assessment_statement("일부 항목이 충족되었습니다.", "Korean")

    assert draft.startswith("검토 중인 제안 자료상 ")
    assert "제안/검토 자료에 따르면" not in draft
    assert assessment.startswith("외부 평가 자료상 ")
    assert "평가 자료에 따르면" not in assessment
