from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal
import unicodedata

from esgagents.default_config import DEFAULT_CONFIG
from esgagents.quality import answer_invariant_issues, resolved_answer_quality
from esgagents.customer_text import strip_customer_meta_limitations


PublicationStatus = Literal["published", "review_required", "blocked"]
PUBLICATION_STATUSES: tuple[PublicationStatus, ...] = (
    "published",
    "review_required",
    "blocked",
)

REVIEW_FLAGS = {
    "assessment_based_answer",
    "conflicting_metric",
    "draft_based_answer",
    "human_review_required",
    "legal_review_required",
    "local_partial_evidence",
    "metric_low_confidence",
    "metric_not_found",
    "metric_numeric_withheld",
    "metric_summary_mismatch",
    "partial_answer",
    "rag_partial_coverage",
    "provenance_fallback",
    "source_path_invalid",
    "thin_evidence",
    "upstream_coverage_mismatch",
}


@dataclass(frozen=True)
class PublicationDecision:
    status: PublicationStatus
    reason: str
    issues: tuple[str, ...] = ()


def evaluate_publication(
    answer: Any,
    *,
    accepted_statuses: set[str] | None = None,
    conditional_statuses: set[str] | None = None,
) -> PublicationDecision:
    """Return the deterministic customer-publication decision for an answer."""

    accepted = {
        str(value).strip().casefold()
        for value in (
            accepted_statuses
            if accepted_statuses is not None
            else DEFAULT_CONFIG["accepted_answer_statuses"]
        )
    }
    conditional = {
        str(value).strip().casefold()
        for value in (
            conditional_statuses
            if conditional_statuses is not None
            else DEFAULT_CONFIG.get("conditional_answer_statuses", set())
        )
    }
    final_answer = str(getattr(answer, "final_answer", "") or "").strip()
    qa_status = str(getattr(getattr(answer, "qa", None), "status", "") or "").casefold()
    answer_status = str(getattr(answer, "answer_status", "") or "").strip().casefold()
    local_acceptance_reason = str(
        getattr(answer, "local_acceptance_reason", "") or ""
    )
    local_evidence_accepted = bool(
        getattr(answer, "local_evidence_accepted", False)
    ) and local_acceptance_reason in {
        "accepted_v3_local_partial",
        "accepted_draft_evidence",
        "accepted_assessment_evidence",
    }
    flags = {
        str(flag or "").strip().casefold()
        for flag in (getattr(answer, "quality_flags", []) or [])
        if str(flag or "").strip()
    }
    hard_failures = tuple(
        sorted(
            {
                str(failure or "").strip()
                for failure in (getattr(answer, "hard_failures", []) or [])
                if str(failure or "").strip()
            }
        )
    )

    quality = resolved_answer_quality(answer)

    # Import lazily to avoid the agents package's compatibility imports forming
    # a cycle while publication policy is imported by ReportManagerAgent.
    from esgagents.agents.evidence.metric_facts import (
        conflicting_metric_claims,
        unsupported_numeric_metric_claims,
    )

    metric_audit = getattr(answer, "metric_audit", {}) or {}
    metric_status = str(
        metric_audit.get("metric_status")
        or getattr(answer, "rag_metric_status", "")
        or ""
    ).casefold()
    unresolved_conflicts = conflicting_metric_claims(final_answer, metric_audit)
    final_answer_metric_audit = (
        {**metric_audit, "accepted_facts": []}
        if metric_status == "found_table"
        else metric_audit
    )
    unsupported_metric_claims = (
        unsupported_numeric_metric_claims(final_answer, final_answer_metric_audit)
        if metric_status in {"found_table", "not_found"}
        else []
    )
    claim_blocking, claim_review = _claim_support_issues(answer)
    source_review = _source_review_issues(answer)
    qid_blocking, qid_review = _qid_contract_issues(answer)
    invariant_issues = set(answer_invariant_issues(answer))

    blocking_issues: set[str] = set()
    blocking_reason = ""
    if answer_status not in accepted | conditional and not local_evidence_accepted:
        blocking_reason = "unaccepted_answer_status"
        blocking_issues.add(f"unaccepted_answer_status:{answer_status or 'missing'}")
    if hard_failures:
        if not blocking_reason:
            blocking_reason = "hard_failure"
        blocking_issues.update(hard_failures)
    if unsupported_metric_claims:
        if not blocking_reason:
            blocking_reason = "unsupported_metric_claim"
        blocking_issues.add("unsupported_metric_claim")
    if claim_blocking:
        if not blocking_reason:
            blocking_reason = "unsupported_claim"
        blocking_issues.update(claim_blocking)
    if qid_blocking:
        if not blocking_reason:
            blocking_reason = "thematic_mismatch"
        blocking_issues.update(qid_blocking)
    if qa_status != "passed":
        if not blocking_reason:
            blocking_reason = "qa_not_passed"
        blocking_issues.add(f"qa_status:{qa_status or 'missing'}")
    if quality.grade == "failed" and final_answer:
        if not blocking_reason:
            blocking_reason = quality.reason
        blocking_issues.update(quality.issues)
    if not final_answer:
        if not blocking_reason:
            blocking_reason = "empty_final_answer"
        blocking_issues.add("empty_final_answer")
    if blocking_issues:
        return PublicationDecision(
            "blocked",
            blocking_reason or "blocked",
            tuple(sorted(blocking_issues)),
        )

    review_issues = set(quality.issues)
    review_issues.update(flags.intersection(REVIEW_FLAGS))
    review_issues.update(claim_review)
    review_issues.update(source_review)
    review_issues.update(qid_review)
    review_issues.update(invariant_issues)
    if local_evidence_accepted:
        review_issues.add("local_partial_evidence")
    if metric_status == "not_found":
        review_issues.add("metric_not_found")
    if unresolved_conflicts:
        review_issues.add("unresolved_metric_conflict")
    if quality.grade != "full":
        review_issues.add(f"qa_grade:{quality.grade}")
    if review_issues:
        return PublicationDecision(
            "review_required",
            quality.reason if quality.grade != "full" else "human_review_required",
            tuple(sorted(review_issues)),
        )

    return PublicationDecision("published", "complete_grounded_answer", ())


def _claim_support_issues(answer: Any) -> tuple[set[str], set[str]]:
    blocking: set[str] = set()
    review: set[str] = set()
    for support in getattr(answer, "claim_support", []) or []:
        getter = support.get if isinstance(support, dict) else lambda key, default=None: getattr(support, key, default)
        status = str(getter("support_status", "") or "").casefold()
        claim_id = str(getter("claim_id", "") or "claim")
        source_ids = list(getter("source_ids", []) or [])
        tier = str(getter("support_tier", "") or "tier_unknown").casefold()
        if status == "unsupported":
            blocking.add(f"unsupported_claim:{claim_id}")
        if status in {"grounded", "partial"} and not source_ids:
            blocking.add(f"claim_missing_source:{claim_id}")
        if status in {"grounded", "partial"} and tier == "tier_unknown":
            review.add("unknown_source_tier")
        if status in {"grounded", "partial"} and tier == "tier_4_draft":
            review.add("draft_evidence")
    return blocking, review


def _source_review_issues(answer: Any) -> set[str]:
    issues: set[str] = set()
    for source in getattr(answer, "sources", []) or []:
        if not isinstance(source, dict):
            continue
        if bool(source.get("provenance_fallback")):
            issues.add("provenance_fallback")
        tier = str(source.get("source_tier", "") or "").casefold()
        if tier == "tier_unknown":
            issues.add("unknown_source_tier")
        stable = bool(
            str(source.get("source_path", "") or "").strip()
            or str(source.get("canonical_source_id", "") or "").strip()
            or (
                str(source.get("document_id", "") or "").strip()
                and str(source.get("chunk_id", "") or "").strip()
            )
        )
        if not stable:
            issues.add("source_path_invalid")
    return issues


def _qid_contract_issues(answer: Any) -> tuple[set[str], set[str]]:
    qid = str(getattr(answer, "qid", "") or "")
    text = unicodedata.normalize(
        "NFKC",
        str(getattr(answer, "final_answer", "") or ""),
    ).casefold()
    blocking: set[str] = set()
    review: set[str] = set()
    if qid == "Q021":
        operating_terms = (
            "환경경영팀",
            "환경 담당",
            "ehs팀",
            "실무 조직",
            "운영 조직",
            "environment team",
            "ehs team",
            "operating organization",
        )
        site_terms = (
            "사업장",
            "공장",
            "현장 관리",
            "환경관리체계",
            "환경 관리 체계",
            "site management",
            "facility management",
            "plant management",
        )
        if not any(term in text for term in operating_terms):
            review.add("missing_facet:operating_organization")
        if not any(term in text for term in site_terms):
            review.add("missing_facet:site_management_system")
    if qid == "Q074":
        target_terms = (
            "독립성",
            "이해상충",
            "사외이사",
            "전문성",
            "전문 역량",
            "전문가",
            "independence",
            "conflict of interest",
            "expertise",
            "professionalism",
        )
        proxy_terms = (
            "내부거래",
            "특수관계자",
            "내부회계",
            "rcm",
            "related-party transaction",
            "internal transaction",
            "internal accounting",
        )
        if any(term in text for term in proxy_terms) and not any(
            term in text for term in target_terms
        ):
            blocking.add("thematic_mismatch:committee_risk_proxy")
    if qid == "Q083":
        privacy_or_security = any(
            term in text
            for term in (
                "개인정보",
                "정보보호",
                "보안",
                "privacy",
                "information security",
                "information-security",
                "cyber",
            )
        )
        esg_progress = bool(
            re.search(
                r"esg.{0,15}(?:목표|이행|진척|달성|target|progress)",
                text,
                flags=re.IGNORECASE,
            )
        )
        if privacy_or_security and not esg_progress:
            blocking.add("thematic_mismatch:esg_progress_proxy")
    return blocking, review


def resolved_publication_decision(answer: Any) -> PublicationDecision:
    """Use persisted publication fields when present, otherwise evaluate legacy records."""

    status = str(getattr(answer, "publication_status", "") or "")
    if status in PUBLICATION_STATUSES:
        return PublicationDecision(
            status=status,  # type: ignore[arg-type]
            reason=str(getattr(answer, "publication_reason", "") or ""),
            issues=tuple(
                sorted(set(getattr(answer, "publication_issues", []) or []))
            ),
        )
    return evaluate_publication(answer)


def customer_export_answer(answer: Any) -> str:
    """Return the exact answer that may be written to customer artifacts.

    Review-required answers are customer-visible when they retain a safe,
    substantive claim. Review metadata stays in status/audit fields instead of
    being appended to the customer-facing prose. Blocked answers are never returned.
    """

    persisted = resolved_publication_decision(answer)
    current = evaluate_publication(answer)
    exportable = {"published", "review_required"}
    if persisted.status not in exportable or current.status not in exportable:
        return ""
    candidate, _ = strip_customer_meta_limitations(
        str(getattr(answer, "final_answer", "") or "")
    )
    return candidate


def published_answer(answer: Any) -> str:
    """Backward-compatible alias for the customer-export answer."""

    return customer_export_answer(answer)


def apply_customer_answer_contract(answer: Any) -> PublicationDecision:
    """Normalize an answer so JSON and the customer workbook share one value.

    The function is idempotent and is deliberately called both by the report
    manager and by the output boundary. This protects artifacts constructed by
    tests, legacy loaders, or alternate graph entry points.
    """

    candidate = str(getattr(answer, "final_answer", "") or "").strip()
    cleaned_candidate, limitation_actions = strip_customer_meta_limitations(candidate)
    limitation_only = bool(candidate and not cleaned_candidate and limitation_actions)
    if cleaned_candidate != candidate:
        if candidate and not cleaned_candidate and not str(
            getattr(answer, "last_rejected_answer", "") or ""
        ).strip():
            setattr(answer, "last_rejected_answer", candidate)
        setattr(answer, "final_answer", cleaned_candidate)
        sanitizer_actions = list(getattr(answer, "sanitizer_actions", []) or [])
        sanitizer_actions.extend(limitation_actions)
        setattr(answer, "sanitizer_actions", list(dict.fromkeys(sanitizer_actions)))
        disclosure_flags = list(getattr(answer, "disclosure_flags", []) or [])
        disclosure_flags.append("customer_meta_limitation_removed")
        setattr(answer, "disclosure_flags", list(dict.fromkeys(disclosure_flags)))

    persisted = resolved_publication_decision(answer)
    current = evaluate_publication(answer)
    if (
        persisted.status == "blocked"
        and not str(getattr(answer, "final_answer", "") or "").strip()
    ):
        decision = persisted
    else:
        decision = _stricter_decision(persisted, current)

    if limitation_only:
        decision = PublicationDecision(
            "blocked",
            "disclosure_only_answer",
            tuple(sorted({*decision.issues, "disclosure_only_answer"})),
        )

    candidate = str(getattr(answer, "final_answer", "") or "").strip()
    if decision.status == "review_required" and candidate:
        if not _has_substantive_answer(candidate):
            decision = PublicationDecision(
                "blocked",
                "disclosure_only_answer",
                tuple(sorted({*decision.issues, "disclosure_only_answer"})),
            )

    if decision.status == "blocked":
        candidate = str(getattr(answer, "final_answer", "") or "").strip()
        if candidate and not str(getattr(answer, "last_rejected_answer", "") or "").strip():
            setattr(answer, "last_rejected_answer", candidate)
        setattr(answer, "final_answer", "")

    setattr(answer, "publication_status", decision.status)
    setattr(answer, "publication_reason", decision.reason)
    setattr(answer, "publication_issues", list(decision.issues))
    setattr(answer, "consumer_decision", _consumer_decision(decision, answer))
    setattr(answer, "result_bucket", _result_bucket(decision, answer))
    return decision


def _stricter_decision(
    persisted: PublicationDecision,
    current: PublicationDecision,
) -> PublicationDecision:
    rank = {"published": 0, "review_required": 1, "blocked": 2}
    if rank[current.status] > rank[persisted.status]:
        primary, secondary = current, persisted
    else:
        primary, secondary = persisted, current
    return PublicationDecision(
        primary.status,
        primary.reason,
        tuple(sorted({*primary.issues, *secondary.issues})),
    )


def _has_substantive_answer(text: str) -> bool:
    segments = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?。！？])\s+|\n+", str(text or ""))
        if segment.strip()
    ]
    if not segments:
        return False
    return any(
        len(segment) >= 3
        and bool(re.search(r"[A-Za-z가-힣]", segment))
        for segment in segments
    )


def _consumer_decision(decision: PublicationDecision, answer: Any) -> str:
    if decision.status == "published":
        return "answered"
    if decision.status == "review_required":
        return "answered_partial"
    answer_status = str(getattr(answer, "answer_status", "") or "").casefold()
    if answer_status not in {"high_confidence", "medium_confidence", "thin_but_usable"}:
        return "blocked_api_status"
    if any("provenance" in issue or "source_path" in issue for issue in decision.issues):
        return "blocked_provenance"
    qa_status = str(getattr(getattr(answer, "qa", None), "status", "") or "").casefold()
    if qa_status != "passed" or getattr(answer, "hard_failures", None):
        return "blocked_qa"
    return "blocked_evidence"


def _result_bucket(decision: PublicationDecision, answer: Any) -> str:
    if decision.status in {"published", "review_required"}:
        return "answered"
    qa_status = str(getattr(getattr(answer, "qa", None), "status", "") or "").casefold()
    if qa_status == "failed" or getattr(answer, "hard_failures", None):
        return "failed"
    answer_status = str(getattr(answer, "answer_status", "") or "").casefold()
    if answer_status not in {"high_confidence", "medium_confidence", "thin_but_usable"}:
        return "weak"
    return "empty"
