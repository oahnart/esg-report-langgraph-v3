from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


QAGrade = Literal["full", "partial", "cautious", "failed"]
QA_GRADES: tuple[QAGrade, ...] = ("full", "partial", "cautious", "failed")

FAILED_REASON_PRECEDENCE = (
    "rag_missing_required_facets",
    "rag_no_evidence",
    "rag_wrong_topic",
    "writer_empty",
    "empty_evidence",
    "missing_source_path",
    "weak_semantic_labels",
    "thematic_mismatch",
    "unsupported_claim",
    "source_usage_overstated",
    "missing_metric_or_period",
    "qa_failed",
)
PARTIAL_REASON_PRECEDENCE = (
    "missing_metric_or_period",
    "missing_required_facets",
    "missing_expected_facets",
    "disclosed_data_gap",
    "partial_answer",
)
CAUTIOUS_REASON_PRECEDENCE = (
    "draft_evidence",
    "thin_evidence",
    "assessment_only",
    "unknown_source_tier",
)


@dataclass(frozen=True)
class AnswerQuality:
    grade: QAGrade
    reason: str
    issues: tuple[str, ...]


def classify_answer_quality(answer: Any) -> AnswerQuality:
    final_answer = str(getattr(answer, "final_answer", "") or "").strip()
    qa = getattr(answer, "qa", None)
    qa_status = str(getattr(qa, "status", "") or "").casefold()
    notes = list(getattr(qa, "notes", []) or [])
    flags = list(getattr(answer, "quality_flags", []) or [])
    checks = list(getattr(answer, "skill_checks", []) or [])
    hard_failures = list(getattr(answer, "hard_failures", []) or [])
    combined = " | ".join([*notes, *flags, *checks, *hard_failures]).casefold()

    issues: set[str] = set()
    if "empty evidence" in combined:
        issues.add("empty_evidence")
    if "rag_missing_required_facets" in combined or "rag_v3:missing_required_facets" in combined:
        issues.add("rag_missing_required_facets")
    if "rag_no_evidence" in combined or "rag_v3:no_evidence" in combined:
        issues.add("rag_no_evidence")
    if "rag_wrong_topic" in combined or "rag_v3:wrong_topic" in combined:
        issues.add("rag_wrong_topic")
    if "writer_empty" in combined:
        issues.add("writer_empty")
    if (
        "missing source_path" in combined
        or "missing source path" in combined
        or "missing stable provenance" in combined
    ):
        issues.add("missing_source_path")
    if "all evidence semantic labels are weak" in combined:
        issues.add("weak_semantic_labels")
    if any(
        term in combined
        for term in (
            "semantic thematic mismatch",
            "thematic mismatch",
            "wrong topic",
            "semantic misalignment",
        )
    ):
        issues.add("thematic_mismatch")
    if any(
        term in combined
        for term in (
            "unsupported numeric claim",
            "unsupported certification",
            "unsupported initiative claim",
            "unsupported claim",
        )
    ):
        issues.add("unsupported_claim")
    if "source usage overstated" in combined or "source_usage: overstated" in combined:
        issues.add("source_usage_overstated")
    if any(
        term in combined
        for term in (
            "missing_quantitative_metric_result",
            "missing required facet: metric_result",
            "missing required facet: reporting_period",
        )
    ):
        issues.add("missing_metric_or_period")
    if "missing required facet:" in combined:
        issues.add("missing_required_facets")
    if (
        "missing facet:" in combined
        or "missing_facet:" in combined
        or any(check.startswith("facet_") and check.endswith(": missing") for check in checks)
    ):
        issues.add("missing_expected_facets")
    if "missing data disclosed" in combined or "disclosed_data_gap" in combined:
        issues.add("disclosed_data_gap")
    if "partial_answer" in combined or "question_alignment: partial" in combined:
        issues.add("partial_answer")
    if "thin_evidence" in combined or "accepted_thin_evidence" in combined:
        issues.add("thin_evidence")

    sources = [source for source in (getattr(answer, "sources", []) or []) if isinstance(source, dict)]
    claim_support = list(getattr(answer, "claim_support", []) or [])
    claim_tiers = {
        str(
            support.get("support_tier", "")
            if isinstance(support, dict)
            else getattr(support, "support_tier", "")
        ).casefold()
        for support in claim_support
        if str(
            support.get("support_status", "")
            if isinstance(support, dict)
            else getattr(support, "support_status", "")
        ).casefold() in {"grounded", "partial"}
    }
    source_tiers = {str(source.get("source_tier", "") or "").casefold() for source in sources}
    source_tiers.discard("")
    source_statuses = {str(source.get("document_status", "") or "").casefold() for source in sources}
    source_statuses.discard("")
    if (
        "draft_based_answer" in combined
        or "draft_evidence" in combined
        or "tier_4_draft" in claim_tiers
        or (source_tiers and source_tiers <= {"tier_4_draft"})
        or (
            source_statuses
            and source_statuses
            <= {"draft", "proposed", "proposal", "under_review", "under review"}
        )
    ):
        issues.add("draft_evidence")
    if (
        "assessment_based_answer" in combined
        or "tier_3_assessment" in claim_tiers
        or (source_tiers and source_tiers <= {"tier_3_assessment"})
    ):
        issues.add("assessment_only")
    if final_answer and (not source_tiers or source_tiers <= {"tier_unknown"}):
        issues.add("unknown_source_tier")

    hard_failure = bool(hard_failures) or bool(
        issues & {"thematic_mismatch", "unsupported_claim", "source_usage_overstated"}
    )
    if not final_answer or qa_status in {"empty", "failed"} or hard_failure:
        if qa_status == "failed" or hard_failure:
            issues.add("qa_failed")
        if not issues:
            issues.add("writer_empty" if sources else "rag_no_evidence")
        return AnswerQuality(
            "failed",
            _first_reason(issues, FAILED_REASON_PRECEDENCE),
            tuple(sorted(issues)),
        )

    # Draft evidence is never eligible for a full or partial grade. Even when
    # another facet is missing, the source status is the dominant caution.
    if "draft_evidence" in issues or "assessment_only" in issues:
        reason = "draft_evidence" if "draft_evidence" in issues else "assessment_only"
        return AnswerQuality(
            "cautious",
            reason,
            tuple(sorted(issues)),
        )

    if issues.intersection(PARTIAL_REASON_PRECEDENCE):
        return AnswerQuality(
            "partial",
            _first_reason(issues, PARTIAL_REASON_PRECEDENCE),
            tuple(sorted(issues)),
        )

    if issues.intersection(CAUTIOUS_REASON_PRECEDENCE):
        return AnswerQuality(
            "cautious",
            _first_reason(issues, CAUTIOUS_REASON_PRECEDENCE),
            tuple(sorted(issues)),
        )

    return AnswerQuality("full", "complete_grounded_answer", ())


def resolved_answer_quality(answer: Any) -> AnswerQuality:
    classified = classify_answer_quality(answer)
    explicit_grade = str(getattr(answer, "qa_grade", "") or "")
    explicit_reason = str(getattr(answer, "coverage_reason", "") or "")
    explicit_issues = tuple(sorted(set(getattr(answer, "coverage_issues", []) or [])))
    if explicit_grade in QA_GRADES and explicit_reason:
        return AnswerQuality(explicit_grade, explicit_reason, explicit_issues)  # type: ignore[arg-type]
    return classified


def _first_reason(issues: set[str], precedence: tuple[str, ...]) -> str:
    return next((reason for reason in precedence if reason in issues), precedence[-1])
