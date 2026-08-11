from __future__ import annotations

from typing import Any, Iterable

from esgagents.schemas import EvidenceItem, MetricEvidenceItem, RagQuestionResult


METRIC_SUMMARY_FIELDS = (
    "n_rows",
    "n_blocks",
    "n_primary",
    "n_scope_variant",
    "n_denominator",
)


def has_metric_contract(result: RagQuestionResult) -> bool:
    return result.metric_expected is not None or result.metric_status is not None


def metric_contract_warnings(result: RagQuestionResult) -> list[str]:
    if not has_metric_contract(result):
        return ["legacy_metric_contract"] if any(
            item.semantic_label.strip().casefold() == "metric_row" for item in result.items
        ) else []

    warnings: list[str] = []
    status = result.metric_status
    if result.metric_expected is None and status is not None:
        warnings.append("metric_status present without metric_expected")
    if result.metric_expected is False and status != "not_expected":
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
        if not item.table_block.strip():
            warnings.append(f"metric_evidence[{index}] missing table_block")
        if item.block_role is None:
            warnings.append(f"metric_evidence[{index}] missing block_role")
        if not item.entity_class.strip() and not item.entity.strip():
            warnings.append(f"metric_evidence[{index}] missing entity identity")
        if not item.raw_evidence_ko.strip():
            warnings.append(f"metric_evidence[{index}] missing raw evidence")
        if item.metric_form.strip().casefold() != "table_row":
            warnings.append(
                f"metric_evidence[{index}] unsupported metric_form={item.metric_form or 'empty'}"
            )
    for field, values in metric_summary_mismatches(result).items():
        warnings.append(
            f"metric_summary_mismatch:{field}:"
            f"expected={values['expected']}:actual={values['actual']}"
        )
    return list(dict.fromkeys(warnings))


def metric_actual_counts(result: RagQuestionResult) -> dict[str, int]:
    items = list(result.metric_evidence)
    return {
        "n_rows": len(items),
        "n_blocks": len(
            {
                item.table_block.strip()
                for item in items
                if item.block_role == "primary" and item.table_block.strip()
            }
        ),
        "n_primary": sum(item.block_role == "primary" for item in items),
        "n_scope_variant": sum(item.block_role == "scope_variant" for item in items),
        "n_denominator": sum(item.block_role == "denominator" for item in items),
    }


def metric_summary_mismatches(result: RagQuestionResult) -> dict[str, dict[str, int]]:
    summary = result.metric_summary
    if summary is None:
        return {}
    actual = metric_actual_counts(result)
    explicitly_set = set(getattr(summary, "model_fields_set", set(METRIC_SUMMARY_FIELDS)))
    mismatches: dict[str, dict[str, int]] = {}
    for field in METRIC_SUMMARY_FIELDS:
        if field not in explicitly_set:
            continue
        expected = int(getattr(summary, field, 0) or 0)
        if expected != actual[field]:
            mismatches[field] = {"expected": expected, "actual": actual[field]}
    return mismatches


def valid_primary_metric_items(result: RagQuestionResult) -> list[MetricEvidenceItem]:
    if result.metric_expected is not True or result.metric_status != "found_table":
        return []
    return [
        item
        for item in result.metric_evidence
        if item.block_role == "primary"
        and bool(item.table_block.strip())
        and bool(item.entity_class.strip() or item.entity.strip())
        and bool(item.raw_evidence_ko.strip())
        and item.metric_form.strip().casefold() == "table_row"
    ]


def narrative_items(result: RagQuestionResult) -> list[EvidenceItem]:
    # metric_expected is the first routing discriminator in the API contract.
    # A non-metric question keeps the legacy items[] behavior even when newer
    # metadata is present.
    if result.metric_expected is False:
        return _dedupe(result.items)
    if result.metric_status == "found_table":
        return _dedupe([*result.narrative_evidence])
    if result.metric_status == "not_found":
        # Contract §2c: the numeric cells remain empty and the qualitative
        # answer comes from legacy items[] only. narrative_evidence belongs to
        # the found_table interpretation path and must not leak into this one.
        return _dedupe(
            [
                item
                for item in result.items
                if item.semantic_label.strip().casefold() != "metric_row"
            ]
        )
    return _dedupe(result.items)


def routed_writer_items(result: RagQuestionResult) -> list[EvidenceItem]:
    return narrative_items(result)


def routed_gate_items(result: RagQuestionResult) -> list[EvidenceItem]:
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
