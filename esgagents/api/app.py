from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status

from esgagents.default_config import load_config
from esgagents.graph.esg_graph import ESGQualitativeGraph
from esgagents.output_writer import OutputRunExistsError
from esgagents.provenance import verify_runtime_provenance
from esgagents.schemas import CompanyInput, RunArtifacts, model_to_dict
from esgagents.temporal.client import create_temporal_client
from esgagents.temporal.gateway import (
    JobNotFoundError,
    JobNotReadyError,
    JobResultUnavailableError,
    TemporalGateway,
    TemporalUnavailableError,
)
from esgagents.temporal.models import (
    ReportJobAccepted,
    ReportJobCancellation,
    ReportJobStatus,
    TemporalSettings,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.provenance = verify_runtime_provenance()
    settings = TemporalSettings.from_config(load_config())
    try:
        client = await create_temporal_client(settings, lazy=True)
        application.state.temporal_gateway = TemporalGateway(client, settings)
    except Exception:
        logger.exception("Unable to initialize the Temporal client")
        application.state.temporal_gateway = None
    yield


app = FastAPI(title="ESG Qualitative Report Agents", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports/esg/qualitative/generate", deprecated=True)
def generate_qualitative(payload: CompanyInput) -> dict:
    try:
        artifacts = ESGQualitativeGraph().generate(payload)
    except OutputRunExistsError as exc:
        raise HTTPException(status_code=409, detail="output run already exists") from exc
    return model_to_dict(artifacts)


@app.post(
    "/reports/esg/qualitative/jobs",
    response_model=ReportJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_qualitative_job(
    payload: CompanyInput,
    request: Request,
) -> ReportJobAccepted:
    gateway = _temporal_gateway(request)
    try:
        return await gateway.submit(payload)
    except TemporalUnavailableError as exc:
        raise _temporal_unavailable() from exc


@app.get(
    "/reports/esg/qualitative/jobs/{job_id}",
    response_model=ReportJobStatus,
)
async def get_qualitative_job(
    job_id: str,
    request: Request,
) -> ReportJobStatus:
    gateway = _temporal_gateway(request)
    try:
        return await gateway.status(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ESG report job was not found") from exc
    except JobResultUnavailableError as exc:
        raise HTTPException(
            status_code=500,
            detail="ESG report result metadata is unavailable",
        ) from exc
    except TemporalUnavailableError as exc:
        raise _temporal_unavailable() from exc


@app.get(
    "/reports/esg/qualitative/jobs/{job_id}/result",
    response_model=RunArtifacts,
)
async def get_qualitative_job_result(
    job_id: str,
    request: Request,
) -> RunArtifacts:
    gateway = _temporal_gateway(request)
    try:
        return await gateway.result(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ESG report job was not found") from exc
    except JobNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ESG report job is not completed",
        ) from exc
    except JobResultUnavailableError as exc:
        raise HTTPException(
            status_code=500,
            detail="ESG report output is missing or invalid",
        ) from exc
    except TemporalUnavailableError as exc:
        raise _temporal_unavailable() from exc


@app.delete(
    "/reports/esg/qualitative/jobs/{job_id}",
    response_model=ReportJobCancellation,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_qualitative_job(
    job_id: str,
    request: Request,
) -> ReportJobCancellation:
    gateway = _temporal_gateway(request)
    try:
        return await gateway.cancel(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ESG report job was not found") from exc
    except TemporalUnavailableError as exc:
        raise _temporal_unavailable() from exc


def _temporal_gateway(request: Request) -> TemporalGateway:
    gateway = getattr(request.app.state, "temporal_gateway", None)
    if gateway is None:
        raise _temporal_unavailable()
    return gateway


def _temporal_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Temporal service is unavailable",
    )
