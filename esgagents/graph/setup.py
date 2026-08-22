from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from esgagents.agents import ESGAgents

from .conditional_logic import ESGConditionalLogic
from .node_names import ESGGraphNodes
from .state import ESGState


logger = logging.getLogger(__name__)


class ESGGraphSetup:
    def __init__(
        self,
        agents: ESGAgents,
        conditional_logic: ESGConditionalLogic,
        progress_observer: Callable[[str, str], None] | None = None,
    ):
        self.agents = agents
        self.conditional_logic = conditional_logic
        self.progress_observer = progress_observer

    def setup_graph(self) -> StateGraph:
        workflow = StateGraph(ESGState)
        workflow.add_node(
            ESGGraphNodes.COMPANY_INTAKE,
            self._observe(ESGGraphNodes.COMPANY_INTAKE, self.agents.company_intake),
        )
        workflow.add_node(
            ESGGraphNodes.TEMPLATE_SELECTION,
            self._observe(ESGGraphNodes.TEMPLATE_SELECTION, self.agents.template_selector),
        )
        workflow.add_node(
            ESGGraphNodes.QUESTION_PLANNING,
            self._observe(ESGGraphNodes.QUESTION_PLANNING, self.agents.question_planner),
        )
        workflow.add_node(
            ESGGraphNodes.RAG_EVIDENCE_RETRIEVAL,
            self._observe(ESGGraphNodes.RAG_EVIDENCE_RETRIEVAL, self.agents.rag_batch),
        )
        workflow.add_node(
            ESGGraphNodes.EVIDENCE_ELIGIBILITY,
            self._observe(ESGGraphNodes.EVIDENCE_ELIGIBILITY, self.agents.evidence_gate),
        )
        workflow.add_node(
            ESGGraphNodes.EVIDENCE_NORMALIZATION,
            self._observe(ESGGraphNodes.EVIDENCE_NORMALIZATION, self.agents.evidence_normalizer),
        )
        workflow.add_node(
            ESGGraphNodes.QUANTITATIVE_PROCESSING,
            self._observe(
                ESGGraphNodes.QUANTITATIVE_PROCESSING,
                self.agents.quantitative_processing,
            ),
        )
        workflow.add_node(
            ESGGraphNodes.SKILL_SELECTION,
            self._observe(ESGGraphNodes.SKILL_SELECTION, self.agents.skill_router),
        )
        workflow.add_node(
            ESGGraphNodes.EVIDENCE_CURATION,
            self._observe(ESGGraphNodes.EVIDENCE_CURATION, self.agents.evidence_curator),
        )
        workflow.add_node(
            ESGGraphNodes.SKILL_CONTEXT,
            self._observe(ESGGraphNodes.SKILL_CONTEXT, self.agents.skill_context_builder),
        )
        workflow.add_node(
            ESGGraphNodes.ANSWER_DRAFTING,
            self._observe(ESGGraphNodes.ANSWER_DRAFTING, self.agents.skill_writer),
        )
        workflow.add_node(
            ESGGraphNodes.DRAFT_REVIEW,
            self._observe(ESGGraphNodes.DRAFT_REVIEW, self.agents.skill_policy_critic),
        )
        workflow.add_node(
            ESGGraphNodes.SEMANTIC_REVIEW,
            self._observe(ESGGraphNodes.SEMANTIC_REVIEW, self.agents.semantic_critic),
        )
        workflow.add_node(
            ESGGraphNodes.ANSWER_REVISION,
            self._observe(ESGGraphNodes.ANSWER_REVISION, self.agents.revision),
        )
        workflow.add_node(
            ESGGraphNodes.OUTPUT_HYGIENE,
            self._observe(ESGGraphNodes.OUTPUT_HYGIENE, self.agents.output_hygiene),
        )
        workflow.add_node(
            ESGGraphNodes.REPORT_ASSEMBLY,
            self._observe(ESGGraphNodes.REPORT_ASSEMBLY, self.agents.report_manager),
        )

        workflow.add_edge(START, ESGGraphNodes.COMPANY_INTAKE)
        workflow.add_edge(ESGGraphNodes.COMPANY_INTAKE, ESGGraphNodes.TEMPLATE_SELECTION)
        workflow.add_edge(ESGGraphNodes.TEMPLATE_SELECTION, ESGGraphNodes.QUESTION_PLANNING)
        workflow.add_edge(ESGGraphNodes.QUESTION_PLANNING, ESGGraphNodes.RAG_EVIDENCE_RETRIEVAL)
        workflow.add_edge(ESGGraphNodes.RAG_EVIDENCE_RETRIEVAL, ESGGraphNodes.EVIDENCE_ELIGIBILITY)
        workflow.add_edge(ESGGraphNodes.EVIDENCE_ELIGIBILITY, ESGGraphNodes.EVIDENCE_NORMALIZATION)
        workflow.add_edge(
            ESGGraphNodes.EVIDENCE_NORMALIZATION,
            ESGGraphNodes.QUANTITATIVE_PROCESSING,
        )
        workflow.add_edge(ESGGraphNodes.QUANTITATIVE_PROCESSING, ESGGraphNodes.SKILL_SELECTION)
        workflow.add_edge(ESGGraphNodes.SKILL_SELECTION, ESGGraphNodes.EVIDENCE_CURATION)
        workflow.add_edge(ESGGraphNodes.EVIDENCE_CURATION, ESGGraphNodes.SKILL_CONTEXT)
        workflow.add_edge(ESGGraphNodes.SKILL_CONTEXT, ESGGraphNodes.ANSWER_DRAFTING)
        workflow.add_edge(ESGGraphNodes.ANSWER_DRAFTING, ESGGraphNodes.DRAFT_REVIEW)
        workflow.add_edge(ESGGraphNodes.DRAFT_REVIEW, ESGGraphNodes.SEMANTIC_REVIEW)
        workflow.add_conditional_edges(
            ESGGraphNodes.SEMANTIC_REVIEW,
            self.conditional_logic.should_continue_after_critic,
            {
                ESGGraphNodes.ANSWER_REVISION: ESGGraphNodes.ANSWER_REVISION,
                ESGGraphNodes.OUTPUT_HYGIENE: ESGGraphNodes.OUTPUT_HYGIENE,
            },
        )
        workflow.add_edge(ESGGraphNodes.ANSWER_REVISION, ESGGraphNodes.DRAFT_REVIEW)
        workflow.add_edge(ESGGraphNodes.OUTPUT_HYGIENE, ESGGraphNodes.REPORT_ASSEMBLY)
        workflow.add_edge(ESGGraphNodes.REPORT_ASSEMBLY, END)
        return workflow

    def _observe(self, node_name: str, node: Callable[[Any], Any]) -> Callable[[Any], Any]:
        def observed(state: Any) -> Any:
            started = perf_counter()
            if self.progress_observer:
                self.progress_observer(node_name, "started")
            try:
                result = node(state)
            except BaseException:
                logger.exception(
                    "graph_node node=%r status=failed elapsed_ms=%s",
                    node_name,
                    round((perf_counter() - started) * 1000),
                )
                if self.progress_observer:
                    self.progress_observer(node_name, "failed")
                raise
            logger.info(
                "graph_node node=%r status=completed elapsed_ms=%s",
                node_name,
                round((perf_counter() - started) * 1000),
            )
            if self.progress_observer:
                self.progress_observer(node_name, "completed")
            return result

        return observed
