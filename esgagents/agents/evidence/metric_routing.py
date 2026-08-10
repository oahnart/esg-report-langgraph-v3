from __future__ import annotations

from typing import Any, Iterable

from esgagents.schemas import EvidenceItem, MetricEvidenceItem, RagQuestionResult


def has_metric_contract(result: RagQuestionResult) -> bool:
    return result.metric_expected is not None or result.metric_status is not None


def metric_contract_warnings(result: RagQuestionResult) -> list[str]:
    if not has_metric_contract(result):
        return ["legacy_metric_contract"] if any(
            item.semantic_label.strip().casefold() == "metric_row" for item in result.items
        ) else []

    warnings: list[str] = []
    status = result.metric_status
    if result.metric_expected is False and status not in {None, "not_expected"}:
        warnings.append("metric_expected=false conflicts with metric_status")
    if result.metric_expected is True and status == "not_expected":
        warnings.append("metric_expected=true conflicts with metric_status=not_expected")
    if result.metric_expected is True and status is None:
        warnings.append("metric_expected=true without metric_status")
    if status == "found_table" and not result.metric_evidence:
        warnings.append("metric_status=found_table without metric_evidence")
    if status == "not_found" and result.metric_absence is None:
        warnings.append("metric_status=not_found without metric_absence")
    if status == "not_expected" and result.metric_evidence:
        warnings.append("metric_status=not_expected with metric_evidence")
    for index, item in enumerate(result.metric_evidence):
        if item.block_role is None:
            warnings.append(f"metric_evidence[{index}] missing block_role")
        if not item.entity_class.strip() and not item.entity.strip():
            warnings.append(f"metric_evidence[{index}] missing entity identity")
    return list(dict.fromkeys(warnings))


def valid_primary_metric_items(result: RagQuestionResult) -> list[MetricEvidenceItem]:
    if result.metric_status != "found_table":
        return []
    return [
        item
        for item in result.metric_evidence
        if item.block_role == "primary"
        and bool(item.entity_class.strip() or item.entity.strip())
        and bool(item.raw_evidence_ko.strip())
    ]


def narrative_items(result: RagQuestionResult) -> list[EvidenceItem]:
    if result.metric_status == "found_table":
        return _dedupe([*result.narrative_evidence])
    if result.metric_status == "not_found":
        return _dedupe(
            [
                *result.narrative_evidence,
                *[
                    item
                    for item in result.items
                    if item.semantic_label.strip().casefold() != "metric_row"
                ],
            ]
        )
    return _dedupe(result.items)


def routed_writer_items(result: RagQuestionResult) -> list[EvidenceItem]:
    if result.metric_status == "found_table":
        return [*valid_primary_metric_items(result), *narrative_items(result)]
    return narrative_items(result)


def routed_gate_items(result: RagQuestionResult) -> list[EvidenceItem]:
    if result.metric_status == "found_table":
        return [*valid_primary_metric_items(result), *narrative_items(result)]
    return narrative_items(result)


def is_metric_row(item: Any) -> bool:
    return isinstance(item, MetricEvidenceItem) or (
        str(getattr(item, "semantic_label", "") or "").strip().casefold() == "metric_row"
    )


def is_low_metric_confidence(result: RagQuestionResult) -> bool:
    return str(result.metric_confidence or "").strip().casefold() == "low"


def _dedupe(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[tuple[str, str, str]] = set()
    result: list[EvidenceItem] = []
    for item in items:
        key = (
            item.canonical_source_id.strip() or item.source_path.strip(),
            item.chunk_id.strip(),
            " ".join(item.raw_evidence_ko.split()),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
