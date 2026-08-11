from __future__ import annotations

import re


RAW_TABLE_TERMS = (
    "raw data 취합",
    "정량데이터 취합",
    "제품군 리스트",
    "연간출고량",
    "parsed facts",
    "table block",
)
HEADER_TERMS = (
    "단순화 전",
    "단순화 후",
    "용기 용량",
    "용기 무게",
    "제품명",
    "생산량",
    "평가 결과",
    "metric status",
    "source path",
)
DOCUMENT_NAV_TERMS = (
    "company overview",
    "company profile",
    "business performance",
    "esg framework",
    "esg highlight",
    "sustainability performance",
    "appendix",
)
START_CONNECTOR_RE = re.compile(r"^(?:또한|이에 따라|그리고|아울러)[,，]?\s*")
ATTRIBUTION_PHRASES = (
    "제안/검토 자료에 따르면,",
    "평가 자료에 따르면,",
    "검토 중인 제안 자료상",
    "외부 평가 자료상",
)
YEAR_EQUALS_RE = re.compile(r"\b(?:19|20)\d{2}\s*=")
LEADING_FRAGMENT_RE = re.compile(
    r"^(?:[a-z]{1,8}(?:/[a-z]{1,8})?\)|[a-z]{1,8}/[a-z]{1,8}\)|[%/]+\))",
    flags=re.IGNORECASE,
)
ENUMERATION_STUB_RE = re.compile(r"^(?:\d+[.)]?\s*)+$")
LEADING_NUMBERED_BLOCK_RE = re.compile(r"^\d+[.)]\s+\S+")
LEADING_EXAMPLE_RE = re.compile(
    r"^\(?\s*(?:예|예시|e\.g\.|example)\s*[:：)]",
    flags=re.IGNORECASE,
)
INTRO_ONLY_RE = re.compile(
    r"(?:다음과\s*같습니다|다음과\s*같다|as\s+follows)\s*[:.]?\s*(?:\d+[.)]?)?\s*$",
    flags=re.IGNORECASE,
)

def non_narrative_reason(text: str) -> str:
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    lower = value.casefold()
    if any(term.casefold() in lower for term in RAW_TABLE_TERMS):
        return "raw_table_output"
    if LEADING_NUMBERED_BLOCK_RE.search(value):
        return "numbered_block_output"
    if LEADING_EXAMPLE_RE.search(value):
        return "example_fragment_output"
    pipe_count = value.count("|")
    if (pipe_count >= 2 and YEAR_EQUALS_RE.search(value)) or pipe_count >= 6:
        return "table_delimited_output"
    header_count = sum(term.casefold() in lower for term in HEADER_TERMS)
    if header_count >= 4:
        return "header_dump_output"
    # Navigation labels later in a long excerpt do not invalidate an otherwise
    # substantive opening. Header dumps place several labels near the front.
    opening = lower[:400]
    navigation_count = sum(term in opening for term in DOCUMENT_NAV_TERMS)
    if navigation_count >= 3:
        return "document_navigation_dump_output"
    if LEADING_FRAGMENT_RE.search(value):
        return "fragment_output"
    if len(value) >= 240 and not re.search(r"[.!?。！？]", value):
        return "unstructured_long_output"
    return ""


def non_substantive_reason(text: str) -> str:
    """Return why a nominal answer is not meaningful customer prose."""

    value = " ".join(str(text or "").split()).strip()
    if not value:
        return "empty_output"
    structural = non_narrative_reason(value)
    if structural:
        return structural
    if ENUMERATION_STUB_RE.fullmatch(value) or INTRO_ONLY_RE.search(value):
        return "enumeration_stub_output"
    letters = re.findall(r"[A-Za-z가-힣]", value)
    if len(value) < 20 or len(letters) < 8:
        return "short_fragment_output"
    return ""


def has_substantive_answer(text: str) -> bool:
    return not non_substantive_reason(text)


def normalize_answer_coherence(text: str) -> tuple[str, list[str]]:
    value = str(text or "").strip()
    actions: list[str] = []
    without_connector = START_CONNECTOR_RE.sub("", value, count=1).strip()
    if without_connector != value:
        value = without_connector
        actions.append("removed_leading_connector")

    for phrase in ATTRIBUTION_PHRASES:
        seen = False

        def replace(match: re.Match[str]) -> str:
            nonlocal seen
            if not seen:
                seen = True
                return match.group(0)
            return ""

        deduplicated = re.sub(re.escape(phrase), replace, value)
        if deduplicated != value:
            value = deduplicated
            actions.append("deduplicated_source_attribution")

    value = re.sub(r",\s*,", ",", value)
    value = re.sub(r"\.\s*,", ". ", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" ,")
    return value, list(dict.fromkeys(actions))


def safe_narrative_text(text: str) -> str:
    normalized, _ = normalize_answer_coherence(text)
    return "" if non_narrative_reason(normalized) else normalized
