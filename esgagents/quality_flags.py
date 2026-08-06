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
    "legal_review_required",
    "llm_error_fallback",
    "llm_free_text_fallback",
    "markdown_normalized",
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
    "sanitizer_applied",
    "semantic_review_fallback",
    "source_path_invalid",
    "thin_evidence",
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
