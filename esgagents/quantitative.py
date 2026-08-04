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
    EvidenceItem,
    NormalizedCompany,
    QuantitativeEvidence,
    QuantitativeMetric,
    QuantitativeResult,
    RagQuestionResult,
    model_to_dict,
)
from esgagents.template_loader import TemplateRepository


class QuantitativeInputError(RuntimeError):
    pass


HttpGet = Callable[[str, dict[str, str], float], Any]

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


class QuantitativeInputLoader:
    def __init__(self, config: dict[str, Any], http_get: HttpGet | None = None):
        self.config = config
        self.http_get = http_get

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
        path = str(
            self.config.get("quantitative_api_path")
            or "/companies/{company_id}/{year}/quantitative"
        ).format(company_id=company.company_id, year=company.year)
        url = f"{base_url}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        api_key = str(self.config.get("quantitative_api_key") or "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        timeout = float(self.config.get("quantitative_api_timeout_seconds", 30))
        try:
            if self.http_get:
                raw = self.http_get(url, headers, timeout)
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
        company: NormalizedCompany = state["company"]
        metrics = [
            QuantitativeMetric.model_validate(item)
            for item in self.templates.load_quantitative_items()
        ]
        raw, source_path = self.input_loader.load(company)
        evidence = normalize_quantitative_evidence(
            raw,
            company_id=company.company_id,
            year=company.year,
        )
        results = map_quantitative_values(metrics, evidence)
        filled = sum(1 for result in results if result.status == "filled")
        return {
            "quantitative_results": [model_to_dict(result) for result in results],
            "quantitative_stats": {
                "total": len(results),
                "filled": filled,
                "missing": len(results) - filled,
            },
            "quantitative_source_path": source_path,
            **self._bridge_metric_qids(state, results, source_path),
        }

    def _bridge_metric_qids(
        self,
        state: dict[str, Any],
        results: list[QuantitativeResult],
        quantitative_source_path: str,
    ) -> dict[str, Any]:
        if not bool(self.config.get("metric_qid_bridge_enabled", True)):
            return {}

        company: NormalizedCompany = state["company"]
        planned_metrics = [
            planned
            for planned in state.get("planned_questions", [])
            if _is_metric_question(planned)
        ]
        if not planned_metrics:
            return {}

        rag_results = dict(state.get("rag_results", {}))
        evidence_gate = dict(state.get("evidence_gate", {}))
        normalized_evidence = {
            qid: {
                "items": list(value.get("items", [])),
                "evidence_summary": value.get("evidence_summary", ""),
                "sources": list(value.get("sources", [])),
            }
            for qid, value in state.get("normalized_evidence", {}).items()
        }
        quality_flags = {qid: list(flags) for qid, flags in state.get("quality_flags", {}).items()}
        bridge_results: dict[str, list[str]] = {}

        filled = [result for result in results if result.status == "filled"]
        for planned in planned_metrics:
            matches = self._match_metric_question(planned, filled)
            if not matches:
                quality_flags[planned.id] = sorted(
                    set(quality_flags.get(planned.id, []) + ["missing_quantitative_metric_result"])
                )
                bridge_results[planned.id] = []
                continue

            period_defaulted = False
            items: list[EvidenceItem] = []
            sources = []
            summary_parts = []
            for result in matches[:5]:
                period = str(result.metadata.get("reporting_period") or "").strip()
                if not period:
                    period = str(company.year)
                    period_defaulted = True
                source_path = result.source or quantitative_source_path
                text = (
                    f"Quantitative metric ({period}): {result.metric_name} = "
                    f"{result.value} {result.unit or ''}. Source: {source_path}. "
                    f"Metric ID: {result.metric_id}."
                ).strip()
                item = EvidenceItem(
                    score=result.confidence,
                    raw_evidence_ko=text,
                    source_name=Path(source_path).name if source_path else "quantitative_input",
                    source_path=source_path,
                    semantic_label="useful",
                    semantic_reason="quantitative_metric_bridge",
                    semantic_score=result.confidence,
                    canonical_source_id=f"quant_{result.metric_id.lower()}",
                    source_tier="tier_2_operational",
                    source_type="quantitative_metric",
                    document_status="operational",
                    classification_reason="quantitative_bridge",
                )
                items.append(item)
                summary_parts.append(text)
                source = {
                    "source_name": item.source_name,
                    "source_path": item.source_path,
                    "canonical_source_id": item.canonical_source_id,
                    "source_tier": item.source_tier,
                    "source_type": item.source_type,
                    "document_status": item.document_status,
                    "classification_reason": item.classification_reason,
                }
                if source not in sources:
                    sources.append(source)

            existing = normalized_evidence.get(planned.id, {"items": [], "evidence_summary": "", "sources": []})
            existing["items"] = [*items, *existing.get("items", [])]
            existing["evidence_summary"] = "\n".join(
                part
                for part in [*summary_parts, existing.get("evidence_summary", "")]
                if part
            )
            existing_sources = list(existing.get("sources", []))
            for source in sources:
                identity = source.get("canonical_source_id") or f"{source.get('source_name')}|{source.get('source_path')}"
                if not any(
                    identity == (
                        existing_source.get("canonical_source_id")
                        or f"{existing_source.get('source_name')}|{existing_source.get('source_path')}"
                    )
                    for existing_source in existing_sources
                ):
                    existing_sources.append(source)
            existing["sources"] = existing_sources
            normalized_evidence[planned.id] = existing

            normalized_answer = _metric_bridge_answer(company, planned, matches[:5], period_defaulted)
            original_rag = rag_results.get(planned.id)
            rag_results[planned.id] = (
                original_rag.model_copy(update={"normalized_answer_ko": normalized_answer})
                if original_rag
                else RagQuestionResult(
                    question_id=planned.id,
                    question_ko=getattr(planned, "item_ko", ""),
                    normalized_answer_ko=normalized_answer,
                    answer_status="high_confidence",
                    items=items,
                )
            )
            evidence_gate[planned.id] = {"accepted": True, "reason": "accepted_quantitative_bridge"}
            flags = ["quantitative_metric_bridge"]
            if period_defaulted:
                flags.append("reporting_period_defaulted")
            quality_flags[planned.id] = sorted(set(quality_flags.get(planned.id, []) + flags))
            bridge_results[planned.id] = [result.metric_id for result in matches[:5]]

        return {
            "rag_results": rag_results,
            "evidence_gate": evidence_gate,
            "normalized_evidence": normalized_evidence,
            "quality_flags": quality_flags,
            "metric_qid_bridge_results": bridge_results,
        }

    def _match_metric_question(
        self,
        planned: Any,
        filled_results: list[QuantitativeResult],
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
