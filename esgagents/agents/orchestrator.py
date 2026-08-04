from __future__ import annotations

from typing import Any

from esgagents.agents.answering.revision import RevisionAgent
from esgagents.agents.answering.output_hygiene import OutputHygieneAgent
from esgagents.agents.answering.semantic_critic import SemanticCompletenessCriticAgent
from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent
from esgagents.agents.evidence.evidence_normalizer import EvidenceNormalizerAgent
from esgagents.agents.intake.company_intake import CompanyIntakeAgent
from esgagents.agents.managers.report_manager import ReportManagerAgent
from esgagents.agents.planning.question_planner import QuestionPlannerAgent
from esgagents.agents.planning.template_selector import TemplateSelectorAgent
from esgagents.agents.retrieval.rag_batch import RagBatchAgent
from skills.agents import (
    SkillContextBuilderAgent,
    SkillPolicyCriticAgent,
    SkillRegistry,
    SkillRouterAgent,
    SkillWriterAgent,
)
from esgagents.llm_clients import create_llm_pair
from esgagents.quantitative import QuantitativeAgent
from esgagents.rag_client import TeamRagClient
from esgagents.template_loader import TemplateRepository


class ESGAgents:
    """Facade that exposes graph node callables while keeping agents modular."""

    def __init__(
        self,
        config: dict[str, Any],
        templates: TemplateRepository,
        rag_client: TeamRagClient,
    ):
        self.config = config
        self.templates = templates
        self.rag_client = rag_client
        self.quick_llm, self.deep_llm = create_llm_pair(config)

        self.company_intake_agent = CompanyIntakeAgent(config, templates)
        self.template_selector_agent = TemplateSelectorAgent(templates)
        self.question_planner_agent = QuestionPlannerAgent()
        self.rag_batch_agent = RagBatchAgent(config, rag_client)
        self.evidence_gate_agent = EvidenceGateAgent(config)
        self.evidence_normalizer_agent = EvidenceNormalizerAgent(config)
        self.quantitative_agent = QuantitativeAgent(config, templates)
        self.skill_registry = SkillRegistry(config["skill_dir"])
        self.skill_router_agent = SkillRouterAgent(self.skill_registry)
        self.skill_context_builder_agent = SkillContextBuilderAgent(self.skill_registry)
        self.skill_writer_agent = SkillWriterAgent(config, self.quick_llm)
        self.skill_policy_critic_agent = SkillPolicyCriticAgent()
        self.semantic_critic_agent = SemanticCompletenessCriticAgent(config, self.quick_llm)
        self.revision_agent = RevisionAgent(config, self.deep_llm)
        self.output_hygiene_agent = OutputHygieneAgent(config)
        self.report_manager_agent = ReportManagerAgent(config)

    def company_intake(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.company_intake_agent.run(state)

    def template_selector(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.template_selector_agent.run(state)

    def question_planner(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.question_planner_agent.run(state)

    def rag_batch(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.rag_batch_agent.run(state)

    def evidence_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.evidence_gate_agent.run(state)

    def evidence_normalizer(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.evidence_normalizer_agent.run(state)

    def quantitative_processing(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.quantitative_agent.run(state)

    def skill_router(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.skill_router_agent.run(state)

    def skill_context_builder(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.skill_context_builder_agent.run(state)

    def skill_writer(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.skill_writer_agent.run(state)

    def skill_policy_critic(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.skill_policy_critic_agent.run(state)

    def revision(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.revision_agent.run(state)

    def semantic_critic(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.semantic_critic_agent.run(state)

    def output_hygiene(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.output_hygiene_agent.run(state)

    def report_manager(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.report_manager_agent.run(state)
