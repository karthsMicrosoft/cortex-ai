import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services.deadline_extractor import extract

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "deadline_extractor_cases.json").read_text()
)


def _expected(value):
    if value is None:
        return None
    converted = dict(value)
    if "due_at" in converted:
        converted["due_at"] = datetime.fromisoformat(converted["due_at"])
    return converted


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_deadline_extractor_fixture_cases(case):
    now = datetime.fromisoformat(FIXTURE["now"])
    tz = FIXTURE["tz"]

    result = extract(case["input"], now=now, tz=tz)

    assert result == _expected(case["expected"])


def test_empty_string_returns_none():
    now = datetime.fromisoformat(FIXTURE["now"])

    assert extract("", now=now, tz=FIXTURE["tz"]) is None


def test_whitespace_only_returns_none():
    now = datetime.fromisoformat(FIXTURE["now"])

    assert extract("   \n\t  ", now=now, tz=FIXTURE["tz"]) is None


def test_priority_only_returns_priority_key():
    now = datetime.fromisoformat(FIXTURE["now"])

    assert extract("Please triage this #medium", now=now, tz=FIXTURE["tz"]) == {"priority": 2}


def test_combined_detection_direct():
    now = datetime.fromisoformat(FIXTURE["now"])

    assert extract("Pay rent by tomorrow #high #monthly", now=now, tz=FIXTURE["tz"]) == {
        "due_at": datetime.fromisoformat("2026-06-06T23:59:00-07:00"),
        "priority": 1,
        "recurring": "monthly",
    }
