from __future__ import annotations

from typing import Any

from esgagents.agents.answering.question_contracts import build_question_contract
from esgagents.agents.evidence.metric_facts import metric_facts_prompt_lines
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
    facts = [model_to_dict(fact) for fact in getattr(item, "facts", [])]
    fact_text = f" structured_facts={facts}" if facts else ""
    return f"[{'; '.join(metadata)}]{fact_text} {compact(item.raw_evidence_ko)}"


def _format_prepared_evidence_line(item: Any) -> str:
    raw_item = item.raw_item
    metadata = [
        raw_item.source_tier or "tier_unknown",
        raw_item.document_status or "unknown",
        f"evidence_id={item.evidence_id}",
        f"origin={item.origin}",
        f"source={raw_item.source_name}",
    ]
    if raw_item.canonical_source_id:
        metadata.append(f"canonical_source_id={raw_item.canonical_source_id}")
    if raw_item.chunk_id:
        metadata.append(f"chunk_id={raw_item.chunk_id}")
    return f"[{'; '.join(metadata)}] {compact(item.clean_text)}"


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
            metric_audit = normalized_evidence.get(planned.id, {}).get("metric_audit", {})
            metric_status = str(metric_audit.get("metric_status") or "").casefold()
            narrative_only = metric_status in {"found_table", "not_found"}
            metric_lines = [] if narrative_only else metric_facts_prompt_lines(metric_audit)
            normalized = normalized_evidence.get(planned.id, {})
            metric_items = (
                [] if narrative_only else list(normalized.get("metric_items", []))
            )
            curation_present = planned.id in state.get("curated_qualitative_evidence", {})
            prepared_items = (
                list(state.get("curated_qualitative_evidence", {}).get(planned.id, []))
                if curation_present
                else []
            )
            narrative_items = (
                [item.raw_item for item in prepared_items]
                if curation_present
                else list(normalized.get("narrative_items", []))
            )
            if metric_audit.get("numeric_withheld"):
                metric_items = []
            evidence_items = [*metric_items[:5], *narrative_items[:5]]
            metric_evidence_lines = [
                _format_evidence_line(item)
                for item in metric_items[:5]
                if compact(item.raw_evidence_ko)
            ]
            qualitative_evidence_lines = (
                [
                    _format_prepared_evidence_line(item)
                    for item in prepared_items[:5]
                    if compact(item.clean_text)
                ]
                if curation_present
                else [
                    _format_evidence_line(item)
                    for item in narrative_items[:5]
                    if compact(item.raw_evidence_ko)
                ]
            )
            evidence_lines = [*metric_evidence_lines, *qualitative_evidence_lines]
            curation_result = state.get("evidence_curation_results", {}).get(planned.id)
            qualitative_answerability = state.get("qualitative_answerability", {}).get(
                planned.id,
                "SUFFICIENT" if evidence_lines else "INSUFFICIENT",
            )
            curator_enforced = getattr(curation_result, "mode", "") == "enforced"
            contexts[planned.id] = {
                "qid": planned.id,
                "pillar": planned.pillar,
                "question": planned.item_ko,
                "description": planned.description_ko,
                "metric_dimensions": list(contract.metric_dimensions),
                "output_language": company.output_language,
                "system_prompt": spec.system_prompt(),
                "user_prompt": "\n".join(
                    [
                        f"Company: {company.company_name} ({company.company_id})",
                        f"Reporting year: {company.year}",
                        f"Output language: {company.output_language}",
                        f"Question ID: {planned.id}",
                        f"Question: {planned.item_ko}",
                        f"Description: {planned.description_ko}",
                        f"Question contract pillar: {contract.pillar}",
                        f"Metric status: {metric_audit.get('metric_status') or 'legacy/not-applicable'}",
                        f"Metric confidence: {metric_audit.get('metric_confidence') or 'not flagged'}",
                        f"Metric absence: {metric_audit.get('metric_absence') or {}}",
                        f"Required facets: {', '.join(contract.required_facets) or 'none'}",
                        f"Expected facets: {', '.join(contract.expected_facets) or 'none'}",
                        f"Evidence gate: {gate.get('reason', '')}",
                        f"Qualitative evidence route: {normalized.get('qualitative_evidence_route', 'legacy_items')}",
                        f"Qualitative answerability: {qualitative_answerability}",
                        "Accepted structured metric facts:",
                        *(metric_lines or ["- none"]),
                        "Conflicting metric facts (do not use):",
                        *(
                            f"- {item.get('metric', '')} | {item.get('period', '')} | values={item.get('values', [])}"
                            for item in metric_audit.get("conflicts", [])
                        ),
                        "Curated qualitative evidence:",
                        *(f"- {line}" for line in evidence_lines),
                        "Source-use policy: Keep customer-facing Final Answer clean; do not add draft/proposal/consultant attribution phrases to final_answer. Draft/proposal/consultant source limits are carried by quality_flags and review metadata. External assessments support the assessment result and assessed content, not an unstated detailed policy.",
                        "Coverage policy: For metric_status=found_table, the metric table is handled separately from metric_evidence; write Final Answer only from narrative_evidence for context, formulas, boundary changes, accounting-method changes, and comparability caveats. For metric_status=not_found, leave numeric cells empty and use only content routed from non-metric items[]; do not infer, calculate, or move prose numbers into the metric table, but keep inline figures in Final Answer when the exact claim is directly supported by items[].",
                        "Metric scope policy: Final Answer must not use metric table rows, accepted_facts, rejected conflicts, scope_variant rows, denominator rows, or non-primary table rows as reported results. The metric table export handles the full table_block and entity_class detail separately.",
                        "Conflict policy: Never use a metric-period pair listed as conflicting. Keep other non-conflicting supported facts.",
                        "Length policy: Let the answer length be determined by the question and accepted evidence. Cover every directly supported facet needed to answer the question, including relevant policies, governance, processes, actions, metrics, targets, periods, scope, and caveats when evidenced. Use a shorter answer when evidence supports only one narrow claim, and a longer answer when multiple distinct supported facts are needed. Never pad the answer with repetition, generic ESG language, or unsupported context.",
                        "Customer-answer policy: State only supported answer content. Do not mention missing evidence, document scope, partial coverage, review status, additional confirmation, or requests for more information in final_answer; record such gaps only in quality_flags. If no supported answer content remains, return an empty final_answer.",
                        "When evidence_id values are present, also return sentences with sentence_id, text, and the supporting evidence_ids. Every factual sentence must reference at least one supplied evidence_id. Return an evidence-grounded final_answer and concise quality_flags.",
                    ]
                ),
                "evidence_lines": evidence_lines,
                "evidence_items": evidence_items,
                "prepared_evidence": prepared_items,
                "curation_result": curation_result,
                "qualitative_answerability": qualitative_answerability,
                "curator_enforced": curator_enforced,
                "metric_audit": metric_audit,
                "metric_status": metric_audit.get("metric_status"),
                "metric_confidence": metric_audit.get("metric_confidence"),
                "metric_absence": metric_audit.get("metric_absence", {}),
                "accepted": bool(gate.get("accepted"))
                and qualitative_answerability != "INSUFFICIENT"
                and bool(evidence_lines),
                "acceptance_reason": (
                    "curator_insufficient"
                    if qualitative_answerability == "INSUFFICIENT"
                    else gate.get("reason", "")
                ),
                "skill": selection,
            }
        return {"skill_contexts": contexts}
