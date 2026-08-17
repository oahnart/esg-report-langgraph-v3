from __future__ import annotations

import re


CANONICAL_FLAGS = {
    "assessment_attributed",
    "assessment_based_answer",
    "assurance_review_recommended",
    "disclosed_data_gap",
    "draft_attributed",
    "draft_based_answer",
    "forward_looking_statement",
    "coherence_normalized",
    "claim_salvage_applied",
    "conflicting_metric",
    "evidence_extract_fallback",
    "human_review_required",
    "legal_review_required",
    "llm_error_fallback",
    "llm_free_text_fallback",
    "local_partial_evidence",
    "markdown_normalized",
    "metric_low_confidence",
    "metric_not_found",
    "metric_inline_candidate_unstructured",
    "metric_numeric_withheld",
    "metric_summary_mismatch",
    "metric_absence_no_candidate",
    "metric_absence_below_threshold",
    "metric_absence_blocked_by_gate",
    "malformed_metric_row",
    "all_metric_facts_conflicted",
    "missing_data_flag",
    "partial_answer",
    "pii_redacted",
    "quantitative_metric_bridge",
    "rag_assessment_only",
    "rag_draft_only",
    "rag_missing_required_facets",
    "rag_no_evidence",
    "rag_partial_coverage",
    "rag_wrong_topic",
    "revision_applied",
    "revision_error",
    "revision_returned_empty",
    "sanitizer_applied",
    "sanitizer_returned_empty",
    "semantic_review_fallback",
    "source_path_invalid",
    "provenance_fallback",
    "thin_evidence",
    "non_narrative_output",
    "non_substantive_llm_output",
    "enumeration_stub_output",
    "short_fragment_output",
    "structured_metric_fallback",
    "unsupported_metric_llm_output",
    "deterministic_narrative_fallback",
    "upstream_coverage_mismatch",
    "qa_invariant_violation",
    "writer_empty",
}
CANONICAL_PREFIXES = ("missing_facet:", "rag_missing_facet:")
RAG_REASON_MAP = {
    "ASSESSMENT_ONLY": "rag_assessment_only",
    "DRAFT_ONLY": "rag_draft_only",
    "MISSING_REQUIRED_FACETS": "rag_missing_required_facets",
    "NO_EVIDENCE": "rag_no_evidence",
    "WRONG_TOPIC": "rag_wrong_topic",
}
STALE_FLAGS = {"missing_quantitative_metric_result", "accepted_v3_complete"}


def canonicalize_quality_flags(flags: list[str]) -> tuple[list[str], list[str]]:
    canonical: list[str] = []
    notes: list[str] = []
    for raw in flags:
        value = str(raw or "").strip()
        if not value:
            continue
        normalized = value.casefold().replace(" ", "_")
        if normalized in STALE_FLAGS:
            continue
        if normalized in CANONICAL_FLAGS:
            canonical.append(normalized)
            continue
        if normalized.startswith(CANONICAL_PREFIXES):
            canonical.append(normalized)
            continue
        match = re.fullmatch(r"rag_v3:([A-Z_]+)", value, flags=re.IGNORECASE)
        if match and match.group(1).upper() in RAG_REASON_MAP:
            canonical.append(RAG_REASON_MAP[match.group(1).upper()])
            continue
        notes.append(value)
    return sorted(set(canonical)), list(dict.fromkeys(notes))
