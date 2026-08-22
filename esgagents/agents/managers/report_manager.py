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
            normalized = state["normalized_evidence"].get(planned.id, {})
            metric_audit = dict(normalized.get("metric_audit", {}))
            metric_table_only = (
                not final_answer
                and str(metric_audit.get("metric_status") or "").casefold()
                == "found_table"
                and bool(metric_audit.get("accepted_facts"))
                and bool(gate.get("accepted"))
            )
            if final_answer or metric_table_only:
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
            facet_verification = dict(normalized.get("facet_verification", {}) or {})
            off_topic_dropped = list(normalized.get("off_topic_evidence_dropped", []) or [])
            if off_topic_dropped:
                quality_flags = sorted(
                    set([*quality_flags, "off_topic_evidence_dropped", "human_review_required"])
                )
            if facet_verification.get("overclaimed_facets"):
                quality_flags = sorted(
                    set([*quality_flags, "upstream_facet_overclaim", "human_review_required"])
                )
            consumer_decision = self._consumer_decision(
                final_answer=final_answer,
                has_metric_output=metric_table_only,
                answer_status=rag.answer_status if rag else "",
                gate=gate,
                quality_flags=quality_flags,
            )
            revision_count = int(state.get("revision_counts", {}).get(planned.id, 0))
            selection = state.get("skill_selections", {}).get(planned.id, {})
            curation_result = state.get("evidence_curation_results", {}).get(planned.id)
            record = AnswerRecord(
                qid=planned.id,
                source_id=planned.source_id,
                area=planned.area_ko,
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
                qualitative_evidence_route=str(
                    normalized.get("qualitative_evidence_route", "") or ""
                ),
                qualitative_answerability=str(
                    state.get("qualitative_answerability", {}).get(planned.id, "")
                    or ""
                ),
                evidence_curation=(
                    model_to_dict(curation_result)
                    if curation_result is not None
                    else {}
                ),
                pipeline_audit={
                    "structural_gate": dict(
                        state.get("structural_evidence_audit", {}).get(planned.id, {})
                    ),
                    **dict(
                        state.get("evidence_curation_qid_stats", {}).get(planned.id, {})
                    ),
                },
                grounded_sentences=state.get("grounded_final_sentences", {}).get(
                    planned.id,
                    [],
                ),
                grounding_issues=state.get("grounding_issues", {}).get(
                    planned.id,
                    [],
                ),
                consumer_decision=consumer_decision,
                upstream_hints=self._upstream_hints(
                    state.get("upstream_hints", {}).get(planned.id, {}),
                    facet_verification=facet_verification,
                    off_topic_dropped=off_topic_dropped,
                    duplicate_dropped=list(normalized.get("duplicate_evidence_dropped", []) or []),
                ),
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
                original_evidence=self._writer_original_evidence(
                    normalized,
                    state.get("curated_qualitative_evidence", {}).get(planned.id),
                ),
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
            record.pipeline_audit["publication_status"] = publication.status
            records.append(record)
        stats = {"answered": 0, "empty": 0, "weak": 0, "failed": 0}
        for record in records:
            bucket = str(record.result_bucket or "empty")
            stats[bucket if bucket in stats else "empty"] += 1
        qid_stats = {
            record.qid: dict(record.pipeline_audit)
            for record in records
        }
        quality_metrics = self._quality_metrics(state, records, qid_stats)
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
            curation_stats=dict(state.get("evidence_curation_stats", {})),
            curation_qid_stats=qid_stats,
            quality_metrics=quality_metrics,
            provenance=verify_runtime_provenance(),
            rag_request_traces=list(state.get("rag_request_traces", [])),
        )
        return {"artifacts": artifacts}

    @staticmethod
    def _quality_metrics(
        state: dict[str, Any],
        records: list[AnswerRecord],
        qid_stats: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        total = len(records)
        denominator = max(1, total)
        rag_chunks = sum(int(item.get("rag_chunk_count", 0)) for item in qid_stats.values())
        curated_chunks = sum(int(item.get("curated_keep_count", 0)) for item in qid_stats.values())
        curator_candidates = sum(
            int(item.get("curator_candidate_count", 0)) for item in qid_stats.values()
        )
        dropped = sum(int(item.get("curated_drop_count", 0)) for item in qid_stats.values())
        reason_counts: dict[str, int] = {}
        for item in qid_stats.values():
            for reason, count in dict(item.get("drop_reason_counts", {})).items():
                key = str(reason).upper()
                reason_counts[key] = reason_counts.get(key, 0) + int(count)

        semantic_reviews = state.get("semantic_reviews", {})
        issue_types_by_qid = {
            qid: {
                str(getattr(issue, "issue_type", "") or "").upper()
                for issue in getattr(review, "issues", [])
            }
            for qid, review in semantic_reviews.items()
        }
        grounding = state.get("grounding_issues", {})
        revised = [item for item in qid_stats.values() if item.get("revision_called")]
        revised_passed = [
            item for item in revised if item.get("semantic_pass_after_revision") is True
        ]
        publication_counts = {
            status: sum(record.publication_status == status for record in records)
            for status in ("published", "review_required", "blocked")
        }

        def qid_rate(predicate: Any) -> float:
            return round(sum(bool(predicate(record.qid)) for record in records) / denominator, 6)

        return {
            "avg_rag_chunks_per_qid": round(rag_chunks / denominator, 6),
            "avg_curated_chunks_per_qid": round(curated_chunks / denominator, 6),
            "evidence_drop_rate": round(dropped / max(1, curator_candidates), 6),
            "irrelevant_drop_rate": round(
                sum(count for reason, count in reason_counts.items() if "IRRELEVANT" in reason)
                / max(1, curator_candidates),
                6,
            ),
            "noise_drop_rate": round(
                sum(count for reason, count in reason_counts.items() if "NOISE" in reason)
                / max(1, curator_candidates),
                6,
            ),
            "partial_answerability_rate": qid_rate(
                lambda qid: qid_stats.get(qid, {}).get("answerability") == "PARTIAL"
            ),
            "insufficient_answerability_rate": qid_rate(
                lambda qid: qid_stats.get(qid, {}).get("answerability") == "INSUFFICIENT"
            ),
            "unsupported_claim_rate": qid_rate(
                lambda qid: any(
                    issue.startswith("unsupported_sentence")
                    for issue in grounding.get(qid, [])
                )
                or "UNSUPPORTED_CLAIM" in issue_types_by_qid.get(qid, set())
            ),
            "irrelevant_content_rate": qid_rate(
                lambda qid: "IRRELEVANT_CONTENT" in issue_types_by_qid.get(qid, set())
            ),
            "overstatement_rate": qid_rate(
                lambda qid: "OVERSTATEMENT" in issue_types_by_qid.get(qid, set())
            ),
            "numeric_grounding_fail_rate": qid_rate(
                lambda qid: any(
                    issue.startswith("prose_numeric_grounding_fail")
                    for issue in grounding.get(qid, [])
                )
            ),
            "revision_rate": round(len(revised) / denominator, 6),
            "revision_success_rate": round(
                len(revised_passed) / max(1, len(revised)),
                6,
            ),
            "publication_status_counts": publication_counts,
            "drop_reason_counts": reason_counts,
        }

    @staticmethod
    def _upstream_hints(
        hints: dict[str, Any],
        *,
        facet_verification: dict[str, Any],
        off_topic_dropped: list[dict[str, Any]],
        duplicate_dropped: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # The producer's own hints stay untouched; what the client verified
        # locally sits beside them so the audit sheet shows both sides.
        merged = dict(hints)
        if facet_verification:
            merged["facet_verification"] = facet_verification
        if off_topic_dropped:
            merged["off_topic_evidence_dropped"] = off_topic_dropped
        if duplicate_dropped:
            merged["duplicate_evidence_dropped"] = duplicate_dropped
        return merged

    @staticmethod
    def _writer_original_evidence(
        normalized: dict[str, Any],
        curated: list[Any] | None = None,
    ) -> str:
        metric_audit = normalized.get("metric_audit", {}) or {}
        metric_status = str(metric_audit.get("metric_status") or "").casefold()
        narrative_only = metric_status in {"found_table", "not_found"}
        metric_items = [] if narrative_only else list(normalized.get("metric_items", []))
        if metric_audit.get("numeric_withheld"):
            metric_items = []
        qualitative_items = (
            [item.raw_item for item in curated]
            if curated is not None
            else list(normalized.get("narrative_items", []))
        )
        evidence_items = [*metric_items[:5], *qualitative_items[:5]]
        raw_parts = [
            ReportManagerAgent._raw_evidence_text(item)
            for item in evidence_items
            if ReportManagerAgent._raw_evidence_text(item).strip()
        ]
        return "\n\n".join(raw_parts)

    @staticmethod
    def _raw_evidence_text(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("raw_evidence_ko") or "")
        return str(getattr(item, "raw_evidence_ko", "") or "")

    @staticmethod
    def _consumer_decision(
        *,
        final_answer: str,
        has_metric_output: bool = False,
        answer_status: str,
        gate: dict[str, Any],
        quality_flags: list[str],
    ) -> str:
        if final_answer or has_metric_output:
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
