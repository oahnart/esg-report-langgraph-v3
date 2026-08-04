import json
import asyncio

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from esgagents.provenance import (
    ProvenanceError,
    compute_source_digest,
    verify_runtime_provenance,
    write_build_provenance,
)


def _source_tree(root, *, reverse=False):
    entries = [
        ("esgagents/module.py", "VALUE = 1\n"),
        ("skills/writer.md", "writer prompt\n"),
        ("template_v1/template.txt", "template\n"),
        ("pyproject.toml", "[project]\nname='test'\n"),
    ]
    for relative, content in reversed(entries) if reverse else entries:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_source_digest_is_deterministic_and_ignores_cache(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _source_tree(first)
    _source_tree(second, reverse=True)

    initial = compute_source_digest(first)
    assert initial == compute_source_digest(second)

    cache = first / "esgagents" / "__pycache__" / "module.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"ignored")
    assert compute_source_digest(first) == initial

    (first / "esgagents" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert compute_source_digest(first) != initial


def test_strict_provenance_passes_for_matching_source(tmp_path):
    _source_tree(tmp_path)
    build_file = tmp_path / "build.json"
    built = write_build_provenance(tmp_path, build_file, git_sha="abc123")

    record = verify_runtime_provenance(
        {
            "ESG_PROVENANCE_MODE": "strict",
            "ESG_PROVENANCE_BUILD_FILE": str(build_file),
            "ESG_PROVENANCE_SOURCE_ROOT": str(tmp_path),
        }
    )

    assert record["verified"] is True
    assert record["source_digest"] == built["source_digest"]
    assert record["runtime_source_digest"] == built["source_digest"]
    assert record["git_sha"] == "abc123"


def test_strict_provenance_rejects_stale_or_missing_expected_source(tmp_path):
    _source_tree(tmp_path)
    build_file = tmp_path / "build.json"
    write_build_provenance(tmp_path, build_file)
    (tmp_path / "skills" / "writer.md").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ProvenanceError, match="docker compose up --build"):
        verify_runtime_provenance(
            {
                "ESG_PROVENANCE_MODE": "strict",
                "ESG_PROVENANCE_BUILD_FILE": str(build_file),
                "ESG_PROVENANCE_SOURCE_ROOT": str(tmp_path),
            }
        )

    with pytest.raises(ProvenanceError, match="requires ESG_EXPECTED_SOURCE_DIGEST"):
        verify_runtime_provenance(
            {
                "ESG_PROVENANCE_MODE": "strict",
                "ESG_PROVENANCE_BUILD_FILE": str(build_file),
            }
        )


def test_expected_digest_supports_production_without_source_mount(tmp_path):
    _source_tree(tmp_path)
    build_file = tmp_path / "build.json"
    built = write_build_provenance(tmp_path, build_file)

    record = verify_runtime_provenance(
        {
            "ESG_PROVENANCE_MODE": "strict",
            "ESG_PROVENANCE_BUILD_FILE": str(build_file),
            "ESG_EXPECTED_SOURCE_DIGEST": built["source_digest"],
        }
    )

    assert record["verified"] is True
    assert record["runtime_source_digest"] == ""


def test_off_mode_never_requires_build_metadata(tmp_path):
    malformed = tmp_path / "bad.json"
    malformed.write_text(json.dumps([]), encoding="utf-8")

    record = verify_runtime_provenance(
        {
            "ESG_PROVENANCE_MODE": "off",
            "ESG_PROVENANCE_BUILD_FILE": str(malformed),
        }
    )

    assert record["mode"] == "off"
    assert record["verified"] is False


def test_api_checks_provenance_before_temporal_initialization(monkeypatch):
    import esgagents.api.app as app_module

    temporal_called = False

    def reject():
        raise ProvenanceError("stale image")

    async def temporal_client(*args, **kwargs):
        nonlocal temporal_called
        temporal_called = True

    monkeypatch.setattr(app_module, "verify_runtime_provenance", reject)
    monkeypatch.setattr(app_module, "create_temporal_client", temporal_client)

    with pytest.raises(ProvenanceError, match="stale image"):
        with TestClient(app_module.app):
            pass
    assert temporal_called is False


def test_worker_checks_provenance_before_loading_config(monkeypatch):
    import esgagents.temporal.worker as worker_module

    config_called = False

    def reject():
        raise ProvenanceError("stale image")

    def load_config():
        nonlocal config_called
        config_called = True
        return {}

    monkeypatch.setattr(worker_module, "verify_runtime_provenance", reject)
    monkeypatch.setattr(worker_module, "load_config", load_config)

    with pytest.raises(ProvenanceError, match="stale image"):
        asyncio.run(worker_module.run_worker())
    assert config_called is False


def test_cli_returns_exit_two_when_provenance_fails(monkeypatch):
    import esgagents.cli as cli_module

    def reject():
        raise ProvenanceError("stale image")

    monkeypatch.setattr(cli_module, "verify_runtime_provenance", reject)
    result = CliRunner().invoke(
        cli_module.app,
        [
            "generate-qualitative",
            "--company-id",
            "company",
            "--year",
            "2025",
            "--scale",
            "large",
            "--industry",
            "TC",
        ],
    )

    assert result.exit_code == 2
    assert "stale image" in result.output


def test_graph_generate_has_defense_in_depth_gate(monkeypatch):
    import esgagents.graph.esg_graph as graph_module

    def reject():
        raise ProvenanceError("stale image")

    monkeypatch.setattr(graph_module, "verify_runtime_provenance", reject)
    graph = object.__new__(graph_module.ESGQualitativeGraph)

    with pytest.raises(ProvenanceError, match="stale image"):
        graph.generate({})
