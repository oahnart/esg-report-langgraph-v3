from __future__ import annotations

import unicodedata
from typing import Any

from .policy import has_accepted_label, has_evidence_text, has_source_path
from .source_policy import classify_source


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
        for planned in state["planned_questions"]:
            rag = state["rag_results"].get(planned.id)
            if rag is None:
                gate[planned.id] = {"accepted": False, "reason": "missing RAG result"}
                continue
            if not rag.items:
                gate[planned.id] = {"accepted": False, "reason": "empty evidence"}
            else:
                answer_status = rag.answer_status.lower()
                evidence_with_text = [item for item in rag.items if has_evidence_text(item)]
                if rag.is_v3:
                    accepted_label_items = [
                        item
                        for item in evidence_with_text
                        if item.semantic_label.strip().lower() in CONDITIONAL_SEMANTIC_LABELS
                    ]
                    accepted_reason = f"accepted_v3_{rag.coverage_status}"
                elif answer_status in conditional_statuses:
                    accepted_label_items = [
                        item
                        for item in evidence_with_text
                        if item.semantic_label.strip().lower() in CONDITIONAL_SEMANTIC_LABELS
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
                policy_exception = ""
                failure_code = str(rag.failure_code or "").strip().upper()
                if rag.is_v3 and failure_code == "DRAFT_ONLY" and self._draft_only_evidence(accepted_label_items):
                    policy_exception = "accepted_draft_evidence"
                elif rag.is_v3 and failure_code == "ASSESSMENT_ONLY" and self._assessment_only_evidence(accepted_label_items):
                    policy_exception = "accepted_assessment_evidence"
                if rag.is_v3 and not policy_exception:
                    v3_rejection = self._v3_rejection_reason(rag)
                    if v3_rejection:
                        gate[planned.id] = {"accepted": False, "reason": v3_rejection}
                        continue
                if not evidence_with_text:
                    gate[planned.id] = {"accepted": False, "reason": "empty evidence"}
                elif not accepted_label_items:
                    gate[planned.id] = {
                        "accepted": False,
                        "reason": "all evidence semantic labels are weak",
                    }
                elif not any(has_source_path(item) for item in accepted_label_items):
                    gate[planned.id] = {"accepted": False, "reason": "missing source_path"}
                elif policy_exception:
                    gate[planned.id] = {"accepted": True, "reason": policy_exception}
                elif self._draft_only_evidence(accepted_label_items):
                    gate[planned.id] = {"accepted": True, "reason": "accepted_draft_evidence"}
                elif self._assessment_only_evidence(accepted_label_items):
                    gate[planned.id] = {"accepted": True, "reason": "accepted_assessment_evidence"}
                else:
                    gate[planned.id] = {"accepted": True, "reason": accepted_reason}
        return {"evidence_gate": gate}

    @staticmethod
    def _v3_rejection_reason(rag: Any) -> str:
        if rag.client_contract_violations:
            return "rag_v3_contract_violation:" + " | ".join(rag.client_contract_violations)
        if rag.answerable is not True:
            return f"rag_v3:{rag.failure_code or rag.coverage_status or 'unanswerable'}"
        if rag.coverage_status not in {"complete", "partial"}:
            return f"rag_v3:{rag.coverage_status or 'invalid_coverage_status'}"
        return ""

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
