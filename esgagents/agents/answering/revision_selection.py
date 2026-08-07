from __future__ import annotations

from typing import Any

from esgagents.agents.evidence.policy import has_stable_source


def eligible_revision_qids(state: dict[str, Any], max_revision_rounds: int) -> list[str]:
    """Return only failed drafts that can be safely sent to a revision writer."""
    qa_results = state.get("qa_results", {})
    revision_counts = state.get("revision_counts", {})
    evidence_gate = state.get("evidence_gate", {})
    normalized_evidence = state.get("normalized_evidence", {})
    draft_answers = state.get("draft_answers", {})

    eligible: list[str] = []
    for planned in state.get("planned_questions", []):
        qid = planned.id
        qa = qa_results.get(qid)
        evidence = normalized_evidence.get(qid, {})
        if (
            getattr(qa, "status", "") == "failed"
            and int(revision_counts.get(qid, 0)) < max_revision_rounds
            and bool(evidence_gate.get(qid, {}).get("accepted"))
            and bool(draft_answers.get(qid, "").strip())
            and bool(evidence.get("items"))
            and any(
                has_stable_source(source)
                for source in evidence.get("sources", [])
                if isinstance(source, dict)
            )
        ):
            eligible.append(qid)
    return eligible
