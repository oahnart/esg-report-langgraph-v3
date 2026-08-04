from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "p0_qualitative_regressions.json"
EXPECTED_QIDS = {"Q004", "Q017", "Q075", "Q080", "Q082", "Q086", "Q087", "Q091", "Q094"}


def test_p0_regression_fixture_is_compact_and_complete():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture["fixture_version"] == "p0-qualitative-v1"
    assert set(fixture["qids"]) == EXPECTED_QIDS
    assert FIXTURE_PATH.stat().st_size < 10_000
    assert all(case.get("case") and case.get("expected") for case in fixture["qids"].values())
