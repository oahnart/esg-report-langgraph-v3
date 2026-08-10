from types import SimpleNamespace

import pytest

from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent
from esgagents.agents.evidence.evidence_normalizer import EvidenceNormalizerAgent
from esgagents.agents.evidence.metric_facts import (
    format_metric_number,
    metric_numbers_equivalent,
    resolve_metric_facts,
    salvage_conflicting_metric_claims,
    salvage_unsupported_numeric_metric_claims,
)
from esgagents.default_config import load_config
from esgagents.schemas import (
    EvidenceItem,
    EvidenceFact,
    MetricEvidenceItem,
    RagQuestionResult,
    model_to_dict,
)
from skills.agents.writer import SkillWriterAgent


def _narrative(text: str) -> EvidenceItem:
    return EvidenceItem(
        raw_evidence_ko=text,
        source_name="report.pdf",
        source_path="ESG/report.pdf",
        semantic_label="useful",
        source_tier="tier_2_operational",
        document_status="approved",
    )


def _metric(
    text: str,
    *,
    block: str,
    role: str = "primary",
    entity: str = "Daewoong Pharm",
    entity_class: str = "daewoong_pharm",
    rank: int = 1,
) -> MetricEvidenceItem:
    return MetricEvidenceItem(
        raw_evidence_ko=text,
        source_name="metrics.xlsx",
        source_path="ESG/metrics.xlsx",
        semantic_label="metric_row",
        source_tier="tier_2_operational",
        source_type="operational_record",
        document_status="approved",
        table_block=block,
        block_rank=rank,
        block_role=role,
        entity=entity,
        entity_class=entity_class,
    )


def _planned(qid: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=qid,
        pillar="Metrics",
        item_ko="Metric disclosure",
        description_ko="Metric result and narrative",
        example_ko="",
    )


def test_decimal_rounding_uses_answer_precision():
    assert metric_numbers_equivalent("12,771.822", "12771.822287491")
    assert not metric_numbers_equivalent("12,771.821", "12771.822287491")


def test_metric_not_found_salvage_removes_values_but_keeps_years_and_iso_identifiers():
    answer = (
        "The company has operated ISO 14001 since 2022. "
        "In 2025, the water reuse rate was 9.34%."
    )

    salvaged, actions = salvage_unsupported_numeric_metric_claims(
        answer,
        {"metric_status": "not_found", "accepted_facts": []},
    )

    assert "ISO 14001" in salvaged
    assert "2022" in salvaged
    assert "9.34%" not in salvaged
    assert actions == ["removed_claim:unsupported_metric:c2"]
    assert format_metric_number("12771.822287491") == "12,771.822"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"scope": "Factory A"}, {"scope": "Factory B"}),
        ({"value_role": "actual"}, {"value_role": "target"}),
        ({"locator": {"section": "Scope 1"}}, {"locator": {"section": "Scope 2"}}),
    ],
)
def test_scope_role_and_locator_dimensions_do_not_create_false_conflicts(first, second):
    item = _metric("Metric table", block="Emissions")
    item.facts = [
        EvidenceFact(metric="Emissions", period="2025", value="10", unit="tCO2e", **first),
        EvidenceFact(metric="Emissions", period="2025", value="20", unit="tCO2e", **second),
    ]

    audit = resolve_metric_facts([item])

    assert audit["conflict_count"] == 0
    assert audit["accepted_fact_count"] == 2


def test_real_conflict_removes_only_the_related_metric_claim():
    item = _metric("Metric table", block="Emissions")
    item.facts = [
        EvidenceFact(metric="Scope 1", period="2025", value="10", unit="tCO2e", scope="Group"),
        EvidenceFact(metric="Scope 1", period="2025", value="20", unit="tCO2e", scope="Group"),
        EvidenceFact(metric="Energy use", period="2025", value="10", unit="MWh", scope="Group"),
    ]
    audit = resolve_metric_facts([item])

    revised, actions = salvage_conflicting_metric_claims(
        "Scope 1 was 10 tCO2e in 2025. Energy use was 10 MWh in 2025.",
        audit,
    )

    assert "Scope 1" not in revised
    assert "Energy use was 10 MWh" in revised
    assert actions == ["removed_claim:conflicting_metric:c1"]


def test_metric_contract_fields_and_unknown_metadata_survive_model_dump():
    result = RagQuestionResult.model_validate(
        {
            "question_id": "Q039",
            "metric_expected": True,
            "metric_status": "found_table",
            "metric_summary": {"n_rows": 1, "n_blocks": 1, "future_count": 7},
            "metric_confidence": None,
            "metric_evidence": [
                {
                    **model_to_dict(_metric("Water use | ton | 2025=10", block="Water")),
                    "future_metric_tag": "kept",
                }
            ],
            "narrative_evidence": [model_to_dict(_narrative("Boundary changed in 2024."))],
        }
    )

    dumped = model_to_dict(result)
    assert dumped["metric_status"] == "found_table"
    assert dumped["metric_summary"]["future_count"] == 7
    assert dumped["metric_evidence"][0]["future_metric_tag"] == "kept"
    assert dumped["narrative_evidence"][0]["raw_evidence_ko"] == "Boundary changed in 2024."


def test_found_table_uses_only_primary_rows_and_keeps_entities_separate():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            _metric("Water use | ton | 2025=10", block="Pharm water"),
            _metric(
                "Water use | ton | 2025=20",
                block="Group water",
                entity="Daewoong Group",
                entity_class="group_total",
                rank=2,
            ),
            _metric("Sales | KRW | 2025=100", block="Pharm water", role="denominator"),
            _metric(
                "Water use | ton | 2025=3",
                block="Factory water",
                role="scope_variant",
                entity="Factory A",
                entity_class="factory",
                rank=3,
            ),
        ],
        narrative_evidence=[_narrative("The reporting boundary changed in 2024.")],
    )

    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]
    audit = normalized["metric_audit"]

    assert audit["accepted_fact_count"] == 2
    assert audit["conflict_count"] == 0
    assert {fact["entity_class"] for fact in audit["accepted_facts"]} == {
        "daewoong_pharm",
        "group_total",
    }
    assert audit["denominator_row_count"] == 1
    assert audit["scope_variant_row_count"] == 1
    assert len(normalized["metric_items"]) == 2
    assert "boundary changed" in normalized["evidence_summary"].casefold()
    assert len(normalized["metric_evidence"]) == 4


def test_q039_full_fixture_preserves_23_rows_and_five_primary_blocks():
    config = load_config({"agent_mode": "offline"})
    primary_rows = []
    row_number = 1
    for block_rank, block_size in enumerate((5, 4, 3, 3, 2), start=1):
        entity_class = "daewoong_pharm" if block_rank % 2 else "group_total"
        entity = "Daewoong Pharm" if block_rank % 2 else "Daewoong Group"
        for _ in range(block_size):
            primary_rows.append(
                _metric(
                    f"Water metric {row_number} | ton | 2025={row_number}",
                    block=f"Water block {block_rank}",
                    entity=entity,
                    entity_class=entity_class,
                    rank=block_rank,
                )
            )
            row_number += 1
    scope_rows = [
        _metric(
            f"Factory metric {index} | ton | 2025={index}",
            block=f"Water block {index}",
            role="scope_variant",
            entity=f"Factory {index}",
            entity_class="factory",
            rank=index,
        )
        for index in range(1, 5)
    ]
    denominator_rows = [
        _metric(
            f"Sales denominator {index} | KRW | 2025={index * 100}",
            block=f"Water block {index}",
            role="denominator",
            rank=index,
        )
        for index in range(1, 3)
    ]
    rag = RagQuestionResult(
        question_id="Q039",
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="found_table",
        metric_summary={
            "n_rows": 23,
            "n_blocks": 5,
            "n_primary": 17,
            "n_scope_variant": 4,
            "n_denominator": 2,
        },
        metric_evidence=[*primary_rows, *scope_rows, *denominator_rows],
        narrative_evidence=[_narrative("The reporting boundary changed in 2024.")],
    )

    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]
    audit = normalized["metric_audit"]

    assert len(normalized["metric_evidence"]) == 23
    assert audit["accepted_fact_count"] == 17
    assert audit["primary_row_count"] == 17
    assert audit["scope_variant_row_count"] == 4
    assert audit["denominator_row_count"] == 2
    assert len({fact["table_block"] for fact in audit["accepted_facts"]}) == 5


def test_found_table_invalid_primary_identity_is_warned_and_excluded():
    config = load_config({"agent_mode": "offline"})
    rag = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[
            _metric(
                "Water use | ton | 2025=10",
                block="Unknown",
                entity="",
                entity_class="",
            )
        ],
    )
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {"Q039": rag}}
    )["normalized_evidence"]["Q039"]
    assert normalized["metric_audit"]["accepted_fact_count"] == 0
    assert any(
        "missing entity identity" in warning
        for warning in normalized["metric_audit"]["metric_contract_warnings"]
    )


@pytest.mark.parametrize("reason", ["no_candidate", "below_threshold", "blocked_by_gate"])
def test_not_found_with_insufficient_status_is_blocked_by_evidence_gate(reason):
    config = load_config({"agent_mode": "offline"})
    qid = "Q095"
    narrative = _narrative("The company operates stakeholder communication channels.")
    rag = RagQuestionResult.model_validate(
        {
            "question_id": qid,
            "answer_status": "insufficient",
            "metric_expected": True,
            "metric_status": "not_found",
            "metric_absence": {"reason": reason, "n_candidates_seen": 4},
            "items": [model_to_dict(narrative)],
        }
    )
    planned = _planned(qid)

    gate = EvidenceGateAgent(config).run(
        {"planned_questions": [planned], "rag_results": {qid: rag}}
    )["evidence_gate"][qid]
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {qid: rag}}
    )["normalized_evidence"][qid]
    context = {
        "accepted": gate["accepted"],
        "metric_audit": normalized["metric_audit"],
        "metric_absence": normalized["metric_audit"]["metric_absence"],
        "evidence_items": normalized["narrative_items"],
        "output_language": "English",
    }
    writer = SkillWriterAgent({"agent_mode": "offline"}, None)
    result = writer.run(
        {
            "planned_questions": [planned],
            "skill_contexts": {qid: context},
            "evidence_gate": {qid: gate},
            "rag_results": {qid: rag},
            "normalized_evidence": {qid: normalized},
        }
    )

    assert gate["accepted"] is False
    assert normalized["metric_audit"]["accepted_facts"] == []
    assert result["final_answers"][qid] == ""
    assert gate["reason"] in result["quality_flags"][qid]


def test_low_metric_confidence_withholds_numeric_facts_and_requests_review():
    config = load_config({"agent_mode": "offline"})
    qid = "Q019"
    rag = RagQuestionResult(
        question_id=qid,
        answer_status="medium_confidence",
        metric_expected=True,
        metric_status="found_table",
        metric_confidence="low",
        metric_evidence=[_metric("Incidents | count | 2025=4", block="Incidents")],
        narrative_evidence=[_narrative("The company maintains an incident response process.")],
    )
    normalized = EvidenceNormalizerAgent(config).run(
        {"rag_results": {qid: rag}}
    )["normalized_evidence"][qid]
    audit = normalized["metric_audit"]
    assert audit["accepted_facts"] == []
    assert audit["withheld_facts"]
    assert audit["numeric_withheld"] is True

    planned = _planned(qid)
    writer = SkillWriterAgent({"agent_mode": "offline"}, None)
    result = writer.run(
        {
            "planned_questions": [planned],
            "skill_contexts": {
                qid: {
                    "accepted": True,
                    "metric_audit": audit,
                    "metric_absence": {},
                    "evidence_items": normalized["narrative_items"],
                    "output_language": "English",
                }
            },
            "evidence_gate": {qid: {"accepted": True, "reason": "accepted"}},
            "rag_results": {qid: rag},
            "normalized_evidence": {qid: normalized},
        }
    )
    assert "2025=4" not in result["final_answers"][qid]
    assert "metric_low_confidence" in result["quality_flags"][qid]
    assert "human_review_required" in result["quality_flags"][qid]
