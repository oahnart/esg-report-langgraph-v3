from __future__ import annotations

from collections.abc import Iterable

from esgagents.schemas import EvidenceItem


def has_evidence_text(item: EvidenceItem) -> bool:
    return bool(item.raw_evidence_ko.strip())


def has_source_path(item: EvidenceItem) -> bool:
    return bool(item.source_path.strip())


def has_accepted_label(item: EvidenceItem, rejected_labels: Iterable[str]) -> bool:
    rejected = {str(label).strip().lower() for label in rejected_labels}
    return item.semantic_label.strip().lower() not in rejected


def is_usable_evidence(item: EvidenceItem, rejected_labels: Iterable[str]) -> bool:
    return has_evidence_text(item) and has_accepted_label(item, rejected_labels) and has_source_path(item)


def source_name_from_path(source_path: str) -> str:
    return source_path.strip().replace("\\", "/").rsplit("/", 1)[-1]
