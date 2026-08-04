from esgagents.quality import classify_answer_quality, resolved_answer_quality
from esgagents.schemas import AnswerRecord, QAResult


def _answer(**overrides):
    values = {
        "qid": "Q001",
        "final_answer": "Grounded answer",
        "qa": QAResult(status="passed", notes=["grounded"]),
        "sources": [{"source_tier": "tier_1_governing", "document_status": "governing"}],
    }
    values.update(overrides)
    return AnswerRecord(**values)


def test_quality_grade_full_for_complete_strong_answer():
    quality = classify_answer_quality(_answer())

    assert quality.grade == "full"
    assert quality.reason == "complete_grounded_answer"
    assert quality.issues == ()


def test_quality_grade_draft_is_always_cautious_even_when_partial():
    quality = classify_answer_quality(
        _answer(
            qa=QAResult(status="passed", notes=["missing facet: target"]),
            quality_flags=["partial_answer", "draft_based_answer"],
            sources=[{"source_tier": "tier_4_draft", "document_status": "draft"}],
        )
    )

    assert quality.grade == "cautious"
    assert quality.reason == "draft_evidence"
    assert "draft_evidence" in quality.issues


def test_quality_grade_cautious_for_complete_draft_or_assessment_answer():
    draft = classify_answer_quality(
        _answer(
            quality_flags=["draft_based_answer"],
            sources=[{"source_tier": "tier_4_draft", "document_status": "draft"}],
        )
    )
    assessment = classify_answer_quality(
        _answer(sources=[{"source_tier": "tier_3_assessment", "document_status": "assessed"}])
    )

    assert (draft.grade, draft.reason) == ("cautious", "draft_evidence")
    assert (assessment.grade, assessment.reason) == ("cautious", "assessment_only")


def test_quality_grade_failed_for_empty_or_unsupported_answer():
    empty = classify_answer_quality(
        _answer(final_answer="", qa=QAResult(status="empty", notes=["empty evidence"]))
    )
    unsupported = classify_answer_quality(
        _answer(qa=QAResult(status="passed", notes=["unsupported numeric claim: 30%"]))
    )

    assert (empty.grade, empty.reason) == ("failed", "empty_evidence")
    assert (unsupported.grade, unsupported.reason) == ("failed", "unsupported_claim")


def test_resolved_quality_falls_back_for_legacy_record_without_grade():
    legacy = _answer(qa_grade=None, coverage_reason="", coverage_issues=[])

    quality = resolved_answer_quality(legacy)

    assert (quality.grade, quality.reason) == ("full", "complete_grounded_answer")
