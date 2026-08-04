from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from esgagents.default_config import load_config
from esgagents.provenance import verify_runtime_provenance

from .activities import generate_esg_report
from .client import create_temporal_client
from .models import TemporalSettings
from .workflows import ESGReportWorkflow


async def run_worker() -> None:
    verify_runtime_provenance()
    config = load_config()
    settings = TemporalSettings.from_config(config)
    client = await create_temporal_client(settings)
    logging.getLogger(__name__).info(
        "Starting Temporal worker namespace=%s task_queue=%s",
        settings.namespace,
        settings.task_queue,
    )
    with ThreadPoolExecutor(
        max_workers=settings.worker_max_concurrent_activities,
        thread_name_prefix="esg-temporal-activity",
    ) as activity_executor:
        worker = Worker(
            client,
            task_queue=settings.task_queue,
            workflows=[ESGReportWorkflow],
            activities=[generate_esg_report],
            activity_executor=activity_executor,
            max_concurrent_activities=settings.worker_max_concurrent_activities,
        )
        await worker.run()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
