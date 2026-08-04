from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from esgagents.schemas import CompanyInput


JobState = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancel_requested",
    "cancelled",
]


@dataclass(frozen=True)
class TemporalSettings:
    address: str
    namespace: str
    task_queue: str
    api_key: str
    tls: bool
    activity_timeout_seconds: int
    workflow_timeout_seconds: int
    heartbeat_timeout_seconds: int
    activity_max_attempts: int
    worker_max_concurrent_activities: int
    output_dir: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "TemporalSettings":
        return cls(
            address=str(config["temporal_address"]),
            namespace=str(config["temporal_namespace"]),
            task_queue=str(config["temporal_task_queue"]),
            api_key=str(config.get("temporal_api_key") or ""),
            tls=bool(config.get("temporal_tls", False)),
            activity_timeout_seconds=max(
                1,
                int(config["temporal_activity_timeout_seconds"]),
            ),
            workflow_timeout_seconds=max(
                1,
                int(config["temporal_workflow_timeout_seconds"]),
            ),
            heartbeat_timeout_seconds=max(
                1,
                int(config["temporal_heartbeat_timeout_seconds"]),
            ),
            activity_max_attempts=max(1, int(config["temporal_activity_max_attempts"])),
            worker_max_concurrent_activities=max(
                1,
                int(config["temporal_worker_max_concurrent_activities"]),
            ),
            output_dir=str(config["output_dir"]),
        )

    def workflow_input(self, company_input: CompanyInput) -> dict[str, Any]:
        return {
            "company_input": company_input.model_dump(mode="json"),
            "activity": {
                "start_to_close_seconds": self.activity_timeout_seconds,
                "heartbeat_seconds": self.heartbeat_timeout_seconds,
                "maximum_attempts": self.activity_max_attempts,
            },
        }


class ReportJobAccepted(BaseModel):
    job_id: str
    run_id: str
    status: JobState = "pending"
    deduplicated: bool = False
    status_url: str
    result_url: str


class ReportJobStatus(BaseModel):
    job_id: str
    status: JobState
    run_id: str | None = None
    company_id: str | None = None
    year: int | None = None
    temporal_run_id: str | None = None
    started_at: datetime | None = None
    closed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None


class ReportJobCancellation(BaseModel):
    job_id: str
    status: JobState = "cancel_requested"


def workflow_id_for(company_id: str, year: int, run_id: str) -> str:
    identity = f"{company_id.strip().lower()}:{int(year)}:{run_id.strip()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"esg-report-{digest}"


def compact_result(job_id: str, artifacts: Any) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "run_id": artifacts.run_id,
        "company_id": str(artifacts.company["company_id"]),
        "year": int(artifacts.company["year"]),
        "stats": dict(artifacts.stats),
        "quantitative_stats": dict(artifacts.quantitative_stats),
        "output_paths": dict(artifacts.output_paths),
    }
