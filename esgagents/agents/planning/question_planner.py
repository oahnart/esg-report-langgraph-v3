from __future__ import annotations

from typing import Any

from esgagents.schemas import PlannedQuestion


class QuestionPlannerAgent:
    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        scale = state["scale_template"]
        industry = state["industry_template"]
        planned = []
        for question in state["questions"]:
            planned.append(
                PlannedQuestion(
                    **question,
                    material_topics=list(industry.get("material_topics", [])),
                    scale_guidance={
                        "company_profile": scale.get("company_profile", {}),
                        "answer_guidance": scale.get("answer_guidance", {}),
                        "question_adaptation_rules": scale.get("question_adaptation_rules", []),
                    },
                    industry_guidance={
                        "material_topics": industry.get("material_topics", []),
                        "metric_focus": industry.get("metric_focus", []),
                        "risk_lens": industry.get("risk_lens", ""),
                        "answer_guidance": industry.get("answer_guidance", ""),
                    },
                )
            )
        return {"planned_questions": planned}
