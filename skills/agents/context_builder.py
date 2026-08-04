from __future__ import annotations

from typing import Any

from esgagents.agents.answering.question_contracts import build_question_contract
from esgagents.schemas import model_to_dict
from skills.agents.loader import SkillRegistry


def compact(text: str) -> str:
    return " ".join((text or "").split())


def _format_evidence_line(item: Any) -> str:
    metadata = [
        item.source_tier or "tier_unknown",
        item.document_status or "unknown",
        f"source={item.source_name}",
    ]
    locator = {
        key: value
        for key, value in model_to_dict(item.locator).items()
        if value is not None and value != ""
    }
    if item.canonical_source_id:
        metadata.append(f"canonical_source_id={item.canonical_source_id}")
    if item.document_id:
        metadata.append(f"document_id={item.document_id}")
    if item.chunk_id:
        metadata.append(f"chunk_id={item.chunk_id}")
    if locator:
        metadata.append(f"locator={locator}")
    return f"[{'; '.join(metadata)}] {compact(item.raw_evidence_ko)}"


class SkillContextBuilderAgent:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        contexts: dict[str, dict[str, Any]] = {}
        company = state["company"]
        normalized_evidence = state.get("normalized_evidence", {})
        for planned in state["planned_questions"]:
            selection = state["skill_selections"][planned.id]
            spec = self.registry.get(selection["skill_key"])
            gate = state["evidence_gate"].get(planned.id, {})
            rag = state["rag_results"].get(planned.id)
            contract = build_question_contract(planned)
            evidence_items = normalized_evidence.get(planned.id, {}).get("items", [])[:5]
            evidence_lines = [
                _format_evidence_line(item)
                for item in evidence_items
                if compact(item.raw_evidence_ko)
            ]
            contexts[planned.id] = {
                "qid": planned.id,
                "output_language": company.output_language,
                "system_prompt": spec.system_prompt(),
                "user_prompt": "\n".join(
                    [
                        f"Company: {company.company_name} ({company.company_id})",
                        f"Reporting year: {company.year}",
                        f"Output language: {company.output_language}",
                        f"Question ID: {planned.id}",
                        f"Question: {planned.item_ko or (rag.question_ko if rag else '')}",
                        f"Description: {planned.description_ko}",
                        f"Question contract pillar: {contract.pillar}",
                        f"Required facets: {', '.join(contract.required_facets) or 'none'}",
                        f"Expected facets: {', '.join(contract.expected_facets) or 'none'}",
                        f"Evidence gate: {gate.get('reason', '')}",
                        f"RAG coverage status: {rag.coverage_status if rag else ''}",
                        f"RAG answerable: {rag.answerable if rag else ''}",
                        f"RAG covered facets: {', '.join(rag.covered_facets) if rag else 'none'}",
                        f"RAG missing facets: {', '.join(rag.missing_facets) if rag else 'none'}",
                        f"RAG retrieval notes: {' | '.join(rag.retrieval_notes) if rag else 'none'}",
                        "Evidence:",
                        *(f"- {line}" for line in evidence_lines),
                        "Source-use policy: Draft/proposal/consultant evidence may only support explicitly attributed proposed, draft, or planned statements. External assessments support the assessment result and assessed content, not an unstated detailed policy.",
                        "Coverage policy: Address every required facet using only the evidence. Address expected facets when evidence supports them. For Metrics, include both reporting period and metric value/unit when available. If a facet is unsupported, keep a concise cautious answer for the supported evidence and explicitly state that the missing detail was not disclosed; do not guess or invent values.",
                        "RAG constraint: Treat non-Metrics RAG missing facets as unavailable. For Metrics, use a value, explicit zero, or reporting period only when it is directly present in accepted evidence; never infer it from general knowledge or retrieval notes.",
                        "Return only an evidence-grounded final_answer and concise quality_flags.",
                    ]
                ),
                "evidence_lines": evidence_lines,
                "accepted": bool(gate.get("accepted")) and bool(evidence_lines),
                "skill": selection,
            }
        return {"skill_contexts": contexts}
