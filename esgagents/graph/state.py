from __future__ import annotations

from typing import Any, TypedDict

from esgagents.schemas import CompanyInput, RunArtifacts


class ESGState(TypedDict, total=False):
    company_input: CompanyInput | dict[str, Any]
    company: Any
    questions: list[dict[str, Any]]
    scale_template: dict[str, Any]
    industry_template: dict[str, Any]
    template_selection: dict[str, Any]
    planned_questions: list[Any]
    rag_results: dict[str, Any]
    raw_rag_responses: list[dict[str, Any]]
    retrieval_attempts: dict[str, list[dict[str, Any]]]
    rag_request_traces: list[Any]
    evidence_gate: dict[str, Any]
    structural_evidence_audit: dict[str, dict[str, Any]]
    upstream_hints: dict[str, dict[str, Any]]
    upstream_coverage_mismatches: dict[str, bool]
    normalized_evidence: dict[str, Any]
    prepared_qualitative_evidence: dict[str, list[Any]]
    evidence_curation_results: dict[str, Any]
    curator_llm_results: dict[str, Any]
    curator_fingerprints: dict[str, str]
    curated_qualitative_evidence: dict[str, list[Any]]
    qualitative_answerability: dict[str, str]
    evidence_curation_stats: dict[str, int]
    evidence_curation_qid_stats: dict[str, dict[str, Any]]
    quantitative_results: list[dict[str, Any]]
    quantitative_stats: dict[str, int]
    quantitative_source_path: str
    metric_qid_bridge_results: dict[str, list[str]]
    agent_profiles: dict[str, str]
    skill_selections: dict[str, dict[str, Any]]
    skill_contexts: dict[str, dict[str, Any]]
    draft_answers: dict[str, str]
    qa_results: dict[str, Any]
    semantic_reviews: dict[str, Any]
    semantic_llm_reviews: dict[str, Any]
    semantic_review_fingerprints: dict[str, str]
    claim_support: dict[str, list[Any]]
    grounded_draft_sentences: dict[str, list[Any]]
    grounded_final_sentences: dict[str, list[Any]]
    grounding_issues: dict[str, list[str]]
    final_answers: dict[str, str]
    last_rejected_answers: dict[str, str]
    qa_failure_stages: dict[str, str]
    sanitizer_actions: dict[str, list[str]]
    skill_checks: dict[str, list[str]]
    disclosure_flags: dict[str, list[str]]
    hard_failures: dict[str, list[str]]
    quality_flags: dict[str, list[str]]
    revision_counts: dict[str, int]
    artifacts: RunArtifacts
