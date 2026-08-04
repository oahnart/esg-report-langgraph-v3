from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from esgagents.schemas import CompanyInput, RunArtifacts

from .models import (
    ReportJobAccepted,
    ReportJobCancellation,
    ReportJobStatus,
    TemporalSettings,
    workflow_id_for,
)
from .workflows import ESGReportWorkflow


class TemporalGatewayError(RuntimeError):
    pass


class TemporalUnavailableError(TemporalGatewayError):
    pass


class JobNotFoundError(TemporalGatewayError):
    pass


class JobNotReadyError(TemporalGatewayError):
    pass


class JobResultUnavailableError(TemporalGatewayError):
    pass


_STATUS_MAP = {
    WorkflowExecutionStatus.RUNNING: "running",
    WorkflowExecutionStatus.COMPLETED: "completed",
    WorkflowExecutionStatus.FAILED: "failed",
    WorkflowExecutionStatus.CANCELED: "cancelled",
    WorkflowExecutionStatus.TERMINATED: "cancelled",
    WorkflowExecutionStatus.CONTINUED_AS_NEW: "running",
    WorkflowExecutionStatus.TIMED_OUT: "failed",
}


class TemporalGateway:
    def __init__(self, client: Client, settings: TemporalSettings):
        self.client = client
        self.settings = settings

    async def submit(self, company_input: CompanyInput) -> ReportJobAccepted:
        run_id = company_input.resolved_run_id()
        company_input.run_id = run_id
        job_id = workflow_id_for(company_input.company_id, company_input.year, run_id)
        deduplicated = False
        try:
            await self.client.start_workflow(
                ESGReportWorkflow.run,
                self.settings.workflow_input(company_input),
                id=job_id,
                task_queue=self.settings.task_queue,
                execution_timeout=_seconds(self.settings.workflow_timeout_seconds),
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                memo={
                    "run_id": run_id,
                    "company_id": company_input.company_id,
                    "year": company_input.year,
                },
                static_summary=f"Generate ESG report for {company_input.company_id}",
            )
        except WorkflowAlreadyStartedError:
            deduplicated = True
        except RPCError as exc:
            raise _translate_rpc_error(exc) from exc

        base_url = f"/reports/esg/qualitative/jobs/{job_id}"
        return ReportJobAccepted(
            job_id=job_id,
            run_id=run_id,
            status="pending",
            deduplicated=deduplicated,
            status_url=base_url,
            result_url=f"{base_url}/result",
        )

    async def status(self, job_id: str) -> ReportJobStatus:
        handle = self.client.get_workflow_handle(job_id)
        try:
            description = await handle.describe()
            memo = await description.memo()
        except RPCError as exc:
            raise _translate_rpc_error(exc) from exc

        state = _STATUS_MAP.get(description.status, "pending")
        error_code = None
        error_message = None
        if description.status == WorkflowExecutionStatus.FAILED:
            error_code = "workflow_failed"
            error_message = "ESG report generation failed"
        elif description.status == WorkflowExecutionStatus.TIMED_OUT:
            error_code = "workflow_timed_out"
            error_message = "ESG report generation timed out"
        elif description.status == WorkflowExecutionStatus.TERMINATED:
            error_code = "workflow_terminated"
            error_message = "ESG report generation was terminated"

        result = None
        if description.status == WorkflowExecutionStatus.COMPLETED:
            try:
                raw_result = await handle.result()
                result = dict(raw_result)
            except Exception as exc:
                raise JobResultUnavailableError(
                    "Temporal completed the workflow but its result metadata is unavailable"
                ) from exc

        return ReportJobStatus(
            job_id=job_id,
            status=state,
            run_id=_optional_text(memo.get("run_id")),
            company_id=_optional_text(memo.get("company_id")),
            year=_optional_int(memo.get("year")),
            temporal_run_id=description.run_id,
            started_at=description.start_time,
            closed_at=description.close_time,
            error_code=error_code,
            error_message=error_message,
            result=result,
        )

    async def result(self, job_id: str) -> RunArtifacts:
        status = await self.status(job_id)
        if status.status != "completed" or status.result is None:
            raise JobNotReadyError(f"ESG report job {job_id} is not completed")

        output_paths = status.result.get("output_paths") or {}
        json_path_value = output_paths.get("json")
        if not json_path_value:
            raise JobResultUnavailableError("Completed ESG report has no JSON output path")
        json_path = Path(str(json_path_value)).resolve()
        output_root = Path(self.settings.output_dir).resolve()
        try:
            json_path.relative_to(output_root)
        except ValueError as exc:
            raise JobResultUnavailableError(
                "Completed ESG report points outside the configured output directory"
            ) from exc
        try:
            with json_path.open("r", encoding="utf-8") as handle:
                return RunArtifacts.model_validate(json.load(handle))
        except (OSError, ValueError) as exc:
            raise JobResultUnavailableError(
                "Completed ESG report output is missing or invalid"
            ) from exc

    async def cancel(self, job_id: str) -> ReportJobCancellation:
        handle = self.client.get_workflow_handle(job_id)
        try:
            description = await handle.describe()
            if description.status == WorkflowExecutionStatus.RUNNING:
                await handle.cancel(reason="Cancelled through ESG report API")
                state = "cancel_requested"
            else:
                state = _STATUS_MAP.get(description.status, "cancelled")
        except RPCError as exc:
            raise _translate_rpc_error(exc) from exc
        return ReportJobCancellation(job_id=job_id, status=state)


def _seconds(value: int) -> timedelta:
    return timedelta(seconds=value)


def _translate_rpc_error(exc: RPCError) -> TemporalGatewayError:
    if exc.status == RPCStatusCode.NOT_FOUND:
        return JobNotFoundError("ESG report job was not found")
    return TemporalUnavailableError("Temporal service is unavailable")


def _optional_text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
