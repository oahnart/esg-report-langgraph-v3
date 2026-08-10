from __future__ import annotations

import re


# Final answers are copied directly into customer-facing ESG fields. Evidence
# availability and review workflow belong in audit metadata, not in that prose.
# These patterns focus on process/disclaimer language so a factual statement
# about a company's own disclosure practice is not removed.
CUSTOMER_META_LIMITATION_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\bthe scope of (?:the )?supplied (?:evidence|documents?|materials?)\b.*\b(?:confirm|confirmation|required)\b",
        r"\b(?:the )?supplied (?:evidence|documents?|materials?) (?:does not|do not|did not|cannot) confirm\b",
        r"\b(?:not found|could not be found) in (?:the )?supplied (?:evidence|documents?|materials?)\b",
        r"\badditional confirmation (?:is|was|will be) required\b",
        r"\bthis is therefore (?:only )?a partial answer\b",
        r"\bonly supported qualitative information is provided\b",
        r"\bsome content relies on (?:draft|assessment) material\b.*\b(?:confirm|confirmation|required)\b",
        r"\bdo phạm vi (?:của )?(?:tài liệu|nguồn|bằng chứng)(?: được cung cấp)?\b.*\b(?:xác nhận|kiểm chứng) (?:bổ sung|thêm)\b",
        r"\b(?:tài liệu|nguồn|bằng chứng) được cung cấp\b.*\b(?:không|chưa) (?:xác nhận|cho phép xác nhận)\b",
        r"\b(?:không|chưa) tìm thấy\b.*\btrong (?:tài liệu|nguồn|bằng chứng) được cung cấp\b",
        r"\b(?:cần|yêu cầu) (?:được )?(?:xác nhận|kiểm chứng) (?:bổ sung|thêm)\b",
        r"\bđây (?:do đó )?chỉ là (?:một )?câu trả lời (?:một phần|chưa đầy đủ)\b",
        r"\bchỉ cung cấp (?:các )?thông tin định tính (?:đã được hỗ trợ|có căn cứ)\b",
        r"제공된 자료의 범위상.*추가 확인이 필요",
        r"제공된 자료에서.*확인되지.*부분적으로 답변",
        r"추가 확인이 필요",
        r"정성 정보만 제시",
    )
)


def strip_customer_meta_limitations(text: str) -> tuple[str, list[str]]:
    """Remove review/evidence-process disclaimers from customer answer prose."""

    value = str(text or "").strip()
    if not value:
        return "", []
    segments = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?。！？])\s+|\n+", value)
        if segment.strip()
    ]
    retained = [
        segment
        for segment in segments
        if not any(pattern.search(segment) for pattern in CUSTOMER_META_LIMITATION_PATTERNS)
    ]
    cleaned = " ".join(retained).strip()
    actions = ["removed_customer_meta_limitation"] if cleaned != value else []
    return cleaned, actions
