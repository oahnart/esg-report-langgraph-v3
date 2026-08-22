from types import SimpleNamespace

import pytest

from esgagents.agents.answering.grounding import ground_answer_sentences
from esgagents.agents.answering.text_quality import normalize_final_answer_text
from esgagents.agents.evidence.evidence_gate import EvidenceGateAgent
from esgagents.agents.evidence.evidence_curator import EvidenceCuratorAgent
from esgagents.agents.evidence.evidence_normalizer import EvidenceNormalizerAgent
from esgagents.agents.evidence.evidence_preparation import sanitize_evidence_text
from esgagents.agents.evidence.metric_routing import (
    curatable_qualitative_items,
    qualitative_evidence_route,
)
from esgagents.default_config import load_config
from esgagents.progress import ProgressReporter
from esgagents.schemas import (
    EvidenceCurationDrop,
    EvidenceCurationKeep,
    EvidenceCurationResult,
    EvidenceItem,
    MetricEvidenceItem,
    MetricSummary,
    PlannedQuestion,
    PreparedEvidence,
    RagQuestionResult,
    GroundedSentence,
    SkillDraft,
)
from skills.agents.critic import _evidence_corpus
from skills.agents.writer import SkillWriterAgent


def _item(text: str, *, label: str = "useful", chunk_id: str = "c1") -> EvidenceItem:
    return EvidenceItem(
        raw_evidence_ko=text,
        semantic_label=label,
        semantic_score=0.9,
        source_name="source.pdf",
        source_path="ESG/source.pdf",
        canonical_source_id="src-1",
        chunk_id=chunk_id,
    )


def _planned(qid: str = "Q039") -> PlannedQuestion:
    return PlannedQuestion(
        id=qid,
        pillar="Metrics",
        item_ko="용수 관리 현황",
        description_ko="용수 관리 체계와 성과를 설명합니다.",
    )


def _normalized(rag: RagQuestionResult, planned: PlannedQuestion | None = None):
    planned = planned or _planned(rag.question_id)
    return EvidenceNormalizerAgent(load_config({"agent_mode": "offline"})).run(
        {"planned_questions": [planned], "rag_results": {planned.id: rag}}
    )["normalized_evidence"]


def test_v3_qualitative_routing_uses_items_or_narrative_by_metric_contract():
    item = _item("items evidence")
    narrative = _item("narrative evidence", chunk_id="c2")

    not_expected = RagQuestionResult(
        question_id="Q001",
        metric_expected=False,
        metric_status="not_expected",
        items=[item],
        narrative_evidence=[narrative],
    )
    assert qualitative_evidence_route(not_expected) == "items"
    assert curatable_qualitative_items(not_expected) == [item]

    found_table = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        items=[item],
        narrative_evidence=[narrative],
    )
    assert qualitative_evidence_route(found_table) == "narrative_evidence"
    assert curatable_qualitative_items(found_table) == [narrative]

    not_found = RagQuestionResult(
        question_id="Q011",
        metric_expected=True,
        metric_status="not_found",
        items=[item, _item("legacy metric row", label="metric_row", chunk_id="c3")],
    )
    assert qualitative_evidence_route(not_found) == "items"
    assert curatable_qualitative_items(not_found) == [item]


def test_sanitization_preserves_raw_and_creates_clean_text():
    rag = RagQuestionResult(
        question_id="Q001",
        metric_expected=False,
        metric_status="not_expected",
        items=[_item("Policy&#x20;applies.\u200b")],
    )
    normalized = _normalized(rag, _planned("Q001"))["Q001"]
    prepared = normalized["prepared_qualitative_items"][0]

    assert prepared.raw_item.raw_evidence_ko == "Policy&#x20;applies.\u200b"
    assert prepared.clean_text == "Policy applies."
    assert "html_entities_decoded" in prepared.sanitization_actions
    assert "control_unicode_removed" in prepared.sanitization_actions


def test_llm_unavailable_curator_falls_back_and_keeps_metric_lane_untouched():
    planned = _planned()
    narrative = _item("The company monitors water risks.")
    metric = MetricEvidenceItem(
        raw_evidence_ko="Water use | t | 2025=100",
        semantic_label="metric_row",
        source_path="ESG/metrics.xlsx",
        canonical_source_id="metric-src",
        chunk_id="m1",
        table_block="Water > Company",
        block_role="primary",
        entity="Company",
        entity_class="company",
    )
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_summary=MetricSummary(n_rows=1, n_blocks=1, n_primary=1),
        metric_evidence=[metric],
        narrative_evidence=[narrative],
        is_v3_payload=True,
    )
    normalized = _normalized(rag, planned)
    state = {
        "planned_questions": [planned],
        "rag_results": {planned.id: rag},
        "normalized_evidence": normalized,
        "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted_v3_complete"}},
        "skill_selections": {planned.id: {"skill_key": "general_section"}},
        "quality_flags": {},
    }

    result = EvidenceCuratorAgent({}, None).run(state)

    assert result["qualitative_answerability"][planned.id] == "PARTIAL"
    assert len(result["curated_qualitative_evidence"][planned.id]) == 1
    assert len(normalized[planned.id]["metric_evidence"]) == 1
    assert result["evidence_curation_results"][planned.id].evidence_route == "narrative_evidence"
    assert result["evidence_curation_qid_stats"][planned.id]["curated_keep_count"] == 1
    assert result["evidence_curation_qid_stats"][planned.id]["writer_called"] is False
    assert result["evidence_curation_results"][planned.id].mode == "fallback"
    assert {"curator_fallback", "human_review_required"}.issubset(
        result["quality_flags"][planned.id]
    )


def test_legacy_metric_rows_remain_writer_eligible_when_no_qualitative_item_exists():
    planned = _planned("Q031")
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="medium_confidence",
        coverage_status="complete",
        answerable=True,
        items=[_item("Scope 1 emissions | tCO2e | 2025=100", label="metric_row")],
        is_v3_payload=True,
    )
    normalized = _normalized(rag, planned)
    result = EvidenceCuratorAgent({}, None).run(
        {
            "planned_questions": [planned],
            "rag_results": {planned.id: rag},
            "normalized_evidence": normalized,
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "skill_selections": {planned.id: {"skill_key": "carbon"}},
            "quality_flags": {},
        }
    )

    assert result["qualitative_answerability"][planned.id] == "SUFFICIENT"
    assert result["curated_qualitative_evidence"][planned.id] == []


def test_enforced_curator_applies_explicit_keep_drop_without_touching_metrics():
    progress_events = []
    planned = _planned()
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        narrative_evidence=[
            _item("Water governance is monitored.", chunk_id="c1"),
            _item("Employee benefits are reviewed.", chunk_id="c2"),
        ],
        metric_evidence=[
            MetricEvidenceItem(
                raw_evidence_ko="Water use | t | 2025=100",
                semantic_label="metric_row",
                source_path="ESG/metrics.xlsx",
                canonical_source_id="metric-src",
                chunk_id="m1",
                table_block="Water > Company",
                block_role="primary",
                entity="Company",
                entity_class="company",
            )
        ],
        is_v3_payload=True,
    )
    normalized = _normalized(rag, planned)
    prepared = normalized[planned.id]["prepared_qualitative_items"]

    class Structured:
        def invoke(self, prompt):
            return EvidenceCurationResult(
                qid=planned.id,
                evidence_route="narrative_evidence",
                qualitative_answerability="SUFFICIENT",
                keep=[EvidenceCurationKeep(evidence_id=prepared[0].evidence_id)],
                drop=[
                    EvidenceCurationDrop(
                        evidence_id=prepared[1].evidence_id,
                        reason_code="IRRELEVANT",
                    )
                ],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    result = EvidenceCuratorAgent(
        {}, LLM(), ProgressReporter(progress_events.append)
    ).run(
        {
            "planned_questions": [planned],
            "rag_results": {planned.id: rag},
            "normalized_evidence": normalized,
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "skill_selections": {planned.id: {"skill_key": "general_section"}},
            "quality_flags": {},
        }
    )

    curated = result["curated_qualitative_evidence"][planned.id]
    assert [item.evidence_id for item in curated] == [prepared[0].evidence_id]
    assert len(normalized[planned.id]["metric_evidence"]) == 1
    terminal = [
        event
        for event in progress_events
        if event.category == "CURATOR"
        and event.name == planned.id
        and event.status != "started"
    ]
    assert len(terminal) == 1
    assert terminal[0].status == "completed"
    assert terminal[0].duration_seconds is not None
    assert terminal[0].details["kept"] == 1
    assert terminal[0].details["dropped"] == 1


def test_found_table_qualitative_insufficient_does_not_remove_metric_rows():
    planned = _planned()
    metric = MetricEvidenceItem(
        raw_evidence_ko="Water use | t | 2025=100",
        semantic_label="metric_row",
        source_path="ESG/metrics.xlsx",
        canonical_source_id="metric-src",
        chunk_id="m1",
        table_block="Water > Company",
        block_role="primary",
        entity="Company",
        entity_class="company",
    )
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[metric],
        narrative_evidence=[_item("Unrelated employee benefits narrative.")],
        is_v3_payload=True,
    )
    normalized = _normalized(rag, planned)
    prepared = normalized[planned.id]["prepared_qualitative_items"]

    class Structured:
        def invoke(self, prompt):
            return EvidenceCurationResult(
                qid=planned.id,
                evidence_route="narrative_evidence",
                qualitative_answerability="INSUFFICIENT",
                drop=[
                    EvidenceCurationDrop(
                        evidence_id=prepared[0].evidence_id,
                        reason_code="IRRELEVANT",
                    )
                ],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    result = EvidenceCuratorAgent({}, LLM()).run(
        {
            "planned_questions": [planned],
            "rag_results": {planned.id: rag},
            "normalized_evidence": normalized,
            "evidence_gate": {planned.id: {"accepted": True, "reason": "accepted"}},
            "skill_selections": {planned.id: {"skill_key": "general_section"}},
            "quality_flags": {},
        }
    )

    assert result["curated_qualitative_evidence"][planned.id] == []
    assert result["qualitative_answerability"][planned.id] == "INSUFFICIENT"
    assert len(normalized[planned.id]["metric_evidence"]) == 1


def test_grounding_scopes_numbers_to_referenced_evidence():
    clean, _ = sanitize_evidence_text("Water reuse was 9.34% in 2025.")
    rag = RagQuestionResult(
        question_id="Q039",
        metric_expected=True,
        metric_status="found_table",
        narrative_evidence=[_item(clean)],
    )
    prepared = _normalized(rag)["Q039"]["prepared_qualitative_items"]

    grounded, issues = ground_answer_sentences(
        "Water reuse was 9.34% in 2025.",
        prepared,
    )
    assert grounded[0].evidence_ids == [prepared[0].evidence_id]
    assert issues == []

    _, unsupported = ground_answer_sentences(
        "Water reuse was 14.7% in 2025.",
        prepared,
    )
    assert unsupported == ["prose_numeric_grounding_fail:S1"]


def test_curator_has_no_enable_or_shadow_switch_and_grounding_is_default():
    config = load_config()

    assert "evidence_curator_enabled" not in config
    assert "evidence_curator_shadow_mode" not in config
    assert config["sentence_grounding_enforced"] is True
    assert config["max_revision_rounds"] == 1


def test_curator_schema_defaults_to_enforced_and_rejects_removed_modes():
    assert EvidenceCurationResult(
        qid="Q039",
        evidence_route="narrative_evidence",
    ).mode == "enforced"
    for removed_mode in ("disabled", "shadow"):
        with pytest.raises(ValueError):
            EvidenceCurationResult(
                qid="Q039",
                evidence_route="narrative_evidence",
                mode=removed_mode,
            )


def test_metric_only_found_table_passes_structural_gate():
    planned = _planned()
    metric = MetricEvidenceItem(
        raw_evidence_ko="Water use | t | 2025=100",
        semantic_label="metric_row",
        source_path="ESG/metrics.xlsx",
        canonical_source_id="metric-src",
        chunk_id="m1",
        table_block="Water > Company",
        block_role="primary",
        entity="Company",
        entity_class="company",
    )
    rag = RagQuestionResult(
        question_id=planned.id,
        answer_status="high_confidence",
        coverage_status="complete",
        answerable=True,
        metric_expected=True,
        metric_status="found_table",
        metric_evidence=[metric],
        is_v3_payload=True,
    )

    result = EvidenceGateAgent(load_config()).run(
        {"planned_questions": [planned], "rag_results": {planned.id: rag}}
    )

    assert result["evidence_gate"][planned.id] == {
        "accepted": True,
        "reason": "accepted_metric_found_table",
    }
    audit = result["structural_evidence_audit"][planned.id]
    assert audit["eligible_count"] == 1
    assert audit["year_match"] is None
    assert audit["year_validation"] == "not_verifiable_response_omits_year"


def test_policy_critic_corpus_excludes_curator_dropped_evidence():
    kept = PreparedEvidence(
        evidence_id="Q001-EV-11111111",
        origin="items",
        raw_item=_item("The company operates a grievance channel."),
        clean_text="The company operates a grievance channel.",
    )
    normalized = {
        "items": [
            kept.raw_item,
            _item("The company has an unsupported certification.", chunk_id="dropped"),
        ],
        "metric_items": [],
        "metric_audit": {"metric_status": "not_expected"},
    }

    corpus = _evidence_corpus(normalized, [kept])

    assert "grievance channel" in corpus
    assert "unsupported certification" not in corpus


def test_invalid_writer_sentence_mapping_cannot_preserve_unstructured_answer():
    prepared = PreparedEvidence(
        evidence_id="Q001-EV-11111111",
        origin="items",
        raw_item=_item("The company operates a grievance channel."),
        clean_text="The company operates a grievance channel.",
    )

    class Structured:
        def invoke(self, prompt):
            return SkillDraft(
                final_answer="The company has an unsupported certification.",
                sentences=[
                    GroundedSentence(
                        sentence_id="S1",
                        text="The company has an unsupported certification.",
                        evidence_ids=["Q001-EV-deadbeef"],
                    )
                ],
            )

    class LLM:
        def with_structured_output(self, schema):
            return Structured()

    writer = SkillWriterAgent({"sentence_grounding_enforced": True}, LLM())
    answer, flags = writer._draft_answer(
        {
            "prepared_evidence": [prepared],
            "evidence_items": [prepared.raw_item],
            "evidence_lines": [prepared.clean_text],
            "metric_audit": {},
            "curator_enforced": True,
            "system_prompt": "Write grounded ESG prose.",
            "user_prompt": "Use supplied evidence.",
        },
        RagQuestionResult(
            question_id="Q001",
            metric_expected=False,
            metric_status="not_expected",
        ),
    )

    assert "unsupported certification" not in answer
    assert "grievance channel" in answer
    assert "invalid_evidence_reference" in flags
    assert "missing_valid_sentence_mapping" in flags


def test_final_output_decodes_html_and_removes_internal_evidence_ids():
    cleaned, actions = normalize_final_answer_text(
        "The company&#x20;reported Q039-EV-abcdef123456 a target."
    )

    assert cleaned == "The company reported a target."
    assert "html_entities_decoded" in actions
    assert "removed_exposed_evidence_id" in actions
