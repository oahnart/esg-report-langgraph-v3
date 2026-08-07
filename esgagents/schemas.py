from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    if not 1 <= len(value) <= 128:
        raise ValueError(f"{field_name} must be between 1 and 128 characters")
    if not value[0].isalnum() or not value[-1].isalnum():
        raise ValueError(f"{field_name} must start and end with a letter or number")
    if any(not (char.isalnum() or char in "._-") for char in value):
        raise ValueError(f"{field_name} may contain only letters, numbers, '.', '_' and '-'")
    return value


class CompanyInput(BaseModel):
    company_id: str
    company_name: str = ""
    year: int
    scale: str
    industry: str
    top_k: int | None = None
    item_ids: list[str] | None = None
    output_language: str = "Korean"
    run_id: str | None = None

    @field_validator("company_id", "scale", "industry")
    @classmethod
    def _required_text(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("field is required")
        return value

    @field_validator("year")
    @classmethod
    def _valid_year(cls, value: int) -> int:
        if value < 2000 or value > 2100:
            raise ValueError("year must be between 2000 and 2100")
        return value

    @field_validator("company_id")
    @classmethod
    def _valid_company_id(cls, value: str) -> str:
        return validate_identifier(value, "company_id")

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str | None) -> str | None:
        return validate_identifier(value, "run_id") if value is not None else None

    def resolved_run_id(self) -> str:
        return self.run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}"


class NormalizedCompany(BaseModel):
    company_id: str
    company_name: str
    year: int
    scale: str
    industry: str
    top_k: int
    item_ids: list[str] | None = None
    output_language: str
    run_id: str


class EvidenceLocator(BaseModel):
    page: int | None = None
    sheet_name: str | None = None
    slide_number: int | None = None
    section: str | None = None
    paragraph: str | None = None
    cell_range: str | None = None
    spans_units: list[str] | None = None
    confidence: str | None = None


class EvidenceFact(BaseModel):
    metric: str = ""
    period: str = ""
    value: str = ""
    unit: str = ""
    value_role: Literal["actual", "target", "unknown"] = "unknown"
    scope: str = ""
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)

    @field_validator("metric", "period", "value", "unit", "scope", mode="before")
    @classmethod
    def _fact_text(cls, value: Any) -> str:
        return "" if value is None else str(value)


class RagCoverage(BaseModel):
    direct_answer: bool = False
    supports_policy_or_direction: bool = False
    supports_target: bool = False
    supports_accountable_body: bool = False
    supports_role: bool = False
    supports_oversight_cadence: bool = False
    supports_risk_identification: bool = False
    supports_control_or_response: bool = False
    supports_monitoring_follow_up: bool = False
    supports_metric_result: bool = False
    supports_reporting_period: bool = False


class EvidenceItem(BaseModel):
    score: float | int | None = None
    vector_score: float | None = Field(default=None, ge=0.0, le=1.0)
    reranker_score: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_evidence_ko: str = ""
    source_name: str = ""
    source_path: str = ""
    semantic_label: str = ""
    semantic_reason: str = ""
    semantic_score: float | None = Field(default=None, ge=0.0, le=1.0)
    document_id: str = ""
    chunk_id: str = ""
    canonical_source_id: str = ""
    source_tier: str = ""
    source_type: str = ""
    document_status: str = ""
    document_version: str | None = None
    effective_date: date | None = None
    topic: str = ""
    subtopic: str = ""
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)
    facts: list[EvidenceFact] = Field(default_factory=list)
    classification_reason: str = ""

    @field_validator(
        "raw_evidence_ko",
        "source_name",
        "source_path",
        "semantic_label",
        "semantic_reason",
        "document_id",
        "chunk_id",
        "canonical_source_id",
        "source_tier",
        "source_type",
        "document_status",
        "topic",
        "subtopic",
        "classification_reason",
        mode="before",
    )
    @classmethod
    def _optional_text(cls, value: Any) -> str:
        return "" if value is None else str(value)


class RagQuestionResult(BaseModel):
    question_id: str
    question_ko: str = ""
    pillar: Literal["strategy", "governance", "risk_management", "metrics"] | None = None
    normalized_answer_ko: str = ""
    answer_status: str = ""
    retrieval_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage_status: Literal["complete", "partial", "insufficient", "no_evidence"] | None = None
    answerable: bool | None = None
    covered_facets: list[str] = Field(default_factory=list)
    missing_facets: list[str] = Field(default_factory=list)
    failure_code: str | None = None
    failure_reason: str = ""
    retrieval_notes: list[str] = Field(default_factory=list)
    coverage: RagCoverage = Field(default_factory=RagCoverage)
    client_contract_violations: list[str] = Field(default_factory=list)
    items: list[EvidenceItem] = Field(default_factory=list)

    @field_validator("question_ko", "normalized_answer_ko", "answer_status", "failure_reason", mode="before")
    @classmethod
    def _optional_text(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @property
    def is_v3(self) -> bool:
        return self.coverage_status is not None or self.answerable is not None


class RagResponse(BaseModel):
    company_id: str
    request_id: str = ""
    api_version: str = ""
    rag_version: str = ""
    index_version: str = ""
    generated_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)
    client_contract_violations: list[str] = Field(default_factory=list)
    results: list[RagQuestionResult] = Field(default_factory=list)

    @field_validator("request_id", "api_version", "rag_version", "index_version", mode="before")
    @classmethod
    def _optional_metadata_text(cls, value: Any) -> str:
        return "" if value is None else str(value)


class RagRequestTrace(BaseModel):
    request_id: str = ""
    api_version: str = ""
    rag_version: str = ""
    index_version: str = ""
    generated_at: datetime | None = None
    latency_ms: int | None = None
    warnings: list[str] = Field(default_factory=list)
    requested_item_ids: list[str] = Field(default_factory=list)
    top_k: int = 0
    phase: Literal["initial", "retry"] = "initial"
    contract_violations: list[str] = Field(default_factory=list)
    error: str = ""


class QuantitativeMetric(BaseModel):
    metric_id: str
    index: int
    domain: str = ""
    category: str = ""
    subcategory: str = ""
    item: str = ""
    description: str = ""
    unit: str | None = None
    standards: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuantitativeEvidence(BaseModel):
    evidence_id: str
    metric_id: str = ""
    mapped_qualitative_qid: str = ""
    source_id: str = ""
    reporting_period: str = ""
    topic: str = ""
    value: Any = None
    unit: str | None = None
    source: str = ""
    page: int | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metric_id", "mapped_qualitative_qid", "source_id", "reporting_period", "topic", "source", mode="before")
    @classmethod
    def _optional_text(cls, value: Any) -> str:
        return "" if value is None else str(value)


class QuantitativeResult(BaseModel):
    metric_id: str
    index: int
    metric_name: str = ""
    value: Any = None
    unit: str | None = None
    source: str = ""
    status: Literal["filled", "missing"] = "missing"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannedQuestion(BaseModel):
    id: str
    source_id: str = ""
    area_ko: str = ""
    category_ko: str = ""
    pillar: str = ""
    item_ko: str = ""
    description_ko: str = ""
    example_ko: str = ""
    material_topics: list[str] = Field(default_factory=list)
    scale_guidance: dict[str, Any] = Field(default_factory=dict)
    industry_guidance: dict[str, Any] = Field(default_factory=dict)
    answer_policy: Literal["evidence_required"] = "evidence_required"


AgentProfileKey = Literal["carbon", "materiality", "commitment", "general_section"]


class QAResult(BaseModel):
    status: Literal["passed", "empty", "failed"]
    notes: list[str] = Field(default_factory=list)


class SemanticReview(BaseModel):
    alignment: Literal["aligned", "partial", "misaligned", "insufficient"] = "aligned"
    covered_facets: list[str] = Field(default_factory=list)
    missing_facets: list[str] = Field(default_factory=list)
    source_usage: Literal["appropriate", "overstated", "unclear"] = "appropriate"
    notes: list[str] = Field(default_factory=list)


class ClaimSupport(BaseModel):
    claim_id: str
    claim_text: str
    source_ids: list[str] = Field(default_factory=list)
    support_tier: str = "tier_unknown"
    support_status: Literal["grounded", "partial", "unsupported", "data_gap"] = "unsupported"
    facets: list[str] = Field(default_factory=list)
    reporting_period: str = ""
    attribution_required: bool = False


class AnswerRecord(BaseModel):
    qid: str
    source_id: str = ""
    category: str = ""
    question: str = ""
    answer_status: str = ""
    rag_pillar: str = ""
    rag_retrieval_confidence: float | None = None
    rag_coverage_status: str = ""
    rag_answerable: bool | None = None
    rag_covered_facets: list[str] = Field(default_factory=list)
    rag_missing_facets: list[str] = Field(default_factory=list)
    rag_coverage: dict[str, bool] = Field(default_factory=dict)
    rag_failure_code: str = ""
    rag_failure_reason: str = ""
    rag_retrieval_notes: list[str] = Field(default_factory=list)
    rag_contract_violations: list[str] = Field(default_factory=list)
    result_bucket: Literal["answered", "empty", "weak", "failed"] | None = None
    draft_answer: str = ""
    final_answer: str = ""
    last_rejected_answer: str = ""
    qa_failure_stage: str = ""
    sanitizer_actions: list[str] = Field(default_factory=list)
    evidence_summary: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    claim_support: list[ClaimSupport] = Field(default_factory=list)
    qa: QAResult
    agent_profile: AgentProfileKey = "general_section"
    skill_key: AgentProfileKey = "general_section"
    skill_name: str = ""
    skill_version: str = ""
    skill_source_path: str = ""
    skill_selection_reason: str = ""
    skill_checks: list[str] = Field(default_factory=list)
    disclosure_flags: list[str] = Field(default_factory=list)
    hard_failures: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    revision_count: int = 0
    retrieval_attempts: list[dict[str, Any]] = Field(default_factory=list)
    raw_rag_result: dict[str, Any] = Field(default_factory=dict)
    qa_grade: Literal["full", "partial", "cautious", "failed"] | None = None
    coverage_reason: str = ""
    coverage_issues: list[str] = Field(default_factory=list)


class SkillDraft(BaseModel):
    final_answer: str = Field(description="Evidence-grounded ESG disclosure answer.")
    quality_flags: list[str] = Field(
        default_factory=list,
        description="Concise quality or disclosure flags identified while drafting.",
    )
    claim_support: list[ClaimSupport] = Field(default_factory=list)


class RunArtifacts(BaseModel):
    run_id: str
    company: dict[str, Any]
    template_selection: dict[str, Any]
    answers: list[AnswerRecord]
    stats: dict[str, int]
    quantitative_results: list[QuantitativeResult] = Field(default_factory=list)
    quantitative_stats: dict[str, int] = Field(default_factory=dict)
    output_paths: dict[str, str] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    rag_request_traces: list[RagRequestTrace] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
