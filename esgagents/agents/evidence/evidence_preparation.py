from __future__ import annotations

from hashlib import sha256
import html
import re
import unicodedata
from typing import Iterable

from esgagents.agents.answering.text_quality import clean_customer_evidence_text
from esgagents.schemas import EvidenceItem, PreparedEvidence, RagQuestionResult

from .metric_routing import qualitative_evidence_route


WHITESPACE_RE = re.compile(r"\s+")


def prepare_qualitative_evidence(
    qid: str,
    rag: RagQuestionResult,
    items: Iterable[EvidenceItem],
) -> list[PreparedEvidence]:
    origin = qualitative_evidence_route(rag)
    prepared: list[PreparedEvidence] = []
    for item in items:
        clean_text, actions = sanitize_evidence_text(item.raw_evidence_ko)
        prepared.append(
            PreparedEvidence(
                evidence_id=stable_evidence_id(qid, item),
                origin=origin,
                raw_item=item,
                clean_text=clean_text,
                sanitization_actions=actions,
            )
        )
    return prepared


def stable_evidence_id(qid: str, item: EvidenceItem) -> str:
    identity = "|".join(
        (
            qid,
            item.canonical_source_id.strip(),
            item.document_id.strip(),
            item.chunk_id.strip(),
            item.source_path.strip(),
            WHITESPACE_RE.sub(" ", item.raw_evidence_ko).strip(),
        )
    )
    return f"{qid}-EV-{sha256(identity.encode('utf-8')).hexdigest()[:12]}"


def sanitize_evidence_text(text: str) -> tuple[str, list[str]]:
    original = str(text or "")
    actions: list[str] = []
    value = html.unescape(original)
    if value != original:
        actions.append("html_entities_decoded")

    normalized = unicodedata.normalize("NFKC", value)
    if normalized != value:
        actions.append("unicode_normalized")
    value = normalized

    retained: list[str] = []
    removed_control = False
    for char in value:
        category = unicodedata.category(char)
        if char in "\n\t":
            retained.append(char)
        elif category.startswith("C"):
            removed_control = True
        elif category.startswith("Z"):
            retained.append(" ")
        else:
            retained.append(char)
    value = "".join(retained)
    if removed_control:
        actions.append("control_unicode_removed")

    cleaned, boilerplate_actions = clean_customer_evidence_text(value)
    actions.extend(boilerplate_actions)
    markdown_cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    markdown_cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", markdown_cleaned)
    markdown_cleaned = re.sub(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", markdown_cleaned)
    markdown_cleaned = markdown_cleaned.replace("**", "").replace("__", "").replace("`", "")
    if markdown_cleaned != cleaned:
        actions.append("markdown_normalized")
    cleaned = markdown_cleaned
    compacted = WHITESPACE_RE.sub(" ", cleaned).strip()
    if compacted != cleaned:
        actions.append("whitespace_normalized")
    return compacted, list(dict.fromkeys(actions))
