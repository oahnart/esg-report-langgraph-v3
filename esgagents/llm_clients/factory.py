from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {"openai", "hallmdr"}
HALLMDR_DEFAULT_BASE_URL = "https://api.hallmdr.com"


def _agent_mode(config: dict[str, Any]) -> str:
    return str(config.get("agent_mode") or "auto").strip().lower()


def _api_key(config: dict[str, Any], provider: str) -> str:
    generic_key = str(config.get("llm_api_key") or os.environ.get("ESG_LLM_API_KEY") or "").strip()
    if generic_key:
        return generic_key
    if provider == "hallmdr":
        return str(os.environ.get("HALLMDR_API_KEY") or "").strip()
    return str(os.environ.get("OPENAI_API_KEY") or "").strip()


def _hallmdr_base_url(config: dict[str, Any]) -> str:
    base_url = str(
        config.get("llm_base_url")
        or os.environ.get("HALLMDR_API_BASE_URL")
        or HALLMDR_DEFAULT_BASE_URL
    ).rstrip("/")
    if not base_url.lower().endswith("/v1"):
        base_url += "/v1"
    return base_url


def create_llm_client(config: dict[str, Any], model_key: str = "quick_think_llm") -> Any | None:
    """Create an OpenAI-compatible LangChain chat model when runtime config allows it.

    In ``auto`` mode this returns ``None`` when dependencies or credentials are
    unavailable, allowing the ESG graph to use deterministic offline fallback.
    In ``llm`` mode those same conditions raise clear runtime errors.
    """
    mode = _agent_mode(config)
    if mode == "offline":
        return None
    if mode not in {"auto", "llm"}:
        raise ValueError("ESG_AGENT_MODE must be one of: auto, llm, offline")

    provider = str(config.get("llm_provider") or "openai").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        if mode == "llm":
            raise ValueError("ESG_LLM_PROVIDER must be one of: hallmdr, openai")
        logger.warning("Unsupported ESG LLM provider %s; using offline fallback", provider)
        return None

    api_key = _api_key(config, provider)
    if not api_key:
        if mode == "llm":
            expected_key = (
                "ESG_LLM_API_KEY or HALLMDR_API_KEY"
                if provider == "hallmdr"
                else "ESG_LLM_API_KEY or OPENAI_API_KEY"
            )
            raise RuntimeError(f"{expected_key} is required when ESG_AGENT_MODE=llm")
        logger.warning("No API key configured for %s; using offline fallback", provider)
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        if mode == "llm":
            raise RuntimeError("langchain-openai is required for ESG_AGENT_MODE=llm") from exc
        logger.warning("langchain-openai is not installed; using offline fallback")
        return None

    kwargs: dict[str, Any] = {
        "model": config.get(model_key) or config.get("quick_think_llm") or "gpt-4.1-mini",
        "temperature": 0,
        "timeout": config.get("llm_timeout_seconds", 120),
        "api_key": api_key,
        "metadata": {
            "esg_llm_provider": provider,
            "esg_json_repair_retry": bool(
                config.get("llm_json_repair_retry", False)
            ),
            "esg_structured_failure_limit": max(
                0,
                int(config.get("llm_structured_failure_limit", 3) or 0),
            ),
        },
    }
    if provider == "hallmdr":
        kwargs["base_url"] = _hallmdr_base_url(config)
        kwargs["default_headers"] = {
            "User-Agent": str(config.get("llm_user_agent") or "Mozilla/5.0")
        }
    elif config.get("llm_base_url"):
        kwargs["base_url"] = config["llm_base_url"]
    if provider == "openai" and config.get("openai_reasoning_effort"):
        kwargs["model_kwargs"] = {"reasoning_effort": config["openai_reasoning_effort"]}
    logger.info(
        "Creating %s LLM client model=%s base_url=%s",
        provider,
        kwargs["model"],
        kwargs.get("base_url", "provider default"),
    )
    return ChatOpenAI(**kwargs)


def create_llm_pair(config: dict[str, Any]) -> tuple[Any | None, Any | None]:
    return (
        create_llm_client(config, "quick_think_llm"),
        create_llm_client(config, "deep_think_llm"),
    )
