from __future__ import annotations

from collections import OrderedDict
import re
from typing import Any

from esgagents.schemas import EvidenceFact, EvidenceItem, MetricEvidenceItem, model_to_dict

from .metric_facts import resolve_metric_facts
from .metric_routing import (
    has_metric_contract,
    is_low_metric_confidence,
    is_metric_row,
    metric_contract_warnings,
    routed_writer_items,
)
from .policy import is_usable_evidence, resolve_provenance, source_name_from_path
from .source_policy import TIER_RANK, classify_source, evidence_fingerprint, relevance_band


STATUS_RANK = {
    "approved": 6,
    "effective": 6,
    "operational": 5,
    "historical": 4,
    "external_assessment": 3,
    "unknown": 2,
    "draft": 1,
    "proposal": 1,
    "consultant_material": 1,
    "superseded": 0,
}


class EvidenceNormalizerAgent:
    def __init__(self, config: dict[str, Any]):
        self.rejected_labels = {
            str(label).strip().lower() for label in config["rejected_semantic_labels"]
        }
        self.source_policy_enabled = bool(config.get("source_policy_enabled", True))

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, dict[str, Any]] = {}
        for qid, rag in state["rag_results"].items():
            deduped: OrderedDict[str, EvidenceItem] = OrderedDict()
            for item in routed_writer_items(rag):
                if not is_usable_evidence(item, self.rejected_labels):
                    continue
                upstream_canonical_id = item.canonical_source_id.strip()
                source_path = item.source_path.strip()
                source_name = item.source_name.strip() or source_name_from_path(source_path)
                normalized_item = item.model_copy(update={"source_name": source_name, "source_path": source_path})
                if not normalized_item.facts:
                    inferred_facts = self._infer_structured_facts(normalized_item)
                    if inferred_facts:
                        normalized_item = normalized_item.model_copy(update={"facts": inferred_facts})
                classification = classify_source(normalized_item)
                if self.source_policy_enabled:
                    normalized_item = normalized_item.model_copy(update=classification.__dict__)
                    if rag.is_v3:
                        normalized_item = normalized_item.model_copy(
                            update={"canonical_source_id": upstream_canonical_id}
                        )
                if isinstance(normalized_item, MetricEvidenceItem):
                    key = "|".join(
                        (
                            "metric",
                            normalized_item.table_block.strip(),
                            normalized_item.block_role or "",
                            normalized_item.entity_class.strip() or normalized_item.entity.strip(),
                            evidence_fingerprint(normalized_item.raw_evidence_ko),
                        )
                    )
                elif upstream_canonical_id and normalized_item.chunk_id:
                    key = f"{upstream_canonical_id}|{normalized_item.chunk_id}"
                elif rag.is_v3:
                    provenance = resolve_provenance(normalized_item)
                    key = f"{provenance['key']}|{evidence_fingerprint(item.raw_evidence_ko)}"
                else:
                    key = f"{classification.canonical_source_id}|{evidence_fingerprint(item.raw_evidence_ko)}"
                current = deduped.get(key)
                if current is None or self._rank_key(normalized_item) > self._rank_key(current):
                    deduped[key] = normalized_item
            ranked = sorted(
                deduped.values(),
                key=self._rank_key,
                reverse=True,
            )
            if rag.metric_status == "found_table":
                ranked = sorted(ranked, key=self._metric_order_key)
            normalized_answer = (
                " ".join((rag.normalized_answer_ko or "").split())
                if rag.is_v3 and rag.metric_status not in {"found_table", "not_found"}
                else ""
            )
            summary_parts = [normalized_answer] if normalized_answer else []
            if rag.metric_status == "found_table":
                primary_rows = [item for item in ranked if isinstance(item, MetricEvidenceItem)]
                metric_audit = resolve_metric_facts(primary_rows)
                if is_low_metric_confidence(rag):
                    metric_audit["withheld_facts"] = list(metric_audit.get("accepted_facts", []))
                    metric_audit["accepted_facts"] = []
                    metric_audit["accepted_fact_count"] = 0
                    metric_audit["all_numeric_facts_conflicted"] = False
                    metric_audit["numeric_withheld"] = True
            elif has_metric_contract(rag):
                metric_audit = resolve_metric_facts([])
            else:
                metric_audit = resolve_metric_facts(ranked)
            metric_audit.update(
                {
                    "metric_contract": "new" if has_metric_contract(rag) else "legacy",
                    "metric_expected": rag.metric_expected,
                    "metric_status": rag.metric_status,
                    "metric_confidence": rag.metric_confidence,
                    "metric_summary": model_to_dict(rag.metric_summary) if rag.metric_summary else {},
                    "metric_absence": model_to_dict(rag.metric_absence) if rag.metric_absence else {},
                    "metric_contract_warnings": metric_contract_warnings(rag),
                    "metric_evidence_row_count": len(rag.metric_evidence),
                    "primary_row_count": sum(item.block_role == "primary" for item in rag.metric_evidence),
                    "scope_variant_row_count": sum(
                        item.block_role == "scope_variant" for item in rag.metric_evidence
                    ),
                    "denominator_row_count": sum(
                        item.block_role == "denominator" for item in rag.metric_evidence
                    ),
                }
            )
            sources = []
            for item in ranked[:5]:
                text = " ".join(item.raw_evidence_ko.split())
                if text and not normalized_answer and not is_metric_row(item):
                    summary_parts.append(text[:350])
                source = {
                    "source_name": item.source_name,
                    "source_path": item.source_path,
                    "document_id": item.document_id,
                    "chunk_id": item.chunk_id,
                    "canonical_source_id": item.canonical_source_id,
                    "source_tier": item.source_tier,
                    "source_type": item.source_type,
                    "document_status": item.document_status,
                    "document_version": item.document_version,
                    "effective_date": item.effective_date,
                    "topic": item.topic,
                    "subtopic": item.subtopic,
                    "locator": model_to_dict(item.locator),
                    "semantic_label": item.semantic_label,
                    "semantic_score": item.semantic_score,
                    "reranker_score": item.reranker_score,
                    "vector_score": item.vector_score,
                    "score": item.score,
                    "classification_reason": item.classification_reason,
                    "provenance_key": resolve_provenance(item)["key"],
                    "provenance_method": resolve_provenance(item)["method"],
                    "provenance_fallback": resolve_provenance(item)["fallback"],
                    "chunk_ids": [item.chunk_id] if item.chunk_id else [],
                    "locators": [model_to_dict(item.locator)],
                }
                source_key = self._source_dedup_key(source, is_v3=rag.is_v3)
                existing = next(
                    (
                        candidate
                        for candidate in sources
                        if self._source_dedup_key(candidate, is_v3=rag.is_v3) == source_key
                    ),
                    None,
                )
                if existing is None:
                    sources.append(source)
                else:
                    existing["chunk_ids"] = list(
                        dict.fromkeys([*existing.get("chunk_ids", []), *source["chunk_ids"]])
                    )
                    existing["locators"] = list(
                        {
                            self._hashable_value(locator): locator
                            for locator in [*existing.get("locators", []), *source["locators"]]
                        }.values()
                    )
            all_metric_evidence = []
            for item in rag.metric_evidence:
                normalized_metric_item = item
                if not normalized_metric_item.facts:
                    inferred_facts = self._infer_structured_facts(normalized_metric_item)
                    if inferred_facts:
                        normalized_metric_item = normalized_metric_item.model_copy(
                            update={"facts": inferred_facts}
                        )
                all_metric_evidence.append(normalized_metric_item)
            normalized[qid] = {
                "items": ranked,
                "metric_items": [item for item in ranked if is_metric_row(item)],
                "narrative_items": [item for item in ranked if not is_metric_row(item)],
                "evidence_summary": "\n".join(summary_parts),
                "sources": sources,
                "metric_audit": metric_audit,
                "metric_evidence": all_metric_evidence,
                "narrative_evidence": list(rag.narrative_evidence),
            }
        return {"normalized_evidence": normalized}

    @staticmethod
    def _rank_key(item: EvidenceItem) -> tuple[int, float, int, int, float, float, float, int]:
        return (
            relevance_band(item.semantic_label),
            item.semantic_score if item.semantic_score is not None else -1.0,
            TIER_RANK.get(item.source_tier, 0),
            STATUS_RANK.get(item.document_status.strip().casefold(), 0),
            item.reranker_score if item.reranker_score is not None else -1.0,
            item.vector_score if item.vector_score is not None else -1.0,
            float(item.score or 0),
            len(item.source_path or ""),
        )

    @staticmethod
    def _metric_order_key(item: EvidenceItem) -> tuple[int, int, int, str]:
        if not isinstance(item, MetricEvidenceItem):
            return (1, 10**9, 1, item.raw_evidence_ko)
        aggregate_first = 0 if re.search(r"(?:합계|총|소계)", item.raw_evidence_ko) else 1
        return (
            0,
            item.block_rank if item.block_rank is not None else 10**9,
            aggregate_first,
            item.raw_evidence_ko,
        )

    @staticmethod
    def _source_dedup_key(source: dict[str, Any], *, is_v3: bool) -> tuple[str, str]:
        canonical_id = str(source.get("canonical_source_id") or "")
        if canonical_id:
            return canonical_id, ""
        provenance_key = str(source.get("provenance_key") or "")
        if provenance_key:
            return provenance_key, ""
        return str(source.get("source_path") or ""), str(source.get("source_name") or "")

    @staticmethod
    def _hashable_value(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(
                (key, EvidenceNormalizerAgent._hashable_value(item))
                for key, item in sorted(value.items())
            )
        if isinstance(value, list):
            return tuple(EvidenceNormalizerAgent._hashable_value(item) for item in value)
        return value

    @staticmethod
    def _infer_structured_facts(item: EvidenceItem) -> list[EvidenceFact]:
        text = " ".join((item.raw_evidence_ko or "").split())
        generic_metric_row = EvidenceNormalizerAgent._infer_metric_row_facts(item, text)
        if generic_metric_row:
            return generic_metric_row
        waste = re.search(
            r"폐기물\s*발생량\s*합계\s*톤\s*"
            r"([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
            text,
        )
        recycling = re.search(
            r"폐기물\s*재활용률\s*%\s*"
            r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
            text,
        )
        if not waste or not recycling:
            return []
        columns = (
            ("2023", "actual"),
            ("2024", "actual"),
            ("2025", "target"),
            ("2025", "actual"),
            ("2026", "target"),
        )
        facts: list[EvidenceFact] = []
        for index, (period, role) in enumerate(columns, start=1):
            facts.extend(
                [
                    EvidenceFact(
                        metric="waste_generation",
                        period=period,
                        value=waste.group(index),
                        unit="t",
                        value_role=role,
                        locator=item.locator,
                    ),
                    EvidenceFact(
                        metric="waste_recycling_rate",
                        period=period,
                        value=recycling.group(index),
                        unit="%",
                        value_role=role,
                        locator=item.locator,
                    ),
                ]
            )
        return facts

    @staticmethod
    def _infer_metric_row_facts(item: EvidenceItem, text: str) -> list[EvidenceFact]:
        if item.semantic_label.strip().casefold() != "metric_row" and "|" not in text:
            return []
        parts = [part.strip() for part in text.split("|")]
        if len(parts) < 3:
            return []
        year_values = []
        for part in parts[2:]:
            match = re.fullmatch(
                r"((?:19|20)\d{2})\s*=\s*([+-]?\d+(?:,\d{3})*(?:\.\d+)?%?)",
                part,
            )
            if match:
                year_values.append(match.groups())
        if not year_values:
            return []
        metric_path = parts[0]
        metric_name = metric_path.rsplit(">", 1)[-1].strip() or metric_path
        row_unit = parts[1]
        normalized_year_values = [
            (period, value[:-1] if value.endswith("%") else value)
            for period, value in year_values
        ]
        unit = row_unit or ("%" if any(value.endswith("%") for _, value in year_values) else "")
        return [
            EvidenceFact(
                metric=metric_name,
                period=period,
                value=value,
                unit=unit,
                value_role="actual",
                locator=item.locator,
            )
            for period, value in normalized_year_values
        ]
