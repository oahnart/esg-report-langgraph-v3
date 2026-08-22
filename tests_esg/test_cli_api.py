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


def test_cli_full_progress_is_default_and_quiet_can_suppress_it(monkeypatch):
    class ProgressGraph:
        def __init__(self, *args, progress_reporter=None, **kwargs):
            self.progress_reporter = progress_reporter

        def generate(self, payload):
            token = self.progress_reporter.start(
                "CURATOR",
                "Q001",
                current=1,
                total=1,
            )
            self.progress_reporter.finish(
                token,
                details={"kept": 2, "answerability": "SUFFICIENT"},
            )
            raise OutputRunExistsError("output run already exists")

    monkeypatch.setattr("esgagents.cli.ESGQualitativeGraph", ProgressGraph)
    base_args = [
        "generate-qualitative",
        "--company-id",
        "company_1",
        "--year",
        "2025",
        "--scale",
        "large",
        "--industry",
        "TC",
    ]

    detailed = CliRunner().invoke(cli_app, base_args)
    quiet = CliRunner().invoke(cli_app, [*base_args, "--progress-level", "quiet"])

    assert detailed.exit_code == 1
    assert "CURATOR START Q001 question=1/1" in detailed.output
    assert "CURATOR DONE Q001 question=1/1" in detailed.output
    assert "duration=" in detailed.output
    assert "CURATOR" not in quiet.output


def test_cli_success_does_not_dump_run_artifacts_to_terminal(monkeypatch):
    class SuccessfulGraph:
        def __init__(self, *args, **kwargs):
            pass

        def generate(self, payload):
            return {
                "run_id": "run_1",
                "answers": ["large qualitative payload must stay in the output file"],
                "output_paths": {"json": "data/outputs/qualitative_run.json"},
            }

    monkeypatch.setattr("esgagents.cli.ESGQualitativeGraph", SuccessfulGraph)
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
            "--progress-level",
            "quiet",
        ],
    )

    assert result.exit_code == 0
    assert result.output == ""
