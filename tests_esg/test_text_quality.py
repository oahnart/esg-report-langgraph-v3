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


def test_draft_attribution_helper_keeps_customer_prose_clean():
    draft = attribute_draft_statement("회사는 감축 방안을 마련했습니다.", "Korean")
    assessment = attribute_assessment_statement("일부 항목이 충족되었습니다.", "Korean")

    assert draft == "회사는 감축 방안을 마련했습니다."
    assert "제안/검토 자료에 따르면" not in draft
    assert assessment == "일부 항목이 충족되었습니다."
    assert "평가 자료에 따르면" not in assessment


def test_final_answer_hygiene_removes_english_draft_proposal_attribution():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "According to the draft proposal, the company operates ISO 14001."
    )

    assert cleaned == "The company operates ISO 14001."
    assert reason == ""
    assert "removed_source_attribution" in actions


def test_final_answer_hygiene_removes_english_assessment_attribution():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "The external assessment records: safety policy items were partially met."
    )

    assert cleaned == "Safety policy items were partially met."
    assert reason == ""
    assert "removed_source_attribution" in actions


def test_final_answer_boundary_deduplicates_repeated_sentences():
    repeated = (
        "또한, 2025년 기준 내부 이해관계자로부터 접수된 인권 관련 "
        "고충처리 63건에 대해 모두 처리를 완료하였습니다."
    )

    cleaned, reason, actions = clean_final_answer_for_customer(
        "회사는 이해관계자 의견을 수렴하고 있습니다. "
        f"{repeated} 외부 이해관계자 의견도 평가에 반영하고 있습니다. {repeated}"
    )

    assert cleaned.count(repeated) == 1
    assert reason == ""
    assert "deduplicated_repeated_sentence" in actions


def test_final_answer_salvages_after_korean_leading_dependent_fragment():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "미치는 잠재적 영향과 리스크 기회 시나리오를 검토하고 의견을 수렴하고 있습니다. "
        "또한, 2025년 기준 내부 이해관계자로부터 접수된 인권 관련 고충처리 63건에 대해 모두 처리를 완료하였습니다."
    )

    assert not cleaned.startswith("미치는 잠재적 영향")
    assert "고충처리 63건" in cleaned
    assert reason == ""
    assert "salvaged_narrative_after_list_or_heading" in actions


def test_final_answer_removes_intro_only_sentence_before_substance():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "목표는 다음과 같습니다. 2026년 용수 재사용률 목표는 14.7%입니다."
    )

    assert cleaned == "2026년 용수 재사용률 목표는 14.7%입니다."
    assert reason == ""
    assert "removed_intro_only_sentence" in actions


def test_final_answer_removes_duplicate_underspecified_metric_sentence():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "목표는 14.7%입니다. "
        "용수 재사용률은 2024년 7.23%, 2025년 9.34%를 달성하였고, 2026년 목표는 14.7%입니다."
    )

    assert not cleaned.startswith("목표는 14.7%")
    assert "용수 재사용률은 2024년 7.23%" in cleaned
    assert reason == ""
    assert "removed_underspecified_duplicate_metric_sentence" in actions


def test_salvage_keeps_metric_name_and_values_before_topic_particle():
    """A bulleted metric line must not be cut at the ``은/는`` topic particle.

    Regression for Q018/Q047: the salvage heuristic beheaded the sentence at the
    leftmost particle match, dropping the metric name and every measured value
    while keeping the trailing target figure as an orphan clause.
    """

    cleaned, reason, actions = clean_final_answer_for_customer(
        "• 위험 식별 및 완화: 2024년 정보보호 위험 식별을 실시하였습니다. "
        "세부 수행계획을 통해 27개 항목의 이행조치를 완료하고 39개 항목은 이행조치 중에 있습니다. "
        "• 통제 및 예방: 내부 정보 유출 차단을 위해 모니터링 시스템을 상시 운영하고 있습니다."
    )

    assert "27개 항목의 이행조치를 완료하고" in cleaned
    assert "39개 항목은 이행조치 중에 있습니다" in cleaned
    assert reason == ""
    assert "salvaged_narrative_after_list_or_heading" in actions


def test_salvage_still_drops_marker_only_prefix_before_narrative():
    cleaned, reason, actions = clean_final_answer_for_customer(
        "1. 목차 2. 주요 내용 회사는 정보보안 정책을 운영합니다."
    )

    assert cleaned == "회사는 정보보안 정책을 운영합니다."
    assert reason == ""
    assert "salvaged_narrative_after_list_or_heading" in actions


def test_deduplication_matches_sentences_that_differ_only_in_spacing():
    """Regression for Q013: the same evidence sentence re-typed with different
    word spacing and ``·`` separators must count as one sentence."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "약물감시는 모든 제품에 대하여 전 생애주기의 이상사례와 안전성 문제를 "
        "과학적으로 탐지·평가하는 활동으로, 글로벌 규제 보고 의무를 준수합니다. "
        "약물감시는 모든 제품에 대하여 전 생애주기의 이상사례와 안전성 문제를 "
        "과학적 으로 탐지 평가하는 활동으로, 글로벌 규제 보고 의무를 준수합니다."
    )

    assert cleaned.count("약물감시는") == 1
    assert reason == ""
    assert "deduplicated_repeated_sentence" in actions


def test_deduplication_drops_beheaded_copy_of_a_complete_sentence():
    """Regression for Q048: the writer emitted a truncated tail of a sentence
    alongside the intact sentence; only the complete one may survive."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "대웅제약은 친환경 구매 기준을 설정하였습니다. 지원하는 방안을 검토 중에 있습니다. "
        "또한, 공급망 내에 지속가능성이 확산될 수 있도록 협력업체의 안정적 "
        "녹색제품 공급을 지원하는 방안을 검토 중에 있습니다."
    )

    assert "지원하는 방안을 검토 중에 있습니다." in cleaned
    assert cleaned.count("지원하는 방안을 검토 중에 있습니다.") == 1
    assert "협력업체의 안정적 녹색제품 공급을" in cleaned
    assert reason == ""
    assert "deduplicated_repeated_sentence" in actions


def test_trailing_sentence_announcing_a_dropped_list_is_removed():
    """Regression for Q051: the year-by-year plan the sentence announced was
    dropped upstream, leaving an unfulfilled promise as the final sentence."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "대웅제약은 친환경성을 고려한 구매 기준을 설정하였습니다. "
        "또한, 협력업체와 협력하여 연도별로 다음과 같은 실행 계획을 추진하고 있습니다."
    )

    assert cleaned == "대웅제약은 친환경성을 고려한 구매 기준을 설정하였습니다."
    assert reason == ""
    assert "removed_intro_only_sentence" in actions


def test_sentence_announcing_a_list_is_kept_when_the_list_follows():
    cleaned, _, actions = clean_final_answer_for_customer(
        "리스크 대응을 위해 다음과 같은 활동을 수행하고 있습니다. "
        "위험 식별: 2024년 정보보호 위험 식별을 실시하였습니다."
    )

    assert "다음과 같은 활동을 수행하고 있습니다." in cleaned
    assert "removed_intro_only_sentence" not in actions


def test_leading_report_title_and_heading_run_is_stripped():
    """Regression for Q053: a valid sentence arrived with a report cover and
    section-heading run glued to its front, which no structural gate rejects."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "대웅제약 2025 지속가능경영보고서 약물감시 활동 및 성과 약물감시 조직 및 매뉴얼 고도화 "
        "대웅제약의 약물감시는 모든 제품에 대하여 이상사례를 탐지·평가하는 활동으로, "
        "글로벌 규제 보고 의무를 준수합니다."
    )

    assert cleaned.startswith("약물감시는") or cleaned.startswith("대웅제약의 약물감시는")
    assert "지속가능경영보고서" not in cleaned
    assert "매뉴얼 고도화" not in cleaned
    assert reason == ""
    assert "removed_leading_document_title_run" in actions


def test_in_sentence_report_mention_is_not_treated_as_a_title_run():
    cleaned, _, actions = clean_final_answer_for_customer(
        "대웅제약은 인권경영 성과와 활동을 지속가능경영보고서 발간을 통해 "
        "정기적으로 공개하고 있습니다."
    )

    assert "지속가능경영보고서 발간" in cleaned
    assert "removed_leading_document_title_run" not in actions


@pytest.mark.parametrize(
    "answer",
    [
        "제5장 감사실시 제25조(감사계획의 수립) 1 위원회는 감사전략과 감사방침을 수립하여야 한다.",
        "2 위원회는 내부감사부서에 대하여 감사결과에 대한 보고를 요구할 수 있다.",
    ],
)
def test_statute_clause_and_bare_list_index_are_not_customer_prose(answer):
    """Regression for Q053: audit-regulation clauses shipped as the answer."""

    assert non_narrative_reason(answer) == "statute_clause_output"


@pytest.mark.parametrize(
    "answer",
    [
        "대웅제약은 2025년 목표를 달성하였습니다.",
        "평가는 3개 영역, 총 26개 세부 항목으로 구성됩니다.",
    ],
)
def test_ordinary_prose_is_not_flagged_as_a_statute_clause(answer):
    assert non_narrative_reason(answer) == ""


def test_leading_table_of_contents_run_is_stripped():
    """Regression for Q033: a report table of contents was glued in front of the
    real prose, and no structural gate rejected the combined text."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "환산계수 기준변경에 따른 재공시 // 00 CEO 메시지 00 CompanyProfile "
        "00 BusinessPerformance 40 온실가스 배출 관리 및 에너지 감축 "
        "대웅제약은 자원순환 확대를 위해 폐기물 관리 및 감축 활동을 추진하고 있습니다."
    )

    assert cleaned == "대웅제약은 자원순환 확대를 위해 폐기물 관리 및 감축 활동을 추진하고 있습니다."
    assert reason == ""
    assert "removed_leading_document_title_run" in actions


def test_bare_clause_index_before_a_digit_is_a_statute_clause():
    """Regression for Q053: ``"3 2인 이상의 감사위원이 ..."`` is a regulation clause
    whose number was split from its text, not customer prose."""

    assert (
        non_narrative_reason("3 2인 이상의 감사위원이 업무를 분담하는 경우에는 책임을 구분하여야 한다.")
        == "statute_clause_output"
    )


def test_plain_register_sentences_are_reported_not_rewritten():
    from esgagents.agents.answering.text_quality import plain_register_sentences

    answer = (
        "대웅제약은 녹색구매정책을 수립하였습니다. "
        "본 정책은 녹색제품 구매의무 이행에 필요한 사항을 규정함을 목적으로 한다. "
        "임직원은 유관부서에게 협조를 요청할 수 있다."
    )
    reported = plain_register_sentences(answer)

    assert len(reported) == 2
    assert all(sentence.rstrip(".").endswith(("한다", "있다")) for sentence in reported)
    assert "대웅제약은 녹색구매정책을 수립하였습니다." not in reported


def test_polite_register_answer_reports_nothing():
    from esgagents.agents.answering.text_quality import plain_register_sentences

    assert plain_register_sentences(
        "대웅제약은 정책을 운영하고 있습니다. 관련 절차를 매년 점검합니다."
    ) == []


def test_leading_internal_working_note_run_is_stripped():
    """Regression for Q057: an internal to-do note ("인증패 사진 인사기획팀 전달 예정")
    plus award headings sat in front of the real prose."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "가족친화 선도기업 인증패 사진 인사기획팀 전달 예정 가족친화 선도기업 선정 "
        "GPTW 주관 '대한민국 부모가 가장 일하기 좋은 기업' 수상 조직문화 성과 "
        "대웅제약은 자율과 성장 중심의 조직문화를 기반으로 근무환경을 지속 강화하고 있습니다."
    )

    assert cleaned == "대웅제약은 자율과 성장 중심의 조직문화를 기반으로 근무환경을 지속 강화하고 있습니다."
    assert "전달 예정" not in cleaned
    assert reason == ""
    assert "removed_leading_document_title_run" in actions


def test_polite_planned_delivery_sentence_is_not_treated_as_a_working_note():
    cleaned, _, actions = clean_final_answer_for_customer(
        "대웅제약은 구호 물품을 각 지역 이재민에게 전달 예정입니다."
    )

    assert cleaned == "대웅제약은 구호 물품을 각 지역 이재민에게 전달 예정입니다."
    assert "removed_leading_document_title_run" not in actions


@pytest.mark.parametrize(
    ("plain", "polite"),
    [
        ("종사자의 안전과 건강이 동등하게 보호되도록 관리한다.", "종사자의 안전과 건강이 동등하게 보호되도록 관리합니다."),
        ("이사회는 그 권한을 위원회에 위임할 수 있다.", "이사회는 그 권한을 위원회에 위임할 수 있습니다."),
        ("본 정책은 지속 가능한 성장을 목적으로 한다.", "본 정책은 지속 가능한 성장을 목적으로 합니다."),
        ("폐기물 배출량을 원천적으로 줄이기 위해 노력해야 한다.", "폐기물 배출량을 원천적으로 줄이기 위해 노력해야 합니다."),
        ("피감사부서장은 이에 협조하여야 한다.", "피감사부서장은 이에 협조하여야 합니다."),
        ("5개 시군에 걸쳐 진행됐다.", "5개 시군에 걸쳐 진행됐습니다."),
        ("평가 대상은 협력회사이다.", "평가 대상은 협력회사입니다."),
    ],
)
def test_source_register_sentences_are_restated_not_dropped(plain, polite):
    """A regulation clause carries real disclosure; only its ending is wrong."""

    from esgagents.agents.answering.text_quality import normalize_to_polite_register

    converted, actions = normalize_to_polite_register(plain)

    assert converted == polite
    assert actions == ["normalized_to_polite_register"]


def test_polite_register_text_is_left_untouched():
    from esgagents.agents.answering.text_quality import normalize_to_polite_register

    answer = "대웅제약은 정책을 운영하고 있습니다. 평가는 26개 항목으로 구성됩니다."
    converted, actions = normalize_to_polite_register(answer)

    assert converted == answer
    assert actions == []


def test_register_conversion_only_rewrites_the_sentence_ending():
    from esgagents.agents.answering.text_quality import normalize_to_polite_register

    plain = "회사는 공정개선, 원료 대체, 재활용을 통해 사용량을 줄이기 위해 노력해야 한다."
    converted, _ = normalize_to_polite_register(plain)

    assert converted.startswith("회사는 공정개선, 원료 대체, 재활용을 통해 사용량을 줄이기 위해 노력해야 ")
    assert converted.count("한다") == 0


def test_leading_timeline_table_run_is_stripped():
    """Regression for Q065/Q066: a roadmap table of bare years was glued in front
    of the real prose, and no structural gate rejected the combined sentence."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "영역별 평가 결과 2025 2026 평가 기준 마련 공급망 관리 체계 구축 2027 2028 "
        "협력회사 역량 강화 프로그램 확대 2029 자회사 및 해외 법인으로 확산 로드맵 추진체계 "
        "대웅제약은 공급망 지속가능 경영을 위해 ESG 팀 내에 전담 역할을 설정하고 있습니다."
    )

    assert cleaned == "대웅제약은 공급망 지속가능 경영을 위해 ESG 팀 내에 전담 역할을 설정하고 있습니다."
    assert reason == ""
    assert "removed_leading_document_title_run" in actions


def test_timeline_table_run_is_stripped_mid_answer_too():
    cleaned, _, actions = clean_final_answer_for_customer(
        "대웅제약은 포괄적 관리 기준을 적용하고 있습니다. "
        "영역별 평가 결과 2025 2026 평가 기준 마련 2027 2028 역량 강화 2029 해외 확산 "
        "대웅제약은 ESG 팀 내에 전담 역할을 설정하고 있습니다."
    )

    assert "2027 2028" not in cleaned
    assert cleaned.startswith("대웅제약은 포괄적 관리 기준을 적용하고 있습니다.")
    assert cleaned.endswith("대웅제약은 ESG 팀 내에 전담 역할을 설정하고 있습니다.")
    assert "removed_leading_document_title_run" in actions


@pytest.mark.parametrize(
    "answer",
    [
        "대웅제약은 2022년, 2023년, 2024년 및 2025년 재활용률을 각각 공시하고 있습니다.",
        "재활용률은 2024년 89.2%, 2025년 89.1%를 달성하였으며 2026년 목표는 90.2%입니다.",
        "2022년: 박스테이프 변경 2023년: 라벨 적용 2024년: 케이스 개선 2025년: 용기 축소",
    ],
)
def test_prose_mentioning_several_years_is_not_treated_as_a_timeline_table(answer):
    cleaned, _, actions = clean_final_answer_for_customer(answer)

    assert cleaned == answer
    assert "removed_leading_document_title_run" not in actions


def test_missing_sentence_boundary_before_a_connector_is_restored():
    """Regression for Q019: the source lost the stop between two clauses, so a
    polite ending ran straight into the next sentence."""

    from esgagents.agents.answering.text_quality import normalize_answer_coherence

    fixed, actions = normalize_answer_coherence(
        "2022년 ISO 27001 인증을 획득하였습니다 그 결과, 보안 역량을 강화하였습니다."
    )

    assert fixed == "2022년 ISO 27001 인증을 획득하였습니다. 그 결과, 보안 역량을 강화하였습니다."
    assert "restored_sentence_boundary" in actions


def test_leading_result_connector_with_no_antecedent_is_removed():
    from esgagents.agents.answering.text_quality import normalize_answer_coherence

    fixed, actions = normalize_answer_coherence(
        "그 결과 2022년 제약업계 최초로 ISO 27001 인증을 획득하였습니다."
    )

    assert fixed == "2022년 제약업계 최초로 ISO 27001 인증을 획득하였습니다."
    assert "removed_leading_connector" in actions


@pytest.mark.parametrize(
    "answer",
    [
        "회사는 정책을 운영하고 있습니다. 또한 매년 점검합니다.",
        "임직원은 규정을 준수해야 한다고 합니다 만 예외가 있습니다.",
        "평가는 26개 항목으로 구성됩니다. 대웅제약은 이를 매년 점검합니다.",
    ],
)
def test_well_formed_answers_keep_their_punctuation(answer):
    from esgagents.agents.answering.text_quality import normalize_answer_coherence

    fixed, actions = normalize_answer_coherence(answer)

    assert fixed == answer
    assert "restored_sentence_boundary" not in actions


def test_flattened_column_header_row_is_raw_table_output():
    """Regression for Q079: a committee table's header row ("구분 | 기능 | 실적")
    arrived as running text and no detector recognised it."""

    assert non_narrative_reason("구분 기능 실적 감사의 이사회 출석 현황 7회 개최") == "raw_table_output"


def test_prose_using_the_header_words_naturally_is_not_a_raw_table():
    assert non_narrative_reason("구분에 따라 기능별 실적을 매년 점검하고 있습니다.") == ""


def test_prose_after_a_flattened_table_row_survives():
    """The committee table swallowed a following clause about 상근감사 제도 because the
    whole run had no sentence stop until the very end."""

    cleaned, reason, actions = clean_final_answer_for_customer(
        "정관에 따라 이사회는 3명 이상 9명 이내의 이사로 구성합니다. "
        "위원회 기능 및 개최실적 구분 기능 실적 감사의 이사회 출석 현황 7회 개최 "
        "관계사거래위원회 계열사 간 거래의 사전 심의 인사보상위원회 신규임원을 선임 확인 중 "
        "감사기구 운영 상근감사 제도 (주)대웅제약은 2025년까지 상근감사 제도를 운영하여 "
        "감사 1인이 이사회에 참석하고 독립적인 감독 기능을 수행해 왔습니다."
    )

    assert "구분 기능 실적" not in cleaned
    assert "확인 중" not in cleaned
    assert "7회 개최" not in cleaned
    assert cleaned.startswith("정관에 따라 이사회는 3명 이상 9명 이내의 이사로 구성합니다.")
    assert "(주)대웅제약은 2025년까지 상근감사 제도를 운영하여" in cleaned
    assert reason == ""
    assert "removed_leading_document_title_run" in actions
