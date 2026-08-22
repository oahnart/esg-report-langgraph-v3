from __future__ import annotations

from requests import ConnectionError

from esgagents.progress import (
    ProgressReporter,
    format_progress_event,
    safe_error_detail,
)
from esgagents.rag_client import TeamRagClient


def test_progress_event_contains_wall_clock_total_elapsed_and_task_duration():
    events = []
    reporter = ProgressReporter(events.append, level="full")

    token = reporter.start(
        "CURATOR",
        "Q023",
        current=23,
        total=85,
        details={"evidence": 6},
    )
    reporter.finish(
        token,
        details={"kept": 4, "dropped": 2, "answerability": "SUFFICIENT"},
    )

    assert [event.status for event in events] == ["started", "completed"]
    assert events[-1].duration_seconds is not None
    rendered = format_progress_event(events[-1])
    assert "CURATOR DONE Q023" in rendered
    assert "question=23/85" in rendered
    assert "duration=" in rendered
    assert "kept=4" in rendered
    assert "answerability=SUFFICIENT" in rendered


def test_progress_levels_filter_detail_without_hiding_steps():
    events = []
    reporter = ProgressReporter(events.append, level="steps")

    reporter.event("CURATOR", "Q001")
    reporter.event("STEP", "01 Normalize Company Input", verbosity="steps")

    assert [(event.category, event.name) for event in events] == [
        ("STEP", "01 Normalize Company Input")
    ]


def test_rag_http_attempts_report_retry_endpoint_duration_and_redact_secrets():
    events = []
    calls = 0

    def transport(endpoint, payload, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("Authorization: Bearer private-token")
        return {
            "request_id": "rag-request-1",
            "latency_ms": 17,
            "results": [{"question_id": "Q001"}],
        }

    reporter = ProgressReporter(events.append, level="full")
    client = TeamRagClient(
        "https://rag.example",
        qualitative_path="/qualitative/evidence/v3?api_key=super-secret",
        max_retries=1,
        transport=transport,
        progress_reporter=reporter,
    )

    result = client._post(
        {"company_id": "company", "item_ids": ["Q001"], "year": 2025, "top_k": 5}
    )

    assert result["request_id"] == "rag-request-1"
    terminal = [event for event in events if event.status != "started"]
    assert [event.status for event in terminal] == ["retry", "completed"]
    assert all(event.duration_seconds is not None for event in terminal)
    rendered = "\n".join(format_progress_event(event) for event in events)
    assert "endpoint=https://rag.example/qualitative/evidence/v3" in rendered
    assert "api_key=[REDACTED]" in rendered
    assert "super-secret" not in rendered
    assert "private-token" not in rendered
    assert "request_id=rag-request-1" in rendered


def test_error_detail_redacts_bearer_and_key_values():
    rendered = safe_error_detail(
        RuntimeError(
            'Authorization: Bearer abc.def api_key=my-secret password=hunter2 '
            '"access_token": "json-secret"'
        )
    )

    assert "abc.def" not in rendered
    assert "my-secret" not in rendered
    assert "hunter2" not in rendered
    assert "json-secret" not in rendered
    assert rendered.count("[REDACTED]") >= 4


def test_reporter_counts_full_detail_even_when_step_only_output_filters_it():
    events = []
    reporter = ProgressReporter(events.append, level="steps")

    token = reporter.start("RAG API", "POST qualitative evidence")
    reporter.finish(token, status="retry")

    assert events == []
    assert reporter.count("RAG API", "started") == 1
    assert reporter.count("RAG API", "retry") == 1
