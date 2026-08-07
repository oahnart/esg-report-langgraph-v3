from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

from esgagents.schemas import (
    NormalizedCompany,
    QuantitativeEvidence,
    QuantitativeMetric,
    QuantitativeResult,
    model_to_dict,
)
from esgagents.template_loader import TemplateRepository


class QuantitativeInputError(RuntimeError):
    pass


HttpRequest = Callable[[str, dict[str, str], float, str, dict[str, Any] | None], Any]

LIST_KEYS = ("items", "data", "records", "evidence", "rows", "results", "metrics")
TOPIC_KEYS = (
    "topic",
    "title",
    "item",
    "name",
    "metric_name",
    "indicator",
    "mapped_item",
    "subcategory",
    "category",
)
VALUE_KEYS = ("value", "amount", "metric_value", "actual", "current_value")
UNIT_KEYS = ("unit",)
SOURCE_KEYS = ("source", "source_pdf", "source_file", "report", "url")
TAG_KEYS = (
    "metric_id",
    "quant_metric_id",
    "mapped_quantitative_id",
    "mapped_item_id",
    "mapped_qualitative_qid",
    "source_id",
    "category",
    "subcategory",
)
QUALITATIVE_QID_KEYS = ("mapped_qualitative_qid", "qualitative_qid", "qid")
SOURCE_ID_KEYS = ("source_id", "qualitative_source_id", "ebx_indicator")
REPORTING_PERIOD_KEYS = ("reporting_period", "period", "fiscal_year", "year")
STOPWORDS = {
    "and",
    "or",
    "the",
    "of",
    "for",
    "with",
    "to",
    "in",
    "a",
    "an",
    "company",
    "year",
}


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _first_value(item: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if not _is_blank(value):
            return value
    return None


def _as_records(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in LIST_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return [raw]
    raise QuantitativeInputError("quantitative input must be a JSON object or array")


def _stable_id(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _page_from_item(item: dict[str, Any]) -> int | None:
    raw_page = item.get("page") or item.get("source_page") or item.get("page_number")
    if _is_blank(raw_page):
        pages = item.get("source_pages") or item.get("pages")
        if isinstance(pages, list) and pages:
            raw_page = pages[0]
        elif isinstance(pages, str):
            match = re.search(r"\d+", pages)
            raw_page = match.group(0) if match else None
    try:
        return int(raw_page) if not _is_blank(raw_page) else None
    except (TypeError, ValueError):
        return None


def _value_from_item(item: dict[str, Any], year: int) -> Any:
    direct = _first_value(item, VALUE_KEYS)
    if not _is_blank(direct):
        return direct
    for key in (f"value_{year}", str(year)):
        value = item.get(key)
        if not _is_blank(value):
            return value
    values = item.get("values")
    if isinstance(values, dict):
        for key in (str(year), year, "current", "latest"):
            value = values.get(key)
            if not _is_blank(value):
                return value
        year_keys = sorted(
            (key for key in values if str(key).isdigit()),
            key=lambda key: int(str(key)),
            reverse=True,
        )
        for key in year_keys:
            value = values.get(key)
            if not _is_blank(value):
                return value
    return None


def normalize_quantitative_evidence(
    raw: Any,
    *,
    company_id: str,
    year: int,
) -> list[QuantitativeEvidence]:
    records: list[QuantitativeEvidence] = []
    for index, item in enumerate(_as_records(raw), start=1):
        payload = item if isinstance(item, dict) else {"value": item}
        topic = str(_first_value(payload, TOPIC_KEYS) or "").strip()
        value = _value_from_item(payload, year)
        unit = _first_value(payload, UNIT_KEYS)
        source = str(_first_value(payload, SOURCE_KEYS) or "").strip()
        metric_id = str(
            payload.get("metric_id")
            or payload.get("quant_metric_id")
            or payload.get("mapped_quantitative_id")
            or ""
        ).strip()
        mapped_qualitative_qid = str(_first_value(payload, QUALITATIVE_QID_KEYS) or "").strip()
        source_id = str(_first_value(payload, SOURCE_ID_KEYS) or "").strip()
        reporting_period = str(_first_value(payload, REPORTING_PERIOD_KEYS) or "").strip()
        raw_tags = payload.get("tags")
        tags = [str(tag) for tag in raw_tags if not _is_blank(tag)] if isinstance(raw_tags, list) else []
        for key in TAG_KEYS:
            if not _is_blank(payload.get(key)):
                tags.append(str(payload[key]))
        confidence_raw = payload.get("confidence", 0.8 if not _is_blank(value) else 0.4)
        try:
            confidence = max(0.0, min(float(confidence_raw), 1.0))
        except (TypeError, ValueError):
            confidence = 0.7
        records.append(
            QuantitativeEvidence(
                evidence_id=str(
                    payload.get("evidence_id")
                    or payload.get("id")
                    or _stable_id(company_id, index, topic, value)
                ),
                metric_id=metric_id,
                mapped_qualitative_qid=mapped_qualitative_qid,
                source_id=source_id,
                reporting_period=reporting_period,
                topic=topic,
                value=value,
                unit=str(unit).strip() if not _is_blank(unit) else None,
                source=source,
                page=_page_from_item(payload),
                confidence=confidence,
                tags=sorted(set(tags)),
                metadata=payload,
            )
        )
    return records


def _normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"\w+", _normalize_text(value), flags=re.UNICODE)
        if len(token) > 1 and token not in STOPWORDS
    }


def _metric_query(metric: QuantitativeMetric) -> str:
    standards = " ".join(str(value) for value in metric.standards.values() if not _is_blank(value))
    return " ".join(
        part
        for part in (
            metric.domain,
            metric.category,
            metric.subcategory,
            metric.item,
            metric.description,
            standards,
        )
        if part
    )


def _evidence_haystack(evidence: QuantitativeEvidence) -> str:
    descriptive_tags = [
        tag
        for tag in evidence.tags
        if not re.fullmatch(r"quant-\d+", _normalize_text(tag))
    ]
    metadata_values = [
        evidence.metadata.get(key)
        for key in (
            "metric_name",
            "indicator",
            "mapped_item",
            "subcategory",
            "category",
            "raw_line",
            "name",
        )
    ]
    return " ".join(
        str(part)
        for part in (
            evidence.topic,
            *descriptive_tags,
            *metadata_values,
        )
        if not _is_blank(part)
    )


def _is_exact_mapping(metric: QuantitativeMetric, evidence: QuantitativeEvidence) -> bool:
    metadata = evidence.metadata
    candidates = [
        evidence.metric_id,
        evidence.evidence_id,
        *evidence.tags,
        metadata.get("metric_id"),
        metadata.get("quant_metric_id"),
        metadata.get("mapped_quantitative_id"),
    ]
    expected = {_normalize_text(metric.metric_id), f"quant-{metric.index:04d}"}
    return any(_normalize_text(candidate) in expected for candidate in candidates if candidate)


def _match_metric(
    metric: QuantitativeMetric,
    evidence_pool: Iterable[QuantitativeEvidence],
) -> tuple[QuantitativeEvidence, float, str] | None:
    query = _metric_query(metric)
    query_tokens = _tokens(query)
    matches: list[tuple[QuantitativeEvidence, float, str]] = []
    for evidence in evidence_pool:
        if _is_blank(evidence.value):
            continue
        exact = _is_exact_mapping(metric, evidence)
        haystack = _evidence_haystack(evidence)
        evidence_tokens = _tokens(haystack)
        overlap = query_tokens & evidence_tokens
        if not exact and not overlap:
            continue
        if exact:
            score = 0.99
            reason = "exact_metric_mapping"
        else:
            denominator = math.sqrt(max(len(query_tokens), 1) * max(len(evidence_tokens), 1))
            score = 0.65 * (len(overlap) / denominator) + 0.15 * evidence.confidence
            reason = "metric_match"
        if metric.unit and evidence.unit and _normalize_text(metric.unit) == _normalize_text(evidence.unit):
            score += 0.08
        normalized_haystack = _normalize_text(haystack)
        if metric.item and _normalize_text(metric.item) in normalized_haystack:
            score += 0.12
        if metric.category and _normalize_text(metric.category) in normalized_haystack:
            score += 0.05
        matches.append((evidence, round(min(score, 1.0), 3), reason))
    matches.sort(key=lambda item: item[1], reverse=True)
    return matches[0] if matches else None


def map_quantitative_values(
    metrics: Iterable[QuantitativeMetric],
    evidence_pool: list[QuantitativeEvidence],
) -> list[QuantitativeResult]:
    results: list[QuantitativeResult] = []
    for metric in metrics:
        matched = _match_metric(metric, evidence_pool)
        if matched:
            evidence, score, reason = matched
            results.append(
                QuantitativeResult(
                    metric_id=metric.metric_id,
                    index=metric.index,
                    metric_name=metric.item or metric.subcategory or metric.metric_id,
                    value=evidence.value,
                    unit=evidence.unit or metric.unit,
                    source=evidence.source,
                    status="filled",
                    confidence=score,
                    metadata={
                        "evidence_id": evidence.evidence_id,
                        "match_reason": reason,
                        "evidence_topic": evidence.topic,
                        "source_page": evidence.page,
                        "raw_metric_id": evidence.metadata.get("metric_id"),
                        "mapped_item_id": evidence.metadata.get("mapped_item_id"),
                        "mapped_qualitative_qid": evidence.mapped_qualitative_qid,
                        "source_id": evidence.source_id,
                        "reporting_period": evidence.reporting_period,
                    },
                )
            )
        else:
            results.append(
                QuantitativeResult(
                    metric_id=metric.metric_id,
                    index=metric.index,
                    metric_name=metric.item or metric.subcategory or metric.metric_id,
                    unit=metric.unit,
                    status="missing",
                    confidence=0.0,
                    metadata={"reason": "No company quantitative data matched this metric."},
                )
            )
    return results


def _is_quant_210_response(raw: Any) -> bool:
    return (
        isinstance(raw, dict)
        and raw.get("kind") == "quantitative"
        and raw.get("catalog_pack") == "quant_210"
    )


def _validate_quant_210_response(raw: dict[str, Any], company: NormalizedCompany) -> list[dict[str, Any]]:
    if raw.get("company_id") != company.company_id:
        raise QuantitativeInputError(
            "quant_210 response company_id does not match request"
        )
    if int(raw.get("year") or 0) != company.year:
        raise QuantitativeInputError("quant_210 response year does not match request")
    items = raw.get("items")
    if not isinstance(items, list):
        raise QuantitativeInputError("quant_210 response items must be an array")
    total = raw.get("total")
    if total is not None and int(total) != len(items):
        raise QuantitativeInputError("quant_210 response total does not match items length")
    return [item for item in items if isinstance(item, dict)]


def _answer_status(item: dict[str, Any]) -> str:
    answer = item.get("answer")
    if not isinstance(answer, dict):
        return "missing"
    return str(answer.get("status") or "missing").strip().lower()


def _answer_payload(item: dict[str, Any]) -> dict[str, Any]:
    answer = item.get("answer")
    return answer if isinstance(answer, dict) else {}


def _best_evidence_source(answer: dict[str, Any]) -> str:
    if answer.get("source"):
        return str(answer.get("source") or "")
    evidence = answer.get("evidence")
    if isinstance(evidence, list) and evidence:
        first = evidence[0]
        if isinstance(first, dict):
            return str(first.get("source") or "")
    return ""


def _evidence_locator(answer: dict[str, Any]) -> dict[str, Any]:
    evidence = answer.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return {}
    first = evidence[0]
    if not isinstance(first, dict):
        return {}
    return {
        key: first.get(key)
        for key in (
            "page",
            "section_path",
            "sheet",
            "cell",
            "year_column",
            "row_context",
            "record_id",
            "source_path",
        )
        if first.get(key) not in (None, "")
    }


def map_quant_210_values(
    raw: dict[str, Any],
    *,
    company: NormalizedCompany,
) -> tuple[list[QuantitativeResult], dict[str, int]]:
    items = _validate_quant_210_response(raw, company)
    results: list[QuantitativeResult] = []
    counts = {"answered": 0, "missing": 0, "needs_confirmation": 0}
    for index, item in enumerate(items, start=1):
        status = _answer_status(item)
        if status not in counts:
            counts["missing"] += 1
            status = "missing"
        else:
            counts[status] += 1

        answer = _answer_payload(item)
        publishable = status == "answered"
        metric_id = str(item.get("item_id") or f"quant_210_{index}")
        value = answer.get("value") if publishable else None
        source = _best_evidence_source(answer) if publishable else ""
        confidence = {
            "high": 1.0,
            "medium": 0.7,
            "low": 0.3,
        }.get(str(answer.get("confidence") or "").lower(), 0.0 if not publishable else 0.7)
        answer_reason = str(answer.get("reason") or "")
        if status == "needs_confirmation":
            answer_reason = "needs_confirmation: value withheld pending unit/customer confirmation"
        metadata = {
            "catalog_pack": raw.get("catalog_pack"),
            "api_kind": raw.get("kind"),
            "mapped_qualitative_qid": (
                item.get("mapped_qualitative_qid")
                or answer.get("mapped_qualitative_qid")
                or ""
            ),
            "source_id": item.get("source_id") or answer.get("source_id") or "",
            "domain": item.get("domain") or "",
            "category": item.get("category") or "",
            "subcategory": item.get("subcategory") or "",
            "question": item.get("question") or "",
            "answer_status": status,
            "answer_reason": answer_reason,
            "answer_text": answer.get("text") if publishable else None,
            "normalized_value": answer.get("normalized_value") if publishable else None,
            "year": answer.get("year") or raw.get("year"),
            "evidence": answer.get("evidence") if publishable else [],
            "evidence_locator": _evidence_locator(answer) if publishable else {},
            "standards": item.get("standards") or {},
        }
        if status == "needs_confirmation":
            metadata["needs_confirmation"] = True
            metadata["withheld_value_reason"] = answer_reason
        results.append(
            QuantitativeResult(
                metric_id=metric_id,
                index=index,
                metric_name=item.get("item") or item.get("subcategory") or metric_id,
                value=value,
                unit=answer.get("unit") or item.get("unit"),
                source=source,
                status="filled" if publishable else "missing",
                confidence=confidence if publishable else 0.0,
                metadata=metadata,
            )
        )
    stats = {
        "total": len(results),
        "filled": counts["answered"],
        "missing": counts["missing"],
        "needs_confirmation": counts["needs_confirmation"],
        "published": counts["answered"],
    }
    return results, stats


class QuantitativeInputLoader:
    def __init__(self, config: dict[str, Any], http_get: HttpRequest | None = None):
        self.config = config
        self.http_request = http_get

    def load(self, company: NormalizedCompany) -> tuple[Any, str]:
        mode = str(self.config.get("quantitative_input_mode", "file")).strip().lower()
        if mode == "file":
            return self._load_file(company)
        if mode == "api":
            return self._load_api(company)
        raise QuantitativeInputError(
            "ESG_QUANTITATIVE_INPUT_MODE must be either 'file' or 'api'"
        )

    def _load_file(self, company: NormalizedCompany) -> tuple[Any, str]:
        path = (
            Path(self.config["quantitative_input_dir"])
            / company.company_id
            / str(company.year)
            / "quantitative_raw.json"
        )
        if not path.exists():
            return None, str(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuantitativeInputError(f"invalid quantitative input file {path}: {exc}") from exc
        if not isinstance(raw, (dict, list)):
            raise QuantitativeInputError(f"quantitative input file {path} must contain an object or array")
        return raw, str(path)

    def _load_api(self, company: NormalizedCompany) -> tuple[Any, str]:
        base_url = str(self.config.get("quantitative_api_base_url") or "").rstrip("/")
        if not base_url:
            raise QuantitativeInputError(
                "ESG_QUANTITATIVE_API_BASE_URL is required in api mode"
            )
        method = str(self.config.get("quantitative_api_method") or "GET").strip().upper()
        if method not in {"GET", "POST"}:
            raise QuantitativeInputError(
                "ESG_QUANTITATIVE_API_METHOD must be either 'GET' or 'POST'"
            )
        path = str(
            self.config.get("quantitative_api_path")
            or "/companies/{company_id}/{year}/quantitative"
        ).format(
            company_id=company.company_id,
            company_name=company.company_name,
            year=company.year,
        )
        url = f"{base_url}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        api_key = str(self.config.get("quantitative_api_key") or "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        timeout = float(self.config.get("quantitative_api_timeout_seconds", 30))
        payload = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            payload = {
                "company_id": company.company_id,
                "company_name": company.company_name,
                "year": company.year,
            }
        try:
            if self.http_request:
                raw = self.http_request(url, headers, timeout, method, payload)
            elif method == "POST":
                response = requests.post(url, json=payload, headers=headers, timeout=timeout)
                response.raise_for_status()
                raw = response.json()
            else:
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                raw = response.json()
        except Exception as exc:
            raise QuantitativeInputError(f"quantitative API request failed for {url}: {exc}") from exc
        if not isinstance(raw, (dict, list)):
            raise QuantitativeInputError("quantitative API must return a JSON object or array")
        snapshot_path = (
            Path(self.config["cache_dir"])
            / "quantitative"
            / company.company_id
            / str(company.year)
            / company.run_id
            / "api_snapshot_quantitative.json"
        )
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return raw, str(snapshot_path)


class QuantitativeAgent:
    def __init__(
        self,
        config: dict[str, Any],
        templates: TemplateRepository,
        input_loader: QuantitativeInputLoader | None = None,
    ):
        self.config = config
        self.templates = templates
        self.input_loader = input_loader or QuantitativeInputLoader(config)

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if not bool(self.config.get("quantitative_output_enabled", False)):
            return {
                "quantitative_results": [],
                "quantitative_stats": {},
                "quantitative_source_path": "",
                "metric_qid_bridge_results": {},
            }

        company: NormalizedCompany = state["company"]
        raw, source_path = self.input_loader.load(company)
        is_quant_210 = _is_quant_210_response(raw)
        if is_quant_210:
            results, stats = map_quant_210_values(raw, company=company)
        else:
            metrics = [
                QuantitativeMetric.model_validate(item)
                for item in self.templates.load_quantitative_items()
            ]
            evidence = normalize_quantitative_evidence(
                raw,
                company_id=company.company_id,
                year=company.year,
            )
            results = map_quantitative_values(metrics, evidence)
            filled = sum(1 for result in results if result.status == "filled")
            stats = {
                "total": len(results),
                "filled": filled,
                "missing": len(results) - filled,
            }
        return {
            "quantitative_results": [model_to_dict(result) for result in results],
            "quantitative_stats": stats,
            "quantitative_source_path": source_path,
            "metric_qid_bridge_results": {},
        }

    def _bridge_metric_qids(
        self,
        state: dict[str, Any],
        results: list[QuantitativeResult],
        quantitative_source_path: str,
        exact_only: bool = False,
    ) -> dict[str, Any]:
        return {}

    def _match_metric_question(
        self,
        planned: Any,
        filled_results: list[QuantitativeResult],
        exact_only: bool = False,
    ) -> list[QuantitativeResult]:
        exact = [
            result
            for result in filled_results
            if str(result.metadata.get("mapped_qualitative_qid") or "").strip() == planned.id
            or (
                getattr(planned, "source_id", "")
                and str(result.metadata.get("source_id") or "").strip() == getattr(planned, "source_id", "")
            )
        ]
        if exact:
            return sorted(exact, key=lambda result: result.confidence, reverse=True)
        if exact_only:
            return []

        question_tokens = _tokens(
            " ".join(
                str(value or "")
                for value in (
                    getattr(planned, "category_ko", ""),
                    getattr(planned, "item_ko", ""),
                    getattr(planned, "description_ko", ""),
                )
            )
        )
        scored = []
        for result in filled_results:
            haystack = " ".join(
                str(value or "")
                for value in (
                    result.metric_name,
                    result.metadata.get("evidence_topic"),
                    result.metadata.get("mapped_item_id"),
                    result.metadata.get("raw_metric_id"),
                )
            )
            overlap = question_tokens & _tokens(haystack)
            if not overlap:
                continue
            score = len(overlap) + result.confidence
            scored.append((score, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [result for _, result in scored[:3]]


def _is_metric_question(planned: Any) -> bool:
    pillar = str(getattr(planned, "pillar", "") or "").casefold()
    return "metric" in pillar or "지표" in pillar


def _metric_bridge_answer(
    company: NormalizedCompany,
    planned: Any,
    results: list[QuantitativeResult],
    period_defaulted: bool,
) -> str:
    clauses = []
    for result in results:
        period = str(result.metadata.get("reporting_period") or "").strip() or str(company.year)
        unit = f" {result.unit}" if result.unit else ""
        source = str(result.source or result.metadata.get("evidence_topic") or "").strip()
        source_clause = f" 출처는 {source}입니다" if source else " 정량 입력자료를 기준으로 작성되었습니다"
        clauses.append(f"보고기간 {period}의 {result.metric_name}은(는) {result.value}{unit}입니다.{source_clause}")
    suffix = " 정량 입력자료를 기준으로 작성되었습니다."
    if period_defaulted:
        suffix = f" 보고기간은 회사 입력 연도({company.year})를 기준으로 보완했습니다."
    question = getattr(planned, "item_ko", "") or "해당 지표"
    return f"{question}에 대해 " + "; ".join(clauses) + suffix


def _legacy_metric_bridge_answer(
    company: NormalizedCompany,
    planned: Any,
    results: list[QuantitativeResult],
    period_defaulted: bool,
) -> str:
    clauses = []
    for result in results:
        period = str(result.metadata.get("reporting_period") or "").strip() or str(company.year)
        unit = f" {result.unit}" if result.unit else ""
        clauses.append(f"{period} {result.metric_name}은(는) {result.value}{unit}입니다")
    suffix = " 정량 입력자료를 기준으로 작성되었습니다."
    if period_defaulted:
        suffix = f" 보고기간은 회사 입력 연도({company.year})를 기준으로 보완했습니다."
    return f"{getattr(planned, 'item_ko', '해당 지표')}에 대해 " + "; ".join(clauses) + "." + suffix
