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
    "직접에너지",
    "간접에너지",
    "에너지 사용량 계",
    "에너지 사용량 원단위",
    "매출(생산액)",
    "GJ/억원",
)
DOCUMENT_NAV_TERMS = (
    "company overview",
    "company profile",
    "business performance",
    "esg framework",
    "esg journey",
    "esg performance",
    "human rights impact",
    "esg highlight",
    "sustainability performance",
    "appendix",
)
EDITORIAL_CUE_TERMS = (
    "왼쪽처럼",
    "오른쪽 그림 참고",
    "체계 수정",
    "도식화",
    "업데이트 현재 그림",
    "상세프로세스",
    "name tag",
    "원본 sr",
    "참고 부탁드립니다",
)
START_CONNECTOR_RE = re.compile(r"^(?:또한|이에 따라|그리고|아울러|이를 위해|하지만)[,，]?\s*")
ATTRIBUTION_PHRASES = (
    "제안/검토 자료에 따르면,",
    "평가 자료에 따르면,",
    "제안 자료에 따르면,",
    "검토 중인 제안 자료상",
    "외부 평가 자료상",
)
SOURCE_ATTRIBUTION_RE = re.compile(
    r"(?:제안/검토\s*자료에\s*따르면,?|평가\s*자료에\s*따르면,?|제안\s*자료에\s*따르면,?|"
    r"검토\s*중인\s*제안\s*자료상|외부\s*평가\s*자료상)\s*"
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
ARROW_EDITORIAL_RE = re.compile(r"[\u25c0\u25b6]\s*[^.!?\u3002\uff01\uff1f]{0,700}?[\u25c0\u25b6]")
NAME_TAG_PREFIX_RE = re.compile(
    r"^\s*\[name\s+tag\].{0,500}?(?=(?:대웅제약은|회사는|당사는|디지털\s*전환|정보보호\s*정책|그\s*결과|앞으로도)\b)",
    flags=re.IGNORECASE | re.DOTALL,
)
REPORT_NAV_RE = re.compile(
    r"(?:[가-힣A-Za-z0-9_.()/-]{1,40}\s*)?(?:20\d{2}\s*)?지속가능경영보고서\s*\d*\s*"
    r"(?:(?:COMPANY\s+OVERVIEW|COMPANY\s+PROFILE|BUSINESS\s+PERFORMANCE|ESG\s+JOURNEY|"
    r"ESG\s+FRAMEWORK|ESG\s+HIGHLIGHT|ESG\s+PERFORMANCE|SUSTAINABILITY\s+PERFORMANCE|"
    r"HUMAN\s+RIGHTS\s+IMPACT|APPENDIX)\s*)+",
    flags=re.IGNORECASE,
)
SECTION_HEADING_RE = re.compile(
    r"\b정보보안\s*및\s*개인정보\s*보호\s*보안사고\s*예방\s*및\s*대응\s*활동\b"
)
EDITORIAL_SENTENCE_RE = re.compile(
    r"(?:왼쪽처럼|오른쪽\s*그림\s*참고|체계\s*수정|도식화|상세프로세스|"
    r"업데이트\s*현재\s*그림|참고\s*부탁드립니다)",
    flags=re.IGNORECASE,
)
TRAILING_HEADING_FRAGMENT_RE = re.compile(
    r"\s+(?:정보보호\s*)?(?:목표|전담조직|관리체계|운영체계|정책|전략)"
    r"(?:\s+(?:정보보호|정보보안|목표|전담조직|관리체계|운영체계|정책|전략)){1,}\s*$"
)
REPORT_TITLE_PREFIX_RE = re.compile(
    r"^(?:[A-Za-z]+-[^.!?。！？]{0,180}?)?[^.!?。！？]{0,180}?"
    r"지속가능경영보고서[^.!?。！？]{0,180}?(?=(?:19|20)\d{2}\s*년\s+)"
)
LEADING_PROCESS_DUMP_RE = re.compile(
    r"^(?=(?:[^.!?。！？]{0,420}(?:임상시험|시판허가|첨부문서|설명서|모니터링|위해성|유익성)){3,})"
    r"[^.!?。！？]{40,520}?(?=대웅제약(?:의\s*약물감시는|은\s+품질경영))"
)
LEADING_DRAFT_HEADING_RE = re.compile(
    r"^(검토\s*중인\s*제안\s*자료상\s+)(?!대웅|당사|회사)"
    r"[^.!?。！？]{5,180}?(?=(?:대웅제약은|대웅은|당사는|회사는)\b)"
)
INLINE_KNOWN_HEADING_RE = re.compile(
    r"(?:^|\s+)(?:업계최초\s*직무급\s*제도와\s*여성인재\s*육성|품질\s*부문\s*조직)\s+(?=대웅제약은\b)"
)


def non_narrative_reason(text: str) -> str:
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    lower = value.casefold()
    if any(term.casefold() in lower[:500] for term in EDITORIAL_CUE_TERMS):
        return "editorial_instruction_output"
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
    metric_label_count = sum(
        term.casefold() in lower
        for term in (
            "직접에너지",
            "간접에너지",
            "에너지 사용량 계",
            "에너지 사용량 원단위",
            "매출(생산액)",
            "gj/억원",
        )
    )
    if metric_label_count >= 3 and not re.search(r"[.!?。！？]", value):
        return "metric_label_dump_output"
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

    without_report_prefix = REPORT_TITLE_PREFIX_RE.sub("", value, count=1).strip()
    if without_report_prefix != value:
        value = without_report_prefix
        actions.append("removed_report_title_prefix")

    without_process_dump = LEADING_PROCESS_DUMP_RE.sub("", value, count=1).strip()
    if without_process_dump != value:
        value = without_process_dump
        actions.append("removed_leading_process_dump")

    without_draft_heading = LEADING_DRAFT_HEADING_RE.sub(r"\1", value, count=1).strip()
    if without_draft_heading != value:
        value = without_draft_heading
        actions.append("removed_leading_heading_fragment")

    without_inline_heading = INLINE_KNOWN_HEADING_RE.sub(" ", value)
    if without_inline_heading != value:
        value = without_inline_heading
        actions.append("removed_inline_heading_fragment")

    fixed_terms = re.sub(r"인권\s+노동", "인권·노동", value)
    fixed_terms = re.sub(
        r"디지털\s*전환이\s*빠르게\s*진행됨에\s*따라\s*정보보안\s*및\s*정보보호의\s*중요성이\s*증가함에\s*따라",
        "디지털 전환이 빠르게 진행되면서 정보보안 및 정보보호의 중요성이 커짐에 따라",
        fixed_terms,
    )
    fixed_terms = re.sub(r"이상사례\s+안전성\s+문제", "이상사례와 안전성 문제", fixed_terms)
    fixed_terms = re.sub(r"과학적으로\s*탐지\s*평가하는", "과학적으로 탐지·평가하는", fixed_terms)
    fixed_terms = re.sub(
        r"RMP\s+재평가\s+보고\s+재심사\s+사용권고",
        "RMP, 재평가, 보고, 재심사, 사용권고",
        fixed_terms,
    )
    fixed_terms = re.sub(
        r"대웅그룹의\s*이사회는\s*대표이사를\s*포함한\s*이사회\s*체계를\s*운영하며",
        "대웅그룹은 대표이사를 포함한 이사회를 운영하며",
        fixed_terms,
    )
    fixed_terms = re.sub(
        r"((?:검토\s*중인\s*제안\s*자료상|외부\s*평가\s*자료상|제안\s*자료에\s*따르면,|평가\s*자료에\s*따르면,)\s*)또한[,，]?\s*",
        r"\1",
        fixed_terms,
    )
    fixed_terms = re.sub(r"마련해\s*놓고\s*있습니다", "운영하고 있습니다", fixed_terms)
    if fixed_terms != value:
        value = fixed_terms
        actions.append("repaired_awkward_korean_phrase")

    without_source_attribution = SOURCE_ATTRIBUTION_RE.sub("", value).strip()
    if without_source_attribution != value:
        value = without_source_attribution
        actions.append("removed_source_attribution")

    value = re.sub(r",\s*,", ",", value)
    value = re.sub(r"\.\s*,", ". ", value)
    value = re.sub(r"(^|\s)[,，]\s*", r"\1", value)
    repaired_parenthetical = re.sub(
        r"분할\s*물적\s*분할\s*포함\)",
        "분할(물적 분할 포함)",
        value,
    )
    if repaired_parenthetical != value:
        value = repaired_parenthetical
        actions.append("repaired_parenthetical_fragment")
    trimmed = TRAILING_HEADING_FRAGMENT_RE.sub("", value).strip()
    if trimmed != value:
        value = trimmed
        actions.append("removed_trailing_heading_fragment")
    value = re.sub(r"\s{2,}", " ", value).strip(" ,")
    return value, list(dict.fromkeys(actions))


def clean_customer_evidence_text(text: str) -> tuple[str, list[str]]:
    """Remove source/editorial boilerplate before deterministic answer fallback."""

    value = str(text or "").strip()
    actions: list[str] = []
    if not value:
        return "", []
    lower = value.casefold()
    cleanup_needed = (
        bool(ARROW_EDITORIAL_RE.search(value))
        or bool(NAME_TAG_PREFIX_RE.search(value))
        or bool(REPORT_NAV_RE.search(value))
        or bool(SECTION_HEADING_RE.search(value))
        or any(term.casefold() in lower for term in EDITORIAL_CUE_TERMS)
        or sum(term in lower for term in DOCUMENT_NAV_TERMS) >= 2
    )
    if not cleanup_needed:
        return value, []

    cleaned = ARROW_EDITORIAL_RE.sub(" ", value)
    cleaned = NAME_TAG_PREFIX_RE.sub(" ", cleaned)
    cleaned = REPORT_NAV_RE.sub(" ", cleaned)
    cleaned = SECTION_HEADING_RE.sub(" ", cleaned)
    for term in DOCUMENT_NAV_TERMS:
        cleaned = re.sub(re.escape(term), " ", cleaned, flags=re.IGNORECASE)

    segments = [
        segment.strip(" \t\r\n,;:-·•")
        for segment in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", cleaned)
        if segment.strip(" \t\r\n,;:-·•")
    ]
    retained: list[str] = []
    for segment in segments:
        normalized = " ".join(segment.split())
        lower = normalized.casefold()
        if EDITORIAL_SENTENCE_RE.search(normalized):
            continue
        if sum(term in lower for term in DOCUMENT_NAV_TERMS) >= 2:
            continue
        if re.fullmatch(r"(?:[A-Z][A-Z\s&/-]{2,}|[0-9\s.]+)", normalized):
            continue
        retained.append(normalized)

    result = " ".join(retained).strip()
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\s+([.!?\u3002\uff01\uff1f])", r"\1", result).strip()
    if result != value:
        actions.append("removed_source_boilerplate")
    return result, actions


def safe_narrative_text(text: str) -> str:
    cleaned, _ = clean_customer_evidence_text(text)
    normalized, _ = normalize_answer_coherence(cleaned)
    return "" if non_narrative_reason(normalized) else normalized
