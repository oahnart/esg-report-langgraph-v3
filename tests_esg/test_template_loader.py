from esgagents.default_config import DEFAULT_CONFIG
from esgagents.template_loader import TemplateRepository


def test_template_repository_validates_source_of_truth():
    repo = TemplateRepository(DEFAULT_CONFIG["template_dir"])

    repo.validate()

    assert len(repo.load_questions()) == 95
    assert len(repo.load_scales()) == 4
    assert len(repo.load_industries()) == 11


def test_company_scale_and_industry_fallback_mapping():
    repo = TemplateRepository(DEFAULT_CONFIG["template_dir"])

    assert repo.normalize_scale("Large Company") == "large_enterprise"
    assert repo.normalize_scale("sme") == "sme"
    assert repo.normalize_industry("TC") == "TC"
    assert repo.normalize_industry("Technology and Communications") == "TC"
