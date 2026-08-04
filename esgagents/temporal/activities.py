from __future__ import annotations

import logging
from contextvars import copy_context
from threading import Event, Lock, Thread
from typing import Any

from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError, CancelledError

from esgagents.default_config import load_config
from esgagents.graph.esg_graph import ESGQualitativeGraph
from esgagents.output_writer import OutputPathError, OutputWriter
from esgagents.provenance import ProvenanceError
from esgagents.schemas import CompanyInput

from .models import compact_result

logger = logging.getLogger(__name__)


def _safe_non_retryable_message(exc: BaseException) -> str:
    if isinstance(exc, ProvenanceError):
        return "Container provenance verification failed"
    if isinstance(exc, ValidationError):
        return "Invalid ESG report input"
    if isinstance(exc, FileNotFoundError):
        return "Required ESG template or input file was not found"
    if isinstance(exc, OutputPathError):
        return "Invalid ESG output path"
    return "Invalid ESG report configuration or input"


@activity.defn(name="generate_esg_report")
def generate_esg_report(company_payload: dict[str, Any]) -> dict[str, Any]:
    info = activity.info()
    job_id = info.workflow_id
    heartbeat_stop = Event()
    heartbeat_lock = Lock()
    heartbeat_state = {
        "job_id": job_id,
        "node": "ESG Report Workflow",
        "phase": "starting",
    }

    def heartbeat(node_name: str, phase: str) -> None:
        with heartbeat_lock:
            heartbeat_state.update(node=node_name, phase=phase)
            details = dict(heartbeat_state)
        activity.heartbeat(details)
        logger.info(
            "Temporal ESG activity progress job_id=%s temporal_run_id=%s node=%s phase=%s",
            job_id,
            info.workflow_run_id,
            node_name,
            phase,
        )

    def periodic_heartbeat() -> None:
        timeout = info.heartbeat_timeout.total_seconds() if info.heartbeat_timeout else 180
        interval = max(1.0, min(60.0, timeout / 3))
        while not heartbeat_stop.wait(interval):
            with heartbeat_lock:
                details = dict(heartbeat_state)
                details["phase"] = f"{details['phase']}:running"
            try:
                activity.heartbeat(details)
            except (CancelledError, RuntimeError):
                heartbeat_stop.set()
                return

    heartbeat_context = copy_context()
    heartbeat_thread = Thread(
        target=lambda: heartbeat_context.run(periodic_heartbeat),
        name=f"temporal-heartbeat-{job_id[:12]}",
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        parsed = CompanyInput.model_validate(company_payload)
        config = load_config({"checkpoint_enabled": False})
        writer = OutputWriter(
            config["output_dir"],
            output_timezone=config["output_timezone"],
        )
        existing = writer.load_existing(
            parsed.company_id,
            parsed.year,
            parsed.resolved_run_id(),
        )
        if existing is not None:
            heartbeat("Write Report Output", "reused")
            return compact_result(job_id, existing)

        heartbeat("ESG Report Workflow", "started")
        graph = ESGQualitativeGraph(
            config=config,
            output_writer=writer,
            progress_observer=heartbeat,
        )
        artifacts = graph.generate(
            parsed,
            write_outputs=True,
            retry_outputs=True,
        )
        heartbeat("ESG Report Workflow", "completed")
        return compact_result(job_id, artifacts)
    except CancelledError:
        logger.info(
            "Temporal ESG activity cancelled job_id=%s temporal_run_id=%s",
            job_id,
            info.workflow_run_id,
        )
        raise
    except (ValidationError, ValueError, FileNotFoundError, OutputPathError, ProvenanceError) as exc:
        logger.warning(
            "Temporal ESG activity rejected job_id=%s error_type=%s",
            job_id,
            type(exc).__name__,
        )
        raise ApplicationError(
            _safe_non_retryable_message(exc),
            type=type(exc).__name__,
            non_retryable=True,
        ) from exc
    except Exception as exc:
        logger.exception(
            "Temporal ESG activity failed job_id=%s error_type=%s",
            job_id,
            type(exc).__name__,
        )
        raise ApplicationError(
            "ESG report generation failed",
            type=type(exc).__name__,
        ) from exc
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1)
