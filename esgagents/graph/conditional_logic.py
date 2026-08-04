from __future__ import annotations

from typing import Any

from esgagents.agents.answering.revision_selection import eligible_revision_qids

from .node_names import ESGGraphNodes


class ESGConditionalLogic:
    def __init__(self, max_revision_rounds: int = 1):
        self.max_revision_rounds = max(0, int(max_revision_rounds))

    def should_continue_after_critic(self, state: dict[str, Any]) -> str:
        if eligible_revision_qids(state, self.max_revision_rounds):
            return ESGGraphNodes.ANSWER_REVISION
        return ESGGraphNodes.OUTPUT_HYGIENE
