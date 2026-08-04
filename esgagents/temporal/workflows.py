from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ESGReportWorkflow")
class ESGReportWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        activity_options = payload["activity"]
        return await workflow.execute_activity(
            "generate_esg_report",
            payload["company_input"],
            result_type=dict,
            start_to_close_timeout=timedelta(
                seconds=int(activity_options["start_to_close_seconds"]),
            ),
            heartbeat_timeout=timedelta(
                seconds=int(activity_options["heartbeat_seconds"]),
            ),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=int(activity_options["maximum_attempts"]),
            ),
        )
