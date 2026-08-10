from __future__ import annotations

import time
import re
from typing import Any, Callable

import requests
from pydantic import ValidationError
from requests import HTTPError, RequestException

from esgagents.schemas import RagQuestionResult, RagResponse


class TeamRagError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str = "",
        request_id: str = "",
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        self.retryable = retryable


Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]

_RETRYABLE_HTTP_STATUSES = {429, 500, 503, 504}
_REQUIRED_V3_RESPONSE_FIELDS = {
    "company_id",
    "request_id",
    "api_version",
    "rag_version",
    "index_version",
    "generated_at",
    "latency_ms",
    "results",
}
_REQUIRED_V3_RESULT_FIELDS = {
    "question_id",
    "normalized_answer_ko",
    "answer_status",
    "items",
}
_REQUIRED_V3_EVIDENCE_FIELDS = {
    "score",
    "vector_score",
    "reranker_score",
    "semantic_score",
    "semantic_label",
    "semantic_reason",
    "raw_evidence_ko",
    "source_name",
    "source_path",
    "document_id",
    "chunk_id",
    "canonical_source_id",
    "source_type",
    "document_status",
    "source_tier",
    "document_version",
    "effective_date",
    "topic",
    "subtopic",
    "locator",
}
_V3_ANSWER_STATUSES = {
    "high_confidence",
    "medium_confidence",
    "thin_but_usable",
    "insufficient",
    "no_evidence",
}
_V3_PILLARS = {"strategy", "governance", "risk_management", "metrics"}
_V3_SEMANTIC_LABELS = {"useful", "partial", "metric_row", "weak", "irrelevant", "no_match"}
_V3_SOURCE_TYPES = {
    "policy",
    "policy_procedure",
    "operating_procedure",
    "manual",
    "operational_record",
    "performance_report",
    "board_record",
    "committee_record",
    "external_assessment",
    "certification",
    "consultant_material",
    "proposal",
    "unknown",
}
_V3_DOCUMENT_STATUSES = {
    "approved",
    "effective",
    "operational",
    "historical",
    "external_assessment",
    "draft",
    "proposal",
    "consultant_material",
    "superseded",
    "unknown",
}
_V3_SOURCE_TIERS = {
    "tier_1_governing",
    "tier_2_operational",
    "tier_3_assessment",
    "tier_4_draft",
    "tier_unknown",
}
_TRACEABLE_SOURCE_RE = re.compile(
    r"(?:^https?://|\.(?:pdf|pptx?|docx?|xlsx?|csv|tsv|html?|txt)(?:[?#].*)?$)",
    re.IGNORECASE,
)
_V3_FAILURE_CODES = {
    "NO_EVIDENCE",
    "ALL_EVIDENCE_WEAK",
    "MISSING_REQUIRED_FACETS",
    "WRONG_TOPIC",
    "SCOPE_LIMITED",
    "DRAFT_ONLY",
    "ASSESSMENT_ONLY",
    "MISSING_SOURCE_PATH",
    "CONFLICTING_EVIDENCE",
    "UNSUPPORTED_REPORTING_PERIOD",
    "INTERNAL_RETRIEVAL_ERROR",
}
_V3_UNANSWERABLE_FAILURE_CODES = _V3_FAILURE_CODES - {
    "SCOPE_LIMITED",
    "DRAFT_ONLY",
    "ASSESSMENT_ONLY",
}


class TeamRagClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int | float = 30,
        max_retries: int = 2,
        transport: Transport | None = None,
        qualitative_path: str = "/qualitative/evidence/v3",
        request_contract: str = "new",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.transport = transport
        self.qualitative_path = f"/{qualitative_path.strip('/')}"
        normalized_contract = str(request_contract or "new").strip().casefold()
        if normalized_contract not in {"new", "legacy"}:
            raise ValueError("request_contract must be 'new' or 'legacy'")
        self.request_contract = normalized_contract
        self.session = requests.Session()

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}{self.qualitative_path}"

    @property
    def is_v3(self) -> bool:
        return self.qualitative_path.rstrip("/").endswith("/v3")

    def fetch_evidence(
        self,
        company_id: str,
        item_ids: list[str],
        top_k: int,
        year: int,
    ) -> RagResponse:
        if not item_ids and self.request_contract == "legacy":
            return RagResponse(company_id=company_id, results=[])
        if self.request_contract == "new":
            payload = {
                "company_id": company_id,
                "question_ids": item_ids,
                "top_k": top_k,
            }
        else:
            payload = {
                "company_id": company_id,
                "item_ids": item_ids,
                "top_k": top_k,
                "year": year,
            }
        data = self._post(payload)
        if self.is_v3:
            return self._parse_v3_response(data, company_id=company_id, item_ids=item_ids)
        return RagResponse.model_validate(data)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.transport:
            last_error: Exception | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    data = self.transport(self.endpoint, payload, float(self.timeout_seconds))
                    if not isinstance(data, dict):
                        raise TeamRagError("Team RAG returned a non-object JSON payload")
                    return data
                except RequestException as exc:
                    last_error = exc
                    if attempt < self.max_retries:
                        time.sleep(0.25 * (attempt + 1))
                        continue
                except Exception:
                    raise
                break
            raise TeamRagError(
                f"Team RAG request failed: {last_error}",
                retryable=True,
            ) from last_error
        if not self.base_url:
            raise TeamRagError("TEAM_RAG_BASE_URL is required for live RAG calls")

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            retryable = False
            try:
                response = self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise TeamRagError("Team RAG returned a non-object JSON payload")
                return data
            except HTTPError as exc:
                last_error = self._format_http_error(exc, payload)
                retryable = bool(getattr(last_error, "retryable", False))
            except RequestException as exc:
                last_error = exc
                retryable = True
            except Exception as exc:
                last_error = exc
                retryable = False

            if not retryable or attempt >= self.max_retries:
                break
            time.sleep(0.25 * (attempt + 1))

        if isinstance(last_error, TeamRagError):
            raise last_error
        raise TeamRagError(
            f"Team RAG request failed: {last_error}",
            retryable=isinstance(last_error, RequestException),
        ) from last_error

    def _parse_v3_response(
        self,
        data: dict[str, Any],
        *,
        company_id: str,
        item_ids: list[str],
    ) -> RagResponse:
        requested_ids = list(dict.fromkeys(item_ids))
        response_violations = [
            f"missing response field: {field}"
            for field in sorted(_REQUIRED_V3_RESPONSE_FIELDS - data.keys())
        ]
        response_violations.extend(
            f"response field must not be null: {field}"
            for field in sorted(_REQUIRED_V3_RESPONSE_FIELDS)
            if field in data and data.get(field) is None
        )

        if data.get("company_id") != company_id:
            raise TeamRagError(
                "Team RAG v3 contract violation: response company_id does not match request",
                error_code="CLIENT_CONTRACT_COMPANY_MISMATCH",
            )

        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise TeamRagError(
                "Team RAG v3 contract violation: results must be an array",
                error_code="CLIENT_CONTRACT_INVALID_RESULTS",
            )

        result_ids = [raw.get("question_id") for raw in raw_results if isinstance(raw, dict)]
        duplicates = sorted({qid for qid in result_ids if qid and result_ids.count(qid) > 1})
        if duplicates:
            raise TeamRagError(
                f"Team RAG v3 contract violation: duplicate question IDs: {duplicates}",
                error_code="CLIENT_CONTRACT_DUPLICATE_RESULT",
            )
        unrequested = sorted(
            {str(qid) for qid in result_ids if requested_ids and qid not in requested_ids}
        )
        if unrequested:
            raise TeamRagError(
                f"Team RAG v3 contract violation: unrequested question IDs: {unrequested}",
                error_code="CLIENT_CONTRACT_UNREQUESTED_RESULT",
            )

        parsed_results: dict[str, RagQuestionResult] = {}
        for index, raw_result in enumerate(raw_results):
            if not isinstance(raw_result, dict):
                response_violations.append(f"result at index {index} is not an object")
                continue
            qid = str(raw_result.get("question_id") or "")
            if not qid:
                response_violations.append(f"result at index {index} has no question_id")
                continue
            parsed_results[qid] = self._parse_v3_result(raw_result)

        if not requested_ids:
            normalized = dict(data)
            normalized["company_id"] = company_id
            normalized["results"] = list(parsed_results.values())
            normalized["client_contract_violations"] = response_violations
            return RagResponse.model_validate(normalized)

        ordered_results: list[RagQuestionResult] = []
        for qid in requested_ids:
            result = parsed_results.get(qid)
            if result is None:
                warning = f"requested question_id {qid} was omitted by Team RAG"
                result = RagQuestionResult(
                    question_id=qid,
                    answer_status="insufficient",
                    coverage_status="no_evidence",
                    answerable=False,
                    failure_code="CLIENT_WARNING_SKIPPED_QID",
                    failure_reason=warning,
                    retrieval_notes=["Created locally because Team RAG omitted this question."],
                    client_contract_warnings=[warning],
                    is_v3_payload=True,
                )
            ordered_results.append(result)

        normalized = dict(data)
        normalized["company_id"] = company_id
        normalized["results"] = ordered_results
        normalized["client_contract_violations"] = response_violations
        try:
            return RagResponse.model_validate(normalized)
        except ValidationError as exc:
            raise TeamRagError(
                f"Team RAG v3 contract violation: invalid response metadata: {exc}",
                error_code="CLIENT_CONTRACT_INVALID_RESPONSE",
            ) from exc

    def _parse_v3_result(self, raw: dict[str, Any]) -> RagQuestionResult:
        violations = [
            f"missing result field: {field}"
            for field in sorted(_REQUIRED_V3_RESULT_FIELDS - raw.keys())
        ]
        violations.extend(
            f"result field must not be null: {field}"
            for field in sorted(_REQUIRED_V3_RESULT_FIELDS)
            if field in raw and raw.get(field) is None
        )
        warnings: list[str] = []
        coverage = raw.get("coverage")
        if "coverage" in raw and not isinstance(coverage, dict):
            violations.append("coverage must be an object")

        items = raw.get("items")
        if "items" in raw and not isinstance(items, list):
            violations.append("items must be an array")
        elif isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    violations.append(f"evidence item at index {index} is not an object")
                    continue
                missing = sorted(_REQUIRED_V3_EVIDENCE_FIELDS - item.keys())
                violations.extend(f"evidence item {index} missing field: {field}" for field in missing)
                nullable_evidence_fields = {
                    "vector_score",
                    "reranker_score",
                    "document_version",
                    "effective_date",
                }
                violations.extend(
                    f"evidence item {index} field must not be null: {field}"
                    for field in sorted(_REQUIRED_V3_EVIDENCE_FIELDS - nullable_evidence_fields)
                    if field in item and item.get(field) is None
                )
                if "locator" in item and not isinstance(item.get("locator"), dict):
                    violations.append(f"evidence item {index} locator must be an object")
                if not _TRACEABLE_SOURCE_RE.search(str(item.get("source_path") or "").strip()):
                    has_fallback = bool(str(item.get("canonical_source_id") or "").strip()) or bool(
                        str(item.get("document_id") or "").strip()
                        and str(item.get("chunk_id") or "").strip()
                    )
                    message = f"evidence item {index} has invalid source_path"
                    if has_fallback:
                        warnings.append(message)
                    else:
                        violations.append(message)
                facts = item.get("facts", [])
                if "facts" in item and not isinstance(facts, list):
                    violations.append(f"evidence item {index} facts must be an array")
                elif isinstance(facts, list):
                    for fact_index, fact in enumerate(facts):
                        if not isinstance(fact, dict):
                            violations.append(
                                f"evidence item {index} fact {fact_index} must be an object"
                            )
                        elif fact.get("value_role", "unknown") not in {"actual", "target", "unknown"}:
                            violations.append(
                                f"evidence item {index} fact {fact_index} has invalid value_role"
                            )
                if item.get("semantic_label") not in _V3_SEMANTIC_LABELS:
                    violations.append(f"evidence item {index} has invalid semantic_label")
                if item.get("source_type") not in _V3_SOURCE_TYPES:
                    violations.append(f"evidence item {index} has invalid source_type")
                if item.get("document_status") not in _V3_DOCUMENT_STATUSES:
                    violations.append(f"evidence item {index} has invalid document_status")
                if item.get("source_tier") not in _V3_SOURCE_TIERS:
                    violations.append(f"evidence item {index} has invalid source_tier")
                score = item.get("score")
                if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
                    violations.append(f"evidence item {index} score must be between 0 and 1")

        status = raw.get("coverage_status")
        answerable = raw.get("answerable")
        answer_status = raw.get("answer_status")
        failure_code = raw.get("failure_code")
        if "pillar" in raw and raw.get("pillar") is not None and raw.get("pillar") not in _V3_PILLARS:
            warnings.append("invalid optional pillar")
        if answer_status not in _V3_ANSWER_STATUSES:
            violations.append("invalid answer_status")
        if status in {"complete", "partial"} and answerable is not None and answerable is not True:
            warnings.append(f"coverage_status={status} conflicts with answerable=false")
        if status in {"insufficient", "no_evidence"} and answerable is not None and answerable is not False:
            warnings.append(f"coverage_status={status} conflicts with answerable=true")
        expected_answer_statuses = {
            "complete": {"high_confidence", "medium_confidence"},
            "partial": {"thin_but_usable", "medium_confidence"},
            "insufficient": {"insufficient"},
            "no_evidence": {"no_evidence"},
        }
        if status is not None and (
            status == "partial"
            and answer_status == "medium_confidence"
            and failure_code != "SCOPE_LIMITED"
        ):
            warnings.append("partial medium_confidence normally uses failure_code=SCOPE_LIMITED")
        elif status in expected_answer_statuses and answer_status not in expected_answer_statuses[status]:
            warnings.append(
                f"answer_status={answer_status or 'empty'} conflicts with coverage_status={status}"
            )
        if status == "no_evidence" and items:
            warnings.append("coverage_status=no_evidence conflicts with non-empty items")
        if status == "complete" and failure_code is not None:
            warnings.append("coverage_status=complete normally uses failure_code=null")
        if failure_code is not None and failure_code not in _V3_FAILURE_CODES:
            warnings.append("invalid optional failure_code")
        if failure_code in _V3_UNANSWERABLE_FAILURE_CODES and answerable is True:
            warnings.append(f"failure_code={failure_code} conflicts with answerable=true")

        candidate = dict(raw)
        candidate["is_v3_payload"] = True
        candidate["client_contract_warnings"] = list(dict.fromkeys(warnings))
        if candidate.get("pillar") not in _V3_PILLARS:
            candidate["pillar"] = None
        if candidate.get("coverage_status") not in {
            "complete",
            "partial",
            "insufficient",
            "no_evidence",
        }:
            candidate["coverage_status"] = None
        if not isinstance(candidate.get("answerable"), bool):
            candidate["answerable"] = None
        confidence = candidate.get("retrieval_confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            candidate["retrieval_confidence"] = None
        if not isinstance(candidate.get("items"), list):
            candidate["items"] = []
        if not isinstance(candidate.get("coverage"), dict):
            candidate["coverage"] = {}
        for key in ("covered_facets", "missing_facets", "retrieval_notes"):
            if not isinstance(candidate.get(key), list):
                candidate[key] = []
        if violations:
            original_failure = str(candidate.get("failure_reason") or "").strip()
            candidate.update(
                answer_status="insufficient",
                coverage_status="insufficient" if candidate["items"] else "no_evidence",
                answerable=False,
                failure_code="CLIENT_CONTRACT_VIOLATION",
                failure_reason="; ".join(filter(None, [original_failure, *violations])),
                client_contract_violations=violations,
                client_contract_warnings=list(dict.fromkeys(warnings)),
            )
        try:
            return RagQuestionResult.model_validate(candidate)
        except ValidationError as exc:
            validation_violations = [
                f"schema validation error at {'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ]
            all_violations = list(dict.fromkeys([*violations, *validation_violations]))
            return RagQuestionResult(
                question_id=str(raw.get("question_id") or ""),
                question_ko=str(raw.get("question_ko") or ""),
                normalized_answer_ko="",
                answer_status="insufficient",
                coverage_status="no_evidence",
                answerable=False,
                failure_code="CLIENT_CONTRACT_VIOLATION",
                failure_reason="; ".join(all_violations),
                retrieval_notes=["Invalid v3 fields were discarded by the client."],
                client_contract_violations=all_violations,
                client_contract_warnings=list(dict.fromkeys(warnings)),
                items=[],
                is_v3_payload=True,
            )

    def _format_http_error(self, exc: HTTPError, payload: dict[str, Any]) -> TeamRagError:
        response = exc.response
        status = response.status_code if response is not None else None
        reason = response.reason if response is not None else ""
        body = ""
        request_id = ""
        error_code = ""
        error_message = ""
        if response is not None:
            try:
                error_payload = response.json()
            except (ValueError, TypeError):
                error_payload = None
            if isinstance(error_payload, dict):
                request_id = str(error_payload.get("request_id") or "")
                error = error_payload.get("error")
                if isinstance(error, dict):
                    error_code = str(error.get("code") or "")
                    error_message = str(error.get("message") or "")
            body = response.text.strip()
            if len(body) > 1000:
                body = f"{body[:1000]}..."

        item_ids = payload.get("question_ids") or payload.get("item_ids") or []
        payload_summary = {
            "company_id": payload.get("company_id"),
            "item_id_count": len(item_ids) if isinstance(item_ids, list) else "unknown",
            "item_ids_sample": item_ids[:5] if isinstance(item_ids, list) else item_ids,
            "top_k": payload.get("top_k"),
            "year": payload.get("year"),
            "request_contract": self.request_contract,
        }
        status_label = status if status is not None else "unknown"
        message = f"HTTP {status_label} {reason}".strip()
        if error_code or error_message or request_id:
            message = (
                f"{message}; error_code={error_code or 'unknown'}; "
                f"request_id={request_id or 'unknown'}; error_message={error_message or 'unknown'}"
            )
        elif body:
            message = f"{message}; response_body={body}"
        message = f"{message}; payload_summary={payload_summary}"
        return TeamRagError(
            message,
            status_code=status,
            error_code=error_code,
            request_id=request_id,
            retryable=status in _RETRYABLE_HTTP_STATUSES,
        )
