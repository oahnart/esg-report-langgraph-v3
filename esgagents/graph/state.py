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
    normalized_evidence: dict[str, Any]
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
    claim_support: dict[str, list[Any]]
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
