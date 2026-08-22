from __future__ import annotations

import re
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable

from esgagents.agents.answering.revision import RevisionAgent
from esgagents.agents.answering.semantic_critic import SemanticCompletenessCriticAgent
from esgagents.default_config import load_config
from esgagents.graph.setup import ESGGraphSetup
from esgagents.progress import ProgressReporter
from esgagents.schemas import EvidenceItem, QAResult, SemanticReview, SkillDraft
from skills.agents.writer import SkillWriterAgent


class RecordingStructuredLLM:
    metadata: dict[str, Any] = {}

    def __init__(
        self,
        response_factory: Callable[[type[Any], str], Any],
        *,
        fail_qid: str = "",
        fail_exception: type[Exception] = RuntimeError,
        delay: float = 0.02,
    ):
        self.response_factory = response_factory
        self.fail_qid = fail_qid
        self.fail_exception = fail_exception
        self.delay = delay
        self.schema: type[Any] = SkillDraft
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def with_structured_output(self, schema: type[Any]) -> "RecordingStructuredLLM":
        self.schema = schema
        return self

    def invoke(self, prompt: Any) -> Any:
        text = "\n".join(str(getattr(message, "content", message)) for message in prompt)
        match = re.search(r"Q\d{3}", text)
        qid = match.group(0) if match else "Q000"
        with self._lock:
            self.calls.append(qid)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            if qid == self.fail_qid:
                raise self.fail_exception(f"synthetic failure for {qid}")
            return self.response_factory(self.schema, qid)
        finally:
            with self._lock:
                self.active -= 1


def _planned(qid: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=qid,
        source_id=qid,
        pillar="Strategy",
        category_ko="Environment",
        item_ko=f"Environmental policy {qid}",
        description_ko="Describe the current environmental policy.",
    )


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        raw_evidence_ko=(
            "The company maintains an environmental policy and updates its "
            "environmental policy annually."
        ),
        source_name="policy.pdf",
        source_path="ESG/policy.pdf",
        canonical_source_id="policy",
        document_id="policy-doc",
        chunk_id="policy-chunk",
        semantic_label="useful",
        source_tier="tier_2_operational",
        document_status="approved",
    )


def _writer_state(qids: list[str]) -> dict[str, Any]:
    planned = [_planned(qid) for qid in qids]
    return {
        "planned_questions": planned,
        "skill_contexts": {
            qid: {
                "qid": qid,
                "accepted": True,
                "system_prompt": "Write a grounded ESG answer.",
                "user_prompt": f"Question ID: {qid}",
                "metric_audit": {},
                "metric_absence": {},
                "evidence_items": [_evidence()],
                "output_language": "English",
            }
            for qid in qids
        },
        "evidence_gate": {qid: {"accepted": True, "reason": "accepted"} for qid in qids},
        "rag_results": {
            qid: SimpleNamespace(
                metric_status="",
                metric_confidence="",
                normalized_answer_ko=f"Fallback answer for {qid}.",
            )
            for qid in qids
        },
        "normalized_evidence": {qid: {"sources": []} for qid in qids},
        "quality_flags": {},
        "revision_counts": {},
    }


def _revision_state(qids: list[str]) -> dict[str, Any]:
    planned = [_planned(qid) for qid in qids]
    item = _evidence()
    answer = "The company maintains an environmental policy."
    return {
        "planned_questions": planned,
        "company": SimpleNamespace(company_name="Company", output_language="English"),
        "qa_results": {
            qid: QAResult(status="failed", notes=["missing required facet: policy_or_direction"])
            for qid in qids
        },
        "evidence_gate": {qid: {"accepted": True, "reason": "accepted"} for qid in qids},
        "normalized_evidence": {
            qid: {
                "items": [item],
                "sources": [{"source_path": item.source_path}],
                "metric_audit": {},
                "evidence_summary": item.raw_evidence_ko,
            }
            for qid in qids
        },
        "draft_answers": {qid: answer for qid in qids},
        "final_answers": {qid: "" for qid in qids},
        "revision_counts": {},
        "quality_flags": {},
        "sanitizer_actions": {},
        "skill_selections": {},
    }


def _semantic_state(qids: list[str]) -> dict[str, Any]:
    planned = [_planned(qid) for qid in qids]
    item = _evidence()
    answer = "The company maintains an environmental policy."
    return {
        "planned_questions": planned,
        "company": SimpleNamespace(output_language="English"),
        "qa_results": {qid: QAResult(status="passed", notes=["grounded"]) for qid in qids},
        "draft_answers": {qid: answer for qid in qids},
        "final_answers": {qid: answer for qid in qids},
        "normalized_evidence": {
            qid: {
                "items": [item],
                "sources": [{"source_path": item.source_path}],
                "metric_audit": {},
            }
            for qid in qids
        },
        "rag_results": {
            qid: SimpleNamespace(
                is_v3=False,
                metric_status="",
                answer_status="high_confidence",
                retrieval_notes=[],
                covered_facets=[],
                missing_facets=[],
                coverage_status="complete",
            )
            for qid in qids
        },
        "quality_flags": {},
        "skill_checks": {},
        "claim_support": {},
        "last_rejected_answers": {},
        "qa_failure_stages": {},
        "sanitizer_actions": {},
        "semantic_reviews": {},
        "semantic_llm_reviews": {},
        "semantic_review_fingerprints": {},
    }


def _draft_response(schema: type[Any], qid: str) -> Any:
    assert schema is SkillDraft
    return SkillDraft(final_answer=f"Grounded answer for {qid}.")


def _revision_response(schema: type[Any], qid: str) -> Any:
    assert schema is SkillDraft
    return SkillDraft(final_answer="The company maintains an environmental policy.")


def _semantic_response(schema: type[Any], qid: str) -> Any:
    assert schema is SemanticReview
    return SemanticReview(
        alignment="aligned",
        covered_facets=["policy_or_direction"],
        source_usage="appropriate",
    )


def test_writer_parallelism_is_bounded_deterministic_and_failure_isolated():
    qids = [f"Q{index:03d}" for index in range(1, 9)]
    state = _writer_state(qids)
    parallel_llm = RecordingStructuredLLM(
        _draft_response,
        fail_qid="Q004",
        fail_exception=ValueError,
    )
    parallel = SkillWriterAgent({"writer_concurrency": 4}, parallel_llm).run(state)

    sequential_llm = RecordingStructuredLLM(
        _draft_response,
        fail_qid="Q004",
        fail_exception=ValueError,
        delay=0,
    )
    sequential = SkillWriterAgent({"writer_concurrency": 1}, sequential_llm).run(state)

    assert 1 < parallel_llm.max_active <= 4
    assert sequential_llm.max_active == 1
    assert list(parallel["draft_answers"]) == qids
    assert parallel["draft_answers"] == sequential["draft_answers"]
    assert parallel["quality_flags"] == sequential["quality_flags"]
    assert parallel["draft_answers"]["Q004"] == "Fallback answer for Q004."
    assert "llm_error_fallback" in parallel["quality_flags"]["Q004"]


def test_writer_timeout_is_isolated_to_its_qid():
    qids = ["Q001", "Q002", "Q003"]
    llm = RecordingStructuredLLM(
        _draft_response,
        fail_qid="Q002",
        fail_exception=TimeoutError,
        delay=0,
    )

    result = SkillWriterAgent({"writer_concurrency": 3}, llm).run(_writer_state(qids))

    assert result["draft_answers"]["Q002"] == "Fallback answer for Q002."
    assert result["draft_answers"]["Q001"] == "Grounded answer for Q001."
    assert result["draft_answers"]["Q003"] == "Grounded answer for Q003."
    assert "llm_error_fallback" in result["quality_flags"]["Q002"]


def test_writer_progress_reports_each_qid_and_fallback_duration():
    qids = ["Q001", "Q002", "Q003"]
    events = []
    llm = RecordingStructuredLLM(
        _draft_response,
        fail_qid="Q002",
        delay=0,
    )

    SkillWriterAgent(
        {"writer_concurrency": 3},
        llm,
        ProgressReporter(events.append),
    ).run(_writer_state(qids))

    terminal = {
        event.name: event
        for event in events
        if event.category == "WRITER" and event.status != "started"
    }
    assert set(terminal) == set(qids)
    assert terminal["Q002"].status == "fallback"
    assert all(event.duration_seconds is not None for event in terminal.values())


def test_revision_parallelism_is_bounded_and_failure_isolated():
    qids = [f"Q{index:03d}" for index in range(1, 9)]
    llm = RecordingStructuredLLM(_revision_response, fail_qid="Q004")
    result = RevisionAgent(
        {"revision_concurrency": 4, "max_revision_rounds": 2}, llm
    ).run(_revision_state(qids))

    assert 1 < llm.max_active <= 4
    assert list(result["revision_counts"]) == qids
    assert result["revision_counts"] == {qid: 1 for qid in qids}
    assert all(result["final_answers"][qid] for qid in qids)
    assert "revision_error" in result["quality_flags"]["Q004"]
    assert "revision_error" not in result["quality_flags"]["Q003"]

    sequential_llm = RecordingStructuredLLM(
        _revision_response,
        fail_qid="Q004",
        delay=0,
    )
    sequential = RevisionAgent(
        {"revision_concurrency": 1, "max_revision_rounds": 2}, sequential_llm
    ).run(_revision_state(qids))

    assert sequential_llm.max_active == 1
    assert result["draft_answers"] == sequential["draft_answers"]
    assert result["final_answers"] == sequential["final_answers"]
    assert result["quality_flags"] == sequential["quality_flags"]
    assert result["revision_counts"] == sequential["revision_counts"]


def test_revision_progress_reports_real_worker_start_and_failure_fallback():
    qids = ["Q001", "Q002", "Q003"]
    events = []
    llm = RecordingStructuredLLM(_revision_response, fail_qid="Q002", delay=0)

    RevisionAgent(
        {"revision_concurrency": 2, "max_revision_rounds": 1},
        llm,
        ProgressReporter(events.append),
    ).run(_revision_state(qids))

    terminal = {
        event.name: event
        for event in events
        if event.category == "REVISION"
        and event.name != "summary"
        and event.status != "started"
    }
    assert terminal["Q002"].status == "fallback"
    assert terminal["Q001"].status == "completed"
    assert terminal["Q003"].status == "completed"
    assert all(event.duration_seconds is not None for event in terminal.values())


def test_semantic_review_cache_reuses_unchanged_inputs_and_refreshes_one_qid():
    qids = ["Q001", "Q002", "Q003"]
    llm = RecordingStructuredLLM(_semantic_response, delay=0)
    critic = SemanticCompletenessCriticAgent(
        {
            "semantic_qa_enabled": True,
            "semantic_qa_concurrency": 3,
            "semantic_qa_incremental": True,
        },
        llm,
    )
    state = _semantic_state(qids)

    first = critic.run(state)
    assert len(llm.calls) == 3
    state.update(first)

    second = critic.run(state)
    assert len(llm.calls) == 3
    state.update(second)

    changed = "The company updates its environmental policy annually."
    state["draft_answers"]["Q002"] = changed
    state["final_answers"]["Q002"] = changed
    third = critic.run(state)

    assert len(llm.calls) == 4
    assert llm.calls[-1] == "Q002"
    assert set(third["semantic_reviews"]) == set(qids)


def test_semantic_incremental_can_be_disabled_for_rollback():
    qids = ["Q001", "Q002"]
    llm = RecordingStructuredLLM(_semantic_response, delay=0)
    critic = SemanticCompletenessCriticAgent(
        {
            "semantic_qa_enabled": True,
            "semantic_qa_concurrency": 2,
            "semantic_qa_incremental": False,
        },
        llm,
    )
    state = _semantic_state(qids)
    state.update(critic.run(state))
    critic.run(state)

    assert len(llm.calls) == 4


def test_semantic_progress_reports_each_llm_review_with_verdict_and_duration():
    qids = ["Q001", "Q002", "Q003"]
    events = []
    llm = RecordingStructuredLLM(_semantic_response, delay=0)
    critic = SemanticCompletenessCriticAgent(
        {
            "semantic_qa_enabled": True,
            "semantic_qa_concurrency": 2,
            "semantic_qa_incremental": False,
        },
        llm,
        ProgressReporter(events.append),
    )

    critic.run(_semantic_state(qids))

    terminal = {
        event.name: event
        for event in events
        if event.category == "SEMANTIC"
        and event.name in qids
        and event.status != "started"
    }
    assert set(terminal) == set(qids)
    assert all(event.status == "completed" for event in terminal.values())
    assert all(event.duration_seconds is not None for event in terminal.values())
    assert all(event.details["verdict"] == "PASS" for event in terminal.values())


def test_performance_config_defaults_are_enabled_and_bounded():
    config = load_config({"agent_mode": "offline"})

    assert config["writer_concurrency"] == 4
    assert config["revision_concurrency"] == 4
    assert config["semantic_qa_incremental"] is True


def test_graph_node_timing_keeps_progress_callback_contract(caplog):
    events: list[tuple[str, str]] = []
    setup = ESGGraphSetup(
        agents=None,
        conditional_logic=None,
        progress_observer=lambda node, status: events.append((node, status)),
    )
    wrapped = setup._observe("Synthetic Node", lambda state: {"value": state["value"] + 1})

    with caplog.at_level("INFO"):
        result = wrapped({"value": 1})

    assert result == {"value": 2}
    assert events == [
        ("Synthetic Node", "started"),
        ("Synthetic Node", "completed"),
    ]
    assert any(
        "graph_node node='Synthetic Node' status=completed elapsed_ms=" in record.message
        for record in caplog.records
    )
