from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
JSON_FIELD_BOUNDARY_RE = re.compile(r"(?<=[\]\"}0-9eE])\s*\n\s*(?=\"[^\"\n]+\"\s*:)")


class PromptStructuredLLM:
    """Structured-output adapter for OpenAI-compatible models without tool calling."""

    def __init__(self, llm: Any, schema: type[T]):
        self.llm = llm
        self.schema = schema

    def invoke(self, prompt: Any) -> T:
        instruction = SystemMessage(
            content=(
                "/no_think\n"
                "Return exactly one valid JSON object matching this JSON schema. "
                "Do not return markdown, code fences, analysis, or additional text.\n"
                f"JSON schema: {json.dumps(self.schema.model_json_schema(), ensure_ascii=False)}"
            )
        )
        if isinstance(prompt, (list, tuple)):
            messages = [instruction, *prompt]
        else:
            messages = [instruction, HumanMessage(content=str(prompt))]
        response = self.llm.invoke(messages)
        content = getattr(response, "content", str(response))
        if not isinstance(content, str):
            content = str(content)
        return self.schema.model_validate(_json_object(content))


def _json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        value = _loads_json_with_repair(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("No JSON object found in LLM response")
        value = _loads_json_with_repair(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Structured LLM response must be a JSON object")
    return value


def _loads_json_with_repair(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as original:
        repaired = _repair_common_json_shape_errors(text)
        if repaired != text:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise original


def _repair_common_json_shape_errors(text: str) -> str:
    repaired = text.strip()
    repaired = re.sub(r"^```(?:json)?\s*", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\s*```$", "", repaired)
    repaired = JSON_FIELD_BOUNDARY_RE.sub(",\n", repaired)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def bind_structured(llm: Any | None, schema: type[T], agent_name: str) -> Optional[Any]:
    if llm is None:
        return None
    metadata = getattr(llm, "metadata", None) or {}
    if metadata.get("esg_llm_provider") == "hallmdr":
        return PromptStructuredLLM(llm, schema)
    try:
        return llm.with_structured_output(schema)
    except (AttributeError, NotImplementedError) as exc:
        logger.warning("%s structured output unavailable; using free-text fallback: %s", agent_name, exc)
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any | None,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    if structured_llm is not None:
        try:
            return render(structured_llm.invoke(prompt))
        except Exception as exc:
            logger.warning("%s structured call failed; retrying as free text: %s", agent_name, exc)

    if plain_llm is None:
        raise RuntimeError(f"{agent_name} has no LLM available")
    response = plain_llm.invoke(prompt)
    return getattr(response, "content", str(response))
