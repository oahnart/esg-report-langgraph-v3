from __future__ import annotations

from typing import Any

from esgagents.schemas import AgentProfileKey
from skills.agents.loader import SkillRegistry


CARBON_QIDS = {"Q029", "Q030", "Q031"}

KEYWORDS: dict[AgentProfileKey, tuple[str, ...]] = {
    "carbon": (
        "carbon footprint",
        "ghg",
        "scope 1",
        "scope 2",
        "scope 3",
        "tcfd",
        "net-zero",
        "net zero",
        "tco2",
        "greenhouse gas",
        "온실가스",
        "탄소",
    ),
    "materiality": (
        "materiality",
        "material topic",
        "double materiality",
        "stakeholder consultation",
        "prioritisation",
        "prioritization",
        "중대성",
        "중대",
        "이해관계자",
    ),
    "commitment": (
        "commitment",
        "pledge",
        "target date",
        "on track",
        "at risk",
        "behind target",
        "progress status",
        "science-based target",
        "sbti",
        "목표",
        "이행",
        "진척",
        "약속",
        "공약",
    ),
}


class SkillRouterAgent:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        selections: dict[str, dict[str, Any]] = {}
        agent_profiles: dict[str, AgentProfileKey] = {}
        for planned in state["planned_questions"]:
            text = self._selection_text(planned)
            key, reason = self.select(planned.id, text)
            spec = self.registry.get(key)
            if spec.key != key:
                reason = f"{reason}; skill_fallback_used"
            selections[planned.id] = {
                "skill_key": spec.key,
                "skill_name": spec.name,
                "skill_version": spec.version,
                "skill_source_path": spec.source_path,
                "skill_selection_reason": reason,
            }
            agent_profiles[planned.id] = spec.key
        return {"skill_selections": selections, "agent_profiles": agent_profiles}

    def select(self, qid: str, text: str) -> tuple[AgentProfileKey, str]:
        normalized = text.lower()
        if qid in CARBON_QIDS:
            return "carbon", f"qid={qid}"
        for key in ("materiality", "commitment", "carbon"):
            match = next((keyword for keyword in KEYWORDS[key] if keyword in normalized), "")
            if match:
                return key, f"keyword={match}"
        return "general_section", "default=general_section"

    def _selection_text(self, planned: Any) -> str:
        values = [
            planned.id,
            planned.source_id,
            planned.area_ko,
            planned.category_ko,
            planned.pillar,
            planned.item_ko,
            planned.description_ko,
            planned.example_ko,
            " ".join(planned.material_topics or []),
        ]
        return " ".join(str(value) for value in values if value)
