from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from esgagents.schemas import AgentProfileKey


SKILL_FILES: dict[AgentProfileKey, str] = {
    "carbon": "carbon-footprint-narrative-writer.md",
    "materiality": "materiality-assessment-writer.md",
    "commitment": "esg-commitment-tracker.md",
    "general_section": "esg-report-section-writer.md",
}


FALLBACK_NAMES: dict[AgentProfileKey, str] = {
    "carbon": "Carbon Narrative Writer",
    "materiality": "Materiality Assessment Writer",
    "commitment": "ESG Commitment Tracker",
    "general_section": "ESG Report Section Writer",
}


@dataclass(frozen=True)
class SkillSpec:
    key: AgentProfileKey
    name: str
    description: str = ""
    version: str = ""
    source_path: str = ""
    instruction: str = ""
    rules: tuple[str, ...] = field(default_factory=tuple)
    checklist: tuple[str, ...] = field(default_factory=tuple)
    language_policy: str = ""
    legal_note: str = ""

    def system_prompt(self) -> str:
        pieces = [
            f"You are the {self.name}.",
            "Use this ESG skill instruction as binding system policy.",
            self.instruction,
        ]
        if self.rules:
            pieces.extend(["Rules:", *[f"- {rule}" for rule in self.rules]])
        if self.checklist:
            pieces.extend(["Skill checklist:", *[f"- {item}" for item in self.checklist]])
        if self.language_policy:
            pieces.append(f"Language policy: {self.language_policy}")
        if self.legal_note:
            pieces.append(f"Disclosure/legal note: {self.legal_note}")
        pieces.extend(
            [
                "Global evidence policy:",
                "- Use only the evidence in the user prompt.",
                "- If evidence is missing, weak, or does not support the question, return an empty final_answer.",
                "- Do not invent metrics, targets, certifications, statuses, or commitments.",
                "Final answer delivery policy:",
                "- Return only report-ready content that answers the user's question.",
                "- Checklists, report wrappers, preparer details, process notes, and legal/publication disclaimers are internal instructions, not final_answer content.",
                "- Never mention AI, a model, an assistant, a prompt, drafting assistance, or system instructions in final_answer.",
            ]
        )
        return "\n".join(piece for piece in pieces if piece)


class SkillRegistry:
    def __init__(self, skill_dir: str | Path):
        self.skill_dir = Path(skill_dir)
        self._skills = self._load_all()

    def get(self, key: AgentProfileKey | str) -> SkillSpec:
        fallback_key: AgentProfileKey = "general_section"
        if key in self._skills:
            return self._skills[key]  # type: ignore[index]
        return self._skills.get(fallback_key, _fallback_skill(fallback_key, self.skill_dir / SKILL_FILES[fallback_key]))

    def all(self) -> dict[AgentProfileKey, SkillSpec]:
        return dict(self._skills)

    def _load_all(self) -> dict[AgentProfileKey, SkillSpec]:
        skills: dict[AgentProfileKey, SkillSpec] = {}
        for key, filename in SKILL_FILES.items():
            path = self.skill_dir / filename
            try:
                skills[key] = parse_skill_markdown(key, path)
            except OSError:
                skills[key] = _fallback_skill(key, path)
        return skills


def parse_skill_markdown(key: AgentProfileKey, path: Path) -> SkillSpec:
    raw = path.read_text(encoding="utf-8")
    metadata = _parse_frontmatter(raw)
    instruction = _extract_instruction(raw)
    rules = tuple(_extract_rule_lines(instruction or raw))
    checklist = tuple(_extract_checklist(raw))
    return SkillSpec(
        key=key,
        name=metadata.get("name") or FALLBACK_NAMES[key],
        description=metadata.get("description", ""),
        version=metadata.get("version", ""),
        source_path=str(path),
        instruction=instruction or metadata.get("description", ""),
        rules=rules,
        checklist=checklist,
        language_policy=_extract_language_policy(instruction or raw),
        legal_note=_extract_legal_note(raw),
    )


def _parse_frontmatter(raw: str) -> dict[str, str]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*", raw, flags=re.DOTALL)
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _extract_instruction(raw: str) -> str:
    section = _section(raw, "Instructions")
    code_match = re.search(r"```\s*\n(.*?)\n```", section, flags=re.DOTALL)
    instruction = code_match.group(1) if code_match else section
    instruction = re.sub(r"^\*\(.*?\)\*\s*", "", instruction.strip(), flags=re.DOTALL)
    instruction = re.sub(
        r"^##\s+LEGACY REPORT-SECTION STRUCTURE.*?(?=^##\s+|\Z)",
        "",
        instruction,
        flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    return instruction.strip()


def _section(raw: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, raw, flags=re.MULTILINE)
    if not match:
        return ""
    rest = raw[match.end() :]
    next_heading = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _extract_rule_lines(text: str) -> list[str]:
    rules = []
    for line in text.splitlines():
        stripped = line.strip()
        normalized = stripped.lstrip("-*0123456789. )").strip()
        lower = normalized.lower()
        if lower.startswith(("do not ", "never ", "if no ", "if only ", "no ", "flag ")):
            rules.append(normalized)
    return _unique(rules)


def _extract_checklist(raw: str) -> list[str]:
    items = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("[ ]"):
            items.append(stripped[3:].strip())
    return _unique(items)


def _extract_language_policy(text: str) -> str:
    policies = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("French:", "Bilingual:", "Language:")):
            policies.append(stripped)
    return " ".join(policies)


def _extract_legal_note(raw: str) -> str:
    notes = []
    for line in raw.splitlines():
        stripped = line.strip("- ").strip()
        lower = stripped.lower()
        if "legal review" in lower or "assurance" in lower or "greenwashing" in lower:
            notes.append(stripped)
    return " ".join(_unique(notes)[:4])


def _unique(items: list[str]) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def _fallback_skill(key: AgentProfileKey, path: Path) -> SkillSpec:
    return SkillSpec(
        key=key,
        name=FALLBACK_NAMES[key],
        version="fallback",
        source_path=str(path),
        instruction="Draft evidence-grounded ESG report narrative using only provided evidence.",
        rules=("Do not invent unsupported ESG claims.",),
        checklist=("claims_grounded",),
    )
