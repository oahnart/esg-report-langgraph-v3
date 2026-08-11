import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from esgagents.default_config import load_config
from esgagents.llm_clients.factory import create_llm_client, create_llm_pair
from esgagents.llm_clients.structured import PromptStructuredLLM, bind_structured


class FakeChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.metadata = kwargs.get("metadata")


def install_fake_langchain_openai(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))


def test_hallmdr_client_uses_default_chat_completions_base_and_key(monkeypatch):
    install_fake_langchain_openai(monkeypatch)
    config = load_config(
        {
            "agent_mode": "llm",
            "llm_provider": "hallmdr",
            "llm_api_key": "hall-key",
            "llm_base_url": "https://api.hallmdr.com/",
            "quick_think_llm": "llm/gemma4",
        }
    )

    client = create_llm_client(config)

    assert client.kwargs["model"] == "llm/gemma4"
    assert client.kwargs["api_key"] == "hall-key"
    assert client.kwargs["base_url"] == "https://api.hallmdr.com/v1"
    assert client.kwargs["default_headers"]["User-Agent"] == "Mozilla/5.0"
    assert client.metadata == {
        "esg_llm_provider": "hallmdr",
        "esg_json_repair_retry": False,
        "esg_structured_failure_limit": 3,
    }
    assert "model_kwargs" not in client.kwargs


def test_hallmdr_uses_provider_key_and_builds_quick_deep_pair(monkeypatch):
    install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("HALLMDR_API_KEY", "provider-key")
    monkeypatch.delenv("ESG_LLM_API_KEY", raising=False)
    config = load_config(
        {
            "agent_mode": "llm",
            "llm_provider": "hallmdr",
            "llm_api_key": "",
            "llm_base_url": None,
            "quick_think_llm": "llm/gemma4-quick",
            "deep_think_llm": "llm/gemma4-deep",
        }
    )

    quick, deep = create_llm_pair(config)

    assert quick.kwargs["api_key"] == "provider-key"
    assert quick.kwargs["model"] == "llm/gemma4-quick"
    assert deep.kwargs["model"] == "llm/gemma4-deep"
    assert quick.kwargs["base_url"] == "https://api.hallmdr.com/v1"


def test_hallmdr_missing_key_respects_agent_mode(monkeypatch):
    monkeypatch.delenv("ESG_LLM_API_KEY", raising=False)
    monkeypatch.delenv("HALLMDR_API_KEY", raising=False)
    base_config = {
        "llm_provider": "hallmdr",
        "llm_api_key": "",
        "llm_base_url": "https://api.hallmdr.com",
    }

    assert create_llm_client({**base_config, "agent_mode": "auto"}) is None
    with pytest.raises(RuntimeError, match="HALLMDR_API_KEY"):
        create_llm_client({**base_config, "agent_mode": "llm"})


def test_openai_does_not_use_hallmdr_key(monkeypatch):
    install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("HALLMDR_API_KEY", "wrong-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    client = create_llm_client(
        {
            "agent_mode": "llm",
            "llm_provider": "openai",
            "llm_api_key": "",
            "quick_think_llm": "gpt-test",
        }
    )

    assert client.kwargs["api_key"] == "openai-key"
    assert client.kwargs["model"] == "gpt-test"


class StructuredResult(BaseModel):
    answer: str


class FakeHallMDRLLM:
    metadata = {"esg_llm_provider": "hallmdr"}

    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content='```json\n{"answer": "ok"}\n```')


class FakeJSONModeHallMDRLLM(FakeHallMDRLLM):
    def __init__(self):
        super().__init__()
        self.bound_kwargs = None

    def bind(self, **kwargs):
        self.bound_kwargs = kwargs
        return self


def test_hallmdr_structured_output_uses_prompt_json_adapter():
    llm = FakeHallMDRLLM()
    structured = bind_structured(llm, StructuredResult, "test")

    result = structured.invoke("return an answer")

    assert isinstance(structured, PromptStructuredLLM)
    assert result == StructuredResult(answer="ok")
    assert "Return exactly one valid JSON object" in llm.messages[0].content


def test_hallmdr_structured_output_prefers_native_json_mode():
    llm = FakeJSONModeHallMDRLLM()
    structured = bind_structured(llm, StructuredResult, "test")

    result = structured.invoke("return an answer")

    assert result == StructuredResult(answer="ok")
    assert llm.bound_kwargs == {"response_format": {"type": "json_object"}}
    assert "Return exactly one valid JSON object" in llm.messages[0].content


def test_hallmdr_structured_output_repairs_missing_field_comma():
    llm = FakeHallMDRLLM()
    llm.invoke = lambda messages: SimpleNamespace(content='{"answer": "ok"\n "extra": "ignored"}')
    structured = bind_structured(llm, StructuredResult, "test")

    assert structured.invoke("return an answer") == StructuredResult(answer="ok")


def test_hallmdr_structured_output_repairs_same_line_missing_field_comma():
    llm = FakeHallMDRLLM()
    llm.invoke = lambda messages: SimpleNamespace(content='{"answer": "ok" "extra": "ignored"}')
    structured = bind_structured(llm, StructuredResult, "test")

    assert structured.invoke("return an answer") == StructuredResult(answer="ok")


def test_hallmdr_structured_output_retries_unescaped_quote_response():
    llm = FakeHallMDRLLM()
    llm.metadata = {
        "esg_llm_provider": "hallmdr",
        "esg_json_repair_retry": True,
    }
    responses = iter(
        [
            '{"answer": "Use "recycled" water."}',
            '{"answer": "Use \\"recycled\\" water."}',
        ]
    )
    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=next(responses))

    llm.invoke = invoke
    structured = bind_structured(llm, StructuredResult, "test")

    assert structured.invoke("return an answer") == StructuredResult(answer='Use "recycled" water.')
    assert len(calls) == 2
    assert "JSON syntax repairer" in calls[1][0].content
    assert calls[1][1].content == '{"answer": "Use "recycled" water."}'


def test_hallmdr_invalid_json_fails_fast_without_second_llm_request():
    llm = FakeHallMDRLLM()
    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content='{"answer": "Use "recycled" water."}')

    llm.invoke = invoke
    structured = bind_structured(llm, StructuredResult, "test")

    with pytest.raises(ValueError):
        structured.invoke("return an answer")

    assert len(calls) == 1


def test_hallmdr_structured_circuit_opens_after_consecutive_invalid_json():
    llm = FakeHallMDRLLM()
    llm.metadata = {
        "esg_llm_provider": "hallmdr",
        "esg_structured_failure_limit": 2,
    }
    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content="not-json")

    llm.invoke = invoke
    structured = bind_structured(llm, StructuredResult, "test")

    with pytest.raises(ValueError):
        structured.invoke("first")
    with pytest.raises(ValueError):
        structured.invoke("second")
    with pytest.raises(RuntimeError, match="circuit open"):
        structured.invoke("third")

    assert len(calls) == 2


def test_hallmdr_structured_output_repairs_missing_array_item_comma_locally():
    llm = FakeHallMDRLLM()
    llm.invoke = lambda messages: SimpleNamespace(
        content='{"answer": "ok", "items": ["first"\n"second"]}'
    )

    class ResultWithItems(BaseModel):
        answer: str
        items: list[str]

    structured = bind_structured(llm, ResultWithItems, "test")

    assert structured.invoke("return an answer") == ResultWithItems(
        answer="ok",
        items=["first", "second"],
    )
