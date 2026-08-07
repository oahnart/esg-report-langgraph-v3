from __future__ import annotations

from collections.abc import Iterable
import re

from esgagents.schemas import EvidenceItem


def has_evidence_text(item: EvidenceItem) -> bool:
    return bool(item.raw_evidence_ko.strip())


def has_source_path(item: EvidenceItem) -> bool:
    return is_traceable_source_path(item.source_path)


def resolve_provenance(item: EvidenceItem) -> dict[str, str | bool]:
    source_path = str(item.source_path or "").strip()
    canonical_source_id = str(item.canonical_source_id or "").strip()
    document_id = str(item.document_id or "").strip()
    chunk_id = str(item.chunk_id or "").strip()
    if is_traceable_source_path(source_path):
        return {
            "key": source_path,
            "method": "source_path",
            "fallback": False,
        }
    if canonical_source_id:
        return {
            "key": canonical_source_id,
            "method": "canonical_source_id",
            "fallback": True,
        }
    if document_id and chunk_id:
        return {
            "key": f"{document_id}|{chunk_id}",
            "method": "document_chunk",
            "fallback": True,
        }
    return {"key": "", "method": "none", "fallback": False}


def has_stable_provenance(item: EvidenceItem) -> bool:
    return bool(resolve_provenance(item)["key"])


def has_stable_source(source: dict[str, object]) -> bool:
    source_path = str(source.get("source_path") or "").strip()
    if is_traceable_source_path(source_path):
        return True
    if str(source.get("canonical_source_id") or "").strip():
        return True
    return bool(
        str(source.get("document_id") or "").strip()
        and str(source.get("chunk_id") or "").strip()
    )


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
    return (
        has_evidence_text(item)
        and has_accepted_label(item, rejected_labels)
        and has_stable_provenance(item)
    )


def source_name_from_path(source_path: str) -> str:
    return source_path.strip().replace("\\", "/").rsplit("/", 1)[-1]
