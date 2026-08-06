from __future__ import annotations

from collections.abc import Iterable
import re

from esgagents.schemas import EvidenceItem


def has_evidence_text(item: EvidenceItem) -> bool:
    return bool(item.raw_evidence_ko.strip())


def has_source_path(item: EvidenceItem) -> bool:
    return is_traceable_source_path(item.source_path)


TRACEABLE_SOURCE_RE = re.compile(
    r"(?:^https?://|\.(?:pdf|pptx?|docx?|xlsx?|csv|tsv|html?|txt)(?:[?#].*)?$)",
    re.IGNORECASE,
)


def is_traceable_source_path(value: str) -> bool:
    return bool(TRACEABLE_SOURCE_RE.search(str(value or "").strip()))


def has_accepted_label(item: EvidenceItem, rejected_labels: Iterable[str]) -> bool:
    rejected = {str(label).strip().lower() for label in rejected_labels}
    return item.semantic_label.strip().lower() not in rejected


def is_usable_evidence(item: EvidenceItem, rejected_labels: Iterable[str]) -> bool:
    return has_evidence_text(item) and has_accepted_label(item, rejected_labels) and has_source_path(item)


def source_name_from_path(source_path: str) -> str:
    return source_path.strip().replace("\\", "/").rsplit("/", 1)[-1]
