from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any
import unicodedata
import re

from esgagents.agents.evidence.policy import resolve_provenance
from esgagents.agents.evidence.source_policy import TIER_RANK
from esgagents.schemas import EvidenceItem, model_to_dict


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


def resolve_metric_facts(items: list[EvidenceItem]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    metric_rows = [item for item in items if item.semantic_label.strip().casefold() == "metric_row"]
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
            key = (metric.casefold(), period.casefold())
            groups[key].append(
                {
                    "metric": metric,
                    "period": period,
                    "value": str(fact.value),
                    "normalized_value": normalized_value,
                    "unit": unit,
                    "value_role": fact.value_role,
                    "scope": fact.scope,
                    "locator": model_to_dict(fact.locator),
                    "source_id": str(provenance["key"]),
                    "provenance_method": str(provenance["method"]),
                    "source_tier": item.source_tier or "tier_unknown",
                    "source_name": item.source_name,
                    "score": float(item.score or 0),
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

    accepted.sort(key=lambda fact: (fact["metric"].casefold(), fact["period"].casefold()))
    conflicts.sort(key=lambda fact: (fact["metric"].casefold(), fact["period"].casefold()))
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
        lines.append(
            f"- {fact.get('metric', '')}: {fact.get('period', '')}="
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
        values = {str(value) for value in conflict.get("values", [])}
        if period and period in normalized_answer and values.intersection(number_matches):
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
        supported_numbers = {
            normalize_metric_number(fact.get("normalized_value") or fact.get("value"))
            for fact in facts
        }
        supported_numbers.update(
            normalize_metric_number(fact.get("period")) for fact in facts
        )
        supported_numbers.discard(None)
        if claim_numbers.issubset(supported_numbers):
            return facts
    return []
