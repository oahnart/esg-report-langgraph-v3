from __future__ import annotations

from dataclasses import dataclass

from esgagents.schemas import AgentProfileKey


@dataclass(frozen=True)
class ESGProfile:
    key: AgentProfileKey
    name: str
    purpose: str
    must_do: tuple[str, ...]
    must_not_do: tuple[str, ...]
    self_checks: tuple[str, ...]


PROFILES: dict[AgentProfileKey, ESGProfile] = {
    "carbon": ESGProfile(
        key="carbon",
        name="Carbon Narrative Writer",
        purpose="Draft climate, GHG, emissions, energy, and net-zero narrative from provided evidence.",
        must_do=(
            "State figures only when they appear in evidence.",
            "Keep Scope 1, Scope 2, Scope 3, tCO2e, baseline, offset, and target wording precise.",
            "Disclose data gaps, boundary changes, and methodology limitations when evidence mentions them.",
            "Mark forward-looking net-zero or reduction pathway statements as subject to legal review.",
        ),
        must_not_do=(
            "Do not invent emissions, reductions, offsets, targets, or on-track status.",
            "Do not present offsets as equivalent to direct reductions.",
            "Do not imply a net-zero commitment unless evidence states it.",
        ),
        self_checks=(
            "all_figures_supported",
            "scope_terms_precise",
            "offsets_not_overstated",
            "forward_looking_flagged",
        ),
    ),
    "materiality": ESGProfile(
        key="materiality",
        name="Materiality Assessment Writer",
        purpose="Draft materiality assessment and stakeholder-prioritisation narrative from evidence.",
        must_do=(
            "Narrate the materiality process and conclusions provided by evidence.",
            "Keep single materiality and double materiality dimensions separate when evidence contains them.",
            "Mention stakeholder groups, scoring, exclusions, and limitations only when supported.",
        ),
        must_not_do=(
            "Do not decide new material topics for the company.",
            "Do not invent stakeholder views, scores, consultation volumes, or excluded-topic rationale.",
            "Do not present ESRS double materiality when only one dimension is evidenced.",
        ),
        self_checks=(
            "material_topics_supported",
            "stakeholder_claims_supported",
            "excluded_topics_not_invented",
        ),
    ),
    "commitment": ESGProfile(
        key="commitment",
        name="ESG Commitment Tracker",
        purpose="Draft commitment, target, pledge, and progress-status narrative from evidence.",
        must_do=(
            "Use clear progress wording when evidence supports a status.",
            "Use status unknown when progress data is missing.",
            "Flag overdue, at-risk, behind, revised, or decommissioned commitments when evidence states them.",
        ),
        must_not_do=(
            "Do not mark a commitment on track without progress evidence.",
            "Do not soften behind-target evidence into positive wording.",
            "Do not change stated commitment text to make progress look better.",
        ),
        self_checks=(
            "status_supported",
            "unknown_when_no_progress_data",
            "target_revisions_flagged",
        ),
    ),
    "general_section": ESGProfile(
        key="general_section",
        name="ESG Report Section Writer",
        purpose="Draft a defensible ESG report-section answer from retrieved evidence.",
        must_do=(
            "Use measured report language aligned to the question, scale, and industry context.",
            "Attribute all concrete claims to evidence.",
            "Disclose material limitations when evidence contains them.",
        ),
        must_not_do=(
            "Do not invent metrics, certifications, memberships, ratings, or commitments.",
            "Do not use promotional language unsupported by external evidence.",
            "Do not omit material caveats found in evidence.",
        ),
        self_checks=(
            "claims_grounded",
            "no_promotional_overstatement",
            "limitations_preserved",
        ),
    ),
}


def get_profile(key: AgentProfileKey | str) -> ESGProfile:
    return PROFILES.get(key, PROFILES["general_section"])  # type: ignore[arg-type]


def profile_keys() -> list[AgentProfileKey]:
    return list(PROFILES.keys())
