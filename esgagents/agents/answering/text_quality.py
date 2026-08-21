from __future__ import annotations

import re
import unicodedata


RAW_TABLE_TERMS = (
    "raw data 취합",
    "정량데이터 취합",
    "제품군 리스트",
    "연간출고량",
    "parsed facts",
    "table block",
    # A column-header row: "구분 | 기능 | 실적" flattened into running text. Bare
    # consecutive header nouns never occur in a written sentence.
    "구분 기능 실적",
)
# Web-page and news-portal chrome that survives scraping. Every marker here is
# site furniture that no ESG disclosure sentence contains: accessibility
# skip-links, and the copyright/serial footer of a news article. "공지사항" is
# deliberately NOT a marker -- a privacy policy legitimately says it will
# announce amendments "웹사이트 공지사항을 통하여".
WEB_CHROME_TERMS = (
    "주메뉴바로가기",
    "본문바로가기",
    "메뉴바로가기",
    "콘텐츠바로가기",
    "무단전재",
    "배포금지",
    "연재물",
    "관련기사",
)
# The same bracketed publisher tag repeated inside one sentence -- "[딜사이트]
# 증권 포럼 [딜사이트] 유통 포럼" -- is a link list, never a sentence.
REPEATED_BRACKET_TAG_RE = re.compile(r"(\[[^\[\]\n]{2,12}\])(?:[^\[\n]{0,60}\1)+")
# A run of relative-age stamps ("160일 ... 36일 ...") is a headline feed.
NEWS_AGE_STAMP_RE = re.compile(r"(?<![\d,.])\d{1,3}일(?=\s)")


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
START_CONNECTOR_RE = re.compile(
    r"^(?:또한|이에 따라|그리고|아울러|이를 위해|하지만|그\s*결과|이\s*결과|그리하여)[,，]?\s*"
)
# A polite ending running straight into the next clause means the source lost the
# sentence boundary. Only a clause opener is accepted as the follower, so wording
# such as "...라고 합니다 만" is left alone.
MISSING_SENTENCE_STOP_RE = re.compile(
    r"(습니다|합니다|입니다|됩니다)\s+"
    r"(?=(?:그\s*결과|이\s*결과|그리하여|또한|그리고|아울러|하지만|그러나|따라서|이에\s|이러한|"
    r"대웅제약은|대웅그룹은|회사는|당사는))"
)
ATTRIBUTION_PHRASES = (
    "제안/검토 자료에 따르면,",
    "평가 자료에 따르면,",
    "제안 자료에 따르면,",
    "검토 중인 제안 자료상",
    "외부 평가 자료상",
    "according to the draft proposal,",
    "according to the proposal under review,",
    "the proposal under review states:",
    "the proposal under review describes",
    "according to the external assessment,",
    "the external assessment records:",
    "external assessment records:",
    "theo đề xuất đang được xem xét",
    "theo đề xuất",
    "de xuat dang duoc xem xet",
)
SOURCE_ATTRIBUTION_RE = re.compile(
    r"(?:제안/검토\s*자료에\s*따르면,?|평가\s*자료에\s*따르면,?|제안\s*자료에\s*따르면,?|"
    r"검토\s*중인\s*제안\s*자료상|외부\s*평가\s*자료상|"
    r"according\s+to\s+the\s+draft\s+proposal,?|according\s+to\s+the\s+proposal\s+under\s+review,?|"
    r"the\s+proposal\s+under\s+review\s+(?:states:|describes(?:\s+that)?)|"
    r"according\s+to\s+the\s+external\s+assessment,?|(?:the\s+)?external\s+assessment\s+records:|"
    r"theo\s+(?:đề|de)\s*xuất(?:\s+(?:đang|dang)\s+(?:được|duoc)\s+xem\s+xét)?,?|"
    r"(?:đề|de)\s*xuất\s+(?:đang|dang)\s+(?:được|duoc)\s+xem\s+xét)\s*",
    flags=re.IGNORECASE,
)
SOURCE_LIMITATION_REWRITE_RE = re.compile(
    r"(?:방안으로\s*제시(?:하고\s*있습니다|됩니다|된|됨)?|"
    r"presented\s+as\s+(?:a\s+)?(?:proposal|proposed\s+measure|measure|plan)|"
    r"described\s+as\s+(?:a\s+)?(?:proposal|proposed\s+measure|measure|plan))",
    flags=re.IGNORECASE,
)
YEAR_EQUALS_RE = re.compile(r"\b(?:19|20)\d{2}\s*=")
LEADING_FRAGMENT_RE = re.compile(
    r"^(?:[a-z]{1,8}(?:/[a-z]{1,8})?\)|[a-z]{1,8}/[a-z]{1,8}\)|[%/]+\))",
    flags=re.IGNORECASE,
)
KOREAN_LEADING_DEPENDENT_FRAGMENT_RE = re.compile(
    r"^(?:미치는|인식하는|발생하는|검토하는|수렴하는|반영하는|관리하는|제공하는|수립하는)\s+\S+"
)
ENUMERATION_STUB_RE = re.compile(r"^(?:\d+[.)]?\s*)+$")
LEADING_NUMBERED_BLOCK_RE = re.compile(r"^\d+[.)]\s+\S+")
ANY_LIST_MARKER_RE = re.compile(r"(?:^|\s)(?:\d{1,3}[.)]|[A-Za-z][.)]|[IVXivx]{1,6}[.)])\s+\S+")
TRAILING_LIST_MARKER_RE = re.compile(r"(?:^|\s)(?:\d{1,3}[.)]|[A-Za-z][.)]|[IVXivx]{1,6}[.)])\s*$")
SPECIAL_LIST_SYMBOL_RE = re.compile(
    r"[\u2022\u2023\u2043\u204c\u204d\u2219\u25a0-\u25ff\u2605-\u2606\u2610-\u2612\u2713-\u2718\u2756\u276f]"
)
LEADING_SPECIAL_LIST_SYMBOL_RE = re.compile(
    r"^[\u2022\u2023\u2043\u204c\u204d\u2219\u25a0-\u25ff\u2605-\u2606\u2610-\u2612\u2713-\u2718\u2756\u276f]\s+\S+"
)
REFERENCE_MARK_RE = re.compile(r"[\u203b\uff0a]")
QUESTION_MARK_RE = re.compile(r"[?\uff1f]")
LEADING_PARENTHETICAL_HEADING_RE = re.compile(r"^\(([^)]{0,60})\)\s+\S+")
KOREAN_CHAR_RE = re.compile(r"[\uac00-\ud7a3]")
KOREAN_DECLARATIVE_ENDING_RE = re.compile(
    r"(?:다|니다|습니다|입니다|합니다|됩니다|있습니다|없습니다|였습니다|하였습니다|한다|된다|있다|없다)[.。]?$"
)
KOREAN_QUESTION_CONTEXT_RE = re.compile(
    r"(?:있는지|하는지|했는지|인지|여부(?:를)?|관련\s*질문|핵심지표란)\s*(?:확인)?\s*[.。/\\|]*$"
)
LEADING_PROCEDURE_HEADING_FRAGMENT_RE = re.compile(
    r"^[^.?!\u3002\uff01\uff1f]{0,120}(?:업무\s*절차|work\s*procedure|procedure)\s*\)\s+\S+",
    flags=re.IGNORECASE,
)
REPORT_COVER_BOILERPLATE_RE = re.compile(
    r"^(?=[^.?!\u3002\uff01\uff1f]{0,220}\bESG\s+DATA\s+REPORT\b)"
    r"(?=[^.?!\u3002\uff01\uff1f]{0,260}(?:보고서\s*개요|report\s+overview))",
    flags=re.IGNORECASE,
)
KOREAN_NARRATIVE_START_RE = re.compile(
    r"(?:회사는|당사는|[A-Za-z0-9&()./\-·\uac00-\ud7a3]{2,50}(?:은|는)\s)"
)
LEADING_EXAMPLE_RE = re.compile(
    r"^\(?\s*(?:예|예시|e\.g\.|example)\s*[:：)]",
    flags=re.IGNORECASE,
)
INTRO_ONLY_RE = re.compile(
    r"(?:다음과\s*같습니다|다음과\s*같다|as\s+follows)\s*[:.]?\s*(?:\d+[.)]?)?\s*$",
    flags=re.IGNORECASE,
)
# Text sitting between a report cover/title-or-contents marker and the first
# narrative clause is navigation, section headings or an internal working note --
# never prose worth keeping. The working-note markers exclude their polite and
# connective forms, which do occur in real sentences ("...전달 예정입니다").
DOCUMENT_TITLE_PREFIX_RE = re.compile(
    r"지속가능경영보고서|보고서\s*개요|SUSTAINABILITY\s+REPORT|ESG\s+DATA\s+REPORT"
    r"|CEO\s*메시지|CompanyProfile|Company\s+Profile|BusinessPerformance"
    r"|ESG경영\s*Framework|\[\s*E\s*\]\s*\[\s*S\s*\]\s*\[\s*G\s*\]"
    r"|(?:취합|전달|작성|검토)\s*예정(?!입니다|이며|이고|이나)"
    r"|사진\s*[가-힣]{2,10}팀",
    flags=re.IGNORECASE,
)
# A Korean statute/regulation clause heading is document structure, not prose.
# The bare-index form covers a clause number split from its text ("3 2인 이상의 ...").
STATUTE_CLAUSE_HEADING_RE = re.compile(
    r"^(?:제\s*\d+\s*[장절조](?:의\s*\d+)?|\d{1,2}\s+(?=[가-힣\d]))"
)
# Source regulations and policies are written in the plain declarative register
# (``~한다``/``~할 수 있다``); the customer answer is written in the polite register
# (``~합니다``). A plain-register sentence in the answer is pasted source text.
PLAIN_REGISTER_SENTENCE_RE = re.compile(
    r"(?:한다|한다고\s*한다|할\s*수\s*있다|될\s*수\s*있다|된다|아니다|이다)\s*[.。]?\s*$"
)
ENUMERATION_PROMISE_RE = re.compile(
    r"\ub2e4\uc74c\uacfc\s*\uac19\uc740\s*[^.!?\u3002\uff01\uff1f]{0,40}?"
    r"(?:\uacc4\ud68d|\ud56d\ubaa9|\ub0b4\uc6a9|\ud65c\ub3d9|\uc815\ucc45|\uae30\uc900|\uc808\ucc28|\uc0ac\ud56d|\uacfc\uc81c|\uc870\uce58|\ud504\ub85c\uadf8\ub7a8|\uc81c\ub3c4|\uccb4\uacc4)\s*(?:\uc744|\ub97c)\s*"
    r"[^.!?\u3002\uff01\uff1f]{0,24}(?:\ud569\ub2c8\ub2e4|\uc788\uc2b5\ub2c8\ub2e4|\ud558\uc600\uc2b5\ub2c8\ub2e4)\s*[.\u3002]?\s*$"
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
    r"(?:^|\s+)(?:업계최초\s*직무급\s*제도와\s*여성인재\s*육성|품질\s*부문\s*조직|"
    r"(?:EHS\s*인증\s*현황\s*)?(?:EHS\s*중장기\s*목표\s*)?(?:환경경영\s*관리체계\s*)?환경경영)"
    r"\s+(?=(?:대웅제약은|대웅은|당사는|회사는)\b)"
)
INLINE_SOURCE_REFERENCE_RE = re.compile(
    r"(?:^|\s+)(?:[A-Za-z가-힣()·\s]{0,40}\s*)?(?:20\d{2}\s*)?"
    r"(?:SR\s*보고서|지속가능경영보고서)\s*P\.?\s*\d+"
    r"(?:(?!참고|source|출처)[^.!?\u3002\uff01\uff1f]){0,220}"
    r"(?:참고|source|출처)\s*",
    flags=re.IGNORECASE,
)

ALLOWED_SYMBOL_PUNCTUATION = set("%&+-/=@.,;:()[]·")


def _capitalize_initial_ascii(text: str) -> str:
    if text and "a" <= text[0] <= "z":
        return text[0].upper() + text[1:]
    return text


def normalize_final_answer_text(text: str) -> tuple[str, list[str]]:
    """Normalize customer prose without chasing one-off bad characters."""

    original = str(text or "").strip()
    value = unicodedata.normalize("NFKC", original)
    actions: list[str] = []
    retained: list[str] = []
    removed_control = False
    removed_symbol = False
    for char in value:
        category = unicodedata.category(char)
        if char in "\n\t":
            retained.append(char)
            continue
        if category[0] == "C":
            removed_control = True
            continue
        if category[0] == "Z":
            retained.append(" ")
            continue
        if (
            category[0] in {"P", "S"}
            and char not in ALLOWED_SYMBOL_PUNCTUATION
            and char not in {"'", '"'}
        ):
            retained.append(" ")
            removed_symbol = True
            continue
        retained.append(char)

    cleaned = "".join(retained)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(
        r"^[\u2022\u2023\u2043\u204c\u204d\u2219\u25a0-\u25ff\u2605-\u2606\u2610-\u2612\u2713-\u2718\u2756\u276f]\s+",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:\s*[/\\|]+\s*)+([.。])$", r"\1", cleaned)
    cleaned = re.sub(r"(?:[/\\|]+\s*)+$", "", cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:")
    cleaned_without_intro, removed_intro = remove_intro_only_sentences(cleaned)
    if removed_intro:
        cleaned = cleaned_without_intro
        actions.append("removed_intro_only_sentence")
    cleaned_without_generic_metric, removed_generic_metric = (
        remove_duplicate_underspecified_metric_sentences(cleaned)
    )
    if removed_generic_metric:
        cleaned = cleaned_without_generic_metric
        actions.append("removed_underspecified_duplicate_metric_sentence")
    if removed_control:
        actions.append("removed_control_unicode")
    if removed_symbol:
        actions.append("removed_symbol_punctuation")
    if cleaned != original and not actions:
        actions.append("normalized_unicode_punctuation")
    return cleaned, actions


def remove_intro_only_sentences(text: str) -> tuple[str, bool]:
    parts = [
        part.strip()
        for part in re.split(
            r"(?<!\d)(?<=[.!?\u3002\uff01\uff1f])(?!\d)\s+",
            str(text or ""),
        )
        if part.strip()
    ]
    if len(parts) < 2:
        return text, False
    retained: list[str] = []
    removed = False
    for index, part in enumerate(parts):
        stripped = part.strip()
        is_last = index == len(parts) - 1
        if not is_last and INTRO_ONLY_RE.search(stripped):
            removed = True
            continue
        # A trailing sentence that announces a list nothing follows is an
        # unfulfilled promise: the enumeration it introduced was dropped
        # upstream, so the announcement reads as a truncated answer.
        if is_last and index > 0 and (
            INTRO_ONLY_RE.search(stripped) or ENUMERATION_PROMISE_RE.search(stripped)
        ):
            removed = True
            continue
        retained.append(part)
    if not removed or not retained:
        return text, False
    return " ".join(retained).strip(), True


def remove_duplicate_underspecified_metric_sentences(text: str) -> tuple[str, bool]:
    parts = [
        part.strip()
        for part in re.split(
            r"(?<!\d)(?<=[.!?\u3002\uff01\uff1f])(?!\d)\s+",
            str(text or ""),
        )
        if part.strip()
    ]
    if len(parts) < 2:
        return text, False
    compact_parts = [re.sub(r"\s+", "", part).casefold() for part in parts]
    retained: list[str] = []
    removed = False
    for index, part in enumerate(parts):
        if not re.match(r"^(?:목표|target)\s*(?:은|는|:)", part, flags=re.IGNORECASE):
            retained.append(part)
            continue
        tokens = {
            re.sub(r"\s+", "", match.group(0)).casefold()
            for match in re.finditer(
                r"\d[\d,.]*\s*(?:%|건|명|인|회|개|톤|tons?|tonnes?|tCO2e|GJ/억원|kg/억원|억원|원|시간|hours?)",
                part,
                flags=re.IGNORECASE,
            )
        }
        if tokens and any(
            token in other and idx != index
            for token in tokens
            for idx, other in enumerate(compact_parts)
        ):
            removed = True
            continue
        retained.append(part)
    if not removed:
        return text, False
    return " ".join(retained).strip(), True


def final_answer_block_reason(text: str) -> str:
    """Return why text must not be exposed as a customer-facing Final Answer."""

    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    structural = non_narrative_reason(value)
    if structural:
        return structural
    if KOREAN_QUESTION_CONTEXT_RE.search(value) or QUESTION_MARK_RE.search(value):
        return "question_context_output"
    hangul_count = len(KOREAN_CHAR_RE.findall(value))
    if hangul_count >= 8 and not KOREAN_DECLARATIVE_ENDING_RE.search(value):
        return "korean_fragment_output"
    return ""


def customer_source_attribution_reason(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    if SOURCE_ATTRIBUTION_RE.search(value):
        return "source_attribution_output"
    if SOURCE_LIMITATION_REWRITE_RE.search(value):
        return "source_limitation_rewrite_output"
    return ""


def clean_final_answer_for_customer(text: str) -> tuple[str, str, list[str]]:
    """Normalize and validate the final customer answer in one idempotent pass."""

    original = str(text or "").strip()
    without_title_run, removed_title_run = strip_leading_document_title_run(original)
    if removed_title_run:
        original = without_title_run
    initial_reason = final_answer_block_reason(original)
    cleaned, actions = normalize_final_answer_text(original)
    if removed_title_run:
        actions.append("removed_leading_document_title_run")
    without_source_attribution = SOURCE_ATTRIBUTION_RE.sub("", cleaned).strip()
    if without_source_attribution != cleaned:
        cleaned = _capitalize_initial_ascii(without_source_attribution)
        actions.append("removed_source_attribution")
    cleaned_reason = final_answer_block_reason(cleaned)
    salvaged, salvage_actions = salvage_final_answer_narrative(
        cleaned,
        initial_reason or cleaned_reason,
    )
    if salvaged:
        cleaned = salvaged
        actions.extend(salvage_actions)
    deduplicated, removed_duplicate = deduplicate_repeated_sentences(cleaned)
    if removed_duplicate:
        cleaned = deduplicated
        actions.append("deduplicated_repeated_sentence")
    without_chrome, removed_chrome = drop_web_chrome_sentences(cleaned)
    if removed_chrome:
        cleaned = without_chrome
        actions.append("removed_web_navigation_sentence")
    cleaned_reason = final_answer_block_reason(cleaned)
    final_reason = cleaned_reason if initial_reason == "korean_fragment_output" else initial_reason or cleaned_reason
    if salvaged and not cleaned_reason:
        final_reason = ""
    return cleaned, final_reason, actions


# Sentence-final plain/journalistic endings mapped to the polite register the
# customer answer is written in. Every entry is a sentence-final verb ending, so
# the substitution is anchored at the end of a sentence and cannot alter wording
# mid-clause. Order matters: 아니다 must be matched before the shorter 이다.
POLITE_REGISTER_ENDINGS = (
    ("아니다", "아닙니다"),
    ("이다", "입니다"),
    ("한다", "합니다"),
    ("있다", "있습니다"),
    ("없다", "없습니다"),
    ("된다", "됩니다"),
    ("했다", "했습니다"),
    ("됐다", "됐습니다"),
    ("였다", "였습니다"),
    ("웠다", "웠습니다"),
)
POLITE_REGISTER_RE = re.compile(
    r"(" + "|".join(plain for plain, _ in POLITE_REGISTER_ENDINGS) + r")(\s*[.。]?)\s*$"
)
POLITE_REGISTER_MAP = dict(POLITE_REGISTER_ENDINGS)


def normalize_to_polite_register(text: str) -> tuple[str, list[str]]:
    """Restate source-register sentences in the answer's polite register.

    Regulations, policies and press copy are written in the plain or journalistic
    register (``관리한다``, ``요청할 수 있다``, ``진행됐다``) while the customer answer uses
    the polite one (``관리합니다``). Dropping such a sentence loses real disclosure, so
    convert it instead. Only the sentence-final ending is rewritten, which keeps
    the clause structure -- and therefore the meaning -- untouched.
    """

    sentences = re.split(r"((?<=[.!?。！？])\s+|\n+)", str(text or ""))
    converted: list[str] = []
    actions: list[str] = []
    for index, chunk in enumerate(sentences):
        if index % 2 or not chunk.strip():
            converted.append(chunk)
            continue
        match = POLITE_REGISTER_RE.search(chunk.rstrip())
        if match is None:
            converted.append(chunk)
            continue
        trailing = chunk[len(chunk.rstrip()):]
        replacement = POLITE_REGISTER_MAP[match.group(1)] + (match.group(2) or "")
        converted.append(
            chunk.rstrip()[: match.start()] + replacement + trailing
        )
        actions.append("normalized_to_polite_register")
    return "".join(converted), list(dict.fromkeys(actions))


def plain_register_sentences(text: str) -> list[str]:
    """Return answer sentences written in the source register rather than prose.

    Regulations and internal policies use the plain declarative form (``~한다``),
    while the customer answer uses the polite form (``~합니다``). A plain-register
    sentence therefore signals source text quoted verbatim, which both breaks the
    register and states a rule as if it described practice. Rewriting Korean verb
    endings mechanically risks ungrammatical output, so this only reports.
    """

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+", str(text or ""))
        if part.strip()
    ]
    return [part for part in sentences if PLAIN_REGISTER_SENTENCE_RE.search(part)]


def _leading_structural_run_end(value: str) -> int | None:
    """End offset of a leading cover/heading or timeline run, if the answer has one.

    Both shapes are document structure that a table extractor glued in front of real
    prose, and both must sit before any sentence break to qualify -- otherwise an
    ordinary sentence mentioning a report or a set of years would be truncated.
    """

    head = value[:220]
    match = DOCUMENT_TITLE_PREFIX_RE.search(head[:80])
    if match is not None and not re.search(r"[.!?。！？]", value[: match.start()]):
        return match.end()
    # A curated raw-table marker means the rows that follow it are table content;
    # any prose after them is worth keeping on its own.
    for term in RAW_TABLE_TERMS:
        position = head.casefold().find(term.casefold())
        if position >= 0 and not re.search(r"[.!?。！？]", value[:position]):
            return position + len(term)
    # A roadmap or milestone table arrives as bare years with no predicate between
    # them. Years written as "2025년" belong to prose and are excluded.
    years = list(re.finditer(r"(?<!\d)(?:19|20)\d{2}(?!\s*년|\s*\.|\d)", head))
    if len(years) >= 3 and not re.search(r"[.!?。！？]", value[: years[-1].end()]):
        return years[-1].end()
    return None


def strip_leading_document_title_run(text: str) -> tuple[str, bool]:
    """Drop a leading report title plus the section headings that follow it.

    A grammatical sentence can arrive with a cover/heading run glued to its
    front -- ``"대웅제약 2025 지속가능경영보고서 약물감시 활동 및 성과 약물감시 조직 및 매뉴얼
    고도화 대웅제약의 약물감시는 ... 준수합니다."``. The sentence itself is valid, so no
    structural gate rejects it; only the prefix has to go. The marker must sit at
    the start of the answer, before any sentence break, so an in-sentence mention
    such as ``"지속가능경영보고서 발간"`` is untouched. A roadmap or timeline table
    reaches the answer the same way, recognised instead by its run of bare years.
    """

    value = " ".join(str(text or "").split())
    if not value:
        return text, False
    parts = re.split(r"(?<=[.!?。！？])\s+", value)
    stripped = [_strip_structural_run_from_sentence(part) for part in parts]
    if stripped == parts:
        return text, False
    return " ".join(part for part in stripped if part).strip(), True


def _strip_structural_run_from_sentence(sentence: str) -> str:
    """Remove a cover/heading or timeline run glued to the front of one sentence.

    A table extractor can attach the run to any sentence, not only the first, so a
    roadmap block reaches the middle of an answer just as readily as its start.
    """

    value = sentence.strip()
    if not value:
        return sentence
    run_end = _leading_structural_run_end(value)
    if run_end is None:
        return sentence
    narrative = KOREAN_NARRATIVE_START_RE.search(value, run_end)
    if narrative is None or narrative.start() <= run_end:
        return sentence
    remainder = value[narrative.start():].strip(" ,;:-·|")
    if not _has_salvage_substance(remainder) or final_answer_block_reason(remainder):
        return sentence
    return remainder


def salvage_final_answer_narrative(text: str, reason: str) -> tuple[str, list[str]]:
    """Keep existing narrative prose after removable list/heading fragments."""

    if reason not in {
        "list_fragment_output",
        "list_dump_output",
        "numbered_block_output",
        "symbol_marker_output",
        "parenthetical_heading_output",
        "korean_leading_fragment_output",
    }:
        return "", []
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return "", []

    retained: list[str] = []
    for segment in _salvage_candidate_segments(value, reason):
        candidate = _clean_salvage_candidate(segment)
        if not candidate or candidate == value:
            continue
        if not _has_salvage_substance(candidate):
            continue
        if final_answer_block_reason(candidate):
            continue
        retained.append(candidate)

    if not retained:
        return "", []
    result = " ".join(dict.fromkeys(retained))
    result = re.sub(r"\s{2,}", " ", result).strip()
    return result, ["salvaged_narrative_after_list_or_heading"]


def _salvage_candidate_segments(value: str, reason: str) -> list[str]:
    segments: list[str] = []
    if reason == "parenthetical_heading_output":
        segments.append(LEADING_PARENTHETICAL_HEADING_RE.sub("", value, count=1))
    segments.extend(
        segment
        for segment in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", value)
        if segment.strip()
    )
    segments.extend(segment for segment in ANY_LIST_MARKER_RE.split(value) if segment.strip())
    markers = list(ANY_LIST_MARKER_RE.finditer(value))
    if markers:
        segments.append(value[markers[-1].end():])
    return segments


def _is_droppable_salvage_prefix(prefix: str) -> bool:
    """Allow the narrative-start cut only when nothing substantive precedes it.

    ``KOREAN_NARRATIVE_START_RE`` matches the topic particle ``은/는``, which also
    ends adnominal verb forms and appears mid-sentence constantly. Cutting on the
    leftmost match beheads a complete sentence and silently drops whatever came
    before it -- typically the metric name and its measured values, e.g.
    ``"27개 항목의 이행조치를 완료하고 39개 항목은 이행조치 중에 있습니다."`` collapsing to
    ``"항목은 이행조치 중에 있습니다."``. Only a marker/numbering prefix, or a run of
    report cover and section-heading text, is droppable.
    """

    value = str(prefix or "").strip()
    if not value:
        return False
    if not KOREAN_CHAR_RE.search(value) and not re.search(r"[A-Za-z]", value):
        return True
    return bool(DOCUMENT_TITLE_PREFIX_RE.search(value))


def _clean_salvage_candidate(segment: str) -> str:
    value = str(segment or "").strip(" \t\r\n,;:-/\\|")
    value = LEADING_PARENTHETICAL_HEADING_RE.sub("", value, count=1).strip()
    value = re.sub(r"^(?:\d{1,3}[.)]|[A-Za-z][.)]|[IVXivx]{1,6}[.)])\s+", "", value).strip()
    value = re.sub(
        r"^[\u2022\u2023\u2043\u204c\u204d\u2219\u25a0-\u25ff\u2605-\u2606\u2610-\u2612\u2713-\u2718\u2756\u276f]\s+",
        "",
        value,
    ).strip()
    if SPECIAL_LIST_SYMBOL_RE.search(value) or REFERENCE_MARK_RE.search(value):
        return ""
    if KOREAN_CHAR_RE.search(value):
        explicit_start = re.search(r"(?:회사는|당사는)", value)
        if explicit_start and explicit_start.start() > 0:
            value = value[explicit_start.start():].strip(" ,;:-")
        else:
            narrative_start = KOREAN_NARRATIVE_START_RE.search(value)
            if (
                narrative_start
                and narrative_start.start() > 0
                and _is_droppable_salvage_prefix(value[: narrative_start.start()])
            ):
                value = value[narrative_start.start():].strip(" ,;:-")
    if ANY_LIST_MARKER_RE.search(value):
        return ""
    if TRAILING_LIST_MARKER_RE.search(value):
        return ""
    return re.sub(r"\s{2,}", " ", value).strip()


def _has_salvage_substance(value: str) -> bool:
    letters = re.findall(r"[A-Za-z\uac00-\ud7a3]", str(value or ""))
    return len(str(value or "").strip()) >= 12 and len(letters) >= 6


def non_narrative_reason(text: str) -> str:
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    lower = value.casefold()
    if any(term.casefold() in lower[:500] for term in EDITORIAL_CUE_TERMS):
        return "editorial_instruction_output"
    if REPORT_COVER_BOILERPLATE_RE.search(value):
        return "document_boilerplate_output"
    if LEADING_PROCEDURE_HEADING_FRAGMENT_RE.search(value):
        return "procedure_heading_fragment_output"
    if STATUTE_CLAUSE_HEADING_RE.search(value):
        return "statute_clause_output"
    if any(term.casefold() in lower for term in RAW_TABLE_TERMS):
        return "raw_table_output"
    if LEADING_NUMBERED_BLOCK_RE.search(value):
        return "numbered_block_output"
    if len(ANY_LIST_MARKER_RE.findall(value)) >= 2:
        return "list_dump_output"
    if ANY_LIST_MARKER_RE.search(value):
        return "list_fragment_output"
    special_markers = SPECIAL_LIST_SYMBOL_RE.findall(value)
    if REFERENCE_MARK_RE.search(value) or (
        special_markers
        and not (len(special_markers) == 1 and LEADING_SPECIAL_LIST_SYMBOL_RE.search(value))
    ):
        return "symbol_marker_output"
    heading_match = LEADING_PARENTHETICAL_HEADING_RE.search(value)
    if heading_match and not re.search(r"\d", heading_match.group(1)):
        return "parenthetical_heading_output"
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
    if KOREAN_LEADING_DEPENDENT_FRAGMENT_RE.search(value):
        return "korean_leading_fragment_output"
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
    with_stops = MISSING_SENTENCE_STOP_RE.sub(r"\1. ", value)
    if with_stops != value:
        value = with_stops
        actions.append("restored_sentence_boundary")

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

    without_source_reference = INLINE_SOURCE_REFERENCE_RE.sub(" ", value)
    if without_source_reference != value:
        value = without_source_reference
        actions.append("removed_inline_source_reference")

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
        r"((?:검토\s*중인\s*제안\s*자료상|외부\s*평가\s*자료상|제안\s*자료에\s*따르면,|평가\s*자료에\s*따르면,|according\s+to\s+the\s+draft\s+proposal,?|according\s+to\s+the\s+proposal\s+under\s+review,?|according\s+to\s+the\s+external\s+assessment,?)\s*)또한[,，]?\s*",
        r"\1",
        fixed_terms,
    )
    fixed_terms = re.sub(r"마련해\s*놓고\s*있습니다", "운영하고 있습니다", fixed_terms)
    if fixed_terms != value:
        value = fixed_terms
        actions.append("repaired_awkward_korean_phrase")

    without_source_attribution = SOURCE_ATTRIBUTION_RE.sub("", value).strip()
    if without_source_attribution != value:
        value = _capitalize_initial_ascii(without_source_attribution)
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
    deduplicated, removed_duplicate = deduplicate_repeated_sentences(value)
    if removed_duplicate:
        value = deduplicated
        actions.append("deduplicated_repeated_sentence")
    value = re.sub(r"\s{2,}", " ", value).strip(" ,")
    return value, list(dict.fromkeys(actions))


def _is_web_chrome_sentence(sentence: str) -> bool:
    """True when the sentence is scraped site furniture rather than prose."""

    value = str(sentence or "")
    lowered = value.casefold()
    if any(term in lowered for term in WEB_CHROME_TERMS):
        return True
    if REPEATED_BRACKET_TAG_RE.search(value):
        return True
    return len(NEWS_AGE_STAMP_RE.findall(value)) >= 2


NEWS_FOOTER_TERMS = ("무단전재", "배포금지", "연재물", "관련기사")


def drop_web_chrome_sentences(text: str) -> tuple[str, bool]:
    """Remove scraped navigation/headline sentences, keeping the real prose.

    Removal is per sentence because the dump is often embedded between valid
    sentences: a privacy-policy answer can carry four good sentences, then the
    whole site menu, then a closing sentence.
    """

    parts = [
        part
        for part in re.findall(r"[^.!?。！？]+[.!?。！？]?", str(text or ""))
        if part.strip()
    ]
    if not parts:
        return text, False
    # A news-portal footer anywhere in the answer establishes that the passage
    # was scraped from an article page. Sentence splitting shatters a headline
    # feed into fragments that each carry only one age stamp, so inside such an
    # answer a single stamp is enough to identify the remaining fragments.
    from_news_page = any(term in str(text or "") for term in NEWS_FOOTER_TERMS)
    retained = [
        part
        for part in parts
        if not _is_web_chrome_sentence(part)
        and not (from_news_page and NEWS_AGE_STAMP_RE.search(part))
    ]
    if len(retained) == len(parts):
        return text, False
    return " ".join(part.strip() for part in retained).strip(), True


def deduplicate_repeated_sentences(text: str) -> tuple[str, bool]:
    parts = [
        part.strip()
        for part in re.findall(r"[^.!?\u3002\uff01\uff1f]+[.!?\u3002\uff01\uff1f]?", str(text or ""))
        if part.strip()
    ]
    if len(parts) < 2:
        return text, False
    keys = [_sentence_identity_key(part) for part in parts]
    seen: set[str] = set()
    retained: list[str] = []
    removed = False
    for index, part in enumerate(parts):
        key = keys[index]
        if len(key) >= 30 and key in seen:
            removed = True
            continue
        if _is_redundant_sentence_fragment(key, index, keys):
            removed = True
            continue
        seen.add(key)
        retained.append(part)
    if not removed:
        return text, False
    return " ".join(retained).strip(), True


def _sentence_identity_key(part: str) -> str:
    """Collapse spacing and separator noise so re-typed repeats compare equal.

    Writers restate the same evidence sentence with different word spacing or
    with ``\u00b7`` swapped for a space (``\uacfc\ud559\uc801\uc73c\ub85c``/``\uacfc\ud559\uc801 \uc73c\ub85c``,
    ``\ud0d0\uc9c0\u00b7\ud3c9\uac00``/``\ud0d0\uc9c0 \ud3c9\uac00``), which an exact-string check treats as distinct.
    """

    value = unicodedata.normalize("NFKC", str(part or ""))
    value = value.rstrip(".!?\u3002\uff01\uff1f").strip()
    return re.sub(r"[\s\u00b7\u2027\u30fb,;:()\[\]/\\|\-\u2013\u2014]+", "", value).casefold()


def _is_redundant_sentence_fragment(key: str, index: int, keys: list[str]) -> bool:
    """Drop a sentence that another sentence already states in full.

    A beheaded copy of a sentence can survive next to the intact one -- e.g.
    ``"\uc9c0\uc6d0\ud558\ub294 \ubc29\uc548\uc744 \uac80\ud1a0 \uc911\uc5d0 \uc788\uc2b5\ub2c8\ub2e4."`` alongside the complete
    ``"\ub610\ud55c, \uacf5\uae09\ub9dd \ub0b4\uc5d0 ... \ub179\uc0c9\uc81c\ud488 \uacf5\uae09\uc744 \uc9c0\uc6d0\ud558\ub294 \ubc29\uc548\uc744 \uac80\ud1a0 \uc911\uc5d0 \uc788\uc2b5\ub2c8\ub2e4."``. The
    fragment adds nothing and reads as a truncation defect, so keep the longer
    sentence only. Matching is restricted to a suffix: an arbitrary substring can
    be a legitimate shorter statement, but a tail that another sentence completes
    is the beheading signature.
    """

    if len(key) < 12:
        return False
    for other_index, other in enumerate(keys):
        if other_index == index or len(other) <= len(key):
            continue
        if other.endswith(key):
            return True
    return False


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
    final, reason, _ = clean_final_answer_for_customer(normalized)
    return "" if reason else final
