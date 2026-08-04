from __future__ import annotations

import asyncio
from dataclasses import replace

from fastapi.testclient import TestClient
from temporalio.client import WorkflowExecutionStatus
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import ActivityEnvironment

from esgagents.api.app import app
from esgagents.schemas import CompanyInput, RunArtifacts
from esgagents.temporal import activities, workflows
from esgagents.temporal.gateway import (
    JobNotReadyError,
    TemporalGateway,
    TemporalUnavailableError,
)
from esgagents.temporal.models import (
    ReportJobAccepted,
    ReportJobCancellation,
    ReportJobStatus,
    TemporalSettings,
    workflow_id_for,
)


def _settings(tmp_path) -> TemporalSettings:
    return TemporalSettings(
        address="localhost:7233",
        namespace="default",
        task_queue="esg-report",
        api_key="",
        tls=False,
        activity_timeout_seconds=3600,
        workflow_timeout_seconds=7200,
        heartbeat_timeout_seconds=180,
        activity_max_attempts=2,
        worker_max_concurrent_activities=2,
        output_dir=str(tmp_path),
    )


def _company(run_id: str = "run_temporal") -> CompanyInput:
    return CompanyInput(
        company_id="acme",
        company_name="Acme",
        year=2025,
        scale="large",
        industry="TC",
        item_ids=["Q001"],
        run_id=run_id,
    )


def _artifacts(tmp_path) -> RunArtifacts:
    json_path = tmp_path / "qualitative_run.json"
    return RunArtifacts(
        run_id="run_temporal",
        company={
            "company_id": "acme",
            "company_name": "Acme",
            "year": 2025,
        },
        template_selection={},
        answers=[],
        stats={"answered": 0, "empty": 0, "weak": 0, "failed": 0},
        quantitative_stats={"filled": 0, "missing": 0},
        output_paths={"json": str(json_path)},
    )


def test_workflow_id_is_deterministic_and_scoped_to_company_year_run():
    first = workflow_id_for("ACME", 2025, "run_1")

    assert first == workflow_id_for("acme", 2025, "run_1")
    assert first != workflow_id_for("acme", 2026, "run_1")
    assert first != workflow_id_for("other", 2025, "run_1")
    assert first.startswith("esg-report-")


def test_workflow_uses_configured_activity_timeouts_and_retry(monkeypatch):
    captured = {}

    async def execute_activity(name, payload, **kwargs):
        captured["name"] = name
        captured["payload"] = payload
        captured["kwargs"] = kwargs
        return {"run_id": payload["run_id"]}

    monkeypatch.setattr(workflows.workflow, "execute_activity", execute_activity)
    payload = {
        "company_input": _company().model_dump(mode="json"),
        "activity": {
            "start_to_close_seconds": 3600,
            "heartbeat_seconds": 180,
            "maximum_attempts": 2,
        },
    }

    result = asyncio.run(workflows.ESGReportWorkflow().run(payload))

    assert result == {"run_id": "run_temporal"}
    assert captured["name"] == "generate_esg_report"
    assert captured["kwargs"]["start_to_close_timeout"].total_seconds() == 3600
    assert captured["kwargs"]["heartbeat_timeout"].total_seconds() == 180
    assert captured["kwargs"]["retry_policy"].maximum_attempts == 2


def test_activity_heartbeats_nodes_and_returns_only_compact_metadata(monkeypatch, tmp_path):
    heartbeats = []
    artifacts = _artifacts(tmp_path)

    class FakeWriter:
        def __init__(self, *args, **kwargs):
            pass

        def load_existing(self, *args, **kwargs):
            return None

    class FakeGraph:
        def __init__(self, *args, progress_observer=None, **kwargs):
            self.progress_observer = progress_observer

        def generate(self, *args, **kwargs):
            self.progress_observer("01 Normalize Company Input", "started")
            self.progress_observer("01 Normalize Company Input", "completed")
            return artifacts

    monkeypatch.setattr(activities, "OutputWriter", FakeWriter)
    monkeypatch.setattr(activities, "ESGQualitativeGraph", FakeGraph)
    monkeypatch.setattr(
        activities,
        "load_config",
        lambda overrides=None: {
            "checkpoint_enabled": False,
            "output_dir": str(tmp_path),
            "output_timezone": "Asia/Bangkok",
        },
    )
    environment = ActivityEnvironment()
    environment.info = replace(
        ActivityEnvironment.default_info(),
        workflow_id="job-123",
        workflow_run_id="temporal-run-123",
    )
    environment.on_heartbeat = lambda *details: heartbeats.extend(details)

    result = environment.run(
        activities.generate_esg_report,
        _company().model_dump(mode="json"),
    )

    assert result["job_id"] == "job-123"
    assert result["run_id"] == "run_temporal"
    assert "answers" not in result
    assert any(item["node"] == "01 Normalize Company Input" for item in heartbeats)


def test_gateway_returns_same_job_for_duplicate_submission(tmp_path):
    class DuplicateClient:
        async def start_workflow(self, *args, **kwargs):
            raise WorkflowAlreadyStartedError(kwargs["id"], "ESGReportWorkflow")

    gateway = TemporalGateway(DuplicateClient(), _settings(tmp_path))

    accepted = asyncio.run(gateway.submit(_company()))

    assert accepted.deduplicated is True
    assert accepted.job_id == workflow_id_for("acme", 2025, "run_temporal")


def test_gateway_maps_completed_description_and_compact_result(tmp_path):
    class Description:
        status = WorkflowExecutionStatus.COMPLETED
        run_id = "temporal-run"
        start_time = None
        close_time = None

        async def memo(self):
            return {"run_id": "run_temporal", "company_id": "acme", "year": 2025}

    class Handle:
        async def describe(self):
            return Description()

        async def result(self):
            return {
                "run_id": "run_temporal",
                "output_paths": {"json": str(tmp_path / "qualitative_run.json")},
            }

    class Client:
        def get_workflow_handle(self, job_id):
            return Handle()

    job = asyncio.run(TemporalGateway(Client(), _settings(tmp_path)).status("job-123"))

    assert job.status == "completed"
    assert job.run_id == "run_temporal"
    assert job.result["output_paths"]["json"].endswith("qualitative_run.json")


class _FakeAPIGateway:
    def __init__(self, mode: str = "ok"):
        self.mode = mode

    async def submit(self, payload):
        if self.mode == "unavailable":
            raise TemporalUnavailableError("offline")
        return ReportJobAccepted(
            job_id="job-123",
            run_id=payload.resolved_run_id(),
            status="pending",
            status_url="/reports/esg/qualitative/jobs/job-123",
            result_url="/reports/esg/qualitative/jobs/job-123/result",
        )

    async def status(self, job_id):
        return ReportJobStatus(job_id=job_id, status="running")

    async def result(self, job_id):
        raise JobNotReadyError("not ready")

    async def cancel(self, job_id):
        return ReportJobCancellation(job_id=job_id)


def test_async_job_api_submit_status_result_not_ready_and_cancel():
    with TestClient(app) as client:
        app.state.temporal_gateway = _FakeAPIGateway()
        response = client.post(
            "/reports/esg/qualitative/jobs",
            json=_company().model_dump(mode="json"),
        )
        job_id = response.json()["job_id"]

        assert response.status_code == 202
        assert client.get(f"/reports/esg/qualitative/jobs/{job_id}").status_code == 200
        assert (
            client.get(f"/reports/esg/qualitative/jobs/{job_id}/result").status_code
            == 409
        )
        assert client.delete(f"/reports/esg/qualitative/jobs/{job_id}").status_code == 202


def test_async_job_api_returns_503_without_exposing_internal_error():
    with TestClient(app) as client:
        app.state.temporal_gateway = _FakeAPIGateway(mode="unavailable")
        response = client.post(
            "/reports/esg/qualitative/jobs",
            json=_company().model_dump(mode="json"),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Temporal service is unavailable"}
    assert "offline" not in response.text
