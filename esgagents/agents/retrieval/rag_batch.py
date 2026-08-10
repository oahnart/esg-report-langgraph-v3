from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from esgagents.rag_client import TeamRagClient
from esgagents.schemas import (
    EvidenceItem,
    MetricEvidenceItem,
    NormalizedCompany,
    RagQuestionResult,
    RagRequestTrace,
    RagResponse,
    model_to_dict,
)

from esgagents.agents.evidence.policy import has_evidence_text, has_stable_provenance
from esgagents.agents.evidence.source_policy import evidence_fingerprint


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


class RagBatchAgent:
    def __init__(self, config: dict[str, Any], rag_client: TeamRagClient):
        self.config = config
        self.rag_client = rag_client

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        company: NormalizedCompany = state["company"]
        qids = [q.id for q in state["planned_questions"]]
        batch_size = int(self.config["team_rag_batch_size"])
        concurrency = max(1, int(self.config["team_rag_concurrency"]))
        batches = chunked(qids, batch_size)
        results: dict[str, RagQuestionResult] = {}
        attempts: dict[str, list[dict[str, Any]]] = {qid: [] for qid in qids}
        raw_responses = []
        request_traces: list[RagRequestTrace] = []

        def fetch(batch: list[str]):
            return self.rag_client.fetch_evidence(company.company_id, batch, company.top_k, company.year)

        with ThreadPoolExecutor(max_workers=min(concurrency, max(1, len(batches)))) as pool:
            futures = {pool.submit(fetch, batch): batch for batch in batches}
            for future in as_completed(futures):
                response = future.result()
                raw_responses.append(model_to_dict(response))
                request_traces.append(
                    self._request_trace(
                        response,
                        requested_item_ids=futures[future],
                        top_k=company.top_k,
                        phase="initial",
                    )
                )
                for item in response.results:
                    results[item.question_id] = item
                    attempts.setdefault(item.question_id, []).append(
                        self._attempt_metadata(
                            top_k=company.top_k,
                            reason="initial",
                            result=item,
                            response=response,
                        )
                    )

        retry_top_k = int(self.config.get("team_rag_retry_top_k", 0) or 0)
        if retry_top_k > company.top_k:
            retry_qids = [
                qid
                for qid in qids
                if self._should_retry(results.get(qid))
            ]
            if retry_qids:
                for qid in retry_qids:
                    current = results.get(qid)
                    attempts.setdefault(qid, []).append(
                        {
                            "top_k": retry_top_k,
                            "retry_reason": self._retry_reason(current),
                            "eligible_item_count_before_retry": len(
                                self._eligible_retry_items(current.items if current else [])
                            ),
                        }
                    )
                retry_batches = chunked(retry_qids, batch_size)
                with ThreadPoolExecutor(max_workers=min(concurrency, max(1, len(retry_batches)))) as pool:
                    futures = {
                        pool.submit(
                            self.rag_client.fetch_evidence,
                            company.company_id,
                            batch,
                            retry_top_k,
                            company.year,
                        ): batch
                        for batch in retry_batches
                    }
                    for future in as_completed(futures):
                        try:
                            response = future.result()
                        except Exception as exc:
                            request_traces.append(
                                RagRequestTrace(
                                    requested_item_ids=list(futures[future]),
                                    top_k=retry_top_k,
                                    phase="retry",
                                    error=str(exc),
                                )
                            )
                            for qid in futures[future]:
                                attempts.setdefault(qid, []).append(
                                    {
                                        "top_k": retry_top_k,
                                        "retry_reason": "retry failed",
                                        "error": str(exc),
                                    }
                                )
                            continue
                        raw_responses.append(model_to_dict(response))
                        request_traces.append(
                            self._request_trace(
                                response,
                                requested_item_ids=futures[future],
                                top_k=retry_top_k,
                                phase="retry",
                            )
                        )
                        for item in response.results:
                            attempts.setdefault(item.question_id, []).append(
                                self._attempt_metadata(
                                    top_k=retry_top_k,
                                    reason="retry_result",
                                    result=item,
                                    response=response,
                                )
                            )
                            if item.is_v3 or self._eligible_retry_items(item.items):
                                results[item.question_id] = self._merge_retry_result(
                                    results.get(item.question_id),
                                    item,
                                )

        for qid in qids:
            if qid not in results:
                attempts.setdefault(qid, []).append(
                    {
                        "top_k": company.top_k,
                        "retry_reason": "missing RAG result",
                        "eligible_item_count": 0,
                    }
                )
        return {
            "rag_results": results,
            "raw_rag_responses": raw_responses,
            "retrieval_attempts": attempts,
            "rag_request_traces": request_traces,
        }

    def _should_retry(self, result: RagQuestionResult | None) -> bool:
        if result is None:
            return True
        if result.metric_status == "not_found":
            return bool(
                result.metric_absence
                and result.metric_absence.reason
                in {"no_candidate", "below_threshold", "blocked_by_gate"}
            )
        if result.metric_status == "found_table":
            return not any(
                item.block_role == "primary"
                and bool(item.entity_class.strip() or item.entity.strip())
                for item in result.metric_evidence
            ) or bool(result.client_contract_violations)
        if not result.items:
            return True
        if result.is_v3:
            return (
                result.answer_status.strip().casefold() in {"insufficient", "no_evidence"}
                or bool(result.client_contract_violations)
                or bool(result.missing_facets)
                or str(result.coverage_status or "").casefold() == "partial"
            )
        return not self._eligible_retry_items(result.items)

    def _retry_reason(self, result: RagQuestionResult | None) -> str:
        if result is None:
            return "missing RAG result"
        if result.metric_status == "not_found":
            absence_reason = result.metric_absence.reason if result.metric_absence else "unknown"
            return f"metric_not_found:{absence_reason}"
        if result.metric_status == "found_table" and not result.metric_evidence:
            return "found_table_without_metric_evidence"
        if result.is_v3:
            if result.client_contract_violations:
                return "v3 contract violation"
            if result.answer_status:
                return result.answer_status
        if not result.items:
            return "empty evidence"
        if not self._eligible_retry_items(result.items):
            if not any(has_stable_provenance(item) for item in result.items):
                return "missing stable provenance"
            return "all evidence semantic labels are weak"
        return "eligible evidence available"

    def _attempt_metadata(
        self,
        *,
        top_k: int,
        reason: str,
        result: RagQuestionResult,
        response: RagResponse,
    ) -> dict[str, Any]:
        eligible_count = len(self._eligible_retry_items(result.items))
        return {
            "top_k": top_k,
            "retry_top_k": top_k,
            "retry_reason": reason,
            "answer_status": result.answer_status,
            "coverage_status": result.coverage_status,
            "answerable": result.answerable,
            "retrieval_confidence": result.retrieval_confidence,
            "covered_facets": list(result.covered_facets),
            "missing_facets": list(result.missing_facets),
            "failure_code": result.failure_code,
            "request_id": response.request_id,
            "item_count": len(result.items),
            "eligible_item_count": eligible_count,
            "metric_status": result.metric_status,
            "metric_evidence_row_count": len(result.metric_evidence),
            "metric_primary_block_count": len(
                {
                    item.table_block
                    for item in result.metric_evidence
                    if item.block_role == "primary"
                }
            ),
        }

    def _request_trace(
        self,
        response: RagResponse,
        *,
        requested_item_ids: list[str],
        top_k: int,
        phase: str,
    ) -> RagRequestTrace:
        violations = list(response.client_contract_violations)
        for result in response.results:
            violations.extend(
                f"{result.question_id}: {violation}"
                for violation in result.client_contract_violations
            )
        return RagRequestTrace(
            request_id=response.request_id,
            api_version=response.api_version,
            rag_version=response.rag_version,
            index_version=response.index_version,
            generated_at=response.generated_at,
            latency_ms=response.latency_ms,
            warnings=list(response.warnings),
            requested_item_ids=list(requested_item_ids),
            top_k=top_k,
            phase=phase,
            contract_violations=list(dict.fromkeys(violations)),
        )

    def _eligible_retry_items(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        rejected_labels = {
            str(label).strip().lower()
            for label in self.config.get("rejected_semantic_labels", set())
        }
        return [
            item
            for item in items
            if has_evidence_text(item)
            and has_stable_provenance(item)
            and item.semantic_label.strip().lower() not in rejected_labels
        ]

    def _merge_retry_result(
        self,
        original: RagQuestionResult | None,
        retry: RagQuestionResult,
    ) -> RagQuestionResult:
        if original is None:
            return retry
        if original.is_v3 or retry.is_v3:
            preferred, secondary = self._preferred_v3_result(original, retry)
            if preferred is original:
                return original
        else:
            preferred, secondary = retry, original
        seen: set[tuple[str, str]] = set()
        merged_items = []
        for item in [*preferred.items, *secondary.items]:
            key = self._evidence_dedup_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged_items.append(item)
        merged_metric_evidence = self._merge_metric_evidence(
            preferred.metric_evidence,
            secondary.metric_evidence,
        )
        narrative_seen: set[tuple[str, str]] = set()
        merged_narrative = []
        for item in [*preferred.narrative_evidence, *secondary.narrative_evidence]:
            key = self._evidence_dedup_key(item)
            if key in narrative_seen:
                continue
            narrative_seen.add(key)
            merged_narrative.append(item)
        return preferred.model_copy(
            update={
                "items": merged_items,
                "metric_evidence": merged_metric_evidence,
                "narrative_evidence": merged_narrative,
            }
        )

    def _preferred_v3_result(
        self,
        original: RagQuestionResult,
        retry: RagQuestionResult,
    ) -> tuple[RagQuestionResult, RagQuestionResult]:
        status_rank = {
            "high_confidence": 5,
            "medium_confidence": 4,
            "thin_but_usable": 3,
            "insufficient": 2,
            "no_evidence": 1,
        }

        def quality(result: RagQuestionResult) -> tuple[int, int, int, int, int, int, float]:
            eligible = self._eligible_retry_items(result.items)
            preferred_source_count = sum(
                str(getattr(item, "source_tier", "") or "")
                in {"tier_1_governing", "tier_2_operational"}
                for item in eligible
            )
            structured_fact_count = sum(len(getattr(item, "facts", []) or []) for item in eligible)
            primary_blocks = len(
                {
                    item.table_block
                    for item in result.metric_evidence
                    if item.block_role == "primary"
                }
            )
            metric_rank = (
                2
                if result.metric_status == "found_table" and primary_blocks
                else 1
                if result.metric_status == "found_table"
                else 0
            ) if result.metric_expected else 0
            return (
                metric_rank,
                status_rank.get(result.answer_status.strip().casefold(), 0),
                primary_blocks,
                preferred_source_count,
                structured_fact_count,
                len(eligible),
                float(result.retrieval_confidence or 0.0),
            )

        return (retry, original) if quality(retry) > quality(original) else (original, retry)

    @staticmethod
    def _merge_metric_evidence(
        preferred: list[MetricEvidenceItem],
        secondary: list[MetricEvidenceItem],
    ) -> list[MetricEvidenceItem]:
        seen: set[tuple[str, str, str, str]] = set()
        merged: list[MetricEvidenceItem] = []
        for item in [*preferred, *secondary]:
            key = (
                item.table_block.strip(),
                item.block_role or "",
                item.entity_class.strip() or item.entity.strip(),
                evidence_fingerprint(item.raw_evidence_ko),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    @staticmethod
    def _evidence_dedup_key(item: EvidenceItem) -> tuple[str, str]:
        if item.canonical_source_id.strip() and item.chunk_id.strip():
            return (item.canonical_source_id.strip(), item.chunk_id.strip())
        return (item.source_path.strip(), evidence_fingerprint(item.raw_evidence_ko))
