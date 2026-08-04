import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from openpyxl import Workbook
from openpyxl import load_workbook

from esgagents.output_writer import (
    AUDIT_COLUMNS,
    COMBINED_QUALITATIVE_COLUMNS,
    EXCEL_FALLBACK_TEXT,
    OutputRunExistsError,
    OutputWriter,
    QUANTITATIVE_COLUMNS,
    build_coverage_summary,
    clean_excel_text,
)
from esgagents.schemas import AnswerRecord, QAResult, QuantitativeResult, RagRequestTrace, RunArtifacts


def _audit_value(worksheet, column_name, row=2):
    column = AUDIT_COLUMNS.index(column_name) + 1
    return worksheet.cell(row=row, column=column).value


def test_output_writer_creates_json_and_excel_audit(tmp_path):
    artifacts = RunArtifacts(
        run_id="run_test",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 1},
        stats={"answered": 1, "empty": 0, "weak": 0, "failed": 0},
        answers=[
            AnswerRecord(
                qid="Q001",
                source_id="EBX-Q-001",
                category="ESG",
                question="question",
                answer_status="high_confidence",
                rag_pillar="governance",
                rag_retrieval_confidence=0.94,
                rag_coverage_status="complete",
                rag_answerable=True,
                rag_covered_facets=["accountable_body", "role"],
                rag_coverage={"direct_answer": True, "supports_role": True},
                draft_answer="draft answer",
                final_answer="answer",
                last_rejected_answer="rejected answer",
                qa_failure_stage="skill_policy_critic",
                sanitizer_actions=["removed_unsupported_numeric_claim:30%"],
                evidence_summary="evidence",
                sources=[{
                    "source_name": "doc.docx",
                    "source_path": "ESG/doc.docx",
                    "document_id": "doc_123",
                    "chunk_id": "chunk_123",
                    "canonical_source_id": "src_123",
                    "source_tier": "tier_1_governing",
                    "source_type": "policy_procedure",
                    "document_status": "governing",
                    "effective_date": "2025-01-01",
                    "classification_reason": "inferred_keyword:policy",
                    "locator": {"page": 3, "section": "Governance"},
                }],
                qa=QAResult(status="passed", notes=["grounded"]),
                retrieval_attempts=[
                    {"top_k": 5, "retry_reason": "initial", "eligible_item_count": 0},
                    {"top_k": 12, "retry_reason": "empty evidence", "eligible_item_count": 1},
                ],
            )
        ],
        rag_request_traces=[
            RagRequestTrace(
                request_id="rag-req-1",
                api_version="3.0",
                rag_version="rag-v3",
                index_version="index-v1",
                generated_at=datetime(2025, 8, 1, tzinfo=ZoneInfo("UTC")),
                requested_item_ids=["Q001"],
                top_k=5,
            )
        ],
    )

    written = OutputWriter(tmp_path).write(artifacts)
    wb = load_workbook(written.output_paths["excel"])
    ws = wb["Qualitative Audit"]

    assert [cell.value for cell in ws[1]] == AUDIT_COLUMNS
    assert ws.max_row == 2
    assert ws["A2"].value == "Q001"
    assert _audit_value(ws, "QA Grade") == "full"
    assert _audit_value(ws, "Result Bucket") == "answered"
    assert _audit_value(ws, "Coverage Reason") == "complete_grounded_answer"
    assert "empty evidence" in _audit_value(ws, "Retrieval Attempts")
    assert _audit_value(ws, "Draft Answer") == "draft answer"
    assert _audit_value(ws, "Last Rejected Answer") == "rejected answer"
    assert _audit_value(ws, "QA Failure Stage") == "skill_policy_critic"
    assert _audit_value(ws, "Sanitizer Actions") == "removed_unsupported_numeric_claim:30%"
    assert "source_tier=tier_1_governing" in _audit_value(ws, "Sources")
    assert "classification_reason=inferred_keyword:policy" in _audit_value(ws, "Sources")
    assert _audit_value(ws, "RAG Coverage") == "complete"
    assert _audit_value(ws, "RAG Answerable") is True
    assert '"direct_answer": true' in _audit_value(ws, "RAG Structured Coverage")
    assert "locator(page=3,section=Governance)" in _audit_value(ws, "Sources")
    combined = load_workbook(written.output_paths["combined_excel"])["Qualitative"]
    assert "source_type=policy_procedure" in combined["E2"].value
    payload = json.loads(open(written.output_paths["json"], encoding="utf-8").read())
    assert payload["answers"][0]["draft_answer"] == "draft answer"
    assert payload["answers"][0]["last_rejected_answer"] == "rejected answer"
    assert payload["answers"][0]["qa_failure_stage"] == "skill_policy_critic"
    assert payload["answers"][0]["sanitizer_actions"] == ["removed_unsupported_numeric_claim:30%"]
    assert payload["answers"][0]["sources"][0]["source_tier"] == "tier_1_governing"
    assert payload["rag_request_traces"][0]["generated_at"] == "2025-08-01T00:00:00Z"
    assert written.output_paths["json"].endswith("qualitative_run.json")
    assert written.output_paths["coverage_summary"].endswith("coverage_summary.json")
    coverage = json.loads(open(written.output_paths["coverage_summary"], encoding="utf-8").read())
    assert coverage["total_qids"] == 1
    assert coverage["groups"]["unsupported_claim"] == []
    assert coverage["retrieval"]["retried_qids"] == ["Q001"]
    assert coverage["retrieval"]["retry_helped_qids"] == ["Q001"]
    assert coverage["rag"]["coverage_status_stats"] == {"complete": 1}
    assert coverage["rag"]["answerable_stats"]["true"] == 1
    assert coverage["rag"]["request_ids"] == ["rag-req-1"]


def test_output_writer_cleans_illegal_excel_characters(tmp_path):
    artifacts = RunArtifacts(
        run_id="run_test",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 1},
        stats={"answered": 1, "empty": 0, "weak": 0, "failed": 0},
        answers=[
            AnswerRecord(
                qid="Q025",
                source_id="EBX-Q-025",
                category="ESG",
                question="question",
                answer_status="high_confidence",
                final_answer="answer",
                evidence_summary="감사실\x01소개",
                sources=[{"source_name": "doc\x01.docx", "source_path": "ESG/doc.docx"}],
                qa=QAResult(status="passed", notes=["grounded\x01note"]),
            )
        ],
    )

    written = OutputWriter(tmp_path).write(artifacts)
    wb = load_workbook(written.output_paths["excel"])
    ws = wb["Qualitative Audit"]

    assert _audit_value(ws, "Evidence Summary") == "감사실소개"
    assert _audit_value(ws, "Sources") == "doc.docx | ESG/doc.docx"
    assert _audit_value(ws, "QA Notes") == "groundednote"


def test_clean_excel_text_removes_invalid_xml_characters_and_truncates():
    assert clean_excel_text("ok\ud800bad\uffff") == "okbad"
    assert len(clean_excel_text("x" * 40000)) == 32767


@pytest.mark.parametrize("value", ["=1+1", "+CMD", "-2+3", "@SUM(A1:A2)", "  =1+1"])
def test_clean_excel_text_neutralizes_formula_prefixes(value):
    assert clean_excel_text(value) == "'" + value


def test_excel_formula_neutralization_does_not_change_json(tmp_path):
    artifacts = RunArtifacts(
        run_id="run_formula",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 1},
        stats={"answered": 1, "empty": 0, "weak": 0, "failed": 0},
        answers=[
            AnswerRecord(
                qid="Q001",
                final_answer="=1+1",
                evidence_summary="@SUM(A1:A2)",
                qa=QAResult(status="passed", notes=["grounded"]),
            )
        ],
    )

    written = OutputWriter(tmp_path).write(artifacts)
    workbook = load_workbook(written.output_paths["excel"], data_only=False)
    worksheet = workbook["Qualitative Audit"]
    payload = json.loads(
        (tmp_path / "c" / "2025" / "run_formula" / "qualitative_run.json").read_text(
            encoding="utf-8"
        )
    )

    final_answer_cell = worksheet.cell(row=2, column=AUDIT_COLUMNS.index("Final Answer") + 1)
    assert final_answer_cell.value == "'=1+1"
    assert final_answer_cell.data_type == "s"
    assert _audit_value(worksheet, "Evidence Summary") == "'@SUM(A1:A2)"
    assert payload["answers"][0]["final_answer"] == "=1+1"
    assert payload["answers"][0]["evidence_summary"] == "@SUM(A1:A2)"


def test_output_writer_rejects_existing_run_without_overwriting(tmp_path):
    artifacts = RunArtifacts(
        run_id="run_existing",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 0},
        stats={"answered": 0, "empty": 0, "weak": 0, "failed": 0},
        answers=[],
    )
    writer = OutputWriter(tmp_path)
    written = writer.write(artifacts)
    json_path = tmp_path / "c" / "2025" / "run_existing" / "qualitative_run.json"
    original = json_path.read_bytes()

    with pytest.raises(OutputRunExistsError, match="output run already exists"):
        writer.write(written)

    assert json_path.read_bytes() == original


def test_output_writer_temporal_retry_reuses_complete_existing_run(tmp_path):
    artifacts = RunArtifacts(
        run_id="run_retry",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 0},
        stats={"answered": 0, "empty": 0, "weak": 0, "failed": 0},
        answers=[],
    )
    writer = OutputWriter(tmp_path)
    first = writer.write(artifacts)
    json_path = tmp_path / "c" / "2025" / "run_retry" / "qualitative_run.json"
    original = json_path.read_bytes()

    retried = writer.write(artifacts, retry_existing=True)

    assert retried.output_paths == first.output_paths
    assert json_path.read_bytes() == original
    assert not list(json_path.parent.glob("*.tmp*"))


@pytest.mark.parametrize("unsafe_value", ["../escape", r"..\escape", "bad/name"])
def test_output_writer_rejects_unsafe_artifact_identifiers(tmp_path, unsafe_value):
    artifacts = RunArtifacts(
        run_id="run_safe",
        company={"company_id": unsafe_value, "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 0},
        stats={"answered": 0, "empty": 0, "weak": 0, "failed": 0},
        answers=[],
    )

    with pytest.raises(ValueError):
        OutputWriter(tmp_path).write(artifacts)


def test_append_excel_row_uses_fallback_when_assignment_still_fails(tmp_path):
    class Unconvertible:
        pass

    writer = OutputWriter(tmp_path)

    wb = Workbook()
    ws = wb.active
    writer._append_excel_row(ws, [Unconvertible()])

    assert ws["A1"].value == EXCEL_FALLBACK_TEXT


def _combined_artifacts(run_id, company_name="C"):
    return RunArtifacts(
        run_id=run_id,
        company={"company_id": "c", "company_name": company_name, "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 1},
        stats={"answered": 1, "empty": 0, "weak": 0, "failed": 0},
        answers=[
            AnswerRecord(
                qid="Q001",
                source_id="EBX-Q-001",
                category="ESG",
                question="question",
                answer_status="high_confidence",
                rag_pillar="governance",
                rag_retrieval_confidence=0.94,
                rag_coverage_status="complete",
                rag_answerable=True,
                rag_covered_facets=["accountable_body", "role"],
                final_answer="=unsafe",
                evidence_summary="prompt evidence",
                sources=[{"source_name": "report.pdf", "source_path": "ESG/report.pdf"}],
                qa=QAResult(status="passed", notes=[]),
                skill_name="ESG writer",
                skill_version="1",
                skill_selection_reason="matched topic",
                raw_rag_result={
                    "items": [{"raw_evidence_ko": "original evidence"}],
                },
            )
        ],
        quantitative_results=[
            QuantitativeResult(
                metric_id=f"QUANT-{index:04d}",
                index=index,
                metric_name=f"Metric {index}",
                value=index if index == 1 else None,
                unit="unit",
                source="report.pdf" if index == 1 else "",
                status="filled" if index == 1 else "missing",
                confidence=0.99 if index == 1 else 0.0,
                metadata={"index": index},
            )
            for index in range(1, 252)
        ],
        quantitative_stats={"total": 251, "filled": 1, "missing": 250},
    )


def test_output_writer_creates_two_sheet_combined_workbook_and_numbered_names(tmp_path):
    now = lambda: datetime(2026, 7, 31, 9, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
    writer = OutputWriter(tmp_path, now_provider=now)

    first = writer.write(_combined_artifacts("run_1", "Công ty: A/B"))
    second = writer.write(_combined_artifacts("run_2", "Công ty: A/B"))

    first_path = first.output_paths["combined_excel"]
    second_path = second.output_paths["combined_excel"]
    assert first_path.endswith("[langgraph][Công ty_ A_B]report-2026.07.31_1.xlsx")
    assert second_path.endswith("[langgraph][Công ty_ A_B]report-2026.07.31_2.xlsx")

    workbook = load_workbook(first_path, data_only=False)
    assert workbook.sheetnames == ["Qualitative", "Quantitative"]
    qualitative = workbook["Qualitative"]
    quantitative = workbook["Quantitative"]
    assert [cell.value for cell in qualitative[1]] == COMBINED_QUALITATIVE_COLUMNS
    assert [cell.value for cell in quantitative[1]] == QUANTITATIVE_COLUMNS
    assert qualitative["A2"].value == "EBX-Q-001"
    assert qualitative["D2"].value == "original evidence"
    assert qualitative["H2"].value == "'=unsafe"
    assert quantitative.max_row == 252
    assert quantitative["A252"].value == "QUANT-0251"
    assert quantitative["D2"].value == 1
    assert quantitative.freeze_panes == "A2"
    assert len(list((tmp_path / "c" / "2025" / "run_1").iterdir())) == 4

    payload = json.loads(
        (tmp_path / "c" / "2025" / "run_1" / "qualitative_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["quantitative_stats"] == {"total": 251, "filled": 1, "missing": 250}
    assert payload["output_paths"]["combined_excel"] == first_path


def test_coverage_summary_groups_failure_reasons():
    artifacts = RunArtifacts(
        run_id="run_coverage",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 4},
        stats={"answered": 1, "empty": 1, "weak": 1, "failed": 1},
        provenance={"mode": "strict", "verified": True, "source_digest": "abc123"},
        answers=[
            AnswerRecord(
                qid="Q001",
                result_bucket="weak",
                final_answer="",
                qa=QAResult(status="empty", notes=["empty evidence"]),
                retrieval_attempts=[{"top_k": 12, "retry_reason": "empty evidence", "eligible_item_count": 0}],
            ),
            AnswerRecord(
                qid="Q031",
                result_bucket="failed",
                final_answer="",
                qa=QAResult(
                    status="failed",
                    notes=["missing required facet: metric_result", "source usage overstated"],
                ),
                quality_flags=["draft_evidence"],
            ),
            AnswerRecord(
                qid="Q036",
                result_bucket="answered",
                final_answer="Partial cautious answer. The metric value was not disclosed.",
                qa=QAResult(status="passed", notes=["missing facet: target", "missing data disclosed"]),
                quality_flags=["partial_answer", "missing_facet:target", "draft_based_answer"],
            ),
            AnswerRecord(
                qid="Q051",
                result_bucket="failed",
                final_answer="",
                qa=QAResult(status="failed", notes=["unsupported certification or initiative claim"]),
            ),
        ],
    )

    summary = build_coverage_summary(artifacts)

    assert summary["total_qids"] == 4
    assert summary["bucket_stats"] == {"answered": 1, "empty": 1, "weak": 1, "failed": 1}
    assert summary["final_answer_stats"] == {"non_empty": 1, "empty": 3}
    assert summary["qa_stats"] == {"passed": 1, "failed": 2, "empty": 1}
    assert summary["quality_grade_stats"] == {
        "full": 0,
        "partial": 0,
        "cautious": 1,
        "failed": 3,
    }
    assert summary["quality_grade_qids"]["cautious"] == ["Q036"]
    assert summary["provenance"] == {
        "mode": "strict",
        "verified": True,
        "source_digest": "abc123",
    }
    assert summary["coverage_reason_qids"]["empty_evidence"] == ["Q001"]
    assert summary["coverage_reason_qids"]["draft_evidence"] == ["Q036"]
    assert summary["coverage_reason_qids"]["unsupported_claim"] == ["Q051"]
    assert summary["coverage_issue_qids"]["draft_evidence"] == ["Q031", "Q036"]
    assert sum(
        count
        for reasons in summary["coverage_matrix"].values()
        for count in reasons.values()
    ) == 4
    assert summary["empty_final_answer_qids"] == ["Q001", "Q031", "Q051"]
    assert summary["groups"]["empty_evidence"] == ["Q001"]
    assert summary["groups"]["metrics_missing"] == ["Q031"]
    assert summary["groups"]["draft_evidence"] == ["Q031", "Q036"]
    assert summary["groups"]["draft_based_answers"] == ["Q036"]
    assert summary["groups"]["partial_answers"] == ["Q036"]
    assert summary["groups"]["missing_required_facets"] == ["Q031"]
    assert summary["groups"]["missing_expected_facets"] == ["Q036"]
    assert summary["groups"]["source_overstated"] == ["Q031"]
    assert summary["groups"]["unsupported_claim"] == ["Q051"]
    assert summary["retrieval"]["retried_qids"] == ["Q001"]
    assert summary["retrieval"]["retry_unresolved_qids"] == ["Q001"]


def test_coverage_summary_reports_final_answer_counts_separately_from_buckets():
    answers = []
    for index in range(1, 96):
        final_answer = "answer" if index <= 30 else ""
        qa_status = "passed" if index <= 30 else "empty" if index <= 51 else "failed"
        bucket = "answered" if final_answer else "weak" if qa_status == "empty" else "failed"
        answers.append(
            AnswerRecord(
                qid=f"Q{index:03d}",
                result_bucket=bucket,
                final_answer=final_answer,
                qa=QAResult(status=qa_status, notes=[]),
            )
        )
    artifacts = RunArtifacts(
        run_id="run_coverage_counts",
        company={"company_id": "c", "company_name": "C", "year": 2025},
        template_selection={"template_version": "template_v1", "question_count": 95},
        stats={"answered": 30, "empty": 0, "weak": 21, "failed": 44},
        answers=answers,
    )

    summary = build_coverage_summary(artifacts)

    assert summary["stats"] == {"answered": 30, "empty": 0, "weak": 21, "failed": 44}
    assert summary["bucket_stats"] == summary["stats"]
    assert summary["final_answer_stats"] == {"non_empty": 30, "empty": 65}
    assert summary["qa_stats"] == {"passed": 30, "failed": 44, "empty": 21}
    assert summary["quality_grade_stats"] == {
        "full": 0,
        "partial": 0,
        "cautious": 30,
        "failed": 65,
    }
    assert sum(summary["quality_grade_stats"].values()) == 95
    assert len(summary["empty_final_answer_qids"]) == 65


def test_combined_filename_counter_is_unique_for_concurrent_runs(tmp_path):
    now = lambda: datetime(2026, 7, 31, 9, 0, tzinfo=ZoneInfo("Asia/Bangkok"))

    def write(run_id):
        return OutputWriter(tmp_path, now_provider=now).write(
            _combined_artifacts(run_id, "Concurrent Company")
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["run_a", "run_b"]))

    filenames = {result.output_paths["combined_excel"].rsplit("\\", 1)[-1] for result in results}
    assert filenames == {
        "[langgraph][Concurrent Company]report-2026.07.31_1.xlsx",
        "[langgraph][Concurrent Company]report-2026.07.31_2.xlsx",
    }
