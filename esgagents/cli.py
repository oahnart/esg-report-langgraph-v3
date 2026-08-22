from __future__ import annotations

from enum import Enum
from typing import Optional

import typer

from esgagents.graph.esg_graph import ESGQualitativeGraph
from esgagents.output_writer import OutputRunExistsError
from esgagents.provenance import ProvenanceError, verify_runtime_provenance
from esgagents.progress import ProgressEvent, ProgressReporter, format_progress_event
from esgagents.schemas import CompanyInput

app = typer.Typer(help="ESG qualitative report generator")


class ProgressLevelOption(str, Enum):
    full = "full"
    steps = "steps"
    quiet = "quiet"


def _progress_sink(event: ProgressEvent) -> None:
    typer.echo(format_progress_event(event), err=True)


@app.callback()
def main():
    """Run ESG qualitative report workflows."""


@app.command("generate-qualitative")
def generate_qualitative(
    company_id: str = typer.Option(...),
    company_name: str = typer.Option(""),
    year: int = typer.Option(...),
    scale: str = typer.Option(...),
    industry: str = typer.Option(...),
    top_k: Optional[int] = typer.Option(None),
    item_ids: Optional[str] = typer.Option(None, help="Comma-separated QIDs, e.g. Q001,Q002"),
    output_language: str = typer.Option("Korean"),
    run_id: Optional[str] = typer.Option(None),
    progress_level: ProgressLevelOption = typer.Option(
        ProgressLevelOption.full,
        help="Progress detail: full, steps, or quiet.",
    ),
):
    try:
        verify_runtime_provenance()
    except ProvenanceError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    input_payload = CompanyInput(
        company_id=company_id,
        company_name=company_name,
        year=year,
        scale=scale,
        industry=industry,
        top_k=top_k,
        item_ids=[item.strip() for item in item_ids.split(",") if item.strip()] if item_ids else None,
        output_language=output_language,
        run_id=run_id,
    )
    try:
        progress_reporter = ProgressReporter(
            _progress_sink,
            level=progress_level.value,
        )
        ESGQualitativeGraph(
            progress_reporter=progress_reporter
        ).generate(input_payload)
    except OutputRunExistsError:
        typer.echo("Error: output run already exists", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
