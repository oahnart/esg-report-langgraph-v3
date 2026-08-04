from __future__ import annotations

from typing import Any

from esgagents.schemas import CompanyInput, NormalizedCompany
from esgagents.template_loader import TemplateRepository


class CompanyIntakeAgent:
    def __init__(self, config: dict[str, Any], templates: TemplateRepository):
        self.config = config
        self.templates = templates

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        company_input = state["company_input"]
        if not isinstance(company_input, CompanyInput):
            company_input = CompanyInput.model_validate(company_input)
        scale = self.templates.normalize_scale(company_input.scale)
        industry = self.templates.normalize_industry(company_input.industry)
        normalized = NormalizedCompany(
            company_id=company_input.company_id,
            company_name=company_input.company_name or company_input.company_id,
            year=company_input.year,
            scale=scale,
            industry=industry,
            top_k=company_input.top_k or int(self.config["team_rag_top_k"]),
            item_ids=company_input.item_ids,
            output_language=company_input.output_language or self.config["output_language"],
            run_id=company_input.resolved_run_id(),
        )
        return {"company": normalized}
