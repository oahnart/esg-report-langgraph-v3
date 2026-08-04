from __future__ import annotations

import json
from typing import Optional

import typer

from esgagents.graph.esg_graph import ESGQualitativeGraph
from esgagents.output_writer import OutputRunExistsError
from esgagents.provenance import ProvenanceError, verify_runtime_provenance
from esgagents.schemas import CompanyInput, model_to_dict

app = typer.Typer(help="ESG qualitative report generator")


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
        artifacts = ESGQualitativeGraph().generate(input_payload)
    except OutputRunExistsError:
        typer.echo("Error: output run already exists", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(model_to_dict(artifacts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
