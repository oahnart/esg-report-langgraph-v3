from __future__ import annotations

import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _coerce(value: str, reference: Any) -> Any:
    if isinstance(reference, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    if isinstance(reference, set):
        return {item.strip().lower() for item in value.split(",") if item.strip()}
    return value


DEFAULT_CONFIG: dict[str, Any] = {
    "team_rag_base_url": "",
    "team_rag_qualitative_path": "/qualitative/evidence/v3",
    "team_rag_request_contract": "new",
    "team_rag_timeout_seconds": 30,
    "team_rag_top_k": 5,
    "team_rag_retry_top_k": 0,
    "team_rag_batch_size": 20,
    "team_rag_max_retries": 2,
    "team_rag_concurrency": 4,
    "template_dir": str(PROJECT_ROOT / "template_v1"),
    "skill_dir": str(PROJECT_ROOT / "skills"),
    "output_dir": str(PROJECT_ROOT / "data" / "outputs"),
    "cache_dir": str(PROJECT_ROOT / "data" / "cache"),
    "temporal_address": "localhost:7233",
    "temporal_namespace": "default",
    "temporal_task_queue": "esg-report",
    "temporal_api_key": "",
    "temporal_tls": False,
    "temporal_activity_timeout_seconds": 3600,
    "temporal_workflow_timeout_seconds": 7200,
    "temporal_heartbeat_timeout_seconds": 180,
    "temporal_activity_max_attempts": 2,
    "temporal_worker_max_concurrent_activities": 2,
    "quantitative_input_mode": "file",
    "quantitative_input_dir": str(PROJECT_ROOT / "data" / "inputs"),
    "quantitative_api_base_url": "",
    "quantitative_api_path": "/companies/{company_id}/{year}/quantitative",
    "quantitative_api_method": "GET",
    "quantitative_api_key": "",
    "quantitative_api_timeout_seconds": 30,
    "quantitative_output_enabled": False,
    "metric_qid_bridge_enabled": False,
    "output_timezone": "Asia/Bangkok",
    "llm_provider": "openai",
    "llm_api_key": "",
    "llm_base_url": None,
    "llm_user_agent": "Mozilla/5.0",
    "llm_timeout_seconds": 120,
    "llm_json_repair_retry": False,
    "llm_structured_failure_limit": 3,
    "writer_concurrency": 4,
    "revision_concurrency": 4,
    "quick_think_llm": "gpt-4.1-mini",
    "deep_think_llm": "gpt-4.1",
    "openai_reasoning_effort": None,
    "agent_mode": "auto",
    "max_revision_rounds": 2,
    "max_recur_limit": 100,
    "checkpoint_enabled": False,
    "output_language": "Korean",
    "accepted_answer_statuses": {
        "high_confidence",
        "medium_confidence",
        "sufficient",
        "confident",
    },
    "conditional_answer_statuses": {"thin_but_usable"},
    "rejected_semantic_labels": {"weak", "irrelevant", "no_match"},
    "semantic_qa_enabled": True,
    "semantic_qa_concurrency": 4,
    "semantic_qa_incremental": True,
    "source_policy_enabled": True,
    "output_hygiene_enabled": True,
}

_ENV_OVERRIDES = {
    "TEAM_RAG_BASE_URL": "team_rag_base_url",
    "TEAM_RAG_QUALITATIVE_PATH": "team_rag_qualitative_path",
    "TEAM_RAG_REQUEST_CONTRACT": "team_rag_request_contract",
    "TEAM_RAG_TIMEOUT_SECONDS": "team_rag_timeout_seconds",
    "TEAM_RAG_TOP_K": "team_rag_top_k",
    "ESG_TEAM_RAG_RETRY_TOP_K": "team_rag_retry_top_k",
    "TEAM_RAG_BATCH_SIZE": "team_rag_batch_size",
    "TEAM_RAG_MAX_RETRIES": "team_rag_max_retries",
    "TEAM_RAG_CONCURRENCY": "team_rag_concurrency",
    "ESG_TEMPLATE_DIR": "template_dir",
    "ESG_SKILL_DIR": "skill_dir",
    "ESG_OUTPUT_DIR": "output_dir",
    "ESG_CACHE_DIR": "cache_dir",
    "TEMPORAL_ADDRESS": "temporal_address",
    "TEMPORAL_NAMESPACE": "temporal_namespace",
    "TEMPORAL_TASK_QUEUE": "temporal_task_queue",
    "TEMPORAL_API_KEY": "temporal_api_key",
    "TEMPORAL_TLS": "temporal_tls",
    "TEMPORAL_ACTIVITY_TIMEOUT_SECONDS": "temporal_activity_timeout_seconds",
    "TEMPORAL_WORKFLOW_TIMEOUT_SECONDS": "temporal_workflow_timeout_seconds",
    "TEMPORAL_HEARTBEAT_TIMEOUT_SECONDS": "temporal_heartbeat_timeout_seconds",
    "TEMPORAL_ACTIVITY_MAX_ATTEMPTS": "temporal_activity_max_attempts",
    "TEMPORAL_WORKER_MAX_CONCURRENT_ACTIVITIES": "temporal_worker_max_concurrent_activities",
    "ESG_QUANTITATIVE_INPUT_MODE": "quantitative_input_mode",
    "ESG_QUANTITATIVE_INPUT_DIR": "quantitative_input_dir",
    "ESG_QUANTITATIVE_API_BASE_URL": "quantitative_api_base_url",
    "ESG_QUANTITATIVE_API_PATH": "quantitative_api_path",
    "ESG_QUANTITATIVE_API_METHOD": "quantitative_api_method",
    "ESG_QUANTITATIVE_API_KEY": "quantitative_api_key",
    "ESG_QUANTITATIVE_API_TIMEOUT_SECONDS": "quantitative_api_timeout_seconds",
    "ESG_QUANTITATIVE_OUTPUT_ENABLED": "quantitative_output_enabled",
    "ESG_METRIC_QID_BRIDGE_ENABLED": "metric_qid_bridge_enabled",
    "ESG_OUTPUT_TIMEZONE": "output_timezone",
    "ESG_LLM_PROVIDER": "llm_provider",
    "ESG_LLM_API_KEY": "llm_api_key",
    "ESG_LLM_BASE_URL": "llm_base_url",
    "ESG_LLM_USER_AGENT": "llm_user_agent",
    "ESG_LLM_TIMEOUT_SECONDS": "llm_timeout_seconds",
    "ESG_LLM_JSON_REPAIR_RETRY": "llm_json_repair_retry",
    "ESG_LLM_STRUCTURED_FAILURE_LIMIT": "llm_structured_failure_limit",
    "ESG_WRITER_CONCURRENCY": "writer_concurrency",
    "ESG_REVISION_CONCURRENCY": "revision_concurrency",
    "ESG_QUICK_THINK_LLM": "quick_think_llm",
    "ESG_DEEP_THINK_LLM": "deep_think_llm",
    "ESG_OPENAI_REASONING_EFFORT": "openai_reasoning_effort",
    "ESG_AGENT_MODE": "agent_mode",
    "ESG_MAX_REVISION_ROUNDS": "max_revision_rounds",
    "ESG_MAX_RECUR_LIMIT": "max_recur_limit",
    "ESG_CHECKPOINT_ENABLED": "checkpoint_enabled",
    "ESG_OUTPUT_LANGUAGE": "output_language",
    "ESG_ACCEPTED_ANSWER_STATUSES": "accepted_answer_statuses",
    "ESG_CONDITIONAL_ANSWER_STATUSES": "conditional_answer_statuses",
    "ESG_REJECTED_SEMANTIC_LABELS": "rejected_semantic_labels",
    "ESG_SEMANTIC_QA_ENABLED": "semantic_qa_enabled",
    "ESG_SEMANTIC_QA_CONCURRENCY": "semantic_qa_concurrency",
    "ESG_SEMANTIC_QA_INCREMENTAL": "semantic_qa_incremental",
    "ESG_SOURCE_POLICY_ENABLED": "source_policy_enabled",
    "ESG_OUTPUT_HYGIENE_ENABLED": "output_hygiene_enabled",
}


def load_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw not in (None, ""):
            config[key] = _coerce(raw, config.get(key))
    if overrides:
        config.update({k: v for k, v in overrides.items() if v is not None})
    return config
