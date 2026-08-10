from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from esgagents.agents.answering.output_hygiene import OutputHygieneAgent
from esgagents.agents.evidence.metric_facts import metric_numbers_equivalent
from esgagents.publication import evaluate_publication, published_answer
from esgagents.schemas import AnswerRecord, QAResult
from skills.agents.writer import SkillWriterAgent


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "p0_qualitative_regressions.json"
EXPECTED_QIDS = {
    "Q004", "Q017", "Q019", "Q031", "Q055", "Q075", "Q080", "Q082",
    "Q086", "Q087", "Q091", "Q094",
}
EXECUTABLE_QIDS = {"Q019", "Q031", "Q055", "Q075", "Q087", "Q091"}


def test_p0_regression_fixture_is_compact_and_complete():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["fixture_version"] == "p0-qualitative-v1"
    assert set(fixture["qids"]) == EXPECTED_QIDS
    assert FIXTURE_PATH.stat().st_size < 10_000
    assert all(case.get("case") and case.get("expected") for case in fixture["qids"].values())


@pytest.mark.parametrize("qid", sorted(EXECUTABLE_QIDS))
def test_p0_regression_fixture_executes_deterministic_pipeline_cases(qid):
    case = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["qids"][qid]
    case_input = case["input"]

    if qid in {"Q019", "Q055"}:
        planned = SimpleNamespace(
            id=qid,
            pillar="Metrics",
            item_ko="정량 지표",
            description_ko="결과를 설명합니다",
        )
        result = OutputHygieneAgent({"output_hygiene_enabled": True}).run(
            {
                "planned_questions": [planned],
                "final_answers": {qid: case_input["answer"]},
                "quality_flags": {qid: []},
                "qa_results": {qid: QAResult(status="passed")},
            }
        )
        assert result["final_answers"][qid] == ""
        assert result["qa_results"][qid].status == "failed"
        return

    if qid == "Q031":
        assert metric_numbers_equivalent(case_input["candidate"], case_input["source"])
        return

    if qid in {"Q075", "Q087"}:
        fact = {
            **case_input,
            "normalized_value": case_input["value"],
            "source_tier": "tier_2_operational",
            "source_id": "ESG/metrics.xlsx",
        }
        answer = SkillWriterAgent._metric_fallback(
            {
                "output_language": "English",
                "metric_audit": {"accepted_facts": [fact]},
            }
        )
        record = AnswerRecord(
            qid=qid,
            answer_status="medium_confidence",
            final_answer=answer,
            qa=QAResult(status="passed"),
            qa_grade="full",
            coverage_reason="complete_answer",
        )
        assert case_input["metric"] in answer
        assert evaluate_publication(record).status == "published"
        assert published_answer(record) == answer
        return

    record = AnswerRecord(
        qid=qid,
        answer_status="medium_confidence",
        final_answer=case_input["answer"],
        qa=QAResult(status="failed", notes=[case_input["hard_failure"]]),
        qa_grade="failed",
        coverage_reason=case_input["hard_failure"],
        hard_failures=[case_input["hard_failure"]],
    )
    assert evaluate_publication(record).status == "blocked"
    assert published_answer(record) == ""
