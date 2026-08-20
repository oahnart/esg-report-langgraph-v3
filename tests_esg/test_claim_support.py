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


def test_claim_stating_planned_action_as_practice_is_only_partially_supported():
    """Regression for Q003/Q066: evidence commits to a future action while the
    answer reports it as an operating control."""

    items = [
        EvidenceItem(
            raw_evidence_ko=(
                "대웅제약은 협력회사에게 노동인권, 안전보건, 환경, 윤리 등 ESG 전반을 "
                "아우르는 포괄적 관리 기준을 적용하고자 합니다."
            ),
            source_path="ESG/supply_chain.pdf",
            canonical_source_id="operational",
            source_tier="tier_2_operational",
        )
    ]
    support = build_claim_support(
        "대웅제약은 협력회사에 노동인권, 안전보건, 환경, 윤리 등 "
        "ESG 전반의 포괄적 관리 기준을 적용하며 리스크를 관리합니다.",
        items,
    )

    assert [entry.support_status for entry in support] == ["partial"]
    assert support[0].source_ids


def test_planned_action_also_evidenced_as_practice_stays_grounded():
    items = [
        EvidenceItem(
            raw_evidence_ko=(
                "생태환경을 고려한 보호활동을 지속적으로 추진할 계획입니다. "
                "현재도 사업장 인근에서 보호활동을 추진하고 있습니다."
            ),
            source_path="ESG/biodiversity.pdf",
            canonical_source_id="operational",
            source_tier="tier_2_operational",
        )
    ]
    support = build_claim_support(
        "회사는 생태환경을 고려한 보호활동을 지속적으로 추진하고 있습니다.",
        items,
    )

    assert [entry.support_status for entry in support] == ["grounded"]
