import json
from pathlib import Path

from openpyxl import load_workbook

from esgagents.graph.esg_graph import ESGQualitativeGraph
from esgagents.rag_client import TeamRagClient


def test_graph_runs_subset_with_mock_rag_without_writing_outputs(tmp_path):
    def transport(endpoint, payload, timeout):
        return {
            "company_id": payload["company_id"],
            "results": [
                {
                    "question_id": qid,
                    "question_ko": f"{qid} question",
                    "normalized_answer_ko": f"{qid} normalized answer",
                    "answer_status": "high_confidence",
                    "items": [
                        {
                            "score": 1,
                            "raw_evidence_ko": f"{qid} raw evidence",
                            "source_name": "source.docx",
                            "source_path": "ESG/source.docx",
                            "semantic_label": "strong",
                            "semantic_score": 0.95,
                        }
                    ],
                }
                for qid in payload["item_ids"]
            ],
        }

    graph = ESGQualitativeGraph(
        config={
            "output_dir": str(tmp_path),
            "team_rag_batch_size": 2,
            "agent_mode": "offline",
            "quantitative_input_mode": "file",
            "quantitative_input_dir": str(tmp_path / "inputs"),
        },
        rag_client=TeamRagClient(
            "mock://rag",
            transport=transport,
            qualitative_path="/qualitative/evidence/v2",
        ),
    )
    artifacts = graph.generate(
        {
            "company_id": "iljinhysolus",
            "company_name": "Iljin Hysolus",
            "year": 2025,
            "scale": "large",
            "industry": "TC",
            "item_ids": ["Q001", "Q016", "Q047"],
        },
        write_outputs=False,
    )

    assert artifacts.stats == {"answered": 2, "empty": 0, "weak": 0, "failed": 1}
    assert [answer.qid for answer in artifacts.answers] == ["Q001", "Q016", "Q047"]
    assert artifacts.answers[0].sources[0]["source_name"] == "source.docx"
    assert artifacts.answers[0].skill_name
    assert artifacts.answers[2].qa.status == "failed"
    assert "missing required facet: metric_result" in artifacts.answers[2].qa.notes
    assert artifacts.quantitative_stats == {"total": 251, "filled": 0, "missing": 251}
    assert len(artifacts.quantitative_results) == 251


def test_graph_runs_with_checkpoint_enabled(tmp_path):
    def transport(endpoint, payload, timeout):
        return {
            "company_id": payload["company_id"],
            "results": [
                {
                    "question_id": qid,
                    "question_ko": qid,
                    "normalized_answer_ko": "answer",
                    "answer_status": "high_confidence",
                    "items": [
                        {
                            "raw_evidence_ko": "evidence",
                            "source_name": "doc",
                            "source_path": "ESG/doc.docx",
                            "semantic_label": "strong",
                            "semantic_score": 0.9,
                        }
                    ],
                }
                for qid in payload["item_ids"]
            ],
        }

    graph = ESGQualitativeGraph(
        config={
            "checkpoint_enabled": True,
            "cache_dir": str(tmp_path),
            "output_dir": str(tmp_path),
            "agent_mode": "offline",
            "quantitative_input_mode": "file",
            "quantitative_input_dir": str(tmp_path / "inputs"),
        },
        rag_client=TeamRagClient(
            "mock://rag",
            transport=transport,
            qualitative_path="/qualitative/evidence/v2",
        ),
    )
    artifacts = graph.generate(
        {
            "company_id": "checkpoint_company",
            "company_name": "Checkpoint Company",
            "year": 2025,
            "scale": "large",
            "industry": "TC",
            "item_ids": ["Q001"],
            "run_id": "run_checkpoint",
        },
        write_outputs=False,
    )

    assert artifacts.stats["answered"] == 1
    assert (tmp_path / "checkpoints" / "CHECKPOINT_COMPANY.db").exists()


def test_graph_writes_combined_workbook_with_quantitative_input(tmp_path):
    def transport(endpoint, payload, timeout):
        return {
            "company_id": payload["company_id"],
            "results": [
                {
                    "question_id": qid,
                    "question_ko": qid,
                    "normalized_answer_ko": "answer",
                    "answer_status": "high_confidence",
                    "items": [
                        {
                            "raw_evidence_ko": "evidence",
                            "source_name": "report.pdf",
                            "source_path": "ESG/report.pdf",
                            "semantic_label": "strong",
                            "semantic_score": 0.9,
                        }
                    ],
                }
                for qid in payload["item_ids"]
            ],
        }

    input_root = tmp_path / "inputs"
    quantitative_path = input_root / "combined_company" / "2025" / "quantitative_raw.json"
    quantitative_path.parent.mkdir(parents=True)
    quantitative_path.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "metric_id": "QUANT-0001",
                        "value": 100,
                        "unit": "people",
                        "source": "report.pdf",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    graph = ESGQualitativeGraph(
        config={
            "output_dir": str(tmp_path / "outputs"),
            "quantitative_input_mode": "file",
            "quantitative_input_dir": str(input_root),
            "agent_mode": "offline",
            "output_timezone": "Asia/Bangkok",
        },
        rag_client=TeamRagClient(
            "mock://rag",
            transport=transport,
            qualitative_path="/qualitative/evidence/v2",
        ),
    )

    artifacts = graph.generate(
        {
            "company_id": "combined_company",
            "company_name": "Combined Company",
            "year": 2025,
            "scale": "large",
            "industry": "TC",
            "item_ids": ["Q001"],
            "run_id": "run_combined",
        }
    )

    assert artifacts.quantitative_stats == {"total": 251, "filled": 1, "missing": 250}
    assert artifacts.quantitative_results[0].value == 100
    combined_path = Path(artifacts.output_paths["combined_excel"])
    assert combined_path.exists()
    workbook = load_workbook(combined_path, read_only=True)
    assert workbook.sheetnames == ["Qualitative", "Quantitative"]
    assert workbook["Quantitative"].max_row == 252


def test_graph_writes_quant_210_workbook_and_withholds_confirmation_values(tmp_path):
    def transport(endpoint, payload, timeout):
        return {
            "company_id": payload["company_id"],
            "results": [
                {
                    "question_id": qid,
                    "question_ko": qid,
                    "normalized_answer_ko": "answer",
                    "answer_status": "high_confidence",
                    "items": [
                        {
                            "raw_evidence_ko": "evidence",
                            "source_name": "report.pdf",
                            "source_path": "ESG/report.pdf",
                            "semantic_label": "strong",
                            "semantic_score": 0.9,
                        }
                    ],
                }
                for qid in payload["item_ids"]
            ],
        }

    item_ids = [str(value) for value in range(596, 806)]
    item_ids[-1] = "814"
    answered = 0
    items = []
    for item_id in item_ids:
        if item_id in {"693", "814"}:
            status = "needs_confirmation"
            value = 0.7209302325581395 if item_id == "693" else 5.071467
            reason = "needs confirmation"
        elif answered < 76:
            status = "answered"
            answered += 1
            value = answered
            reason = "guided_cell"
        else:
            status = "missing"
            value = None
            reason = "missing"
        items.append(
            {
                "item_id": item_id,
                "mapped_qualitative_qid": "Q063" if item_id == "596" else "",
                "source_id": "EBX-Q-063" if item_id == "596" else "",
                "domain": "사회",
                "category": "구성원 및 다양성",
                "subcategory": "성별",
                "item": f"metric {item_id}",
                "question": f"question {item_id}",
                "unit": "명",
                "standards": {},
                "answer": {
                    "value": value,
                    "unit": "명",
                    "year": 2025,
                    "status": status,
                    "confidence": "high",
                    "reason": reason,
                    "source": "정량데이터.xlsx",
                    "evidence": [{"source": "정량데이터.xlsx", "cell": "J1"}] if value else [],
                },
            }
        )

    class Loader:
        def load(self, company):
            return (
                {
                    "company_id": company.company_id,
                    "company_name": company.company_name,
                    "year": company.year,
                    "kind": "quantitative",
                    "catalog_pack": "quant_210",
                    "total": 210,
                    "items": items,
                },
                "api_snapshot_quantitative.json",
            )

    graph = ESGQualitativeGraph(
        config={
            "output_dir": str(tmp_path / "outputs"),
            "agent_mode": "offline",
            "output_timezone": "Asia/Bangkok",
        },
        rag_client=TeamRagClient(
            "mock://rag",
            transport=transport,
            qualitative_path="/qualitative/evidence/v2",
        ),
    )
    graph.agents.quantitative_agent.input_loader = Loader()

    artifacts = graph.generate(
        {
            "company_id": "daewoong",
            "company_name": "대웅제약",
            "year": 2025,
            "scale": "large",
            "industry": "HC",
            "item_ids": ["Q063"],
            "run_id": "run_quant_210",
        }
    )

    assert artifacts.quantitative_stats == {
        "total": 210,
        "filled": 76,
        "missing": 132,
        "needs_confirmation": 2,
        "published": 76,
    }
    assert len(artifacts.quantitative_results) == 210
    assert artifacts.answers[0].qid == "Q063"
    assert "quantitative_metric_bridge" in artifacts.answers[0].quality_flags
    assert "metric 596" in artifacts.answers[0].evidence_summary
    combined_path = Path(artifacts.output_paths["combined_excel"])
    workbook = load_workbook(combined_path, read_only=True)
    quantitative = workbook["Quantitative"]
    assert quantitative.max_row == 211
    rows_by_metric = {
        row[0]: row
        for row in quantitative.iter_rows(min_row=2, values_only=True)
        if row[0] in {"693", "814"}
    }
    assert rows_by_metric["693"][3] is None
    assert rows_by_metric["814"][3] is None
    assert rows_by_metric["693"][6] == "missing"
    assert "needs_confirmation" in rows_by_metric["693"][8]
