from __future__ import annotations

import re
from typing import Any

from esgagents.quality_flags import canonicalize_quality_flags
from esgagents.schemas import QAResult
from esgagents.customer_text import strip_customer_meta_limitations
from .text_quality import (
    clean_final_answer_for_customer,
    clean_customer_evidence_text,
    customer_source_attribution_reason,
    normalize_answer_coherence,
)


IDENTITY_REQUEST_TERMS = ("성명", "이름", "실명", "담당자명", "name of", "who is")
KOREAN_SURNAMES = (
    "김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주"
    "우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제"
    "모탁국어은편용"
)
ROLE_PATTERN = (
    r"대표이사|사외이사|대표|부장|과장|차장|팀장|사원|이사|상무|전무|임원|위원장"
)
KOREAN_NAME_ROLE_RE = re.compile(
    rf"(?<![가-힣A-Za-z])([{KOREAN_SURNAMES}][가-힣]{{1,2}})\s+"
    rf"({ROLE_PATTERN})(?=\s|,|\)|\.|과|와|이|가|을|를|은|는|$)"
)
KOREAN_NAME_FALSE_POSITIVES = {
    "정관상",
    "구성된",
    "고려한",
    "선임된",
    "포함한",
}
ENGLISH_NAME_ROLE_RE = re.compile(
    r"\b(?:[A-Z][a-z]+\s+){2,3}(CEO|Director|Manager|Officer|Chair|President)\b"
)
ROLE_ONLY_PAREN_RE = re.compile(
    rf"\(\s*(?:{ROLE_PATTERN})(?:\s*,\s*(?:{ROLE_PATTERN}))*\s*\)"
)
ADJACENT_DUPLICATE_ROLE_RE = re.compile(
    rf"\b({ROLE_PATTERN})(?:\s*,\s*\1)+\b"
)
OBSOLETE_SOURCE_ATTRIBUTION_ACTIONS = {
    "restored_required_assessment_attribution",
    "restored_required_draft_attribution",
}

class OutputHygieneAgent:
    def __init__(self, config: dict[str, Any] | None = None):
        self.enabled = bool((config or {}).get("output_hygiene_enabled", True))

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {}
        final_answers = dict(state.get("final_answers", {}))
        quality_flags = {qid: list(flags) for qid, flags in state.get("quality_flags", {}).items()}
        sanitizer_actions = {
            qid: list(actions) for qid, actions in state.get("sanitizer_actions", {}).items()
        }
        qa_results = dict(state.get("qa_results", {}))
        hard_failures = {
            qid: list(failures) for qid, failures in state.get("hard_failures", {}).items()
        }
        planned_by_id = {planned.id: planned for planned in state.get("planned_questions", [])}

        for qid, original in list(final_answers.items()):
            normalized = normalize_markdown(original) if original else ""
            flags = quality_flags.setdefault(qid, [])
            actions = sanitizer_actions.setdefault(qid, [])
            if actions:
                actions[:] = [
                    action
                    for action in actions
                    if action not in OBSOLETE_SOURCE_ATTRIBUTION_ACTIONS
                ]
            planned = planned_by_id.get(qid)
            if original and normalized != original:
                flags.append("markdown_normalized")

            normalized, cleanup_actions = clean_customer_evidence_text(normalized)
            if cleanup_actions:
                flags.append("source_boilerplate_removed")
                actions.extend(cleanup_actions)
            normalized, question_actions = strip_leading_planned_context(normalized, planned)
            if question_actions:
                flags.append("question_context_removed")
                actions.extend(question_actions)

            normalized, coherence_actions = normalize_answer_coherence(normalized)
            if coherence_actions:
                flags.append("coherence_normalized")
                actions.extend(coherence_actions)

            normalized, limitation_actions = strip_customer_meta_limitations(normalized)
            if limitation_actions:
                flags.append("customer_meta_limitation_removed")
                actions.extend(limitation_actions)

            normalized, attribution_actions = preserve_required_source_attribution(
                normalized,
                flags,
                state,
            )
            if attribution_actions:
                actions.extend(attribution_actions)

            question_text = " ".join(
                str(value or "")
                for value in (
                    getattr(planned, "item_ko", ""),
                    getattr(planned, "description_ko", ""),
                )
            ).casefold()
            redacted = normalized
            if normalized and not any(term in question_text for term in IDENTITY_REQUEST_TERMS):
                redacted, pii_actions = sanitize_person_names(normalized)
                actions.extend(pii_actions)

                # Final PII scan immediately before returning the report state.
                rescanned, rescan_actions = sanitize_person_names(redacted)
                redacted = rescanned
                actions.extend(rescan_actions)

            if normalized and redacted != normalized:
                flags.append("pii_redacted")
            cleaned_answer, structural_reason, final_cleanup_actions = clean_final_answer_for_customer(redacted)
            if final_cleanup_actions:
                actions.extend(final_cleanup_actions)
                flags.append("final_answer_normalized")
            redacted = cleaned_answer
            source_reason = customer_source_attribution_reason(redacted)
            source_limited = any(
                str(flag or "").casefold()
                in {"draft_based_answer", "assessment_based_answer"}
                for flag in flags
            )
            if source_reason == "source_attribution_output" or (
                source_reason == "source_limitation_rewrite_output" and source_limited
            ):
                structural_reason = source_reason
            if structural_reason:
                redacted = ""
                flags.append("non_narrative_output")
                failures = hard_failures.setdefault(qid, [])
                failures.extend(["non_narrative_output", structural_reason])
                qa = qa_results.get(qid)
                notes = list(getattr(qa, "notes", []) or [])
                notes.extend(["non_narrative_output", structural_reason])
                qa_results[qid] = (
                    qa.model_copy(update={"status": "failed", "notes": list(dict.fromkeys(notes))})
                    if qa is not None
                    else QAResult(status="failed", notes=list(dict.fromkeys(notes)))
                )
            gate_reason = str(state.get("evidence_gate", {}).get(qid, {}).get("reason", "") or "")
            metric_audit = state.get("normalized_evidence", {}).get(qid, {}).get("metric_audit", {}) or {}
            metric_status = str(metric_audit.get("metric_status") or "").casefold()
            has_metric_table = bool(metric_audit.get("accepted_facts"))
            if not redacted and gate_reason.startswith("accepted") and not (
                metric_status == "found_table" and has_metric_table
            ):
                flags.append("writer_empty")
            canonical_flags, flag_notes = canonicalize_quality_flags(flags)
            qa = qa_results.get(qid)
            if qa is not None and flag_notes:
                qa_results[qid] = qa.model_copy(
                    update={"notes": list(dict.fromkeys([*qa.notes, *flag_notes]))}
                )
            final_answers[qid] = redacted
            quality_flags[qid] = canonical_flags
            sanitizer_actions[qid] = list(dict.fromkeys(actions))

        return {
            "final_answers": final_answers,
            "quality_flags": quality_flags,
            "sanitizer_actions": sanitizer_actions,
            "qa_results": qa_results,
            "hard_failures": hard_failures,
        }


def normalize_markdown(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
    value = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+)", "• ", value)
    value = re.sub(r"\s+[*+-]\s+(?=\*{0,2}[^\n]+)", "\n• ", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"(?<!\w)([*_])([^\n*_]+)\1(?!\w)", r"\2", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def sanitize_person_names(text: str) -> tuple[str, list[str]]:
    actions: list[str] = []
    value = KOREAN_NAME_ROLE_RE.sub(
        lambda match: match.group(0)
        if match.group(1) in KOREAN_NAME_FALSE_POSITIVES
        else match.group(2),
        text,
    )
    value = ENGLISH_NAME_ROLE_RE.sub(lambda match: match.group(1), value)
    if value != text:
        actions.append("redacted_person_name")

    without_parenthetical = ROLE_ONLY_PAREN_RE.sub("", value)
    if without_parenthetical != value:
        actions.append("removed_role_only_parenthetical")
    value = without_parenthetical

    deduplicated = ADJACENT_DUPLICATE_ROLE_RE.sub(lambda match: match.group(1), value)
    if deduplicated != value:
        actions.append("deduplicated_person_roles")
    return deduplicated, actions


def redact_person_names(text: str) -> str:
    value, _ = sanitize_person_names(text)
    return value


def preserve_required_source_attribution(
    text: str,
    flags: list[str],
    state: dict[str, Any],
) -> tuple[str, list[str]]:
    """Keep limited-source attribution in metadata, not customer prose."""

    value = str(text or "").strip()
    normalized_flags = {str(flag or "").strip().casefold() for flag in flags}
    if "draft_based_answer" in normalized_flags:
        return value, ["draft_attribution_kept_in_metadata"]
    if "assessment_based_answer" in normalized_flags:
        return value, ["assessment_attribution_kept_in_metadata"]
    return value, []


def strip_leading_planned_context(text: str, planned: Any | None) -> tuple[str, list[str]]:
    value = str(text or "").strip()
    if not value or planned is None:
        return value, []
    for field in ("item_ko", "description_ko"):
        phrase = " ".join(str(getattr(planned, field, "") or "").split())
        if len(phrase) < 10:
            continue
        if value.casefold().startswith(phrase.casefold()):
            return value[len(phrase):].lstrip(" \t\r\n,;:-·•|"), ["removed_leading_question_context"]
    return value, []
