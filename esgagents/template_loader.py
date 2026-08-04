from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class TemplateValidationError(ValueError):
    pass


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


class TemplateRepository:
    def __init__(self, template_dir: str | Path):
        self.template_dir = Path(template_dir)
        self.question_path = self.template_dir / "question" / "questions.json"
        self.quantitative_path = self.template_dir / "quantitative" / "quantitative_items.json"
        self.scales_dir = self.template_dir / "scales"
        self.industries_dir = self.template_dir / "industries"

    def load_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    def load_questions(self) -> list[dict[str, Any]]:
        questions = self.load_json(self.question_path)
        if not isinstance(questions, list):
            raise TemplateValidationError("questions.json must contain a list")
        ids = [q.get("id") for q in questions]
        if len(questions) != 95:
            raise TemplateValidationError(f"expected 95 questions, found {len(questions)}")
        if len(ids) != len(set(ids)):
            raise TemplateValidationError("duplicate question ids found")
        expected = [f"Q{i:03d}" for i in range(1, 96)]
        if ids != expected:
            raise TemplateValidationError("question ids must be ordered Q001..Q095")
        return questions

    def load_scales(self) -> dict[str, dict[str, Any]]:
        scales = {}
        for path in sorted(self.scales_dir.glob("*.json")):
            data = self.load_json(path)
            scales[data["id"]] = data
        if len(scales) != 4:
            raise TemplateValidationError(f"expected 4 scales, found {len(scales)}")
        return scales

    def load_quantitative_items(self) -> list[dict[str, Any]]:
        items = self.load_json(self.quantitative_path)
        if not isinstance(items, list):
            raise TemplateValidationError("quantitative_items.json must contain a list")
        if len(items) != 251:
            raise TemplateValidationError(f"expected 251 quantitative metrics, found {len(items)}")
        ids = [item.get("metric_id") for item in items]
        expected = [f"QUANT-{index:04d}" for index in range(1, 252)]
        if ids != expected:
            raise TemplateValidationError(
                "quantitative metric ids must be ordered QUANT-0001..QUANT-0251"
            )
        indexes = [item.get("index") for item in items]
        if indexes != list(range(1, 252)):
            raise TemplateValidationError("quantitative metric indexes must be ordered 1..251")
        return items

    def load_industries(self) -> dict[str, dict[str, Any]]:
        industries = {}
        for path in sorted(self.industries_dir.glob("*.json")):
            data = self.load_json(path)
            industries[data["id"].upper()] = data
        if len(industries) != 11:
            raise TemplateValidationError(f"expected 11 industries, found {len(industries)}")
        return industries

    def validate(self) -> None:
        self.load_questions()
        self.load_quantitative_items()
        self.load_scales()
        self.load_industries()

    def normalize_scale(self, value: str) -> str:
        scales = self.load_scales()
        key = _norm(value)
        aliases = {
            "large": "large_enterprise",
            "large_company": "large_enterprise",
            "enterprise": "large_enterprise",
            "big": "large_enterprise",
            "mid": "mid_market",
            "mid_market_company": "mid_market",
            "medium": "mid_market",
            "sme": "sme",
            "small": "sme",
            "small_and_medium_enterprise": "sme",
            "unlisted": "unlisted",
            "private": "unlisted",
        }
        if key in scales:
            return key
        if key in aliases:
            return aliases[key]
        for scale_id, data in scales.items():
            candidates = [scale_id, data.get("name_en", ""), data.get("name_vi", ""), data.get("name_ko", "")]
            if key in {_norm(str(candidate)) for candidate in candidates if candidate}:
                return scale_id
        raise TemplateValidationError(f"unknown scale: {value}")

    def normalize_industry(self, value: str) -> str:
        industries = self.load_industries()
        raw = value.strip()
        if raw.upper() in industries:
            return raw.upper()
        key = _norm(raw)
        for industry_id, data in industries.items():
            candidates = [
                industry_id,
                data.get("name_en", ""),
                data.get("name_vi", ""),
                data.get("name_ko", ""),
                Path(str(data.get("id", industry_id))).stem,
            ]
            if key in {_norm(str(candidate)) for candidate in candidates if candidate}:
                return industry_id
        for path in self.industries_dir.glob("*.json"):
            if key in _norm(path.stem):
                data = self.load_json(path)
                return data["id"].upper()
        raise TemplateValidationError(f"unknown industry: {value}")
