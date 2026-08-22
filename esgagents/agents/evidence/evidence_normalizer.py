from __future__ import annotations

from collections import Counter, OrderedDict
import re
from typing import Any

from esgagents.schemas import EvidenceFact, EvidenceItem, MetricEvidenceItem, model_to_dict

from esgagents.agents.answering.question_contracts import (
    QuestionContract,
    build_question_contract,
)

from .metric_facts import resolve_metric_facts
from .metric_routing import (
    has_metric_contract,
    is_low_metric_confidence,
    is_metric_row,
    metric_actual_counts,
    metric_contract_warnings,
    metric_summary_mismatches,
    routed_writer_items,
    valid_primary_metric_items,
)
from .evidence_preparation import prepare_qualitative_evidence
from .policy import is_usable_evidence, resolve_provenance, source_name_from_path
from .upstream_audit import (
    excluded_topic_dimensions,
    substituted_topic_dimensions,
    verify_upstream_facets,
)
from .source_policy import (
    TIER_RANK,
    classify_source,
    evidence_fingerprint,
    is_unanswered_assessment_criteria,
    relevance_band,
)


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


ENTITY_PARTICLE_RE = re.compile(r"(?:은|는|이|가|의)$")
# A legal entity is written either with its legal-form prefix ("㈜ 대웅제약") or with a
# corporate suffix. Document-type words ("취업규칙", "이사회운영 규정") must not match.
BODY_ENTITY_RE = re.compile(
    r"(?:㈜|\(주\))\s*([가-힣]{2,12})"
    r"|([가-힣]{2,12}(?:그룹|제약|바이오|파마|홀딩스))(?=은|는|이|가|의|\s|,|\)|$)"
)
SOURCE_ENTITY_RE = re.compile(
    r"(?:^|[\s_\-])((?:㈜|\(주\))?\s*[가-힣]{2,12}(?:그룹|제약|바이오|파마|홀딩스))"
)
ENTITY_SCAN_LIMIT = 260


def evidence_entity(item: Any) -> str:
    """Legal entity an evidence item speaks for, from its text or its source name."""

    body = " ".join(str(getattr(item, "raw_evidence_ko", "") or "").split())
    match = BODY_ENTITY_RE.search(body[:ENTITY_SCAN_LIMIT])
    if match:
        return ENTITY_PARTICLE_RE.sub("", (match.group(1) or match.group(2)).strip())
    name = str(
        getattr(item, "source_name", "") or getattr(item, "source_path", "") or ""
    ).replace("\\", "/").rsplit("/", 1)[-1]
    hits = SOURCE_ENTITY_RE.findall(name)
    if hits:
        return ENTITY_PARTICLE_RE.sub(
            "", max(hits, key=len).replace("㈜", "").replace("(주)", "").strip()
        )
    return ""


def dominant_entity(items: Any) -> str:
    """The entity the corpus overwhelmingly speaks for, i.e. the reporting company.

    Derived from the evidence rather than configuration so it needs no per-company
    setup, and required to be a clear majority so a mixed corpus yields no preference.
    """

    counts: Counter[str] = Counter()
    for item in items:
        entity = evidence_entity(item)
        if entity:
            counts[entity] += 1
    if not counts:
        return ""
    entity, count = counts.most_common(1)[0]
    return entity if count >= max(3, 0.6 * sum(counts.values())) else ""


class EvidenceNormalizerAgent:
    def __init__(self, config: dict[str, Any]):
        self.rejected_labels = {
            str(label).strip().lower() for label in config["rejected_semantic_labels"]
        }
        self.source_policy_enabled = bool(config.get("source_policy_enabled", True))
        self.topic_isolation_enabled = bool(config.get("topic_isolation_enabled", True))
        self.entity_preference_enabled = bool(
            config.get("entity_preference_enabled", True)
        )
        self.reporting_entity = ""

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, dict[str, Any]] = {}
        contracts = self._question_contracts(state)
        self.reporting_entity = (
            dominant_entity(
                item
                for rag in state["rag_results"].values()
                for item in routed_writer_items(rag)
                if not is_metric_row(item)
            )
            if self.entity_preference_enabled
            else ""
        )
        for qid, rag in state["rag_results"].items():
            contract = contracts.get(qid)
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
            ranked, duplicate_evidence_dropped = self._collapse_repeated_evidence(ranked)
            ranked, off_topic_evidence_dropped = self._drop_substituted_topics(ranked, contract)
            withheld_assessment_criteria = [
                item for item in ranked if is_unanswered_assessment_criteria(item)
            ]
            if withheld_assessment_criteria:
                ranked = [
                    item
                    for item in ranked
                    if not is_unanswered_assessment_criteria(item)
                ]
            if rag.metric_status == "found_table":
                ranked = sorted(ranked, key=self._metric_order_key)
            normalized_answer = (
                " ".join((rag.normalized_answer_ko or "").split())
                if rag.is_v3 and rag.metric_status not in {"found_table", "not_found"}
                else ""
            )
            summary_parts = [normalized_answer] if normalized_answer else []
            if rag.metric_status == "found_table":
                primary_rows = []
                for item in valid_primary_metric_items(rag):
                    normalized_metric_item = item
                    if not normalized_metric_item.facts:
                        inferred_facts = self._infer_structured_facts(normalized_metric_item)
                        if inferred_facts:
                            normalized_metric_item = normalized_metric_item.model_copy(
                                update={"facts": inferred_facts}
                            )
                    classification = classify_source(normalized_metric_item)
                    if self.source_policy_enabled:
                        upstream_canonical_id = normalized_metric_item.canonical_source_id.strip()
                        normalized_metric_item = normalized_metric_item.model_copy(
                            update=classification.__dict__
                        )
                        if rag.is_v3:
                            normalized_metric_item = normalized_metric_item.model_copy(
                                update={"canonical_source_id": upstream_canonical_id}
                            )
                    primary_rows.append(normalized_metric_item)
                primary_rows, off_topic_metric_rows = self._drop_substituted_topics(
                    primary_rows,
                    contract,
                )
                off_topic_evidence_dropped.extend(off_topic_metric_rows)
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
                    "metric_summary_actual": metric_actual_counts(rag),
                    "metric_summary_mismatches": metric_summary_mismatches(rag),
                    "metric_evidence_row_count": len(rag.metric_evidence),
                    "metric_primary_block_count": len(
                        {
                            item.table_block.strip()
                            for item in rag.metric_evidence
                            if item.block_role == "primary" and item.table_block.strip()
                        }
                    ),
                    "primary_row_count": sum(item.block_role == "primary" for item in rag.metric_evidence),
                    "scope_variant_row_count": sum(
                        item.block_role == "scope_variant" for item in rag.metric_evidence
                    ),
                    "denominator_row_count": sum(
                        item.block_role == "denominator" for item in rag.metric_evidence
                    ),
                }
            )
            # A metric question grounds metric_result in the metric lane, so the
            # facet check has to see both lanes the writer will see.
            facet_verification = verify_upstream_facets(
                covered_facets=rag.covered_facets,
                missing_facets=rag.missing_facets,
                contract_facets=(
                    (*contract.required_facets, *contract.expected_facets) if contract else ()
                ),
                items=[
                    *(primary_rows if rag.metric_status == "found_table" else []),
                    *ranked,
                ],
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
            prepared_qualitative_items = prepare_qualitative_evidence(
                qid,
                rag,
                [item for item in ranked if not is_metric_row(item)],
            )
            normalized[qid] = {
                "items": ranked,
                "metric_items": (
                    primary_rows
                    if rag.metric_status == "found_table"
                    else [item for item in ranked if is_metric_row(item)]
                ),
                "narrative_items": [item for item in ranked if not is_metric_row(item)],
                "qualitative_items": [item for item in ranked if not is_metric_row(item)],
                "prepared_qualitative_items": prepared_qualitative_items,
                "qualitative_evidence_route": (
                    prepared_qualitative_items[0].origin
                    if prepared_qualitative_items
                    else (
                        "narrative_evidence"
                        if rag.metric_status == "found_table"
                        else "items"
                        if rag.metric_status in {"not_expected", "not_found"}
                        or rag.metric_expected is False
                        else "legacy_items"
                    )
                ),
                "evidence_summary": "\n".join(summary_parts),
                "sources": sources,
                "metric_audit": metric_audit,
                "metric_evidence": all_metric_evidence,
                "narrative_evidence": list(rag.narrative_evidence),
                "withheld_assessment_criteria": withheld_assessment_criteria,
                "duplicate_evidence_dropped": duplicate_evidence_dropped,
                "off_topic_evidence_dropped": off_topic_evidence_dropped,
                "facet_verification": facet_verification,
            }
        return {"normalized_evidence": normalized}

    @staticmethod
    def _question_contracts(state: dict[str, Any]) -> dict[str, QuestionContract]:
        return {
            str(getattr(planned, "id", "") or ""): build_question_contract(planned)
            for planned in state.get("planned_questions", [])
            if str(getattr(planned, "id", "") or "")
        }

    def _drop_substituted_topics(
        self,
        items: list[EvidenceItem],
        contract: QuestionContract | None,
    ) -> tuple[list[EvidenceItem], list[dict[str, Any]]]:
        # Spec §13: an excerpt about a mutually exclusive topic must not stand in
        # for the requested one. The producer no longer drops those, and its own
        # topic labels come back as "misc", so the question contract is the only
        # usable signal.
        if not self.topic_isolation_enabled or contract is None:
            return items, []
        own = tuple(contract.metric_dimensions)
        excluded = excluded_topic_dimensions(own)
        if not excluded:
            return items, []
        kept: list[EvidenceItem] = []
        dropped: list[dict[str, Any]] = []
        for item in items:
            substituted = substituted_topic_dimensions(item.raw_evidence_ko, own, excluded)
            if not substituted:
                kept.append(item)
                continue
            dropped.append(
                {
                    "chunk_id": item.chunk_id,
                    "canonical_source_id": item.canonical_source_id,
                    "source_name": item.source_name,
                    "semantic_label": item.semantic_label,
                    "requested_dimensions": list(own),
                    "substituted_dimensions": list(substituted),
                }
            )
        return kept, dropped

    @staticmethod
    def _collapse_repeated_evidence(
        items: list[EvidenceItem],
    ) -> tuple[list[EvidenceItem], list[dict[str, Any]]]:
        # Team RAG dedupes only by canonical_source_id + chunk_id, so an excerpt
        # stored in several source documents comes back once per document with a
        # different chunk_id. The list is already ranked, so the first copy is
        # the strongest one and the later copies only inflate the citations.
        # Metric rows keep their own dedup key because a primary row and a
        # scope_variant row may legitimately carry the same text.
        kept: list[EvidenceItem] = []
        winners: dict[str, EvidenceItem] = {}
        dropped: list[dict[str, Any]] = []
        for item in items:
            if is_metric_row(item):
                kept.append(item)
                continue
            fingerprint = evidence_fingerprint(item.raw_evidence_ko)
            winner = winners.get(fingerprint)
            if winner is None:
                winners[fingerprint] = item
                kept.append(item)
                continue
            dropped.append(
                {
                    "evidence_fingerprint": fingerprint,
                    "kept_canonical_source_id": winner.canonical_source_id,
                    "kept_chunk_id": winner.chunk_id,
                    "kept_source_name": winner.source_name,
                    "kept_semantic_label": winner.semantic_label,
                    "dropped_canonical_source_id": item.canonical_source_id,
                    "dropped_chunk_id": item.chunk_id,
                    "dropped_source_name": item.source_name,
                    "dropped_semantic_label": item.semantic_label,
                }
            )
        return kept, dropped

    def _rank_key(
        self, item: EvidenceItem
    ) -> tuple[int, int, float, int, int, float, float, float, int]:
        return (
            self._entity_band(item),
            relevance_band(item.semantic_label),
            item.semantic_score if item.semantic_score is not None else -1.0,
            TIER_RANK.get(item.source_tier, 0),
            STATUS_RANK.get(item.document_status.strip().casefold(), 0),
            item.reranker_score if item.reranker_score is not None else -1.0,
            item.vector_score if item.vector_score is not None else -1.0,
            float(item.score or 0),
            len(item.source_path or ""),
        )

    def _entity_band(self, item: EvidenceItem) -> int:
        """Rank the reporting entity's own evidence above another entity's.

        Source documents come one per legal entity, near-identical but for the
        subject and the figures -- a group paragraph and a subsidiary paragraph both
        describing "폐기물 배출량 대비 재활용률". Retrieval scores them the same, so the
        writer has no basis to choose and has been seen emitting both values side by
        side. Preferring the reporting entity is a ranking tier, not a filter: another
        entity's evidence stays available, it just stops outranking the company's own.
        """

        if not self.reporting_entity:
            return 1
        entity = evidence_entity(item)
        if not entity:
            return 1
        return 2 if entity == self.reporting_entity else 0

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
