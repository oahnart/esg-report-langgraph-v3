from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from skills.agents.context_builder import compact
from esgagents.schemas import QAResult
from esgagents.agents.evidence.policy import has_stable_source
from esgagents.agents.evidence.metric_facts import metric_numbers_equivalent


PROMOTIONAL_TERMS = (
    "outstanding",
    "exceptional",
    "world-leading",
    "world class",
    "best-in-class",
    "game-changing",
    "pioneering",
    "transformative",
    "industry-leading",
)
CERTIFICATION_TERMS = (
    "certified",
    "certification",
    "iso ",
    "b corp",
    "ecovadis",
    "cdp",
    "re100",
    "sbti",
)
QUESTION_REQUEST_TERMS = (
    "설명해 주세요",
    "설명해주세요",
    "기술해 주세요",
    "작성해 주세요",
    "please explain",
    "please describe",
    "describe the",
    "explain the",
)
CERTIFICATION_CLAIM_PATTERNS = (
    r"\b(?:is|are|was|were|be|been|being)\s+[^.。!?;\n]{0,80}\bcertified\b",
    r"\b(?:has|have|holds?|obtained|achieved|received|maintains?)\s+[^.。!?;\n]{0,80}\b(?:certification|iso\s*\d+|b corp|ecovadis|cdp|re100|sbti)\b",
    r"\b(?:joined|participates?\s+in|member\s+of|signator(?:y|ies)\s+to)\s+[^.。!?;\n]{0,80}\b(?:cdp|re100|sbti|ecovadis)\b",
    r"(?:인증|이니셔티브)[^.。!?;\n]{0,40}(?:획득|취득|보유|유지|완료|가입|참여|등록|서명|받)",
    r"(?:획득|취득|보유|유지|완료|가입|참여|등록|서명)[^.。!?;\n]{0,40}(?:인증|이니셔티브|re100|sbti|cdp|ecovadis)",
)
DELIVERY_META_PATTERNS = (
    r"\bai(?:-assisted)?\b",
    r"artificial intelligence",
    r"\b(?:language )?model\b",
    r"\bprompt\b",
    r"\bassistant\b",
    r"drafted with",
    r"prepared by:",
    r"subject to legal review",
    r"\[fls\b",
    r"\uc778\uacf5\uc9c0\ub2a5",
    r"ai\s*\uc9c0\uc6d0",
    r"\ubc95\uc801\s*\uac80\ud1a0",
)
NUMERIC_RE = re.compile(r"\d+(?:[,.]\d+)*(?:\s*%)?")
YEAR_RE = re.compile(r"\b20\d{2}\b")


HARD_FAILURE_NOTES = {
    "unsupported certification or initiative claim",
    "unsupported offset claim",
    "unsupported net-zero commitment",
    "unsupported on-track status",
    "unsupported double-materiality claim",
    "no source metadata",
    "missing source_path",
    "missing stable provenance",
}


def _item_field(item: Any, field: str) -> str:
    if isinstance(item, dict):
        return str(item.get(field, "") or "")
    return str(getattr(item, field, "") or "")


def _evidence_corpus(normalized: dict[str, Any]) -> str:
    evidence_parts = []
    for item in normalized.get("items", []):
        text = compact(_item_field(item, "raw_evidence_ko"))
        stable_source = has_stable_source(
            {
                "source_path": _item_field(item, "source_path"),
                "canonical_source_id": _item_field(item, "canonical_source_id"),
                "document_id": _item_field(item, "document_id"),
                "chunk_id": _item_field(item, "chunk_id"),
            }
        )
        if text and stable_source:
            evidence_parts.append(text)
    if evidence_parts:
        return "\n".join(evidence_parts)
    # Backward compatibility for callers that still provide the pre-P0 shape.
    return compact(normalized.get("evidence_summary", ""))


def _is_list_marker(text: str, match: re.Match[str]) -> bool:
    raw = match.group(0).replace(" ", "")
    if not raw.isdigit() or len(raw) > 2:
        return False
    return bool(re.match(r"\s*[.):]\s+", text[match.end() :]))


def _is_identifier_number(text: str, match: re.Match[str]) -> bool:
    previous = text[match.start() - 1] if match.start() else ""
    following = text[match.end()] if match.end() < len(text) else ""
    return (
        bool(previous and (previous.isascii() and previous.isalpha()))
        or bool(previous and previous in "_-/")
        or bool(following and following in "_-/")
    )


def _is_iso_identifier_number(text: str, match: re.Match[str]) -> bool:
    before = text[max(0, match.start() - 8) : match.start()]
    return bool(re.search(r"\bISO\s*$", before, flags=re.IGNORECASE))


def _is_scope_number(text: str, match: re.Match[str]) -> bool:
    before = text[max(0, match.start() - 12) : match.start()].lower()
    after = text[match.end() : match.end() + 12].lower()
    if "scope" not in before:
        return False
    token = match.group(0).replace(" ", "")
    return token in {"1", "2", "3"} or bool(re.match(r"\s*(?:[,/&]|and|및|·)\s*(?:1|2|3)\b", after))


def _is_page_or_section_number(text: str, match: re.Match[str]) -> bool:
    before = text[max(0, match.start() - 14) : match.start()].lower()
    after = text[match.end() : match.end() + 14].lower()
    if re.search(r"(?:page|p\.?|페이지|쪽)\s*$", before):
        return True
    if re.search(r"(?:page|p\.?|페이지|쪽).{0,8}/\s*$", before):
        return True
    if re.match(r"\s*/\s*\d+", after) and re.search(r"(?:page|p\.?|페이지|쪽)", before):
        return True
    if re.match(r"\s*/\s*(?:page|p\.?|페이지|쪽)?\s*\d+", after):
        return True
    if re.search(r"(?:section|chapter|clause|항목|장|절)\s*$", before):
        return True
    return False


def _is_factory_or_facility_ordinal(text: str, match: re.Match[str]) -> bool:
    after = text[match.end() : match.end() + 4]
    return bool(re.match(r"\s*(?:공장|센터|사업장|라인)", after))


def _is_qid_or_rating_marker(text: str, match: re.Match[str]) -> bool:
    before = text[max(0, match.start() - 3) : match.start()]
    after = text[match.end() : match.end() + 4]
    if re.search(r"[Qq]\s*$", before):
        return True
    if re.match(r"\s*/\s*\d+", after):
        return True
    return False


def _canonical_number(raw: str) -> str:
    token = unicodedata.normalize("NFKC", raw).replace(" ", "")
    suffix = "%" if token.endswith("%") else ""
    body = token[:-1] if suffix else token
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", body):
        body = body.replace(",", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", body):
        try:
            decimal = Decimal(body)
            body = (
                format(decimal, "f").rstrip("0").rstrip(".") or "0"
                if "." in body
                else str(int(decimal))
            )
        except InvalidOperation:
            pass
    return f"{body}{suffix}"


def _number_claims(text: str) -> list[tuple[str, str]]:
    normalized = unicodedata.normalize("NFKC", text or "")
    claims: list[tuple[str, str]] = []
    for match in NUMERIC_RE.finditer(normalized):
        if (
            _is_list_marker(normalized, match)
            or _is_identifier_number(normalized, match)
            or _is_iso_identifier_number(normalized, match)
            or _is_scope_number(normalized, match)
            or _is_page_or_section_number(normalized, match)
            or _is_factory_or_facility_ordinal(normalized, match)
            or _is_qid_or_rating_marker(normalized, match)
        ):
            continue
        raw = match.group(0).replace(" ", "")
        canonical = _canonical_number(raw)
        year_context = bool(re.match(r"\s*년", normalized[match.end() :]))
        year_body = canonical.removesuffix("%")
        if year_context and year_body.isdigit() and len(year_body) <= 2:
            canonical = str(2000 + int(year_body))
        claims.append((canonical, raw))
    return claims


def _source_metadata_text(normalized: dict[str, Any]) -> str:
    parts: list[str] = []
    for source in normalized.get("sources", []):
        if isinstance(source, dict):
            parts.extend(
                str(source.get(field, "") or "")
                for field in (
                    "source_name",
                    "source_path",
                    "canonical_source_id",
                    "document_id",
                    "chunk_id",
                )
            )
    for item in normalized.get("items", []):
        for field in ("source_name", "source_path", "reporting_period"):
            value = _item_field(item, field)
            if value:
                parts.append(value)
        metadata = getattr(item, "metadata", None)
        if isinstance(metadata, dict):
            parts.extend(str(value) for value in metadata.values() if value is not None)
    return "\n".join(parts)


def _is_year_like(canonical: str, display: str) -> bool:
    body = canonical.removesuffix("%")
    raw = display.removesuffix("%")
    return (
        body.isdigit()
        and raw.isdigit()
        and (
            2000 <= int(body) <= 2100
            or (len(raw) == 2 and 0 <= int(raw) <= 99)
        )
    )


def _has_reporting_period_context(answer: str, display: str) -> bool:
    normalized = unicodedata.normalize("NFKC", answer or "")
    for match in re.finditer(re.escape(display), normalized):
        context = normalized[max(0, match.start() - 18) : match.end() + 18].casefold()
        if re.search(r"(?:보고\s*기간|reporting\s*period|period|fy|연도|년도|년|q[1-4]|분기)", context):
            return True
    return False


def _supported_reporting_period_numbers(
    answer: str,
    evidence_text: str,
    normalized: dict[str, Any],
) -> set[str]:
    metadata_text = _source_metadata_text(normalized)
    support_text = "\n".join([evidence_text or "", metadata_text])
    support_numbers = {canonical for canonical, _ in _number_claims(support_text)}
    supported: set[str] = set()
    for canonical, display in _number_claims(answer):
        if _is_year_like(canonical, display) and _has_reporting_period_context(answer, display):
            if canonical in support_numbers or display in metadata_text:
                supported.add(canonical)
    return supported


def _table_header_percent_numbers(text: str) -> set[str]:
    supported: set[str] = set()
    normalized = unicodedata.normalize("NFKC", text or "")
    for row in re.finditer(r"%(?P<values>(?:\s+\d+(?:[,.]\d+)*){1,12})", normalized):
        for match in NUMERIC_RE.finditer(row.group("values")):
            canonical = _canonical_number(match.group(0))
            if not canonical.endswith("%"):
                supported.add(f"{canonical}%")
    return supported


def _structured_fact_numbers(normalized: dict[str, Any]) -> set[str]:
    supported: set[str] = set()
    for item in normalized.get("items", []):
        for fact in getattr(item, "facts", []) or []:
            value = str(getattr(fact, "value", "") or "").strip()
            unit = str(getattr(fact, "unit", "") or "").strip()
            if not value:
                continue
            canonical = _canonical_number(value)
            supported.add(f"{canonical}%" if unit in {"%", "percent"} and not canonical.endswith("%") else canonical)
    for fact in (normalized.get("metric_audit") or {}).get("accepted_facts", []):
        value = str(fact.get("value") or fact.get("normalized_value") or "").strip()
        unit = str(fact.get("unit") or "").strip().casefold()
        if value:
            canonical = _canonical_number(value)
            supported.add(
                f"{canonical}%"
                if unit in {"%", "percent"} and not canonical.endswith("%")
                else canonical
            )
    return supported


class SkillPolicyCriticAgent:
    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        qa: dict[str, QAResult] = {}
        final_answers = dict(state.get("final_answers", state.get("draft_answers", {})))
        quality_flags: dict[str, list[str]] = dict(state.get("quality_flags", {}))
        skill_checks: dict[str, list[str]] = {}
        disclosure_flags: dict[str, list[str]] = {}
        hard_failures: dict[str, list[str]] = {}
        last_rejected_answers = dict(state.get("last_rejected_answers", {}))
        qa_failure_stages = dict(state.get("qa_failure_stages", {}))
        sanitizer_actions = {
            qid: list(actions)
            for qid, actions in state.get("sanitizer_actions", {}).items()
        }

        for planned in state["planned_questions"]:
            qid = planned.id
            answer = state["draft_answers"].get(qid, "")
            gate = state["evidence_gate"].get(qid, {})
            if not answer:
                reason = gate.get("reason", "empty answer")
                missing_source = reason == "missing stable provenance"
                qa[qid] = QAResult(status="failed" if missing_source else "empty", notes=[reason])
                final_answers[qid] = ""
                quality_flags[qid] = sorted(set(quality_flags.get(qid, []) + [reason]))
                hard_failures[qid] = [reason] if missing_source else []
                if missing_source:
                    last_rejected_answers[qid] = answer
                    qa_failure_stages[qid] = "skill_policy_critic"
                else:
                    last_rejected_answers.pop(qid, None)
                    qa_failure_stages.pop(qid, None)
                skill_checks[qid] = [f"evidence_available: {'passed' if gate.get('accepted') else 'failed'}"]
                disclosure_flags[qid] = []
                continue

            normalized = state["normalized_evidence"].get(qid, {})
            evidence_text = _evidence_corpus(normalized)
            notes = self._validation_notes(
                planned,
                state,
                qid,
                answer,
                normalized,
                evidence_text,
            )
            salvaged_answer, salvage_actions = self._salvage_repairable_claims(answer, notes)
            if salvage_actions:
                sanitizer_actions[qid] = sorted(
                    set(sanitizer_actions.get(qid, []) + salvage_actions)
                )
                last_rejected_answers[qid] = answer
                original_notes = list(notes)
                notes = self._validation_notes(
                    planned,
                    state,
                    qid,
                    salvaged_answer,
                    normalized,
                    evidence_text,
                ) if salvaged_answer else sorted(
                    set([*original_notes, "no safe supported claim remains"])
                )
            else:
                salvaged_answer = answer

            qid_hard_failures = [note for note in notes if self._is_hard_failure(note)]
            qid_disclosure_flags = self._disclosure_flags(state, qid, answer)
            qid_checks = self._skill_checks(state, qid, notes, qid_disclosure_flags)

            # QA notes are authoritative in ``qa_results``. Keeping prior failure
            # notes in quality flags makes a successfully revised answer appear stale.
            merged_flags = sorted(set(quality_flags.get(qid, []) + qid_disclosure_flags))
            quality_flags[qid] = merged_flags
            qa[qid] = QAResult(status="failed" if notes else "passed", notes=notes or ["grounded"])
            final_answers[qid] = "" if notes else salvaged_answer
            skill_checks[qid] = qid_checks
            disclosure_flags[qid] = qid_disclosure_flags
            hard_failures[qid] = qid_hard_failures
            if notes:
                last_rejected_answers[qid] = answer
                qa_failure_stages[qid] = "skill_policy_critic"
            else:
                last_rejected_answers.pop(qid, None)
                qa_failure_stages.pop(qid, None)

        return {
            "qa_results": qa,
            "quality_flags": quality_flags,
            "final_answers": final_answers,
            "skill_checks": skill_checks,
            "disclosure_flags": disclosure_flags,
            "hard_failures": hard_failures,
            "last_rejected_answers": last_rejected_answers,
            "qa_failure_stages": qa_failure_stages,
            "sanitizer_actions": sanitizer_actions,
        }

    def _validation_notes(
        self,
        planned: Any,
        state: dict[str, Any],
        qid: str,
        answer: str,
        normalized: dict[str, Any],
        evidence_text: str,
    ) -> list[str]:
        notes: list[str] = []
        notes.extend(self._question_leakage_notes(planned, answer))
        if not any(
            has_stable_source(source)
            for source in normalized.get("sources", [])
            if isinstance(source, dict)
        ):
            notes.append("missing stable provenance")
        notes.extend(self._unsupported_number_notes(answer, evidence_text, normalized))
        notes.extend(self._unsupported_certification_notes(answer, evidence_text))
        notes.extend(self._promotional_notes(answer))
        notes.extend(self._delivery_metadata_notes(answer))
        notes.extend(self._skill_notes(state, qid, answer, evidence_text))
        return sorted(set(notes))

    def _salvage_repairable_claims(
        self,
        answer: str,
        notes: list[str],
    ) -> tuple[str, list[str]]:
        if not answer or not notes or any(note == "missing stable provenance" for note in notes):
            return answer, []
        parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?ă€‚])\s+|\n+|\s*â€¢\s*", answer)
            if part.strip()
        ]
        if not parts:
            parts = [answer.strip()]

        def unsafe(part: str) -> str:
            lower = part.casefold()
            for note in notes:
                if note.startswith("unsupported numeric claim:"):
                    display = note.split(":", 1)[1].strip()
                    if display and display.replace(" ", "") in part.replace(" ", ""):
                        return "unsupported_numeric_claim"
                elif note == "unsupported certification or initiative claim":
                    if self._has_certification_claim(lower):
                        return "unsupported_certification_or_initiative_claim"
                elif note.startswith("unsupported promotional language:"):
                    term = note.split(":", 1)[1].strip()
                    if term and term in lower:
                        return "unsupported_promotional_language"
                elif note == "final answer contains delivery metadata":
                    if any(re.search(pattern, part, flags=re.IGNORECASE) for pattern in DELIVERY_META_PATTERNS):
                        return "delivery_metadata"
                elif note == "unsupported offset claim" and "offset" in lower:
                    return "unsupported_offset_claim"
                elif note == "unsupported net-zero commitment" and ("net-zero" in lower or "net zero" in lower):
                    return "unsupported_net_zero_claim"
                elif note == "unsupported on-track status" and "on track" in lower:
                    return "unsupported_on_track_claim"
                elif note == "unsupported double-materiality claim" and "double materiality" in lower:
                    return "unsupported_double_materiality_claim"
            return ""

        kept: list[str] = []
        actions: list[str] = []
        for part in parts:
            reason = unsafe(part)
            if reason:
                actions.append(f"removed_claim:{reason}")
            else:
                kept.append(part)
        if len(kept) == len(parts):
            return answer, []
        return compact(" ".join(kept)), sorted(set(actions))

    def _question_leakage_notes(self, planned: Any, answer: str) -> list[str]:
        normalized_answer = " ".join(unicodedata.normalize("NFKC", answer or "").split()).casefold()
        for field in ("item_ko", "description_ko"):
            question = " ".join(
                unicodedata.normalize("NFKC", str(getattr(planned, field, "") or "")).split()
            ).casefold()
            if (
                question
                and any(term in question for term in QUESTION_REQUEST_TERMS)
                and question in normalized_answer
            ):
                return ["answer appears to include question text"]
        return []

    def _unsupported_number_notes(
        self,
        answer: str,
        evidence_text: str,
        normalized: dict[str, Any] | None = None,
    ) -> list[str]:
        evidence_numbers = {canonical for canonical, _ in _number_claims(evidence_text)}
        evidence_numbers.update(_table_header_percent_numbers(evidence_text))
        evidence_numbers.update(_structured_fact_numbers(normalized or {}))
        answer_numbers = _number_claims(answer)
        period_numbers = _supported_reporting_period_numbers(answer, evidence_text, normalized or {})
        return [
            f"unsupported numeric claim: {display}"
            for canonical, display in sorted(set(answer_numbers), key=lambda item: item[1])
            if not any(metric_numbers_equivalent(canonical, supported) for supported in evidence_numbers)
            and canonical not in period_numbers
        ]

    def _unsupported_certification_notes(self, answer: str, evidence_text: str) -> list[str]:
        lower_answer = answer.lower()
        lower_evidence = evidence_text.lower()
        evidence_has_certification = any(term in lower_evidence for term in CERTIFICATION_TERMS) or bool(
            re.search(r"\biso\s*\d+\b", lower_evidence, flags=re.IGNORECASE)
        )
        if self._has_certification_claim(lower_answer) and not evidence_has_certification:
            return ["unsupported certification or initiative claim"]
        return []

    @staticmethod
    def _has_certification_claim(lower_answer: str) -> bool:
        return any(
            re.search(pattern, lower_answer, flags=re.IGNORECASE)
            for pattern in CERTIFICATION_CLAIM_PATTERNS
        )

    def _promotional_notes(self, answer: str) -> list[str]:
        lower = answer.lower()
        return [f"unsupported promotional language: {term}" for term in PROMOTIONAL_TERMS if term in lower]

    def _delivery_metadata_notes(self, answer: str) -> list[str]:
        if any(re.search(pattern, answer, flags=re.IGNORECASE) for pattern in DELIVERY_META_PATTERNS):
            return ["final answer contains delivery metadata"]
        return []

    def _skill_notes(self, state: dict[str, Any], qid: str, answer: str, evidence_text: str) -> list[str]:
        skill_key = state.get("skill_selections", {}).get(qid, {}).get("skill_key", "general_section")
        notes = []
        lower_answer = answer.lower()
        lower_evidence = evidence_text.lower()
        if skill_key == "carbon":
            if "offset" in lower_answer and "offset" not in lower_evidence:
                notes.append("unsupported offset claim")
            if ("net-zero" in lower_answer or "net zero" in lower_answer) and not (
                "net-zero" in lower_evidence or "net zero" in lower_evidence
            ):
                notes.append("unsupported net-zero commitment")
        if skill_key == "commitment":
            if "on track" in lower_answer and "on track" not in lower_evidence:
                notes.append("unsupported on-track status")
            if "behind target" in lower_answer and "behind target" not in lower_evidence:
                notes.append("unsupported behind-target status")
        if skill_key == "materiality":
            if "double materiality" in lower_answer and "double materiality" not in lower_evidence:
                notes.append("unsupported double-materiality claim")
        return notes

    def _disclosure_flags(self, state: dict[str, Any], qid: str, answer: str) -> list[str]:
        skill_key = state.get("skill_selections", {}).get(qid, {}).get("skill_key", "general_section")
        lower = answer.lower()
        flags = []
        if YEAR_RE.search(answer) or any(term in lower for term in ("target", "commit", "will", "net-zero", "net zero")):
            flags.append("legal_review_required")
        if skill_key in {"carbon", "materiality"} and any(term in lower for term in ("scope", "materiality", "emission", "assurance")):
            flags.append("assurance_review_recommended")
        if any(term in lower for term in ("not provided", "unknown", "not yet assessed", "data gap")):
            flags.append("missing_data_flag")
        if any(term in lower for term in ("will", "target", "by 20", "pathway")):
            flags.append("forward_looking_statement")
        return sorted(set(flags))

    def _skill_checks(self, state: dict[str, Any], qid: str, notes: list[str], disclosure_flags: list[str]) -> list[str]:
        skill_key = state.get("skill_selections", {}).get(qid, {}).get("skill_key", "general_section")
        checks = [
            f"claims_grounded: {'failed' if notes else 'passed'}",
            f"legal_review_flagged: {'passed' if 'legal_review_required' in disclosure_flags else 'not_applicable'}",
        ]
        if skill_key == "carbon":
            checks.append(f"net_zero_supported: {'failed' if 'unsupported net-zero commitment' in notes else 'passed'}")
            checks.append(f"offset_supported: {'failed' if 'unsupported offset claim' in notes else 'passed'}")
        if skill_key == "commitment":
            checks.append(f"status_supported: {'failed' if 'unsupported on-track status' in notes else 'passed'}")
        if skill_key == "materiality":
            checks.append(f"double_materiality_supported: {'failed' if 'unsupported double-materiality claim' in notes else 'passed'}")
        return checks

    def _is_hard_failure(self, note: str) -> bool:
        return note.startswith("unsupported numeric claim") or note in HARD_FAILURE_NOTES
