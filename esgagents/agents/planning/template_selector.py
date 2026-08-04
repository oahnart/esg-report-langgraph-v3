from __future__ import annotations

from typing import Any

from esgagents.schemas import NormalizedCompany
from esgagents.template_loader import TemplateRepository


class TemplateSelectorAgent:
    def __init__(self, templates: TemplateRepository):
        self.templates = templates

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        company: NormalizedCompany = state["company"]
        questions = self.templates.load_questions()
        scale = self.templates.load_scales()[company.scale]
        industry = self.templates.load_industries()[company.industry]
        selected_ids = company.item_ids or [q["id"] for q in questions]
        question_by_id = {q["id"]: q for q in questions}
        missing = [qid for qid in selected_ids if qid not in question_by_id]
        if missing:
            raise ValueError(f"unknown question ids: {', '.join(missing)}")
        selected = [question_by_id[qid] for qid in selected_ids]
        return {
            "questions": selected,
            "scale_template": scale,
            "industry_template": industry,
            "template_selection": {
                "template_version": "template_v1",
                "scale": company.scale,
                "industry": company.industry,
                "question_count": len(selected),
            },
        }
