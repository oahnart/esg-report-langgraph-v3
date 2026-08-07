from fastapi.testclient import TestClient
from typer.testing import CliRunner

from esgagents.api.app import app as fastapi_app
from esgagents.cli import app as cli_app
from esgagents.output_writer import OutputRunExistsError


def test_cli_exposes_generate_qualitative_subcommand():
    result = CliRunner().invoke(cli_app, ["--help"])

    assert result.exit_code == 0
    assert "generate-qualitative" in result.output


def test_fastapi_exposes_generate_endpoint():
    paths = {route.path for route in fastapi_app.routes}

    assert "/health" in paths
    assert "/reports/esg/qualitative/generate" in paths


def _valid_payload():
    return {
        "company_id": "company_1",
        "company_name": "Company",
        "year": 2025,
        "scale": "large",
        "industry": "TC",
        "item_ids": ["Q001"],
        "run_id": "run_1",
    }


def test_fastapi_rejects_unsafe_company_and_run_identifiers():
    client = TestClient(fastapi_app)
    for field in ("company_id", "run_id"):
        payload = _valid_payload()
        payload[field] = "../escape"

        response = client.post("/reports/esg/qualitative/generate", json=payload)

        assert response.status_code == 422


def test_fastapi_maps_existing_output_to_409(monkeypatch):
    class ConflictGraph:
        def generate(self, payload):
            raise OutputRunExistsError("output run already exists")

    monkeypatch.setattr("esgagents.api.app.ESGQualitativeGraph", ConflictGraph)
    response = TestClient(fastapi_app).post(
        "/reports/esg/qualitative/generate", json=_valid_payload()
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "output run already exists"}


def test_cli_maps_existing_output_to_exit_code_one(monkeypatch):
    class ConflictGraph:
        def __init__(self, *args, **kwargs):
            pass

        def generate(self, payload):
            raise OutputRunExistsError("output run already exists")

    monkeypatch.setattr("esgagents.cli.ESGQualitativeGraph", ConflictGraph)
    result = CliRunner().invoke(
        cli_app,
        [
            "generate-qualitative",
            "--company-id",
            "company_1",
            "--year",
            "2025",
            "--scale",
            "large",
            "--industry",
            "TC",
            "--run-id",
            "run_1",
        ],
    )

    assert result.exit_code == 1
    assert "output run already exists" in result.output
