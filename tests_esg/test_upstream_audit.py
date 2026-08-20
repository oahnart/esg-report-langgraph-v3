from types import SimpleNamespace

from esgagents.agents.answering.question_contracts import METRIC_DIMENSIONS_BY_QID
from esgagents.agents.evidence.evidence_normalizer import EvidenceNormalizerAgent
from esgagents.agents.evidence.upstream_audit import (
    TOPIC_EXCLUSIONS,
    TOPIC_PATTERNS,
    excluded_topic_dimensions,
    has_grounded_facet,
    verify_upstream_facets,
)
from esgagents.default_config import load_config
from esgagents.quality_flags import canonicalize_quality_flags
from esgagents.schemas import EvidenceItem, RagQuestionResult


def _planned(qid: str, pillar: str = "지표 (Metrics)") -> SimpleNamespace:
    return SimpleNamespace(
        id=qid,
        pillar=pillar,
        item_ko=f"{qid} item",
        description_ko=f"{qid} description",
        example_ko="",
    )


def _item(text: str, **updates) -> EvidenceItem:
    values = {
        "raw_evidence_ko": text,
        "source_name": "report.pdf",
        "source_path": "ESG/report.pdf",
        "semantic_label": "useful",
        "semantic_score": 0.8,
        "source_tier": "tier_2_operational",
        "document_status": "approved",
        "canonical_source_id": "src_report",
        "chunk_id": "doc_report_c1",
    }
    values.update(updates)
    return EvidenceItem(**values)


def _normalize(qid: str, items: list[EvidenceItem], *, pillar: str = "지표 (Metrics)", **rag_updates):
    rag_values = {
        "question_id": qid,
        "answer_status": "high_confidence",
        "coverage_status": "complete",
        "answerable": True,
        "metric_expected": False,
        "items": items,
    }
    rag_values.update(rag_updates)
    return EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {
            "rag_results": {qid: RagQuestionResult(**rag_values)},
            "planned_questions": [_planned(qid, pillar)],
        }
    )["normalized_evidence"][qid]


def test_topic_exclusions_stay_in_step_with_question_contracts():
    # A rename in question_contracts would silently disable topic isolation, so
    # every dimension named here must still be a real question dimension.
    question_dimensions = {
        dimension for dimensions in METRIC_DIMENSIONS_BY_QID.values() for dimension in dimensions
    }
    named = set().union(*[left | right for left, right in TOPIC_EXCLUSIONS])
    assert named <= set(TOPIC_PATTERNS)
    # related_party_transactions is only ever an excluded topic, never asked for.
    assert named - question_dimensions == {"related_party_transactions"}


def test_pollutant_question_excludes_greenhouse_gas_and_the_reverse():
    assert excluded_topic_dimensions(METRIC_DIMENSIONS_BY_QID["Q047"]) == frozenset(
        {"scope_1_emissions", "scope_2_emissions", "scope_3_emissions", "energy_use"}
    )
    assert excluded_topic_dimensions(METRIC_DIMENSIONS_BY_QID["Q031"]) == frozenset(
        {"air_pollutant_emissions", "water_pollutant_emissions"}
    )


def test_question_spanning_both_sides_of_a_pair_excludes_nothing():
    # Q039 asks for water consumption and wastewater discharge together.
    assert excluded_topic_dimensions(METRIC_DIMENSIONS_BY_QID["Q039"]) == frozenset()


def test_greenhouse_gas_evidence_is_dropped_from_a_pollutant_question():
    normalized = _normalize(
        "Q047",
        [
            _item(
                "2025년 Scope 1 직접 배출량은 12,345 tCO2eq, Scope 2 간접 배출량은 6,789 tCO2eq입니다.",
                chunk_id="doc_ghg_c1",
                canonical_source_id="src_ghg",
            ),
            _item(
                "2025년 질소산화물(NOx) 배출량은 12.3 톤으로 관리되고 있습니다.",
                chunk_id="doc_air_c1",
                canonical_source_id="src_air",
            ),
        ],
    )

    assert [item.chunk_id for item in normalized["items"]] == ["doc_air_c1"]
    dropped = normalized["off_topic_evidence_dropped"]
    assert [entry["chunk_id"] for entry in dropped] == ["doc_ghg_c1"]
    assert dropped[0]["substituted_dimensions"] == [
        "scope_1_emissions",
        "scope_2_emissions",
    ]


def test_evidence_covering_the_requested_topic_too_is_kept_as_context():
    normalized = _normalize(
        "Q047",
        [
            _item(
                "2025년 대기 오염 물질 배출량과 함께 Scope 1 배출량을 통합 관리하고 있습니다.",
                chunk_id="doc_both_c1",
            )
        ],
    )

    assert [item.chunk_id for item in normalized["items"]] == ["doc_both_c1"]
    assert normalized["off_topic_evidence_dropped"] == []


def test_topic_isolation_can_be_turned_off():
    config = load_config({"agent_mode": "offline", "topic_isolation_enabled": False})
    normalized = EvidenceNormalizerAgent(config).run(
        {
            "rag_results": {
                "Q047": RagQuestionResult(
                    question_id="Q047",
                    answer_status="high_confidence",
                    coverage_status="complete",
                    answerable=True,
                    metric_expected=False,
                    items=[_item("Scope 1 직접 배출량은 12,345 tCO2eq입니다.", chunk_id="doc_ghg_c1")],
                )
            },
            "planned_questions": [_planned("Q047")],
        }
    )["normalized_evidence"]["Q047"]

    assert [item.chunk_id for item in normalized["items"]] == ["doc_ghg_c1"]
    assert normalized["off_topic_evidence_dropped"] == []


def test_topic_isolation_is_inert_without_planned_questions():
    # Callers that hand the normalizer only rag_results keep the old behaviour.
    normalized = EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {
            "rag_results": {
                "Q047": RagQuestionResult(
                    question_id="Q047",
                    answer_status="high_confidence",
                    coverage_status="complete",
                    answerable=True,
                    metric_expected=False,
                    items=[_item("Scope 1 직접 배출량은 12,345 tCO2eq입니다.")],
                )
            }
        }
    )["normalized_evidence"]["Q047"]

    assert len(normalized["items"]) == 1
    assert normalized["off_topic_evidence_dropped"] == []
    assert normalized["facet_verification"] == {}


def test_metric_row_grounds_metric_result_but_a_cadence_does_not():
    assert has_grounded_facet("합계 | 명 | 2024=6.0 | 2025=7.0", "metric_result")
    assert has_grounded_facet("2025년 배출량은 1,234 톤입니다.", "metric_result")
    assert not has_grounded_facet("EHS경영위원회를 반기 1회 이상 개최합니다.", "metric_result")
    assert not has_grounded_facet("인권경영 정책을 수립하여 운영하고 있습니다.", "metric_result")


def test_claimed_metric_result_without_a_number_is_reported_as_overclaimed():
    verification = verify_upstream_facets(
        covered_facets=["metric_result", "reporting_period"],
        missing_facets=[],
        contract_facets=("metric_result", "reporting_period"),
        items=[_item("2025년 폐기물 관리 절차에 따라 배출 시설을 운영하고 있습니다.")],
    )

    assert verification["overclaimed_facets"] == ["metric_result"]
    assert verification["grounded_facets"] == ["reporting_period"]


def test_facet_claim_backed_by_evidence_is_not_flagged():
    verification = verify_upstream_facets(
        covered_facets=["metric_result", "reporting_period"],
        missing_facets=[],
        contract_facets=("metric_result", "reporting_period"),
        items=[_item("2025년 폐기물 발생량 합계는 1,234 톤입니다.")],
    )

    assert "overclaimed_facets" not in verification
    assert verification["grounded_facets"] == ["metric_result", "reporting_period"]


def test_facet_verification_is_skipped_when_no_evidence_came_back():
    assert (
        verify_upstream_facets(
            covered_facets=["metric_result"],
            missing_facets=[],
            contract_facets=("metric_result",),
            items=[],
        )
        == {}
    )


def test_new_audit_flags_are_canonical():
    canonical, notes = canonicalize_quality_flags(
        ["off_topic_evidence_dropped", "upstream_facet_overclaim"]
    )
    assert canonical == ["off_topic_evidence_dropped", "upstream_facet_overclaim"]
    assert notes == []


def test_gate_blocks_a_question_whose_only_evidence_is_off_topic():
    from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent

    state = {
        "planned_questions": [_planned("Q047")],
        "rag_results": {
            "Q047": RagQuestionResult(
                question_id="Q047",
                answer_status="high_confidence",
                coverage_status="complete",
                answerable=True,
                metric_expected=False,
                items=[_item("2025년 Scope 1 직접 배출량은 12,345 tCO2eq입니다.")],
            )
        },
    }

    gate = EvidenceGateAgent(load_config({"agent_mode": "offline"})).run(state)["evidence_gate"]

    assert gate["Q047"] == {"accepted": False, "reason": "off_topic_evidence_only"}


def test_gate_keeps_the_on_topic_subset():
    from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent

    state = {
        "planned_questions": [_planned("Q047")],
        "rag_results": {
            "Q047": RagQuestionResult(
                question_id="Q047",
                answer_status="high_confidence",
                coverage_status="complete",
                answerable=True,
                metric_expected=False,
                items=[
                    _item("Scope 1 직접 배출량은 12,345 tCO2eq입니다.", chunk_id="doc_ghg_c1"),
                    _item("2025년 질소산화물(NOx) 배출량은 12.3 톤입니다.", chunk_id="doc_air_c1"),
                ],
            )
        },
    }

    gate = EvidenceGateAgent(load_config({"agent_mode": "offline"})).run(state)["evidence_gate"]

    assert gate["Q047"]["accepted"] is True
