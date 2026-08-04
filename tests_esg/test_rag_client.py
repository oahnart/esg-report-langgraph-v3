from types import SimpleNamespace

from esgagents.agents.retrieval.rag_batch import RagBatchAgent
from esgagents.default_config import load_config
import pytest
from requests import ConnectionError as RequestsConnectionError
from requests import Response

from esgagents.rag_client import TeamRagClient, TeamRagError
from esgagents.schemas import NormalizedCompany, RagResponse


def _v3_item(*, chunk_id="chunk-1", status="approved", tier="tier_1_governing"):
    return {
        "score": 0.95,
        "vector_score": 0.84,
        "reranker_score": 0.95,
        "semantic_score": 0.91,
        "semantic_label": "useful",
        "semantic_reason": "direct support",
        "raw_evidence_ko": "raw",
        "source_name": "doc.docx",
        "source_path": "ESG/doc.docx",
        "document_id": "doc-1",
        "chunk_id": chunk_id,
        "canonical_source_id": "src-1",
        "source_type": "policy",
        "document_status": status,
        "source_tier": tier,
        "document_version": "1.0",
        "effective_date": None,
        "topic": "governance",
        "subtopic": "oversight",
        "locator": {"page": 1},
    }


def _v3_result(qid, *, coverage_status="complete", answerable=True, failure_code=None, items=None):
    return {
        "question_id": qid,
        "question_ko": "question",
        "pillar": "governance",
        "normalized_answer_ko": "answer" if answerable else "",
        "answer_status": "high_confidence" if coverage_status == "complete" else (
            "thin_but_usable" if coverage_status == "partial" else coverage_status
        ),
        "retrieval_confidence": 0.9,
        "coverage_status": coverage_status,
        "answerable": answerable,
        "covered_facets": ["accountable_body"] if coverage_status != "no_evidence" else [],
        "missing_facets": [] if coverage_status == "complete" else ["role"],
        "failure_code": failure_code,
        "failure_reason": "" if coverage_status == "complete" else "missing facet",
        "retrieval_notes": [],
        "coverage": {"direct_answer": answerable},
        "items": [_v3_item()] if items is None and coverage_status != "no_evidence" else (items or []),
    }


def _v3_response(results, *, company_id="iljinhysolus"):
    return {
        "company_id": company_id,
        "request_id": "rag-req-1",
        "api_version": "3.0",
        "rag_version": "rag-v3",
        "index_version": "index-2025-1",
        "generated_at": "2025-08-01T00:00:00Z",
        "latency_ms": 42,
        "warnings": [],
        "results": results,
    }


def test_rag_client_posts_expected_batch_payload():
    seen = {}

    def transport(endpoint, payload, timeout):
        seen["endpoint"] = endpoint
        seen["payload"] = payload
        seen["timeout"] = timeout
        return _v3_response([_v3_result("Q016"), _v3_result("Q003")])

    client = TeamRagClient("https://rag.example", timeout_seconds=12, transport=transport)
    response = client.fetch_evidence("iljinhysolus", ["Q016", "Q003"], 5, 2025)

    assert seen["endpoint"] == "https://rag.example/qualitative/evidence/v3"
    assert seen["payload"] == {
        "company_id": "iljinhysolus",
        "item_ids": ["Q016", "Q003"],
        "top_k": 5,
        "year": 2025,
    }
    assert seen["timeout"] == 12
    assert response.results[0].question_id == "Q016"


def test_qualitative_path_defaults_to_v3_and_supports_manual_v2_rollback(monkeypatch):
    assert load_config()["team_rag_qualitative_path"] == "/qualitative/evidence/v3"
    monkeypatch.setenv("TEAM_RAG_QUALITATIVE_PATH", "/qualitative/evidence/v2")
    assert load_config()["team_rag_qualitative_path"] == "/qualitative/evidence/v2"
    assert TeamRagClient(
        "https://rag.example",
        qualitative_path="/qualitative/evidence/v2",
    ).endpoint.endswith("/qualitative/evidence/v2")


def test_rag_client_normalizes_null_optional_evidence_text():
    def transport(endpoint, payload, timeout):
        return {
            "company_id": "iljinhysolus",
            "results": [
                {
                    "question_id": "Q017",
                    "question_ko": None,
                    "normalized_answer_ko": None,
                    "answer_status": None,
                    "items": [
                        {
                            "raw_evidence_ko": None,
                            "source_name": None,
                            "source_path": None,
                            "semantic_label": None,
                            "semantic_reason": None,
                        }
                    ],
                }
            ],
        }

    client = TeamRagClient(
        "https://rag.example",
        transport=transport,
        qualitative_path="/qualitative/evidence/v2",
    )
    response = client.fetch_evidence("iljinhysolus", ["Q017"], 5, 2025)

    result = response.results[0]
    item = result.items[0]
    assert result.question_ko == ""
    assert result.normalized_answer_ko == ""
    assert result.answer_status == ""
    assert item.raw_evidence_ko == ""
    assert item.source_name == ""
    assert item.source_path == ""
    assert item.semantic_label == ""
    assert item.semantic_reason == ""


def test_v3_accepts_reference_complete_partial_and_insufficient_results():
    results = [
        _v3_result("Q016"),
        _v3_result("Q003", coverage_status="partial", answerable=True, failure_code="SCOPE_LIMITED"),
        _v3_result(
            "Q047",
            coverage_status="insufficient",
            answerable=False,
            failure_code="MISSING_REQUIRED_FACETS",
            items=[],
        ),
    ]
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response(results))

    response = client.fetch_evidence("iljinhysolus", ["Q016", "Q003", "Q047"], 5, 2025)

    assert [(result.question_id, result.coverage_status, result.answerable) for result in response.results] == [
        ("Q016", "complete", True),
        ("Q003", "partial", True),
        ("Q047", "insufficient", False),
    ]
    assert response.request_id == "rag-req-1"


def test_v3_synthesizes_missing_result_and_records_contract_violation():
    client = TeamRagClient(
        "https://rag.example",
        transport=lambda *_: _v3_response([_v3_result("Q016")]),
    )

    response = client.fetch_evidence("iljinhysolus", ["Q016", "Q047"], 5, 2025)

    missing = response.results[1]
    assert missing.question_id == "Q047"
    assert missing.answerable is False
    assert missing.failure_code == "CLIENT_CONTRACT_MISSING_RESULT"
    assert response.client_contract_violations


@pytest.mark.parametrize(
    ("results", "error_code"),
    [
        ([_v3_result("Q016"), _v3_result("Q016")], "CLIENT_CONTRACT_DUPLICATE_RESULT"),
        ([_v3_result("Q999")], "CLIENT_CONTRACT_UNREQUESTED_RESULT"),
    ],
)
def test_v3_rejects_duplicate_or_unrequested_qids(results, error_code):
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response(results))

    with pytest.raises(TeamRagError) as exc_info:
        client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025)

    assert exc_info.value.error_code == error_code


def test_v3_rejects_company_mismatch():
    client = TeamRagClient(
        "https://rag.example",
        transport=lambda *_: _v3_response([_v3_result("Q016")], company_id="other"),
    )

    with pytest.raises(TeamRagError) as exc_info:
        client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025)

    assert exc_info.value.error_code == "CLIENT_CONTRACT_COMPANY_MISMATCH"


def test_v3_downgrades_missing_fields_nulls_and_inconsistent_status():
    raw = _v3_result("Q016")
    raw.pop("pillar")
    raw["retrieval_confidence"] = None
    raw["answerable"] = False
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response([raw]))

    result = client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025).results[0]

    assert result.answerable is False
    assert result.failure_code == "CLIENT_CONTRACT_VIOLATION"
    assert result.client_contract_violations


@pytest.mark.parametrize(
    ("status", "expected_calls"),
    [(400, 1), (404, 1), (409, 1), (413, 1), (429, 2), (500, 2), (503, 2), (504, 2)],
)
def test_http_retry_policy_and_v3_error_body(status, expected_calls, monkeypatch):
    calls = []
    response = Response()
    response.status_code = status
    response.reason = "error"
    response._content = (
        b'{"request_id":"rag-error-1","error":{"code":"INVALID_REQUEST","message":"bad request"}}'
    )
    response.headers["Content-Type"] = "application/json"
    client = TeamRagClient("https://rag.example", max_retries=1)

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr(client.session, "post", post)
    monkeypatch.setattr("esgagents.rag_client.time.sleep", lambda *_: None)

    with pytest.raises(TeamRagError) as exc_info:
        client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025)

    assert len(calls) == expected_calls
    assert exc_info.value.status_code == status
    assert exc_info.value.request_id == "rag-error-1"
    assert exc_info.value.error_code == "INVALID_REQUEST"


def test_injected_transport_retries_network_errors_only(monkeypatch):
    calls = []

    def transport(*_):
        calls.append(1)
        if len(calls) == 1:
            raise RequestsConnectionError("temporary network error")
        return _v3_response([_v3_result("Q016")])

    monkeypatch.setattr("esgagents.rag_client.time.sleep", lambda *_: None)
    client = TeamRagClient("https://rag.example", max_retries=1, transport=transport)

    response = client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025)

    assert len(calls) == 2
    assert response.results[0].answerable is True


def test_rag_batch_retries_weak_or_empty_results_with_higher_top_k():
    calls = []

    class Client:
        def fetch_evidence(self, company_id, item_ids, top_k, year):
            calls.append((tuple(item_ids), top_k))
            if top_k == 5:
                return RagResponse.model_validate(
                    {
                        "company_id": company_id,
                        "results": [
                            {
                                "question_id": "Q001",
                                "answer_status": "insufficient",
                                "items": [],
                            },
                            {
                                "question_id": "Q002",
                                "answer_status": "high_confidence",
                                "items": [
                                    {
                                        "raw_evidence_ko": "weak evidence",
                                        "source_path": "ESG/weak.docx",
                                        "semantic_label": "weak",
                                    }
                                ],
                            },
                        ],
                    }
                )
            return RagResponse.model_validate(
                {
                    "company_id": company_id,
                    "results": [
                        {
                            "question_id": qid,
                            "normalized_answer_ko": f"{qid} retried answer",
                            "answer_status": "high_confidence",
                            "items": [
                                {
                                    "raw_evidence_ko": f"{qid} traceable evidence",
                                    "source_path": f"ESG/{qid}.docx",
                                    "semantic_label": "useful",
                                }
                            ],
                        }
                        for qid in item_ids
                    ],
                }
            )

    company = NormalizedCompany(
        company_id="company",
        company_name="Company",
        year=2025,
        scale="large_enterprise",
        industry="TC",
        top_k=5,
        output_language="Korean",
        run_id="run",
    )
    agent = RagBatchAgent(
        {
            "team_rag_batch_size": 20,
            "team_rag_concurrency": 1,
            "team_rag_retry_top_k": 12,
            "rejected_semantic_labels": {"weak", "irrelevant", "no_match"},
        },
        Client(),
    )

    result = agent.run(
        {
            "company": company,
            "planned_questions": [SimpleNamespace(id="Q001"), SimpleNamespace(id="Q002")],
        }
    )

    assert calls == [(("Q001", "Q002"), 5), (("Q001", "Q002"), 12)]
    assert result["rag_results"]["Q001"].normalized_answer_ko == "Q001 retried answer"
    assert result["rag_results"]["Q002"].items[0].semantic_label == "useful"
    assert result["retrieval_attempts"]["Q001"][1]["retry_reason"] == "empty evidence"
    assert result["retrieval_attempts"]["Q002"][1]["retry_reason"] == "all evidence semantic labels are weak"
    assert result["retrieval_attempts"]["Q001"][-1]["eligible_item_count"] == 1


def test_rag_batch_keeps_initial_results_when_optional_retry_fails():
    class Client:
        def fetch_evidence(self, company_id, item_ids, top_k, year):
            if top_k == 12:
                raise RuntimeError("HTTP 422 Unprocessable Content")
            return RagResponse.model_validate(
                {
                    "company_id": company_id,
                    "results": [
                        {
                            "question_id": "Q001",
                            "answer_status": "insufficient",
                            "items": [],
                        }
                    ],
                }
            )

    company = NormalizedCompany(
        company_id="company",
        company_name="Company",
        year=2025,
        scale="large_enterprise",
        industry="TC",
        top_k=5,
        output_language="Korean",
        run_id="run",
    )
    agent = RagBatchAgent(
        {
            "team_rag_batch_size": 20,
            "team_rag_concurrency": 1,
            "team_rag_retry_top_k": 12,
            "rejected_semantic_labels": {"weak", "irrelevant", "no_match"},
        },
        Client(),
    )

    result = agent.run({"company": company, "planned_questions": [SimpleNamespace(id="Q001")]})

    assert result["rag_results"]["Q001"].answer_status == "insufficient"
    assert result["retrieval_attempts"]["Q001"][-1]["retry_reason"] == "retry failed"
    assert "HTTP 422" in result["retrieval_attempts"]["Q001"][-1]["error"]


def test_rag_batch_v3_only_replaces_metadata_when_coverage_improves_and_keeps_traces():
    calls = []

    class Client:
        def fetch_evidence(self, company_id, item_ids, top_k, year):
            calls.append(top_k)
            if top_k == 5:
                rows = [
                    _v3_result(
                        "Q001",
                        coverage_status="insufficient",
                        answerable=False,
                        failure_code="MISSING_REQUIRED_FACETS",
                    ),
                    _v3_result(
                        "Q002",
                        coverage_status="insufficient",
                        answerable=False,
                        failure_code="WRONG_TOPIC",
                    ),
                ]
                rows[0]["missing_facets"] = ["role", "oversight_cadence"]
                rows[1]["missing_facets"] = ["role"]
            else:
                rows = [
                    _v3_result(
                        "Q001",
                        coverage_status="partial",
                        answerable=True,
                        failure_code="SCOPE_LIMITED",
                    ),
                    _v3_result(
                        "Q002",
                        coverage_status="insufficient",
                        answerable=False,
                        failure_code="MISSING_REQUIRED_FACETS",
                    ),
                ]
                rows[1]["missing_facets"] = ["role", "oversight_cadence"]
            payload = _v3_response(rows)
            payload["request_id"] = f"req-{top_k}"
            return RagResponse.model_validate(payload)

    company = NormalizedCompany(
        company_id="company",
        company_name="Company",
        year=2025,
        scale="large_enterprise",
        industry="TC",
        top_k=5,
        output_language="Korean",
        run_id="run",
    )
    agent = RagBatchAgent(
        {
            "team_rag_batch_size": 20,
            "team_rag_concurrency": 1,
            "team_rag_retry_top_k": 12,
            "rejected_semantic_labels": {"weak", "irrelevant", "no_match"},
        },
        Client(),
    )

    result = agent.run(
        {
            "company": company,
            "planned_questions": [SimpleNamespace(id="Q001"), SimpleNamespace(id="Q002")],
        }
    )

    assert calls == [5, 12]
    assert result["rag_results"]["Q001"].coverage_status == "partial"
    assert result["rag_results"]["Q002"].failure_code == "WRONG_TOPIC"
    assert len(result["rag_results"]["Q001"].items) == 1
    assert [trace.request_id for trace in result["rag_request_traces"]] == ["req-5", "req-12"]
    assert [trace.phase for trace in result["rag_request_traces"]] == ["initial", "retry"]
