from types import SimpleNamespace

from esgagents.agents.retrieval.rag_batch import RagBatchAgent
from esgagents.default_config import load_config
import pytest
from requests import ConnectionError as RequestsConnectionError
from requests import Response

from esgagents.rag_client import TeamRagClient, TeamRagError
from esgagents.schemas import (
    EvidenceItem,
    MetricEvidenceItem,
    NormalizedCompany,
    RagQuestionResult,
    RagResponse,
)


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
        "question_ids": ["Q016", "Q003"],
        "top_k": 5,
    }
    assert seen["timeout"] == 12
    assert response.results[0].question_id == "Q016"


def test_rag_client_legacy_request_contract_keeps_item_ids_and_year():
    seen = {}

    def transport(endpoint, payload, timeout):
        seen["payload"] = payload
        return _v3_response([_v3_result("Q016")])

    client = TeamRagClient(
        "https://rag.example",
        transport=transport,
        request_contract="legacy",
    )
    client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025)

    assert seen["payload"] == {
        "company_id": "iljinhysolus",
        "item_ids": ["Q016"],
        "top_k": 5,
        "year": 2025,
    }


def test_new_request_contract_sends_empty_question_ids_and_accepts_all_results():
    seen = {}

    def transport(endpoint, payload, timeout):
        seen["payload"] = payload
        return _v3_response([_v3_result("Q016"), _v3_result("Q003")])

    client = TeamRagClient("https://rag.example", transport=transport)
    response = client.fetch_evidence("iljinhysolus", [], 5, 2025)

    assert seen["payload"] == {
        "company_id": "iljinhysolus",
        "question_ids": [],
        "top_k": 5,
    }
    assert [result.question_id for result in response.results] == ["Q016", "Q003"]


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


@pytest.mark.parametrize("failure_code", ["DRAFT_ONLY", "ASSESSMENT_ONLY"])
def test_v3_source_status_does_not_force_answerable_false(failure_code):
    row = _v3_result(
        "Q080",
        coverage_status="partial",
        answerable=True,
        failure_code=failure_code,
    )
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response([row]))

    result = client.fetch_evidence("iljinhysolus", ["Q080"], 5, 2025).results[0]

    assert result.answerable is True
    assert result.failure_code == failure_code
    assert result.client_contract_violations == []


def test_v3_accepts_optional_structured_facts():
    item = _v3_item()
    item["facts"] = [
        {
            "metric": "waste_recycling_rate",
            "period": "2025",
            "value": "62.9",
            "unit": "%",
            "value_role": "actual",
            "scope": "company",
            "locator": {"sheet_name": "KPI", "cell_range": "F12"},
        }
    ]
    row = _v3_result("Q035", items=[item])
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response([row]))

    fact = client.fetch_evidence("iljinhysolus", ["Q035"], 5, 2025).results[0].items[0].facts[0]

    assert (fact.metric, fact.period, fact.value, fact.unit, fact.value_role) == (
        "waste_recycling_rate",
        "2025",
        "62.9",
        "%",
        "actual",
    )
    assert fact.locator.cell_range == "F12"


def test_v3_accepts_metric_row_items_from_qualitative_response():
    item = _v3_item()
    item.update(
        {
            "semantic_label": "metric_row",
            "semantic_reason": "metric_lane_row",
            "confidence_basis": "table_match",
            "raw_evidence_ko": "Water > Withdrawal total | ton | 2022=310596.0 | 2023=343083.0 | 2024=400298.0",
            "source_name": "metrics.xlsx",
            "source_path": "ESG/metrics.xlsx",
            "source_type": "operational_record",
            "source_tier": "tier_2_operational",
            "topic": "metrics",
            "subtopic": "metric_lane",
            "locator": {
                "sheet_name": "Water",
                "section": "Water > Withdrawal total",
                "cell_range": "G27:P27",
                "spans_units": ["ton"],
                "confidence": "exact",
            },
        }
    )
    row = _v3_result(
        "Q039",
        coverage_status="partial",
        answerable=True,
        failure_code="SCOPE_LIMITED",
        items=[item],
    )
    row.update(
        {
            "pillar": "metrics",
            "answer_status": "medium_confidence",
            "normalized_answer_ko": item["raw_evidence_ko"],
            "covered_facets": ["metric_result", "reporting_period"],
            "missing_facets": ["wastewater_discharge"],
            "coverage": {
                "direct_answer": True,
                "supports_metric_result": True,
                "supports_reporting_period": True,
            },
        }
    )
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response([row]))

    result = client.fetch_evidence("iljinhysolus", ["Q039"], 5, 2025).results[0]

    assert result.coverage_status == "partial"
    assert result.answer_status == "medium_confidence"
    assert result.failure_code == "SCOPE_LIMITED"
    assert result.client_contract_violations == []
    assert result.items[0].semantic_label == "metric_row"
    assert result.items[0].locator.spans_units == ["ton"]
    assert result.items[0].locator.confidence == "exact"


def test_v3_preserves_new_metric_contract_fields_and_extra_row_metadata():
    row = _v3_result("Q039", coverage_status="partial", answerable=True, failure_code="SCOPE_LIMITED")
    metric_item = _v3_item()
    metric_item.update(
        {
            "semantic_label": "metric_row",
            "raw_evidence_ko": "Water use | ton | 2025=10",
            "table_block": "Water > Pharm",
            "block_rank": 1,
            "block_role": "primary",
            "entity": "Daewoong Pharm",
            "entity_class": "daewoong_pharm",
            "metric_form": "table_row",
            "future_metric_tag": "preserved",
        }
    )
    row.update(
        {
            "pillar": "metrics",
            "metric_expected": True,
            "metric_status": "found_table",
            "metric_summary": {
                "n_rows": 1,
                "n_blocks": 1,
                "n_primary": 1,
                "n_scope_variant": 0,
                "n_denominator": 0,
            },
            "metric_confidence": None,
            "metric_evidence": [metric_item],
            "narrative_evidence": [_v3_item()],
        }
    )
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response([row]))

    result = client.fetch_evidence("iljinhysolus", ["Q039"], 5, 2025).results[0]
    dumped = result.model_dump(mode="json")

    assert result.metric_expected is True
    assert result.metric_status == "found_table"
    assert result.metric_summary.n_rows == 1
    assert dumped["metric_evidence"][0]["future_metric_tag"] == "preserved"
    assert dumped["narrative_evidence"][0]["raw_evidence_ko"] == "raw"


def test_facet_retry_prefers_operational_metric_table_over_draft_at_equal_coverage():
    agent = RagBatchAgent(load_config({"agent_mode": "offline"}), SimpleNamespace())
    draft = RagQuestionResult(
        question_id="Q035",
        coverage_status="partial",
        answerable=True,
        failure_code="DRAFT_ONLY",
        missing_facets=["waste_recycling_rate"],
        retrieval_confidence=0.99,
        items=[
            EvidenceItem(
                raw_evidence_ko="Draft waste target.",
                source_name="draft.docx",
                source_path="ESG/draft.docx",
                semantic_label="useful",
                source_tier="tier_4_draft",
            )
        ],
    )
    operational = RagQuestionResult(
        question_id="Q035",
        coverage_status="partial",
        answerable=True,
        failure_code="SCOPE_LIMITED",
        missing_facets=["waste_recycling_rate"],
        retrieval_confidence=0.70,
        items=[
            EvidenceItem(
                raw_evidence_ko="2025 waste generation was 1,250 t.",
                source_name="waste_kpi.xlsx",
                source_path="ESG/waste_kpi.xlsx",
                semantic_label="useful",
                source_tier="tier_2_operational",
                facts=[
                    {
                        "metric": "waste_generation",
                        "period": "2025",
                        "value": "1,250",
                        "unit": "t",
                        "value_role": "actual",
                    }
                ],
            )
        ],
    )

    preferred, _ = agent._preferred_v3_result(draft, operational)

    assert preferred is operational


@pytest.mark.parametrize("reason", ["no_candidate", "below_threshold", "blocked_by_gate"])
def test_metric_not_found_is_eligible_for_one_top_k_retry(reason):
    agent = RagBatchAgent(load_config({"agent_mode": "offline"}), SimpleNamespace())
    result = RagQuestionResult(
        question_id="Q023",
        coverage_status="partial",
        answerable=True,
        metric_expected=True,
        metric_status="not_found",
        metric_absence={"reason": reason, "n_candidates_seen": 2},
    )

    assert agent._should_retry(result) is True


def test_metric_retry_with_primary_table_replaces_not_found_result():
    agent = RagBatchAgent(load_config({"agent_mode": "offline"}), SimpleNamespace())
    original = RagQuestionResult(
        question_id="Q023",
        answer_status="medium_confidence",
        coverage_status="partial",
        answerable=True,
        metric_expected=True,
        metric_status="not_found",
        metric_absence={"reason": "below_threshold", "n_candidates_seen": 2},
    )
    retry = RagQuestionResult(
        question_id="Q023",
        answer_status="medium_confidence",
        coverage_status="partial",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            MetricEvidenceItem(
                raw_evidence_ko="Water reuse | 2025=9.34%",
                source_path="ESG/water.xlsx",
                source_tier="tier_2_operational",
                semantic_label="metric_row",
                table_block="Water",
                block_role="primary",
                entity="Daewoong",
            )
        ],
    )

    merged = agent._merge_retry_result(original, retry)

    assert merged.metric_status == "found_table"
    assert merged.metric_evidence[0].block_role == "primary"


def test_weaker_metric_retry_does_not_merge_into_stronger_initial_result():
    agent = RagBatchAgent(load_config({"agent_mode": "offline"}), SimpleNamespace())
    original = RagQuestionResult(
        question_id="Q023",
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            MetricEvidenceItem(
                raw_evidence_ko="Water reuse | 2025=9.34%",
                source_path="ESG/water.xlsx",
                source_tier="tier_2_operational",
                semantic_label="metric_row",
                table_block="Water",
                block_role="primary",
                entity="Daewoong",
            )
        ],
    )
    retry = RagQuestionResult(
        question_id="Q023",
        answer_status="medium_confidence",
        coverage_status="partial",
        answerable=True,
        metric_expected=True,
        metric_status="not_found",
        metric_absence={"reason": "no_candidate", "n_candidates_seen": 0},
    )

    merged = agent._merge_retry_result(original, retry)

    assert merged is original
    assert merged.metric_status == "found_table"


def test_weaker_found_table_retry_enriches_stronger_initial_without_losing_blocks():
    agent = RagBatchAgent(load_config({"agent_mode": "offline"}), SimpleNamespace())
    original = RagQuestionResult(
        question_id="Q039",
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_summary={"n_rows": 1, "n_blocks": 1, "n_primary": 1},
        metric_evidence=[
            MetricEvidenceItem(
                raw_evidence_ko="Water use | ton | 2025=10",
                source_path="ESG/water.xlsx",
                source_tier="tier_2_operational",
                semantic_label="metric_row",
                table_block="Pharm water",
                block_rank=1,
                block_role="primary",
                entity="Daewoong Pharm",
                entity_class="daewoong_pharm",
            )
        ],
    )
    retry = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        coverage_status="partial",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            MetricEvidenceItem(
                raw_evidence_ko="Water use | ton | 2025=20",
                source_path="ESG/water.xlsx",
                source_tier="tier_2_operational",
                semantic_label="metric_row",
                table_block="Group water",
                block_rank=2,
                block_role="primary",
                entity="Daewoong Group",
                entity_class="group_total",
            )
        ],
    )

    merged = agent._merge_retry_result(original, retry)

    assert merged.answer_status == "high_confidence"
    assert {item.table_block for item in merged.metric_evidence} == {
        "Pharm water",
        "Group water",
    }
    assert merged.metric_summary.n_rows == 2
    assert merged.metric_summary.n_blocks == 2
    assert merged.metric_summary.n_primary == 2


def test_v3_synthesizes_missing_result_and_records_contract_violation():
    client = TeamRagClient(
        "https://rag.example",
        transport=lambda *_: _v3_response([_v3_result("Q016")]),
    )

    response = client.fetch_evidence("iljinhysolus", ["Q016", "Q047"], 5, 2025)

    missing = response.results[1]
    assert missing.question_id == "Q047"
    assert missing.answerable is False
    assert missing.failure_code == "CLIENT_WARNING_SKIPPED_QID"
    assert missing.client_contract_warnings
    assert response.client_contract_violations == []


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


def test_v3_keeps_optional_fields_as_warnings_without_downgrading_status():
    raw = _v3_result("Q016")
    raw.pop("pillar")
    raw["retrieval_confidence"] = None
    raw["answerable"] = False
    client = TeamRagClient("https://rag.example", transport=lambda *_: _v3_response([raw]))

    result = client.fetch_evidence("iljinhysolus", ["Q016"], 5, 2025).results[0]

    assert result.answerable is False
    assert result.answer_status == "high_confidence"
    assert result.failure_code is None
    assert result.client_contract_violations == []
    assert result.client_contract_warnings


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
