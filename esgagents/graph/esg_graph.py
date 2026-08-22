from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable

from esgagents.agents import ESGAgents
from esgagents.default_config import load_config
from esgagents.output_writer import OutputWriter
from esgagents.progress import ProgressReporter, safe_error_detail
from esgagents.provenance import verify_runtime_provenance
from esgagents.rag_client import TeamRagClient
from esgagents.schemas import CompanyInput, RunArtifacts
from esgagents.template_loader import TemplateRepository

from .checkpointer import get_checkpointer, thread_id
from .conditional_logic import ESGConditionalLogic
from .propagation import ESGPropagator
from .setup import ESGGraphSetup
from .state import ESGState


logger = logging.getLogger(__name__)


class ESGQualitativeGraph:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        rag_client: TeamRagClient | None = None,
        output_writer: OutputWriter | None = None,
        progress_observer: Callable[[str, str], None] | None = None,
        progress_reporter: ProgressReporter | None = None,
    ):
        self.config = load_config(config)
        self.progress_reporter = progress_reporter or ProgressReporter.from_legacy(
            progress_observer
        )
        self.templates = TemplateRepository(self.config["template_dir"])
        self.rag_client = rag_client or TeamRagClient(
            self.config["team_rag_base_url"],
            qualitative_path=self.config["team_rag_qualitative_path"],
            timeout_seconds=self.config["team_rag_timeout_seconds"],
            max_retries=self.config["team_rag_max_retries"],
            request_contract=self.config["team_rag_request_contract"],
            progress_reporter=self.progress_reporter,
        )
        if rag_client is not None and hasattr(self.rag_client, "set_progress_reporter"):
            self.rag_client.set_progress_reporter(self.progress_reporter)
        self.output_writer = output_writer or OutputWriter(
            self.config["output_dir"],
            output_timezone=self.config["output_timezone"],
        )
        self.agents = ESGAgents(
            self.config,
            self.templates,
            self.rag_client,
            progress_reporter=self.progress_reporter,
        )
        self.conditional_logic = ESGConditionalLogic(self.config.get("max_revision_rounds", 1))
        self.progress_observer = progress_observer
        self.graph_setup = ESGGraphSetup(
            self.agents,
            self.conditional_logic,
            progress_observer=progress_observer,
            progress_reporter=self.progress_reporter,
        )
        self.propagator = ESGPropagator(self.config.get("max_recur_limit", 100))
        self.workflow = self.graph_setup.setup_graph()
        self.graph = self.workflow.compile()

    def generate(
        self,
        company_input: CompanyInput | dict[str, Any],
        write_outputs: bool = True,
        retry_outputs: bool = False,
    ) -> RunArtifacts:
        verify_runtime_provenance()
        parsed = company_input if isinstance(company_input, CompanyInput) else CompanyInput.model_validate(company_input)
        workflow_token = self.progress_reporter.start(
            "WORKFLOW",
            "Generate qualitative report",
            verbosity="steps",
            details={
                "company_id": parsed.company_id,
                "year": parsed.year,
                "scale": parsed.scale,
                "industry": parsed.industry,
            },
        )
        try:
            initial_state: ESGState = self.propagator.create_initial_state(parsed)
            if self.config.get("checkpoint_enabled"):
                run_id = parsed.resolved_run_id()
                parsed.run_id = run_id
                with get_checkpointer(self.config["cache_dir"], parsed.company_id) as saver:
                    graph = self.workflow.compile(checkpointer=saver)
                    final_state = graph.invoke(
                        initial_state,
                        **self.propagator.graph_config(thread_id(parsed.company_id, parsed.year, run_id)),
                    )
            else:
                final_state = self.graph.invoke(initial_state, **self.propagator.graph_config())
            artifacts: RunArtifacts = final_state["artifacts"]
            if write_outputs:
                write_started = perf_counter()
                write_token = self.progress_reporter.start(
                    "STEP",
                    "Write Report Output",
                    verbosity="steps",
                )
                try:
                    artifacts = self.output_writer.write(
                        artifacts,
                        retry_existing=retry_outputs,
                    )
                except BaseException as exc:
                    self.progress_reporter.finish(
                        write_token,
                        status="failed",
                        details={
                            "error_type": type(exc).__name__,
                            "error": safe_error_detail(exc),
                        },
                    )
                    raise
                self.progress_reporter.finish(
                    write_token,
                    details={"outputs": len(artifacts.output_paths)},
                )
                logger.info(
                    "graph_node node=%r status=completed elapsed_ms=%s",
                    "Write Report Output",
                    round((perf_counter() - write_started) * 1000),
                )
            self.progress_reporter.finish(
                workflow_token,
                details={
                    "questions": len(artifacts.answers),
                    "rag_http_attempts": self.progress_reporter.count(
                        "RAG API", "started"
                    ),
                    "rag_retries": self.progress_reporter.count("RAG API", "retry"),
                    "rag_batches": len(artifacts.rag_request_traces),
                    "curator_llm_calls": self.progress_reporter.count(
                        "CURATOR", "started"
                    ),
                    "writer_llm_calls": self.progress_reporter.count(
                        "WRITER", "started"
                    ),
                    "semantic_llm_calls": self.progress_reporter.count(
                        "SEMANTIC", "started"
                    ),
                    "revisions": self.progress_reporter.count(
                        "REVISION", "started"
                    ),
                    "fallbacks": sum(
                        self.progress_reporter.count(category, "fallback")
                        for category in ("CURATOR", "WRITER", "SEMANTIC", "REVISION")
                    ),
                    "stats": artifacts.stats,
                },
            )
            return artifacts
        except BaseException as exc:
            self.progress_reporter.finish(
                workflow_token,
                status="failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": safe_error_detail(exc),
                },
            )
            raise
