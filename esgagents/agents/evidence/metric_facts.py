from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
import unicodedata
import re

from esgagents.agents.evidence.policy import resolve_provenance
from esgagents.agents.evidence.source_policy import TIER_RANK
from esgagents.schemas import EvidenceItem, MetricEvidenceItem, model_to_dict


def normalize_metric_number(value: Any) -> str | None:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        return None
    compact = raw.replace(",", "").replace(" ", "")
    if compact.endswith("%"):
        compact = compact[:-1]
    try:
        number = Decimal(compact)
    except InvalidOperation:
        return None
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", ""} else normalized


def metric_decimal_places(value: Any) -> int:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    compact = raw.replace(",", "").replace(" ", "").removesuffix("%")
    if "." not in compact:
        return 0
    return len(compact.rsplit(".", 1)[1])


def metric_numbers_equivalent(candidate: Any, source: Any) -> bool:
    """Accept exact values and source values rounded to candidate precision."""
    candidate_normalized = normalize_metric_number(candidate)
    source_normalized = normalize_metric_number(source)
    if candidate_normalized is None or source_normalized is None:
        return False
    if candidate_normalized == source_normalized:
        return True
    try:
        candidate_decimal = Decimal(candidate_normalized)
        source_decimal = Decimal(source_normalized)
        quantum = Decimal(1).scaleb(-metric_decimal_places(candidate))
        return source_decimal.quantize(quantum, rounding=ROUND_HALF_UP) == candidate_decimal
    except (InvalidOperation, ValueError):
        return False


def format_metric_number(value: Any, decimal_places: int = 3) -> str:
    normalized = normalize_metric_number(value)
    if normalized is None:
        return str(value or "")
    number = Decimal(normalized)
    places = min(metric_decimal_places(value), max(0, decimal_places))
    if metric_decimal_places(value) > decimal_places:
        number = number.quantize(Decimal(1).scaleb(-decimal_places), rounding=ROUND_HALF_UP)
        places = decimal_places
    rendered = f"{number:,.{places}f}" if places else f"{number:,.0f}"
    return rendered


def unsupported_numeric_metric_claims(
    answer: str,
    metric_audit: dict[str, Any],
) -> list[str]:
    """Return quantitative sentences that are not backed by accepted facts."""

    unsupported: list[str] = []
    for statement in _metric_statements(answer):
        if not _has_substantive_numeric_claim(statement):
            continue
        if metric_facts_supporting_claim(statement, metric_audit):
            continue
        unsupported.append(statement)
    return unsupported


def salvage_unsupported_numeric_metric_claims(
    answer: str,
    metric_audit: dict[str, Any],
) -> tuple[str, list[str]]:
    unsupported = set(unsupported_numeric_metric_claims(answer, metric_audit))
    if not unsupported:
        return answer, []
    kept: list[str] = []
    actions: list[str] = []
    for index, statement in enumerate(_metric_statements(answer), start=1):
        if statement in unsupported:
            actions.append(f"removed_claim:unsupported_metric:c{index}")
        else:
            kept.append(statement)
    return " ".join(kept), actions


def _metric_statements(answer: str) -> list[str]:
    return [
        statement.strip()
        for statement in re.split(r"(?<=[.!?。！？])\s+|\n+", answer or "")
        if statement.strip()
    ]


def _has_substantive_numeric_claim(statement: str) -> bool:
    normalized = unicodedata.normalize("NFKC", statement or "")
    lower = normalized.casefold()
    # Formulas explain methodology rather than report a result. Preserve them
    # in narrative answers even when they contain constants such as x 100.
    if re.search(r"(?:=|×|÷).*(?:/|×|÷)|(?:/|×|÷).*(?:=|×|÷)", normalized):
        return False
    if re.search(
        r"(?:해당\s*사항\s*없음|미발생|발생하지\s*않|no\s+incidents?|none|zero)",
        lower,
    ):
        return True
    for match in re.finditer(r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?%?", normalized):
        token = match.group(0)
        plain = token.replace(",", "").removesuffix("%")
        before = lower[max(0, match.start() - 8):match.start()]
        after = lower[match.end():match.end() + 6]
        if re.search(r"iso\s*$", before):
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", plain) and (
            after.startswith("년")
            or not re.match(r"\s*(?:%|건|명|회|개|톤|tco2e|원|krw|usd)", after)
        ):
            continue
        return True
    return False


def resolve_metric_facts(items: list[EvidenceItem]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    metric_rows = [
        item
        for item in items
        if isinstance(item, MetricEvidenceItem)
        or item.semantic_label.strip().casefold() == "metric_row"
    ]
    parsed_metric_rows = 0
    valid_fact_count = 0

    for item in items:
        item_has_fact = False
        provenance = resolve_provenance(item)
        for fact in item.facts or []:
            metric = " ".join(str(fact.metric or "").split())
            period = " ".join(str(fact.period or "").split())
            unit = " ".join(str(fact.unit or "").split())
            normalized_value = normalize_metric_number(fact.value)
            if not metric or not period or normalized_value is None or not provenance["key"]:
                continue
            item_has_fact = True
            valid_fact_count += 1
            table_block = str(getattr(item, "table_block", "") or "").strip()
            entity = str(getattr(item, "entity", "") or "").strip()
            entity_class = str(getattr(item, "entity_class", "") or "").strip()
            entity_key = entity_class or entity
            locator = model_to_dict(fact.locator)
            scope = " ".join(str(fact.scope or "").split())
            scope_key = scope or " ".join(str(locator.get("section") or "").split())
            value_role = str(fact.value_role or "unknown").strip().casefold()
            key = (
                table_block.casefold(),
                entity_key.casefold(),
                scope_key.casefold(),
                metric.casefold(),
                period.casefold(),
                unit.casefold(),
                value_role,
            )
            groups[key].append(
                {
                    "metric": metric,
                    "period": period,
                    "value": str(fact.value),
                    "normalized_value": normalized_value,
                    "unit": unit,
                    "value_role": fact.value_role,
                    "scope": scope,
                    "scope_key": scope_key,
                    "locator": locator,
                    "source_id": str(provenance["key"]),
                    "provenance_method": str(provenance["method"]),
                    "source_tier": item.source_tier or "tier_unknown",
                    "source_name": item.source_name,
                    "score": float(item.score or 0),
                    "table_block": table_block,
                    "block_rank": getattr(item, "block_rank", None),
                    "block_role": str(getattr(item, "block_role", "") or ""),
                    "entity": entity,
                    "entity_class": entity_class,
                }
            )
        if item_has_fact and item in metric_rows:
            parsed_metric_rows += 1

    accepted: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for entries in groups.values():
        values = sorted({entry["normalized_value"] for entry in entries})
        if len(values) > 1:
            conflicts.append(
                {
                    "metric": entries[0]["metric"],
                    "period": entries[0]["period"],
                    "unit": entries[0]["unit"],
                    "units": sorted({entry["unit"] for entry in entries}),
                    "values": values,
                    "source_ids": sorted({entry["source_id"] for entry in entries}),
                    "table_block": entries[0]["table_block"],
                    "entity": entries[0]["entity"],
                    "entity_class": entries[0]["entity_class"],
                    "scope": entries[0]["scope"],
                    "scope_key": entries[0]["scope_key"],
                    "value_role": entries[0]["value_role"],
                }
            )
            continue
        strongest = max(
            entries,
            key=lambda entry: (
                {
                    "source_path": 3,
                    "canonical_source_id": 2,
                    "document_chunk": 1,
                }.get(entry["provenance_method"], 0),
                TIER_RANK.get(entry["source_tier"], 0),
                entry["score"],
            ),
        )
        accepted.append(strongest)

    accepted.sort(
        key=lambda fact: (
            fact.get("block_rank") if fact.get("block_rank") is not None else 10**9,
            str(fact.get("table_block") or "").casefold(),
            str(fact.get("entity_class") or fact.get("entity") or "").casefold(),
            fact["metric"].casefold(),
            fact["period"].casefold(),
        )
    )
    conflicts.sort(
        key=lambda fact: (
            str(fact.get("table_block") or "").casefold(),
            str(fact.get("entity_class") or fact.get("entity") or "").casefold(),
            fact["metric"].casefold(),
            fact["period"].casefold(),
        )
    )
    return {
        "metric_row_count": len(metric_rows),
        "parsed_metric_row_count": parsed_metric_rows,
        "malformed_metric_row_count": len(metric_rows) - parsed_metric_rows,
        "valid_fact_count": valid_fact_count,
        "accepted_fact_count": len(accepted),
        "accepted_facts": accepted,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "all_numeric_facts_conflicted": bool(valid_fact_count and conflicts and not accepted),
    }


def metric_facts_prompt_lines(metric_audit: dict[str, Any]) -> list[str]:
    lines = []
    for fact in metric_audit.get("accepted_facts", []):
        value = str(fact.get("value", ""))
        unit_value = str(fact.get("unit", ""))
        unit = f" {unit_value}" if unit_value and not value.endswith(unit_value) else ""
        scope = str(fact.get("entity_class") or fact.get("entity") or fact.get("table_block") or "")
        scope_label = f" [{scope}]" if scope else ""
        lines.append(
            f"- {fact.get('metric', '')}{scope_label}: {fact.get('period', '')}="
            f"{value}{unit} "
            f"[source_id={fact.get('source_id', '')}; tier={fact.get('source_tier', '')}]"
        )
    return lines


def conflicting_metric_claims(answer: str, metric_audit: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_answer = unicodedata.normalize("NFKC", answer or "")
    number_matches = {
        normalize_metric_number(match.group(0))
        for match in re.finditer(r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?%?", normalized_answer)
    }
    number_matches.discard(None)
    conflicts = []
    for conflict in metric_audit.get("conflicts", []):
        period = str(conflict.get("period") or "")
        metric = str(conflict.get("metric") or "").strip().casefold()
        values = list(conflict.get("values", []))
        has_conflicting_value = any(
            metric_numbers_equivalent(answer_value, conflict_value)
            for answer_value in number_matches
            for conflict_value in values
        )
        metric_matches = not metric or metric in normalized_answer.casefold()
        if period and period in normalized_answer and metric_matches and has_conflicting_value:
            conflicts.append(conflict)
    return conflicts


def salvage_conflicting_metric_claims(
    answer: str,
    metric_audit: dict[str, Any],
) -> tuple[str, list[str]]:
    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+", answer or "")
        if part.strip()
    ]
    kept: list[str] = []
    actions: list[str] = []
    for index, part in enumerate(parts, start=1):
        if conflicting_metric_claims(part, metric_audit):
            actions.append(f"removed_claim:conflicting_metric:c{index}")
        else:
            kept.append(part)
    return " ".join(kept), actions


def metric_facts_supporting_claim(
    claim: str,
    metric_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized_claim = unicodedata.normalize("NFKC", claim or "")
    lower_claim = normalized_claim.casefold()
    by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in metric_audit.get("accepted_facts", []):
        metric = str(fact.get("metric") or "").strip()
        if metric and metric.casefold() in lower_claim:
            by_metric[metric.casefold()].append(fact)
    for metric_key, facts in by_metric.items():
        claim_without_metric = re.sub(
            re.escape(metric_key),
            " ",
            lower_claim,
            flags=re.IGNORECASE,
        )
        claim_numbers = {
            normalize_metric_number(match.group(0))
            for match in re.finditer(
                r"(?<![A-Za-z0-9])[+-]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9])",
                claim_without_metric,
            )
        }
        claim_numbers.discard(None)
        if not claim_numbers:
            continue
        supported_numbers = [
            fact.get("normalized_value") or fact.get("value") for fact in facts
        ]
        supported_numbers.extend(fact.get("period") for fact in facts)
        if all(
            any(metric_numbers_equivalent(claim_number, supported) for supported in supported_numbers)
            for claim_number in claim_numbers
        ):
            return facts
    return []
