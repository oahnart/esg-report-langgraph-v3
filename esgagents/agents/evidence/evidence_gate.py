from __future__ import annotations

import unicodedata
from typing import Any

from .policy import has_accepted_label, has_evidence_text, has_stable_provenance
from .source_policy import classify_source
from .metric_routing import (
    has_metric_contract,
    is_metric_row,
    metric_contract_warnings,
    routed_gate_items,
)


CONDITIONAL_SEMANTIC_LABELS = {"useful", "partial", "metric_row", "keep", "keep_supportive"}
DRAFT_STATUSES = {"draft", "proposed", "proposal", "under_review", "under review"}
FUTURE_PLAN_TERMS = (
    "plan",
    "planned",
    "future",
    "roadmap",
    "under review",
    "proposal",
    "draft",
    "target",
    "goal",
)


class EvidenceGateAgent:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        accepted_statuses = {str(s).lower() for s in self.config["accepted_answer_statuses"]}
        conditional_statuses = {
            str(s).lower() for s in self.config.get("conditional_answer_statuses", set())
        }
        rejected_labels = {str(s).lower() for s in self.config["rejected_semantic_labels"]}
        gate: dict[str, dict[str, Any]] = {}
        upstream_hints: dict[str, dict[str, Any]] = {}
        upstream_coverage_mismatches: dict[str, bool] = {}
        for planned in state["planned_questions"]:
            rag = state["rag_results"].get(planned.id)
            if rag is None:
                gate[planned.id] = {"accepted": False, "reason": "missing RAG result"}
                upstream_hints[planned.id] = {}
                upstream_coverage_mismatches[planned.id] = False
                continue
            contract_warnings = metric_contract_warnings(rag)
            if contract_warnings:
                rag.client_contract_warnings = list(
                    dict.fromkeys([*rag.client_contract_warnings, *contract_warnings])
                )
            answer_status = rag.answer_status.strip().casefold()
            eligible_by_status = answer_status in accepted_statuses or answer_status in conditional_statuses
            hints = {
                "answerable": rag.answerable,
                "coverage_status": rag.coverage_status,
                "missing_facets": list(rag.missing_facets),
            }
            upstream_hints[planned.id] = hints
            coverage_implies_eligible = (
                True if rag.coverage_status in {"complete", "partial"}
                else False if rag.coverage_status in {"insufficient", "no_evidence"}
                else None
            )
            mismatch = bool(
                (rag.answerable is not None and rag.answerable != eligible_by_status)
                or (
                    coverage_implies_eligible is not None
                    and coverage_implies_eligible != eligible_by_status
                )
            )
            upstream_coverage_mismatches[planned.id] = mismatch
            routed_items = routed_gate_items(rag)
            if rag.metric_status == "found_table" and not routed_items:
                gate[planned.id] = {
                    "accepted": False,
                    "reason": "metric_found_table_without_usable_evidence",
                }
            elif not routed_items:
                gate[planned.id] = {"accepted": False, "reason": "empty evidence"}
            else:
                evidence_with_text = [item for item in routed_items if has_evidence_text(item)]
                if rag.is_v3 or has_metric_contract(rag):
                    if rag.client_contract_violations:
                        gate[planned.id] = {
                            "accepted": False,
                            "reason": "rag_v3_contract_violation:"
                            + " | ".join(rag.client_contract_violations),
                        }
                        continue
                    if not eligible_by_status:
                        gate[planned.id] = {
                            "accepted": False,
                            "reason": f"answer_status={rag.answer_status or 'empty'}",
                        }
                        continue
                    accepted_label_items = [
                        item
                        for item in evidence_with_text
                        if item.semantic_label.strip().lower() in CONDITIONAL_SEMANTIC_LABELS
                        or is_metric_row(item)
                    ]
                    accepted_reason = (
                        "accepted_v3_partial"
                        if answer_status in conditional_statuses
                        else f"accepted_v3_{answer_status}"
                    )
                elif answer_status in conditional_statuses:
                    accepted_label_items = [
                        item
                        for item in evidence_with_text
                        if item.semantic_label.strip().lower() in CONDITIONAL_SEMANTIC_LABELS
                        or is_metric_row(item)
                    ]
                    accepted_reason = "accepted_thin_evidence"
                elif answer_status in accepted_statuses:
                    accepted_label_items = [
                        item for item in evidence_with_text if has_accepted_label(item, rejected_labels)
                    ]
                    accepted_reason = "accepted"
                else:
                    gate[planned.id] = {
                        "accepted": False,
                        "reason": f"answer_status={rag.answer_status or 'empty'}",
                    }
                    continue
                if (
                    rag.metric_status == "not_found"
                    and accepted_label_items
                    and eligible_by_status
                ):
                    accepted_reason = "accepted_metric_not_found"
                policy_exception = ""
                failure_code = str(rag.failure_code or "").strip().upper()
                if rag.is_v3 and failure_code == "DRAFT_ONLY" and self._draft_only_evidence(accepted_label_items):
                    policy_exception = "accepted_draft_evidence"
                elif rag.is_v3 and failure_code == "ASSESSMENT_ONLY" and self._assessment_only_evidence(accepted_label_items):
                    policy_exception = "accepted_assessment_evidence"
                if not evidence_with_text:
                    gate[planned.id] = {"accepted": False, "reason": "empty evidence"}
                elif not accepted_label_items:
                    gate[planned.id] = {
                        "accepted": False,
                        "reason": "all evidence semantic labels are weak",
                    }
                elif not any(has_stable_provenance(item) for item in accepted_label_items):
                    gate[planned.id] = {"accepted": False, "reason": "missing stable provenance"}
                elif policy_exception:
                    gate[planned.id] = {"accepted": True, "reason": policy_exception}
                elif self._draft_only_evidence(accepted_label_items):
                    gate[planned.id] = {"accepted": True, "reason": "accepted_draft_evidence"}
                elif self._assessment_only_evidence(accepted_label_items):
                    gate[planned.id] = {"accepted": True, "reason": "accepted_assessment_evidence"}
                else:
                    gate[planned.id] = {"accepted": True, "reason": accepted_reason}
        return {
            "evidence_gate": gate,
            "upstream_hints": upstream_hints,
            "upstream_coverage_mismatches": upstream_coverage_mismatches,
        }

    @staticmethod
    def _draft_only_evidence(items: list[Any]) -> bool:
        if not items:
            return False
        classifications = [classify_source(item) for item in items]
        return all(
            classification.source_tier == "tier_4_draft"
            or classification.document_status.strip().casefold() in DRAFT_STATUSES
            for classification in classifications
        )

    @staticmethod
    def _assessment_only_evidence(items: list[Any]) -> bool:
        if not items:
            return False
        return all(classify_source(item).source_tier == "tier_3_assessment" for item in items)

    @staticmethod
    def _allows_draft_evidence(planned: Any) -> bool:
        text = unicodedata.normalize(
            "NFKC",
            " ".join(
                str(getattr(planned, field, "") or "")
                for field in ("item_ko", "description_ko", "example_ko")
            ),
        ).casefold()
        return any(term in text for term in FUTURE_PLAN_TERMS)
