from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from esgagents.default_config import DEFAULT_CONFIG
from esgagents.schemas import RunArtifacts, model_to_dict, validate_identifier
from esgagents.quality import QA_GRADES, resolved_answer_quality


AUDIT_COLUMNS = [
    "QID",
    "Source ID",
    "Category",
    "Question",
    "Answer Status",
    "RAG Pillar",
    "RAG Retrieval Confidence",
    "RAG Coverage",
    "RAG Answerable",
    "RAG Covered Facets",
    "RAG Missing Facets",
    "RAG Structured Coverage",
    "RAG Failure Code",
    "RAG Failure Reason",
    "RAG Retrieval Notes",
    "RAG Contract Violations",
    "QA Grade",
    "Final Answer",
    "Evidence Summary",
    "Sources",
    "QA Notes",
    "Agent Profile",
    "Quality Flags",
    "Revision Count",
    "Retrieval Attempts",
    "Skill Key",
    "Skill Name",
    "Skill Version",
    "Skill Source Path",
    "Skill Selection Reason",
    "Skill Checks",
    "Disclosure Flags",
    "Hard Failures",
    "Result Bucket",
    "Coverage Reason",
    "Coverage Issues",
    "Draft Answer",
    "Last Rejected Answer",
    "QA Failure Stage",
    "Sanitizer Actions",
]

COMBINED_QUALITATIVE_COLUMNS = [
    "EBX Indicator",
    "Status",
    "Field",
    "Original Evidence",
    "Evidence Source",
    "Prompt Evidence",
    "Writing Style Description",
    "Final Answer",
]

QUANTITATIVE_COLUMNS = [
    "Metric ID",
    "Index",
    "Metric Name",
    "Value",
    "Unit",
    "Source",
    "Status",
    "Confidence",
    "Metadata",
]

EXCEL_FALLBACK_TEXT = "The content contains characters that cannot be entered into Excel."
EXCEL_MAX_CELL_LENGTH = 32767
COMBINED_FILENAME_RE = re.compile(
    r"^\[langgraph\]\[.*\]report-(?P<date>\d{4}\.\d{2}\.\d{2})_(?P<number>\d+)\.xlsx$",
    re.IGNORECASE,
)
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class OutputPathError(ValueError):
    pass


class OutputRunExistsError(FileExistsError):
    pass


def _is_excel_text_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def clean_excel_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    cleaned = "".join(char for char in value if _is_excel_text_char(char))
    if cleaned.lstrip().startswith(("=", "+", "-", "@")):
        cleaned = "'" + cleaned
    return cleaned[:EXCEL_MAX_CELL_LENGTH]


class OutputWriter:
    def __init__(
        self,
        output_dir: str | Path,
        *,
        output_timezone: str = "Asia/Bangkok",
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_timezone = output_timezone
        self.now_provider = now_provider

    def load_existing(
        self,
        company_id: str,
        year: int,
        run_id: str,
    ) -> RunArtifacts | None:
        output_root, run_dir = self._resolve_run_dir(company_id, year, run_id)
        json_path = run_dir / "qualitative_run.json"
        if not json_path.is_file():
            return None
        try:
            with json_path.open("r", encoding="utf-8") as handle:
                artifacts = RunArtifacts.model_validate(json.load(handle))
            paths = [Path(value).resolve() for value in artifacts.output_paths.values()]
            if not paths or any(not path.is_file() for path in paths):
                return None
            for path in paths:
                path.relative_to(output_root)
            return artifacts
        except (OSError, ValueError, TypeError):
            return None

    def write(
        self,
        artifacts: RunArtifacts,
        *,
        retry_existing: bool = False,
    ) -> RunArtifacts:
        output_root = self.output_dir.resolve()
        company_id = validate_identifier(str(artifacts.company["company_id"]), "company_id")
        run_id = validate_identifier(artifacts.run_id, "run_id")
        _, run_dir = self._resolve_run_dir(company_id, int(artifacts.company["year"]), run_id)
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            if not retry_existing:
                raise OutputRunExistsError("output run already exists") from exc
            existing = self.load_existing(
                company_id,
                int(artifacts.company["year"]),
                run_id,
            )
            if existing is not None:
                return existing
        json_path = run_dir / "qualitative_run.json"
        coverage_path = run_dir / "coverage_summary.json"
        xlsx_path = run_dir / "qualitative_audit.xlsx"
        existing_combined = next(
            (
                path
                for path in run_dir.glob("*.xlsx")
                if COMBINED_FILENAME_RE.match(path.name)
            ),
            None,
        )
        reservation_path: Path | None = None
        if existing_combined is not None:
            combined_path = existing_combined
        else:
            combined_path, reservation_path = self._reserve_combined_path(
                output_root=output_root,
                company_id=company_id,
                year=int(artifacts.company["year"]),
                company_name=str(artifacts.company.get("company_name") or company_id),
                run_dir=run_dir,
            )

        token = uuid4().hex
        json_temp = run_dir / f".qualitative_run.{token}.tmp"
        coverage_temp = run_dir / f".coverage_summary.{token}.tmp"
        xlsx_temp = run_dir / f".qualitative_audit.{token}.tmp.xlsx"
        combined_temp = run_dir / f".combined_report.{token}.tmp.xlsx"
        try:
            artifacts.output_paths = {
                "json": str(json_path),
                "coverage_summary": str(coverage_path),
                "excel": str(xlsx_path),
                "combined_excel": str(combined_path),
            }
            with json_temp.open("w", encoding="utf-8") as handle:
                json.dump(model_to_dict(artifacts), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            with coverage_temp.open("w", encoding="utf-8") as handle:
                json.dump(build_coverage_summary(artifacts), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            self._write_excel(artifacts, xlsx_temp)
            self._write_combined_excel(artifacts, combined_temp)
            os.replace(xlsx_temp, xlsx_path)
            os.replace(combined_temp, combined_path)
            os.replace(coverage_temp, coverage_path)
            os.replace(json_temp, json_path)
            return artifacts
        finally:
            json_temp.unlink(missing_ok=True)
            coverage_temp.unlink(missing_ok=True)
            xlsx_temp.unlink(missing_ok=True)
            combined_temp.unlink(missing_ok=True)
            if reservation_path is not None:
                reservation_path.unlink(missing_ok=True)

    def _resolve_run_dir(
        self,
        company_id: str,
        year: int,
        run_id: str,
    ) -> tuple[Path, Path]:
        output_root = self.output_dir.resolve()
        safe_company_id = validate_identifier(str(company_id), "company_id")
        safe_run_id = validate_identifier(str(run_id), "run_id")
        run_dir = (output_root / safe_company_id / str(int(year)) / safe_run_id).resolve()
        try:
            run_dir.relative_to(output_root)
        except ValueError as exc:
            raise OutputPathError("output run path must remain inside output_dir") from exc
        return output_root, run_dir

    def _write_excel(self, artifacts: RunArtifacts, path: Path) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "Qualitative Audit"
        self._append_excel_row(ws, AUDIT_COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")

        for answer in artifacts.answers:
            quality = resolved_answer_quality(answer)
            self._append_excel_row(ws, [
                answer.qid,
                answer.source_id,
                answer.category,
                answer.question,
                answer.answer_status,
                answer.rag_pillar,
                answer.rag_retrieval_confidence,
                answer.rag_coverage_status,
                answer.rag_answerable,
                "; ".join(answer.rag_covered_facets),
                "; ".join(answer.rag_missing_facets),
                json.dumps(answer.rag_coverage, ensure_ascii=False, sort_keys=True),
                answer.rag_failure_code,
                answer.rag_failure_reason,
                "; ".join(answer.rag_retrieval_notes),
                "; ".join(answer.rag_contract_violations),
                quality.grade,
                answer.final_answer,
                answer.evidence_summary,
                "; ".join(
                    _format_source(src)
                    for src in answer.sources
                ),
                "; ".join(answer.qa.notes),
                answer.agent_profile,
                "; ".join(answer.quality_flags),
                answer.revision_count,
                json.dumps(answer.retrieval_attempts, ensure_ascii=False, sort_keys=True),
                answer.skill_key,
                answer.skill_name,
                answer.skill_version,
                answer.skill_source_path,
                answer.skill_selection_reason,
                "; ".join(answer.skill_checks),
                "; ".join(answer.disclosure_flags),
                "; ".join(answer.hard_failures),
                _answer_result_bucket(answer),
                quality.reason,
                "; ".join(quality.issues),
                answer.draft_answer,
                answer.last_rejected_answer,
                answer.qa_failure_stage,
                "; ".join(answer.sanitizer_actions),
            ])

        widths = [12, 16, 24, 44, 18, 18, 18, 18, 16, 36, 36, 60, 24, 52, 48, 52, 14, 60, 60, 52, 44, 20, 48, 16, 42, 16, 28, 16, 60, 32, 52, 44, 44, 16, 24, 24, 60, 60, 24, 48]
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        wb.save(path)

    def _write_combined_excel(self, artifacts: RunArtifacts, path: Path) -> None:
        workbook = Workbook()
        qualitative = workbook.active
        qualitative.title = "Qualitative"
        quantitative = workbook.create_sheet("Quantitative")

        self._append_excel_row(qualitative, COMBINED_QUALITATIVE_COLUMNS)
        for answer in artifacts.answers:
            self._append_excel_row(
                qualitative,
                [
                    answer.source_id,
                    _combined_status(answer),
                    " / ".join(part for part in (answer.category, answer.question) if part),
                    _original_evidence(answer.raw_rag_result),
                    _evidence_sources(answer.sources),
                    answer.evidence_summary,
                    _writing_style_description(answer),
                    answer.final_answer,
                ],
            )

        self._append_excel_row(quantitative, QUANTITATIVE_COLUMNS)
        for result in sorted(artifacts.quantitative_results, key=lambda item: item.index):
            self._append_excel_row(
                quantitative,
                [
                    result.metric_id,
                    result.index,
                    result.metric_name,
                    result.value,
                    result.unit,
                    result.source,
                    result.status,
                    result.confidence,
                    json.dumps(
                        result.metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                ],
            )

        self._style_report_sheet(
            qualitative,
            widths=[16, 22, 36, 52, 38, 52, 44, 64],
            wrap_columns=set(range(1, 9)),
        )
        self._style_report_sheet(
            quantitative,
            widths=[18, 10, 36, 18, 14, 38, 14, 14, 56],
            wrap_columns={3, 6, 9},
        )
        workbook.save(path)

    def _style_report_sheet(
        self,
        worksheet,
        *,
        widths: list[int],
        wrap_columns: set[int],
    ) -> None:
        worksheet.sheet_view.showGridLines = False
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        worksheet.row_dimensions[1].height = 24
        for cell in worksheet[1]:
            cell.font = Font(name="Carlito", size=11, bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="174A5A")
            cell.alignment = Alignment(vertical="top", wrap_text=False)
        for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
            for cell in row:
                cell.font = Font(name="Carlito", size=11)
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=cell.column in wrap_columns,
                )
        for index, width in enumerate(widths, start=1):
            worksheet.column_dimensions[get_column_letter(index)].width = width

    def _reserve_combined_path(
        self,
        *,
        output_root: Path,
        company_id: str,
        year: int,
        company_name: str,
        run_dir: Path,
    ) -> tuple[Path, Path]:
        output_date = self._output_date()
        company_year_root = output_root / company_id / str(year)
        reservation_dir = company_year_root / ".filename_reservations"
        reservation_dir.mkdir(parents=True, exist_ok=True)
        used_numbers = {
            number
            for path in company_year_root.rglob("*.xlsx")
            if (number := _combined_filename_number(path.name, output_date)) is not None
        }
        for lock_path in reservation_dir.glob(f"{output_date}_*.lock"):
            try:
                used_numbers.add(int(lock_path.stem.rsplit("_", 1)[-1]))
            except ValueError:
                continue
        number = max(used_numbers, default=0) + 1
        while True:
            reservation_path = reservation_dir / f"{output_date}_{number}.lock"
            try:
                descriptor = os.open(
                    reservation_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.close(descriptor)
                if any(
                    _combined_filename_number(path.name, output_date) == number
                    for path in company_year_root.rglob("*.xlsx")
                ):
                    reservation_path.unlink(missing_ok=True)
                    number += 1
                    continue
                break
            except FileExistsError:
                number += 1
        safe_company_name = sanitize_filename_component(company_name) or company_id
        filename = f"[langgraph][{safe_company_name}]report-{output_date}_{number}.xlsx"
        return run_dir / filename, reservation_path

    def _output_date(self) -> str:
        try:
            timezone = ZoneInfo(self.output_timezone)
        except Exception as exc:
            raise ValueError(f"invalid ESG_OUTPUT_TIMEZONE: {self.output_timezone}") from exc
        current = self.now_provider() if self.now_provider else datetime.now(timezone)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone)
        else:
            current = current.astimezone(timezone)
        return current.strftime("%Y.%m.%d")

    def _append_excel_row(self, ws, values: list[Any]) -> None:
        is_empty_sheet = ws.max_row == 1 and ws.max_column == 1 and ws["A1"].value is None
        row_idx = 1 if is_empty_sheet else ws.max_row + 1
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            try:
                cell.value = clean_excel_text(value)
            except Exception:
                cell.value = EXCEL_FALLBACK_TEXT


def _answer_result_bucket(answer: Any) -> str:
    if getattr(answer, "result_bucket", None):
        return str(answer.result_bucket)
    if getattr(answer, "final_answer", ""):
        return "answered"
    qa = getattr(answer, "qa", None)
    if getattr(qa, "status", "") == "failed":
        return "failed"
    accepted_statuses = {str(s).lower() for s in DEFAULT_CONFIG["accepted_answer_statuses"]}
    answer_status = str(getattr(answer, "answer_status", "")).lower()
    qa_notes = " ".join(getattr(qa, "notes", []) or []).lower()
    if "weak" in qa_notes or (answer_status and answer_status not in accepted_statuses and answer_status != "missing"):
        return "weak"
    return "empty"


def build_coverage_summary(artifacts: RunArtifacts) -> dict[str, Any]:
    groups = {
        "empty_evidence": [],
        "metrics_missing": [],
        "draft_evidence": [],
        "draft_based_answers": [],
        "partial_answers": [],
        "missing_required_facets": [],
        "missing_expected_facets": [],
        "source_overstated": [],
        "unsupported_claim": [],
    }
    retrieval = {
        "retried_qids": [],
        "retry_helped_qids": [],
        "retry_unresolved_qids": [],
        "attempts_by_qid": {},
    }
    notes_counter: dict[str, int] = {}
    final_answer_stats = {"non_empty": 0, "empty": 0}
    qa_stats = {"passed": 0, "failed": 0, "empty": 0}
    quality_grade_stats = {grade: 0 for grade in QA_GRADES}
    quality_grade_qids = {grade: [] for grade in QA_GRADES}
    coverage_reason_stats: dict[str, int] = {}
    coverage_reason_qids: dict[str, list[str]] = {}
    coverage_issue_stats: dict[str, int] = {}
    coverage_issue_qids: dict[str, list[str]] = {}
    coverage_matrix: dict[str, dict[str, int]] = {grade: {} for grade in QA_GRADES}
    rag_coverage_status_stats: dict[str, int] = {}
    rag_coverage_status_qids: dict[str, list[str]] = {}
    rag_answerable_stats = {"true": 0, "false": 0, "unknown": 0}
    rag_answerable_qids = {"true": [], "false": [], "unknown": []}
    rag_failure_code_stats: dict[str, int] = {}
    rag_failure_code_qids: dict[str, list[str]] = {}
    rag_contract_violation_qids: dict[str, list[str]] = {}
    empty_final_answer_qids = []
    for answer in artifacts.answers:
        qid = answer.qid
        if answer.final_answer:
            final_answer_stats["non_empty"] += 1
        else:
            final_answer_stats["empty"] += 1
            empty_final_answer_qids.append(qid)
        qa_status = str(getattr(answer.qa, "status", "") or "")
        if qa_status in qa_stats:
            qa_stats[qa_status] += 1
        quality = resolved_answer_quality(answer)
        quality_grade_stats[quality.grade] += 1
        quality_grade_qids[quality.grade].append(qid)
        coverage_reason_stats[quality.reason] = coverage_reason_stats.get(quality.reason, 0) + 1
        coverage_reason_qids.setdefault(quality.reason, []).append(qid)
        grade_matrix = coverage_matrix[quality.grade]
        grade_matrix[quality.reason] = grade_matrix.get(quality.reason, 0) + 1
        for issue in quality.issues:
            coverage_issue_stats[issue] = coverage_issue_stats.get(issue, 0) + 1
            coverage_issue_qids.setdefault(issue, []).append(qid)
        rag_coverage = str(answer.rag_coverage_status or "unknown")
        rag_coverage_status_stats[rag_coverage] = rag_coverage_status_stats.get(rag_coverage, 0) + 1
        rag_coverage_status_qids.setdefault(rag_coverage, []).append(qid)
        answerable_key = (
            "true" if answer.rag_answerable is True
            else "false" if answer.rag_answerable is False
            else "unknown"
        )
        rag_answerable_stats[answerable_key] += 1
        rag_answerable_qids[answerable_key].append(qid)
        if answer.rag_failure_code:
            rag_failure_code_stats[answer.rag_failure_code] = rag_failure_code_stats.get(answer.rag_failure_code, 0) + 1
            rag_failure_code_qids.setdefault(answer.rag_failure_code, []).append(qid)
        for violation in answer.rag_contract_violations:
            rag_contract_violation_qids.setdefault(violation, []).append(qid)
        notes = list(getattr(answer.qa, "notes", []) or [])
        flags = list(answer.quality_flags or [])
        checks = list(answer.skill_checks or [])
        combined = " | ".join([*notes, *flags, *checks]).casefold()
        for note in notes:
            notes_counter[note] = notes_counter.get(note, 0) + 1
        if "empty evidence" in combined:
            groups["empty_evidence"].append(qid)
        if (
            "metric_result" in combined
            or "reporting_period" in combined
            or "missing_quantitative_metric_result" in combined
        ):
            groups["metrics_missing"].append(qid)
        if any(term in combined for term in ("draft", "proposal", "planned", "under review", "검토", "계획")):
            groups["draft_evidence"].append(qid)
        if answer.final_answer and "draft_based_answer" in flags:
            groups["draft_based_answers"].append(qid)
        if answer.final_answer and ("partial_answer" in flags or "missing data disclosed" in combined):
            groups["partial_answers"].append(qid)
        if "missing required facet:" in combined:
            groups["missing_required_facets"].append(qid)
        if "missing facet:" in combined:
            groups["missing_expected_facets"].append(qid)
        if "source usage overstated" in combined:
            groups["source_overstated"].append(qid)
        if "unsupported numeric claim" in combined or "unsupported certification" in combined:
            groups["unsupported_claim"].append(qid)
        attempts = list(answer.retrieval_attempts or [])
        if attempts:
            retrieval["attempts_by_qid"][qid] = attempts
        retry_attempts = [
            attempt for attempt in attempts
            if str(attempt.get("retry_reason", "")) not in {"", "initial"}
        ]
        if retry_attempts:
            retrieval["retried_qids"].append(qid)
            if answer.final_answer:
                retrieval["retry_helped_qids"].append(qid)
            else:
                retrieval["retry_unresolved_qids"].append(qid)

    return {
        "run_id": artifacts.run_id,
        "company": artifacts.company,
        "total_qids": len(artifacts.answers),
        "stats": dict(artifacts.stats),
        "bucket_stats": dict(artifacts.stats),
        "final_answer_stats": final_answer_stats,
        "qa_stats": qa_stats,
        "quality_grade_stats": quality_grade_stats,
        "quality_grade_qids": {
            grade: sorted(qids) for grade, qids in quality_grade_qids.items()
        },
        "coverage_reason_stats": dict(sorted(coverage_reason_stats.items())),
        "coverage_reason_qids": {
            reason: sorted(qids) for reason, qids in sorted(coverage_reason_qids.items())
        },
        "coverage_issue_stats": dict(sorted(coverage_issue_stats.items())),
        "coverage_issue_qids": {
            issue: sorted(qids) for issue, qids in sorted(coverage_issue_qids.items())
        },
        "coverage_matrix": {
            grade: dict(sorted(reasons.items())) for grade, reasons in coverage_matrix.items()
        },
        "provenance": dict(artifacts.provenance),
        "rag": {
            "coverage_status_stats": dict(sorted(rag_coverage_status_stats.items())),
            "coverage_status_qids": {
                status: sorted(qids) for status, qids in sorted(rag_coverage_status_qids.items())
            },
            "answerable_stats": rag_answerable_stats,
            "answerable_qids": {
                status: sorted(qids) for status, qids in rag_answerable_qids.items()
            },
            "failure_code_stats": dict(sorted(rag_failure_code_stats.items())),
            "failure_code_qids": {
                code: sorted(qids) for code, qids in sorted(rag_failure_code_qids.items())
            },
            "contract_violation_count": sum(
                len(qids) for qids in rag_contract_violation_qids.values()
            ) + sum(len(trace.contract_violations) for trace in artifacts.rag_request_traces),
            "contract_violation_qids": {
                violation: sorted(qids)
                for violation, qids in sorted(rag_contract_violation_qids.items())
            },
            "request_ids": sorted({trace.request_id for trace in artifacts.rag_request_traces if trace.request_id}),
            "api_versions": sorted({trace.api_version for trace in artifacts.rag_request_traces if trace.api_version}),
            "rag_versions": sorted({trace.rag_version for trace in artifacts.rag_request_traces if trace.rag_version}),
            "index_versions": sorted({trace.index_version for trace in artifacts.rag_request_traces if trace.index_version}),
            "request_traces": [model_to_dict(trace) for trace in artifacts.rag_request_traces],
        },
        "empty_final_answer_qids": sorted(empty_final_answer_qids),
        "top_failure_notes": [
            {"note": note, "count": count}
            for note, count in sorted(notes_counter.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        "groups": {name: sorted(set(qids)) for name, qids in groups.items()},
        "retrieval": {
            "retried_qids": sorted(set(retrieval["retried_qids"])),
            "retry_helped_qids": sorted(set(retrieval["retry_helped_qids"])),
            "retry_unresolved_qids": sorted(set(retrieval["retry_unresolved_qids"])),
            "attempts_by_qid": retrieval["attempts_by_qid"],
        },
    }


def coverage_reason(answer: Any) -> str:
    return resolved_answer_quality(answer).reason


def sanitize_filename_component(value: str) -> str:
    cleaned = INVALID_FILENAME_CHARS_RE.sub("_", str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(". ")
    return cleaned[:160].rstrip(". ")


def _combined_filename_number(filename: str, output_date: str) -> int | None:
    match = COMBINED_FILENAME_RE.match(filename)
    if not match or match.group("date") != output_date:
        return None
    return int(match.group("number"))


def _combined_status(answer: Any) -> str:
    answer_status = getattr(getattr(answer, "qa", None), "status", "") or "unknown"
    evidence_status = getattr(answer, "answer_status", "") or "UNKNOWN"
    quality = resolved_answer_quality(answer)
    return (
        f"Answer: {answer_status}\n"
        f"QA Grade: {quality.grade}\n"
        f"Coverage: {quality.reason}\n"
        f"RAG Coverage: {getattr(answer, 'rag_coverage_status', '') or 'unknown'}\n"
        f"Answerable: {getattr(answer, 'rag_answerable', None)}\n"
        f"Evidence: {evidence_status}"
    )


def _original_evidence(raw_rag_result: dict[str, Any]) -> str:
    items = raw_rag_result.get("items", []) if isinstance(raw_rag_result, dict) else []
    return "\n\n".join(
        str(item.get("raw_evidence_ko") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("raw_evidence_ko") or "").strip()
    )


def _evidence_sources(sources: list[dict[str, Any]]) -> str:
    return "\n".join(
        _format_source(source)
        for source in sources
        if source.get("source_name") or source.get("source_path")
    )


def _format_source(source: dict[str, Any]) -> str:
    locator = source.get("locator") if isinstance(source.get("locator"), dict) else {}
    metadata = "; ".join(
        f"{field}={source.get(field, '')}"
        for field in (
            "document_id",
            "chunk_id",
            "canonical_source_id",
            "source_tier",
            "source_type",
            "document_status",
            "document_version",
            "effective_date",
            "topic",
            "subtopic",
            "semantic_label",
            "semantic_score",
            "reranker_score",
            "vector_score",
            "score",
            "classification_reason",
        )
        if source.get(field) is not None and source.get(field) != ""
    )
    locator_text = ",".join(
        f"{field}={value}"
        for field, value in locator.items()
        if value is not None and value != ""
    )
    if locator_text:
        metadata = "; ".join(filter(None, [metadata, f"locator({locator_text})"]))
    location = f"{source.get('source_name', '')} | {source.get('source_path', '')}".strip(" |")
    return f"[{metadata}] {location}" if metadata else location


def _writing_style_description(answer: Any) -> str:
    fields = [
        ("Agent profile", getattr(answer, "agent_profile", "")),
        ("Skill", getattr(answer, "skill_name", "")),
        ("Skill version", getattr(answer, "skill_version", "")),
        ("Selection reason", getattr(answer, "skill_selection_reason", "")),
        ("Skill checks", "; ".join(getattr(answer, "skill_checks", []) or [])),
    ]
    return "\n".join(f"{label}: {value}" for label, value in fields if value)
