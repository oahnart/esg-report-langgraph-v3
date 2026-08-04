from __future__ import annotations

from typing import Any

from esgagents.schemas import CompanyInput

from .state import ESGState


class ESGPropagator:
    def __init__(self, max_recur_limit: int = 100):
        self.max_recur_limit = max(10, int(max_recur_limit))

    def create_initial_state(self, company_input: CompanyInput) -> ESGState:
        return {
            "company_input": company_input,
            "quality_flags": {},
            "revision_counts": {},
        }

    def graph_config(self, thread_id_value: str | None = None) -> dict[str, Any]:
        config: dict[str, Any] = {"recursion_limit": self.max_recur_limit}
        if thread_id_value:
            config["configurable"] = {"thread_id": thread_id_value}
        return {"config": config}
