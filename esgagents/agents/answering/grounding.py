from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from esgagents.schemas import GroundedSentence, PreparedEvidence


SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
NUMBER_RE = re.compile(r"\d+(?:[,.]\d+)*(?:\s*%)?")
TOKEN_RE = re.compile(r"[A-Za-z가-힣][A-Za-z0-9가-힣_-]+")
STOPWORDS = {
    "the", "and", "for", "with", "company", "reported", "회사는", "당사는",
    "그리고", "또한", "관련", "대한", "통해", "있습니다", "합니다",
}


def ground_answer_sentences(
    answer: str,
    evidence: Iterable[PreparedEvidence],
) -> tuple[list[GroundedSentence], list[str]]:
    prepared = list(evidence)
    sentences = [part.strip() for part in SENTENCE_RE.split(str(answer or "")) if part.strip()]
    grounded: list[GroundedSentence] = []
    issues: list[str] = []
    for index, sentence in enumerate(sentences, start=1):
        matches = _matching_evidence(sentence, prepared)
        evidence_ids = [item.evidence_id for item in matches]
        sentence_id = f"S{index}"
        grounded.append(
            GroundedSentence(
                sentence_id=sentence_id,
                text=sentence,
                evidence_ids=evidence_ids,
            )
        )
        if not evidence_ids:
            issues.append(f"unsupported_sentence:{sentence_id}")
            continue
        sentence_numbers = _numbers(sentence)
        referenced_numbers = set().union(*(_numbers(item.clean_text) for item in matches))
        if sentence_numbers and not sentence_numbers.issubset(referenced_numbers):
            issues.append(f"prose_numeric_grounding_fail:{sentence_id}")
    return grounded, issues


def _matching_evidence(sentence: str, evidence: list[PreparedEvidence]) -> list[PreparedEvidence]:
    normalized_sentence = _normalize(sentence)
    sentence_tokens = _tokens(sentence)
    ranked: list[tuple[float, PreparedEvidence]] = []
    for item in evidence:
        text = _normalize(item.clean_text)
        if not text:
            continue
        if normalized_sentence and normalized_sentence in text:
            ranked.append((1.0, item))
            continue
        evidence_tokens = _tokens(text)
        if not sentence_tokens:
            continue
        overlap = len(sentence_tokens.intersection(evidence_tokens))
        score = overlap / max(1, min(len(sentence_tokens), 8))
        if overlap >= 2 and score >= 0.3:
            ranked.append((score, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked[:3]]


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _numbers(value: str) -> set[str]:
    return {
        match.group(0).replace(" ", "").replace(",", "")
        for match in NUMBER_RE.finditer(unicodedata.normalize("NFKC", str(value or "")))
    }


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN_RE.findall(unicodedata.normalize("NFKC", str(value or "")))
        if token.casefold() not in STOPWORDS
    }
