import json

import pytest

from esgagents.quantitative import (
    QuantitativeAgent,
    QuantitativeInputError,
    QuantitativeInputLoader,
    map_quant_210_values,
    map_quantitative_values,
    normalize_quantitative_evidence,
)
from esgagents.schemas import NormalizedCompany, PlannedQuestion, QuantitativeMetric
from esgagents.template_loader import TemplateRepository


def _company(run_id="run_quant"):
    return NormalizedCompany(
        company_id="company_1",
        company_name="Company",
        year=2025,
        scale="large_enterprise",
        industry="TC",
        top_k=5,
        output_language="Korean",
        run_id=run_id,
    )


def test_quantitative_catalog_contains_ordered_251_metrics():
    repository = TemplateRepository("template_v1")

    items = repository.load_quantitative_items()

    assert len(items) == 251
    assert items[0]["metric_id"] == "QUANT-0001"
    assert items[-1]["metric_id"] == "QUANT-0251"
    assert [item["index"] for item in items] == list(range(1, 252))


def test_quantitative_normalizer_accepts_aliases_and_exact_mapping():
    evidence = normalize_quantitative_evidence(
        {
            "records": [
                {
                    "quant_metric_id": "QUANT-0001",
                    "indicator": "Total employees",
                    "amount": 1200,
                    "unit": "people",
                    "source_pdf": "report.pdf",
                    "mapped_qualitative_qid": "Q031",
                    "source_id": "EBX-Q-031",
                    "reporting_period": "FY2025",
                    "source_page": 10,
                    "confidence": 0.9,
                }
            ]
        },
        company_id="company_1",
        year=2025,
    )
    metric = QuantitativeMetric(
        metric_id="QUANT-0001",
        index=1,
        item="Total employees",
        unit="people",
    )

    result = map_quantitative_values([metric], evidence)[0]

    assert result.status == "filled"
    assert result.value == 1200
    assert result.source == "report.pdf"
    assert result.confidence == 1.0
    assert result.metadata["match_reason"] == "exact_metric_mapping"
    assert result.metadata["mapped_qualitative_qid"] == "Q031"
    assert result.metadata["source_id"] == "EBX-Q-031"
    assert result.metadata["reporting_period"] == "FY2025"


def _quant_210_fixture():
    return {
        "company_id": "company_1",
        "company_name": "대웅제약",
        "year": 2025,
        "kind": "quantitative",
        "catalog_pack": "quant_210",
        "total": 3,
        "items": [
            {
                "item_id": "596",
                "domain": "사회",
                "category": "구성원 및 다양성",
                "subcategory": "성별",
                "item": "남성",
                "question": "구성원 및 다양성 > 성별 > 남성",
                "unit": "명",
                "standards": {"gri": None},
                "answer": {
                    "text": "1136.0명",
                    "value": 1136,
                    "unit": "명",
                    "normalized_value": 1136,
                    "year": 2025,
                    "status": "answered",
                    "confidence": "high",
                    "reason": "guided_cell",
                    "source": "정량데이터_인사.xlsx",
                    "evidence": [
                        {
                            "text": "남성",
                            "source": "정량데이터_인사.xlsx",
                            "sheet": "25년 사회 raw data 취합",
                            "cell": "J89",
                            "value_raw": 1136,
                            "section_path": "대웅제약 임직원 등 현황",
                        }
                    ],
                },
            },
            {
                "item_id": "597",
                "domain": "사회",
                "category": "구성원 및 다양성",
                "subcategory": "성별",
                "item": "여성",
                "question": "구성원 및 다양성 > 성별 > 여성",
                "unit": "%",
                "standards": {},
                "answer": {
                    "value": None,
                    "unit": "%",
                    "year": 2025,
                    "status": "missing",
                    "confidence": "low",
                    "reason": "[missing_no_source_data] Không có trong baseline multiyear.",
                    "evidence": [],
                },
            },
            {
                "item_id": "693",
                "domain": "사회",
                "category": "구성원 성과평가 & 급여",
                "subcategory": "남성 대비 여성 급여 비율",
                "item": "남성 대비 여성 급여 비율",
                "question": "남성 대비 여성 급여 비율",
                "unit": "%",
                "standards": {},
                "answer": {
                    "text": "0.7209302325581395%",
                    "value": 0.7209302325581395,
                    "unit": "%",
                    "year": 2025,
                    "status": "needs_confirmation",
                    "confidence": "medium",
                    "reason": "matcher · [needs_confirmation:A1] 0.7209302325581395×100 = 72.09; chờ khách xác nhận.",
                    "source": "정량데이터_인사.xlsx",
                    "evidence": [{"source": "정량데이터_인사.xlsx", "cell": "K10"}],
                },
            },
        ],
    }


def test_quant_210_mapper_publishes_answered_and_withholds_needs_confirmation():
    results, stats = map_quant_210_values(_quant_210_fixture(), company=_company())

    assert stats == {
        "total": 3,
        "filled": 1,
        "missing": 1,
        "needs_confirmation": 1,
        "published": 1,
    }
    assert [result.metric_id for result in results] == ["596", "597", "693"]
    assert results[0].status == "filled"
    assert results[0].value == 1136
    assert results[0].unit == "명"
    assert results[0].source == "정량데이터_인사.xlsx"
    assert results[0].metadata["domain"] == "사회"
    assert results[0].metadata["evidence_locator"]["cell"] == "J89"
    assert results[1].status == "missing"
    assert results[1].value is None
    assert "Không có" in results[1].metadata["answer_reason"]
    assert results[2].status == "missing"
    assert results[2].value is None
    assert results[2].source == ""
    assert results[2].metadata["needs_confirmation"] is True
    assert "0.7209302325581395" not in json.dumps(results[2].model_dump(mode="json"), ensure_ascii=False)


def test_quantitative_mapper_uses_text_and_unit_and_keeps_missing_rows():
    evidence = normalize_quantitative_evidence(
        [{"metric_name": "Water consumption", "value": 25, "unit": "m3"}],
        company_id="company_1",
        year=2025,
    )
    metrics = [
        QuantitativeMetric(
            metric_id="QUANT-0001",
            index=1,
            category="Environment",
            item="Water consumption",
            unit="m3",
        ),
        QuantitativeMetric(
            metric_id="QUANT-0002",
            index=2,
            item="Employee turnover",
            unit="%",
        ),
    ]

    results = map_quantitative_values(metrics, evidence)

    assert results[0].status == "filled"
    assert results[0].metadata["match_reason"] == "metric_match"
    assert results[1].status == "missing"
    assert results[1].value is None


def test_quantitative_file_loader_allows_missing_file_and_reads_json(tmp_path):
    config = {
        "quantitative_input_mode": "file",
        "quantitative_input_dir": str(tmp_path),
        "quantitative_output_enabled": True,
    }
    loader = QuantitativeInputLoader(config)
    company = _company()

    raw, source_path = loader.load(company)
    assert raw is None
    assert source_path.endswith("company_1\\2025\\quantitative_raw.json")

    path = tmp_path / "company_1" / "2025" / "quantitative_raw.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"items": [{"metric_id": "QUANT-0001", "value": 10}]}))

    raw, source_path = loader.load(company)
    assert raw["items"][0]["value"] == 10
    assert source_path == str(path)


def test_quantitative_api_loader_saves_run_snapshot(tmp_path):
    seen = {}

    def http_get(url, headers, timeout, method, payload):
        seen.update(url=url, headers=headers, timeout=timeout, method=method, payload=payload)
        return {"metrics": [{"metric_id": "QUANT-0001", "value": 10}]}

    config = {
        "quantitative_input_mode": "api",
        "quantitative_api_base_url": "https://example.test",
        "quantitative_api_path": "/companies/{company_id}/{year}/quantitative",
        "quantitative_api_method": "GET",
        "quantitative_api_key": "secret",
        "quantitative_api_timeout_seconds": 12,
        "cache_dir": str(tmp_path),
    }
    loader = QuantitativeInputLoader(config, http_get=http_get)

    raw, source_path = loader.load(_company())

    assert raw["metrics"][0]["value"] == 10
    assert seen["url"] == "https://example.test/companies/company_1/2025/quantitative"
    assert seen["method"] == "GET"
    assert seen["payload"] is None
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["timeout"] == 12
    assert json.loads(open(source_path, encoding="utf-8").read()) == raw


def test_quantitative_api_loader_posts_quantitative_answers_body(tmp_path):
    seen = {}

    def http_request(url, headers, timeout, method, payload):
        seen.update(url=url, headers=headers, timeout=timeout, method=method, payload=payload)
        return _quant_210_fixture()

    config = {
        "quantitative_input_mode": "api",
        "quantitative_api_base_url": "https://example.test",
        "quantitative_api_path": "/quantitative/answers",
        "quantitative_api_method": "POST",
        "quantitative_api_key": "secret",
        "quantitative_api_timeout_seconds": 12,
        "cache_dir": str(tmp_path),
    }
    loader = QuantitativeInputLoader(config, http_get=http_request)

    raw, source_path = loader.load(_company())

    assert raw["catalog_pack"] == "quant_210"
    assert seen == {
        "url": "https://example.test/quantitative/answers",
        "headers": {
            "Accept": "application/json",
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
        "timeout": 12,
        "method": "POST",
        "payload": {
            "company_id": "company_1",
            "company_name": "Company",
            "year": 2025,
        },
    }
    assert "api_snapshot_quantitative.json" in source_path


def test_quantitative_api_loader_rejects_non_object_response(tmp_path):
    config = {
        "quantitative_input_mode": "api",
        "quantitative_api_base_url": "https://example.test",
        "quantitative_api_path": "/quantitative",
        "quantitative_api_timeout_seconds": 12,
        "cache_dir": str(tmp_path),
    }
    loader = QuantitativeInputLoader(config, http_get=lambda *_: "invalid")

    with pytest.raises(QuantitativeInputError, match="JSON object or array"):
        loader.load(_company())


def test_quantitative_agent_returns_all_catalog_rows_when_input_is_missing(tmp_path):
    config = {
        "quantitative_input_mode": "file",
        "quantitative_input_dir": str(tmp_path),
        "quantitative_output_enabled": True,
    }
    agent = QuantitativeAgent(config, TemplateRepository("template_v1"))

    result = agent.run({"company": _company()})

    assert result["quantitative_stats"] == {"total": 251, "filled": 0, "missing": 251}
    assert len(result["quantitative_results"]) == 251
    assert result["quantitative_results"][0]["status"] == "missing"


def test_quantitative_agent_uses_quant_210_native_results_without_legacy_catalog():
    class Templates:
        def load_quantitative_items(self):
            raise AssertionError("legacy 251 catalog should not be loaded for quant_210")

    class Loader:
        def load(self, company):
            return (_quant_210_fixture(), "api_snapshot_quantitative.json")

    result = QuantitativeAgent({"quantitative_output_enabled": True}, Templates(), Loader()).run({"company": _company()})

    assert result["quantitative_stats"] == {
        "total": 3,
        "filled": 1,
        "missing": 1,
        "needs_confirmation": 1,
        "published": 1,
    }
    assert len(result["quantitative_results"]) == 3
    assert result["quantitative_results"][0]["metric_id"] == "596"
    assert result["quantitative_results"][2]["metric_id"] == "693"
    assert result["quantitative_results"][2]["value"] is None


def test_quant_210_api_mapping_does_not_bridge_to_metrics_qid():
    class Loader:
        def load(self, company):
            raw = _quant_210_fixture()
            raw["items"][0]["mapped_qualitative_qid"] = "Q063"
            raw["items"][0]["source_id"] = "EBX-Q-063"
            raw["items"][2]["mapped_qualitative_qid"] = "Q063"
            raw["items"][2]["source_id"] = "EBX-Q-063"
            return (raw, "api_snapshot_quantitative.json")

    planned = PlannedQuestion(
        id="Q063",
        source_id="EBX-Q-063",
        pillar="Metrics",
        item_ko="êµ¬́„±́› ë‹¤́–‘́„± í˜„í™©",
    )
    result = QuantitativeAgent(
        {"metric_qid_bridge_enabled": True, "quantitative_output_enabled": True},
        object(),
        Loader(),
    ).run(
        {
            "company": _company(),
            "planned_questions": [planned],
            "rag_results": {},
            "evidence_gate": {},
            "normalized_evidence": {},
            "quality_flags": {},
        }
    )

    assert result["metric_qid_bridge_results"] == {}
    assert "rag_results" not in result
    assert "evidence_gate" not in result
    assert "normalized_evidence" not in result
    assert "quality_flags" not in result
    assert result["quantitative_results"][0]["metric_id"] == "596"


def test_quant_210_api_mapping_does_not_bridge_needs_confirmation_only():
    raw = _quant_210_fixture()
    raw["items"] = [raw["items"][2]]
    raw["total"] = 1
    raw["items"][0]["mapped_qualitative_qid"] = "Q063"
    raw["items"][0]["source_id"] = "EBX-Q-063"

    class Loader:
        def load(self, company):
            return (raw, "api_snapshot_quantitative.json")

    planned = PlannedQuestion(id="Q063", source_id="EBX-Q-063", pillar="Metrics")
    result = QuantitativeAgent(
        {"metric_qid_bridge_enabled": True, "quantitative_output_enabled": True},
        object(),
        Loader(),
    ).run(
        {
            "company": _company(),
            "planned_questions": [planned],
            "rag_results": {},
            "evidence_gate": {},
            "normalized_evidence": {},
            "quality_flags": {},
        }
    )

    assert result["metric_qid_bridge_results"] == {}
    assert "quality_flags" not in result
    assert result["quantitative_results"][0]["metric_id"] == "693"
    assert result["quantitative_results"][0]["value"] is None


def test_quantitative_output_does_not_inject_metric_evidence_for_qualitative_qid():
    class Templates:
        def load_quantitative_items(self):
            return [
                {
                    "metric_id": "QUANT-0001",
                    "index": 1,
                    "domain": "환경",
                    "category": "기후행동",
                    "subcategory": "온실가스",
                    "item": "Scope 1 emissions",
                    "unit": "tCO2e",
                    "standards": {},
                    "metadata": {},
                }
            ]

    class Loader:
        def load(self, company):
            return (
                {
                    "items": [
                        {
                            "metric_id": "QUANT-0001",
                            "mapped_qualitative_qid": "Q031",
                            "source_id": "EBX-Q-031",
                            "metric_name": "Scope 1 emissions",
                            "value": 100,
                            "unit": "tCO2e",
                            "reporting_period": "FY2025",
                            "source": "metrics.xlsx",
                        }
                    ]
                },
                "quantitative_raw.json",
            )

    planned = PlannedQuestion(
        id="Q031",
        source_id="EBX-Q-031",
        category_ko="기후행동",
        pillar="지표 (Metrics)",
        item_ko="온실가스 배출량 및 에너지 사용 현황",
    )
    agent = QuantitativeAgent(
        {
            "metric_qid_bridge_enabled": True,
            "quantitative_output_enabled": True,
        },
        Templates(),
        Loader(),
    )

    result = agent.run(
        {
            "company": _company(),
            "planned_questions": [planned],
            "rag_results": {},
            "evidence_gate": {"Q031": {"accepted": False, "reason": "empty evidence"}},
            "normalized_evidence": {},
            "quality_flags": {},
        }
    )

    assert result["quantitative_stats"] == {"total": 1, "filled": 1, "missing": 0}
    assert "evidence_gate" not in result
    assert "rag_results" not in result
    assert "normalized_evidence" not in result
    assert result["metric_qid_bridge_results"] == {}


def test_quantitative_output_does_not_flag_metric_qid_without_match():
    class Templates:
        def load_quantitative_items(self):
            return [
                {
                    "metric_id": "QUANT-0001",
                    "index": 1,
                    "item": "Scope 1 emissions",
                    "unit": "tCO2e",
                }
            ]

    class Loader:
        def load(self, company):
            return ({"items": []}, "quantitative_raw.json")

    planned = PlannedQuestion(id="Q031", pillar="Metrics", item_ko="온실가스 배출량")
    result = QuantitativeAgent(
        {"metric_qid_bridge_enabled": True, "quantitative_output_enabled": True},
        Templates(),
        Loader(),
    ).run(
        {
            "company": _company(),
            "planned_questions": [planned],
            "rag_results": {},
            "evidence_gate": {},
            "normalized_evidence": {},
            "quality_flags": {},
        }
    )

    assert result["metric_qid_bridge_results"] == {}
    assert "quality_flags" not in result


def test_quantitative_agent_is_disabled_by_default_and_does_not_call_loader():
    class Loader:
        def load(self, company):
            raise AssertionError("quantitative loader should not be called unless output is enabled")

    result = QuantitativeAgent({}, object(), Loader()).run({"company": _company()})

    assert result == {
        "quantitative_results": [],
        "quantitative_stats": {},
        "quantitative_source_path": "",
        "metric_qid_bridge_results": {},
    }
