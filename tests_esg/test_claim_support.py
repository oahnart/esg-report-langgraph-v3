from esgagents.agents.answering.claim_support import build_claim_support
from esgagents.schemas import EvidenceItem


def test_claim_support_prefers_operational_source_and_marks_draft_only_claim():
    answer = (
        "회사는 안전보건 정책을 운영합니다. "
        "제안 자료에 따르면 2030년 감축 목표는 30%입니다."
    )
    items = [
        EvidenceItem(
            raw_evidence_ko="회사는 안전보건 정책을 운영합니다.",
            source_path="ESG/policy.docx",
            canonical_source_id="operational",
            source_tier="tier_2_operational",
        ),
        EvidenceItem(
            raw_evidence_ko="2030년 감축 목표 30% 제안",
            source_path="ESG/proposal.docx",
            canonical_source_id="draft",
            source_tier="tier_4_draft",
        ),
    ]

    supports = build_claim_support(answer, items)

    assert [(support.claim_id, support.support_tier) for support in supports] == [
        ("c1", "tier_2_operational"),
        ("c2", "tier_4_draft"),
    ]
    assert supports[0].attribution_required is False
    assert supports[1].attribution_required is False
