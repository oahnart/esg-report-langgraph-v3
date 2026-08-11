from __future__ import annotations

from typing import Any

from esgagents.schemas import (
    AnswerRecord,
    NormalizedCompany,
    QuantitativeResult,
    RunArtifacts,
    model_to_dict,
)
from esgagents.quality import classify_answer_quality
from esgagents.publication import apply_customer_answer_contract, evaluate_publication
from esgagents.provenance import verify_runtime_provenance
from esgagents.agents.answering.question_contracts import build_question_contract


class ReportManagerAgent:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        company: NormalizedCompany = state["company"]
        records = []
        stats = {"answered": 0, "empty": 0, "weak": 0, "failed": 0}
        rag_results = state["rag_results"]
        accepted_statuses = {str(s).lower() for s in self.config["accepted_answer_statuses"]}
        conditional_statuses = {
            str(s).lower()
            for s in self.config.get("conditional_answer_statuses", set())
        }
        for planned in state["planned_questions"]:
            rag = rag_results.get(planned.id)
            qa = state["qa_results"][planned.id]
            final_answer = state["final_answers"].get(planned.id, "")
            gate = state["evidence_gate"].get(planned.id, {})
            gate_reason = str(gate.get("reason", "") or "")
            local_evidence_accepted = bool(gate.get("accepted")) and gate_reason in {
                "accepted_v3_local_partial",
                "accepted_draft_evidence",
                "accepted_assessment_evidence",
            }
            status_eligible = bool(
                rag
                and rag.answer_status.strip().casefold()
                in accepted_statuses | conditional_statuses
            )
            if rag and rag.is_v3 and not status_eligible and not local_evidence_accepted:
                final_answer = ""
            if final_answer and not bool(gate.get("accepted")):
                final_answer = ""
            if final_answer:
                result_bucket = "answered"
            elif qa.status == "failed":
                result_bucket = "failed"
            elif "weak" in gate.get("reason", "") or (
                rag
                and rag.answer_status.lower()
                not in accepted_statuses | conditional_statuses
                and not local_evidence_accepted
            ):
                result_bucket = "weak"
            else:
                result_bucket = "empty"
            normalized = state["normalized_evidence"].get(planned.id, {})
            metric_audit = dict(normalized.get("metric_audit", {}))
            local_dimensions = list(build_question_contract(planned).metric_dimensions)
            if local_dimensions:
                metric_audit["local_dimensions"] = local_dimensions
            quality_flags = list(
                state.get("quality_flags", {}).get(planned.id, [])
            )
            if metric_audit.get("metric_summary_mismatches"):
                quality_flags = sorted(
                    set(
                        [
                            *quality_flags,
                            "metric_summary_mismatch",
                            "human_review_required",
                        ]
                    )
                )
            if local_evidence_accepted and not status_eligible:
                quality_flags = sorted(
                    set([*quality_flags, "local_partial_evidence", "partial_answer"])
                )
            consumer_decision = self._consumer_decision(
                final_answer=final_answer,
                answer_status=rag.answer_status if rag else "",
                gate=gate,
                quality_flags=quality_flags,
            )
            revision_count = int(state.get("revision_counts", {}).get(planned.id, 0))
            selection = state.get("skill_selections", {}).get(planned.id, {})
            record = AnswerRecord(
                qid=planned.id,
                source_id=planned.source_id,
                category=planned.category_ko,
                question=planned.item_ko,
                answer_status=rag.answer_status if rag else "missing",
                rag_pillar=str(getattr(planned, "pillar", "") or ""),
                rag_retrieval_confidence=rag.retrieval_confidence if rag else None,
                rag_coverage_status=rag.coverage_status if rag and rag.coverage_status else "",
                rag_answerable=rag.answerable if rag else None,
                rag_covered_facets=list(rag.covered_facets) if rag else [],
                rag_missing_facets=list(rag.missing_facets) if rag else [],
                rag_coverage=model_to_dict(rag.coverage) if rag and rag.is_v3 else {},
                rag_failure_code=rag.failure_code if rag and rag.failure_code else "",
                rag_failure_reason=rag.failure_reason if rag else "",
                rag_retrieval_notes=list(rag.retrieval_notes) if rag else [],
                rag_contract_violations=list(rag.client_contract_violations) if rag else [],
                rag_contract_warnings=list(rag.client_contract_warnings) if rag else [],
                rag_metric_expected=rag.metric_expected if rag else None,
                rag_metric_status=rag.metric_status if rag and rag.metric_status else "",
                rag_metric_confidence=rag.metric_confidence if rag and rag.metric_confidence else "",
                rag_metric_summary=model_to_dict(rag.metric_summary) if rag and rag.metric_summary else {},
                rag_metric_absence=model_to_dict(rag.metric_absence) if rag and rag.metric_absence else {},
                rag_metric_evidence=[
                    model_to_dict(item) for item in normalized.get("metric_evidence", [])
                ],
                rag_narrative_evidence=[model_to_dict(item) for item in rag.narrative_evidence] if rag else [],
                consumer_decision=consumer_decision,
                upstream_hints=dict(state.get("upstream_hints", {}).get(planned.id, {})),
                upstream_coverage_mismatch=bool(
                    state.get("upstream_coverage_mismatches", {}).get(planned.id, False)
                ),
                local_evidence_accepted=local_evidence_accepted,
                local_acceptance_reason=gate_reason if local_evidence_accepted else "",
                metric_audit=metric_audit,
                result_bucket=result_bucket,
                draft_answer=state.get("draft_answers", {}).get(planned.id, ""),
                final_answer=final_answer,
                last_rejected_answer=state.get("last_rejected_answers", {}).get(planned.id, ""),
                qa_failure_stage=state.get("qa_failure_stages", {}).get(planned.id, ""),
                sanitizer_actions=state.get("sanitizer_actions", {}).get(planned.id, []),
                evidence_summary=normalized.get("evidence_summary", ""),
                sources=normalized.get("sources", []),
                claim_support=state.get("claim_support", {}).get(planned.id, []),
                qa=qa,
                agent_profile=state.get("agent_profiles", {}).get(planned.id, "general_section"),
                skill_key=selection.get("skill_key", state.get("agent_profiles", {}).get(planned.id, "general_section")),
                skill_name=selection.get("skill_name", ""),
                skill_version=selection.get("skill_version", ""),
                skill_source_path=selection.get("skill_source_path", ""),
                skill_selection_reason=selection.get("skill_selection_reason", ""),
                skill_checks=state.get("skill_checks", {}).get(planned.id, []),
                disclosure_flags=state.get("disclosure_flags", {}).get(planned.id, []),
                hard_failures=state.get("hard_failures", {}).get(planned.id, []),
                quality_flags=quality_flags,
                revision_count=revision_count,
                retrieval_attempts=state.get("retrieval_attempts", {}).get(planned.id, []),
                raw_rag_result=model_to_dict(rag) if rag else {},
            )
            quality = classify_answer_quality(record)
            record.qa_grade = quality.grade
            record.coverage_reason = quality.reason
            record.coverage_issues = list(quality.issues)
            publication = evaluate_publication(
                record,
                accepted_statuses={
                    str(value).lower()
                    for value in self.config["accepted_answer_statuses"]
                },
                conditional_statuses={
                    str(value).lower()
                    for value in self.config.get("conditional_answer_statuses", set())
                },
            )
            record.publication_status = publication.status
            record.publication_reason = publication.reason
            record.publication_issues = list(publication.issues)
            apply_customer_answer_contract(record)
            records.append(record)
        stats = {"answered": 0, "empty": 0, "weak": 0, "failed": 0}
        for record in records:
            bucket = str(record.result_bucket or "empty")
            stats[bucket if bucket in stats else "empty"] += 1
        artifacts = RunArtifacts(
            run_id=company.run_id,
            company=model_to_dict(company),
            template_selection=state["template_selection"],
            answers=records,
            stats=stats,
            quantitative_results=[
                QuantitativeResult.model_validate(item)
                for item in state.get("quantitative_results", [])
            ],
            quantitative_stats=dict(state.get("quantitative_stats", {})),
            provenance=verify_runtime_provenance(),
            rag_request_traces=list(state.get("rag_request_traces", [])),
        )
        return {"artifacts": artifacts}

    @staticmethod
    def _consumer_decision(
        *,
        final_answer: str,
        answer_status: str,
        gate: dict[str, Any],
        quality_flags: list[str],
    ) -> str:
        if final_answer:
            partial_markers = {
                "partial_answer",
                "rag_partial_coverage",
                "thin_evidence",
                "conflicting_metric",
                "metric_not_found",
                "metric_low_confidence",
                "metric_numeric_withheld",
                "metric_summary_mismatch",
            }
            return (
                "answered_partial"
                if partial_markers.intersection(quality_flags)
                else "answered"
            )
        if answer_status.strip().casefold() not in {
            "high_confidence",
            "medium_confidence",
            "thin_but_usable",
        }:
            return "blocked_api_status"
        reason = str(gate.get("reason", "") or "")
        if "provenance" in reason or "source_path" in reason:
            return "blocked_provenance"
        if not gate.get("accepted"):
            return "blocked_evidence"
        return "blocked_qa"
