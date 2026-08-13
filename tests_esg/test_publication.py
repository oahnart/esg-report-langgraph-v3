from __future__ import annotations

import pytest

from esgagents.publication import (
    apply_customer_answer_contract,
    customer_export_answer,
    evaluate_publication,
    published_answer,
)
from esgagents.schemas import AnswerRecord, QAResult


def _answer(**updates) -> AnswerRecord:
    values = {
        "qid": "Q001",
        "answer_status": "high_confidence",
        "final_answer": "A grounded customer-ready answer.",
        "qa": QAResult(status="passed"),
        "qa_grade": "full",
        "coverage_reason": "complete_answer",
    }
    values.update(updates)
    return AnswerRecord(**values)


def test_only_full_clean_answer_is_published():
    decision = evaluate_publication(_answer())

    assert decision.status == "published"
    assert published_answer(_answer()) == "A grounded customer-ready answer."


@pytest.mark.parametrize("grade", ["partial", "cautious"])
def test_non_full_safe_answers_require_review(grade):
    answer = _answer(
        qa_grade=grade,
        coverage_reason="partial_answer" if grade == "partial" else "thin_evidence",
        coverage_issues=["partial_answer" if grade == "partial" else "thin_evidence"],
    )

    assert evaluate_publication(answer).status == "review_required"
    assert customer_export_answer(answer) == answer.final_answer
    assert published_answer(answer) == answer.final_answer


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"answer_status": "insufficient"}, "unaccepted_answer_status"),
        ({"qa": QAResult(status="failed")}, "qa_not_passed"),
        ({"qa": QAResult(status="empty")}, "qa_not_passed"),
        ({"final_answer": ""}, "empty_final_answer"),
        ({"hard_failures": ["rag_wrong_topic"]}, "hard_failure"),
    ],
)
def test_unsafe_answers_are_blocked(updates, reason):
    decision = evaluate_publication(_answer(**updates))

    assert decision.status == "blocked"
    assert decision.reason == reason


def test_table_shaped_narrative_fallback_is_blocked():
    answer = _answer(
        final_answer=(
            "CP팀 지대웅 법규 및 규제 위반 벌금 또는 처벌을 받은 사건 "
            "위반 건수 법무실 정은정 억 원 기타 규정 위반 위반 건수"
        ),
        qa=QAResult(status="passed", notes=["table_shaped_narrative_fallback"]),
    )

    decision = evaluate_publication(answer)

    assert decision.status == "blocked"
    assert decision.reason == "non_narrative_output"
    assert "non_narrative_output" in decision.issues


def test_table_shaped_narrative_fallback_bucket_is_failed():
    answer = _answer(
        final_answer="CP팀 지대웅 법규 및 규제 위반 벌금 또는 처벌을 받은 사건 위반 건수",
        qa=QAResult(status="passed", notes=["table_shaped_narrative_fallback"]),
    )

    apply_customer_answer_contract(answer)

    assert answer.final_answer == ""
    assert answer.result_bucket == "failed"
    assert answer.qa_grade == "failed"


def test_locally_admitted_insufficient_answer_requires_review_and_is_exported():
    answer = _answer(
        answer_status="insufficient",
        local_evidence_accepted=True,
        local_acceptance_reason="accepted_v3_local_partial",
        quality_flags=["local_partial_evidence", "partial_answer"],
        qa_grade="partial",
        coverage_reason="missing_expected_facets",
        coverage_issues=["missing_expected_facets", "partial_answer"],
    )

    decision = evaluate_publication(answer)

    assert decision.status == "review_required"
    assert "local_partial_evidence" in decision.issues
    assert customer_export_answer(answer) == answer.final_answer


def test_legacy_record_without_publication_fields_is_inferred_by_current_policy():
    legacy = _answer(publication_status=None)

    assert published_answer(legacy) == legacy.final_answer


def test_writer_downgrades_stale_published_status_to_customer_visible_review():
    stale = _answer(
        publication_status="published",
        publication_reason="complete_grounded_answer",
        qa_grade="partial",
        coverage_reason="partial_answer",
        coverage_issues=["partial_answer"],
    )

    assert customer_export_answer(stale) == stale.final_answer


def test_blocked_candidate_moves_to_last_rejected_answer():
    answer = _answer(
        rag_metric_status="not_found",
        metric_audit={"metric_status": "not_found", "accepted_facts": []},
        final_answer="In 2025, human-rights grievances totaled 63 cases.",
    )

    decision = apply_customer_answer_contract(answer)

    assert decision.status == "blocked"
    assert answer.final_answer == ""
    assert answer.last_rejected_answer.endswith("63 cases.")
    assert answer.consumer_decision == "blocked_evidence"
    assert answer.result_bucket == "empty"


def test_review_answer_keeps_review_metadata_out_of_customer_text():
    answer = _answer(
        qid="Q021",
        qa_grade="partial",
        coverage_reason="missing_expected_facets",
        coverage_issues=["missing_expected_facets"],
        publication_status="review_required",
        publication_reason="missing_expected_facets",
        publication_issues=["missing_facet:operating_organization"],
        final_answer="The Board reviews and approves the EHS policy annually.",
    )

    decision = apply_customer_answer_contract(answer)

    assert decision.status == "review_required"
    assert answer.final_answer == "The Board reviews and approves the EHS policy annually."
    assert "missing_facet:operating_organization" in answer.publication_issues
    assert answer.consumer_decision == "answered_partial"


def test_disclosure_only_review_answer_is_blocked():
    answer = _answer(
        qa_grade="partial",
        coverage_reason="missing_expected_facets",
        coverage_issues=["missing_expected_facets"],
        publication_status="review_required",
        publication_reason="missing_expected_facets",
        publication_issues=["qa_grade:partial"],
        final_answer="The requested information was not found in the supplied evidence.",
    )

    decision = apply_customer_answer_contract(answer)

    assert decision.status == "blocked"
    assert decision.reason == "disclosure_only_answer"
    assert answer.final_answer == ""
    assert answer.last_rejected_answer


def test_draft_review_answer_uses_attribution_without_confirmation_request():
    answer = _answer(
        qa_grade="cautious",
        coverage_reason="draft_evidence",
        coverage_issues=["draft_evidence"],
        publication_status="review_required",
        publication_reason="draft_evidence",
        publication_issues=["draft_evidence", "qa_grade:cautious"],
        final_answer="According to the proposal, the company plans to expand its program.",
    )

    decision = apply_customer_answer_contract(answer)

    assert decision.status == "review_required"
    assert answer.final_answer == "According to the proposal, the company plans to expand its program."
    assert "draft_evidence" in answer.publication_issues


def test_vietnamese_meta_limitation_is_removed_from_substantive_answer():
    answer = _answer(
        qa_grade="partial",
        coverage_reason="partial_answer",
        coverage_issues=["partial_answer"],
        publication_status="review_required",
        publication_reason="partial_answer",
        publication_issues=["qa_grade:partial"],
        final_answer=(
            "Công ty vận hành kênh tiếp nhận khiếu nại về nhân quyền. "
            "Do phạm vi của tài liệu được cung cấp, một số mục cần được xác nhận bổ sung."
        ),
    )

    decision = apply_customer_answer_contract(answer)

    assert decision.status == "review_required"
    assert answer.final_answer == "Công ty vận hành kênh tiếp nhận khiếu nại về nhân quyền."
    assert "customer_meta_limitation_removed" in answer.disclosure_flags
    assert "removed_customer_meta_limitation" in answer.sanitizer_actions


@pytest.mark.parametrize(
    "flag",
    [
        "metric_low_confidence",
        "metric_summary_mismatch",
        "human_review_required",
        "conflicting_metric",
        "legal_review_required",
        "provenance_fallback",
    ],
)
def test_review_flags_prevent_auto_publication(flag):
    decision = evaluate_publication(_answer(quality_flags=[flag]))

    assert decision.status == "review_required"


def test_metric_not_found_numeric_claim_is_blocked_without_accepted_fact():
    answer = _answer(
        rag_metric_status="not_found",
        metric_audit={"metric_status": "not_found", "accepted_facts": []},
        final_answer="In 2025, human-rights grievances totaled 63 cases.",
    )

    decision = evaluate_publication(answer)

    assert decision.status == "blocked"
    assert decision.reason == "unsupported_metric_claim"
    assert "unsupported_metric_claim" in decision.issues


def test_metric_not_found_qualitative_answer_requires_review():
    answer = _answer(
        rag_metric_status="not_found",
        metric_audit={"metric_status": "not_found", "accepted_facts": []},
        final_answer=(
            "The company operates an eco-friendly packaging roadmap. "
            "No quantitative figure was found in the supplied evidence."
        ),
        quality_flags=["metric_not_found", "partial_answer"],
    )

    decision = evaluate_publication(answer)

    assert decision.status == "review_required"
    assert "metric_not_found" in decision.issues


def test_publication_reason_prefers_upstream_failure_over_empty_answer():
    decision = evaluate_publication(
        _answer(answer_status="insufficient", final_answer="", qa=QAResult(status="empty"))
    )

    assert decision.status == "blocked"
    assert decision.reason == "unaccepted_answer_status"
    assert "empty_final_answer" in decision.issues


def test_contradictory_metric_qa_state_cannot_publish_as_full():
    answer = _answer(
        qa=QAResult(status="passed", notes=["metric_not_found"]),
        skill_checks=["facet_metric_result: covered"],
    )

    decision = evaluate_publication(answer)

    assert decision.status == "review_required"
    assert any(issue.startswith("qa_invariant_violation:") for issue in decision.issues)


def test_q021_board_only_answer_requires_review_at_publication_boundary():
    decision = evaluate_publication(
        _answer(
            qid="Q021",
            final_answer="The Board reviews and approves the EHS policy annually.",
        )
    )

    assert decision.status == "review_required"
    assert "missing_facet:operating_organization" in decision.issues
    assert "missing_facet:site_management_system" in decision.issues


@pytest.mark.parametrize(
    ("qid", "answer"),
    [
        (
            "Q074",
            "The Internal Transaction Committee reviews related-party transactions and the RCM.",
        ),
        (
            "Q083",
            "In 2024, information-security risks were assessed across 17 inspection targets.",
        ),
    ],
)
def test_wrong_topic_proxy_is_blocked_at_publication_boundary(qid, answer):
    decision = evaluate_publication(_answer(qid=qid, final_answer=answer))

    assert decision.status == "blocked"
    assert decision.reason in {"thematic_mismatch", "unsupported_metric_claim"}
