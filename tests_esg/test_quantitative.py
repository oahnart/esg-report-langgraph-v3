import json

import pytest

from esgagents.quantitative import (
    QuantitativeAgent,
    QuantitativeInputError,
    QuantitativeInputLoader,
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

    def http_get(url, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        return {"metrics": [{"metric_id": "QUANT-0001", "value": 10}]}

    config = {
        "quantitative_input_mode": "api",
        "quantitative_api_base_url": "https://example.test",
        "quantitative_api_path": "/companies/{company_id}/{year}/quantitative",
        "quantitative_api_key": "secret",
        "quantitative_api_timeout_seconds": 12,
        "cache_dir": str(tmp_path),
    }
    loader = QuantitativeInputLoader(config, http_get=http_get)

    raw, source_path = loader.load(_company())

    assert raw["metrics"][0]["value"] == 10
    assert seen["url"] == "https://example.test/companies/company_1/2025/quantitative"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["timeout"] == 12
    assert json.loads(open(source_path, encoding="utf-8").read()) == raw


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
    }
    agent = QuantitativeAgent(config, TemplateRepository("template_v1"))

    result = agent.run({"company": _company()})

    assert result["quantitative_stats"] == {"total": 251, "filled": 0, "missing": 251}
    assert len(result["quantitative_results"]) == 251
    assert result["quantitative_results"][0]["status"] == "missing"


def test_quantitative_bridge_injects_metric_evidence_for_qualitative_qid():
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
    assert result["evidence_gate"]["Q031"] == {
        "accepted": True,
        "reason": "accepted_quantitative_bridge",
    }
    assert result["rag_results"]["Q031"].answer_status == "high_confidence"
    assert "100 tCO2e" in result["rag_results"]["Q031"].normalized_answer_ko
    assert "보고기간 FY2025" in result["rag_results"]["Q031"].normalized_answer_ko
    assert "출처는 metrics.xlsx" in result["rag_results"]["Q031"].normalized_answer_ko
    assert result["normalized_evidence"]["Q031"]["items"][0].source_type == "quantitative_metric"
    assert result["metric_qid_bridge_results"]["Q031"] == ["QUANT-0001"]


def test_quantitative_bridge_flags_metric_qid_without_match():
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
    result = QuantitativeAgent({"metric_qid_bridge_enabled": True}, Templates(), Loader()).run(
        {
            "company": _company(),
            "planned_questions": [planned],
            "rag_results": {},
            "evidence_gate": {},
            "normalized_evidence": {},
            "quality_flags": {},
        }
    )

    assert result["metric_qid_bridge_results"]["Q031"] == []
    assert result["quality_flags"]["Q031"] == ["missing_quantitative_metric_result"]
