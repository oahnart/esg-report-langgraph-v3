from esgagents.quality import classify_answer_quality, resolved_answer_quality
from esgagents.schemas import AnswerRecord, ClaimSupport, QAResult


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


def test_mixed_sources_are_cautious_only_when_a_claim_depends_on_draft():
    answer = _answer(
        sources=[
            {"source_tier": "tier_2_operational", "document_status": "operational"},
            {"source_tier": "tier_4_draft", "document_status": "draft"},
        ],
        claim_support=[
            ClaimSupport(
                claim_id="c1",
                claim_text="Operational policy claim.",
                source_ids=["operational"],
                support_tier="tier_2_operational",
                support_status="grounded",
            ),
            ClaimSupport(
                claim_id="c2",
                claim_text="Proposed target claim.",
                source_ids=["draft"],
                support_tier="tier_4_draft",
                support_status="grounded",
                attribution_required=False,
            ),
        ],
    )

    quality = classify_answer_quality(answer)

    assert (quality.grade, quality.reason) == ("cautious", "draft_evidence")


def test_auxiliary_draft_source_does_not_lower_operationally_grounded_claim():
    answer = _answer(
        sources=[
            {"source_tier": "tier_2_operational", "document_status": "operational"},
            {"source_tier": "tier_4_draft", "document_status": "draft"},
        ],
        claim_support=[
            ClaimSupport(
                claim_id="c1",
                claim_text="Operational policy claim.",
                source_ids=["operational"],
                support_tier="tier_2_operational",
                support_status="grounded",
            )
        ],
    )

    quality = classify_answer_quality(answer)

    assert (quality.grade, quality.reason) == ("full", "complete_grounded_answer")


def test_quality_grade_failed_for_empty_or_unsupported_answer():
    empty = classify_answer_quality(
        _answer(final_answer="", qa=QAResult(status="empty", notes=["empty evidence"]))
    )
    unsupported = classify_answer_quality(
        _answer(qa=QAResult(status="passed", notes=["unsupported numeric claim: 30%"]))
    )

    assert (empty.grade, empty.reason) == ("failed", "empty_evidence")
    assert (unsupported.grade, unsupported.reason) == ("failed", "unsupported_claim")


def test_quality_uses_specific_writer_empty_reason():
    quality = classify_answer_quality(
        _answer(
            qid="Q015",
            final_answer="",
            qa=QAResult(status="empty", notes=["writer returned empty output"]),
            quality_flags=["writer_empty"],
        )
    )

    assert (quality.grade, quality.reason) == ("failed", "writer_empty")


def test_resolved_quality_falls_back_for_legacy_record_without_grade():
    legacy = _answer(qa_grade=None, coverage_reason="", coverage_issues=[])

    quality = resolved_answer_quality(legacy)

    assert (quality.grade, quality.reason) == ("full", "complete_grounded_answer")


def test_metric_not_found_with_supported_inline_number_is_table_gap_not_prose_gap():
    quality = classify_answer_quality(
        _answer(
            final_answer="2025년 인권 관련 고충처리는 총 63건이며 모두 처리 완료되었습니다.",
            qa=QAResult(status="passed", notes=["metric_not_found"]),
            quality_flags=[
                "metric_not_found",
                "metric_inline_candidate_unstructured",
                "metric_inline_answered",
                "partial_answer",
            ],
            rag_metric_status="not_found",
        )
    )

    assert quality.grade == "partial"
    assert quality.reason == "metric_table_not_found"
    assert "metric_table_not_found" in quality.issues
    assert "missing_metric_or_period" not in quality.issues
