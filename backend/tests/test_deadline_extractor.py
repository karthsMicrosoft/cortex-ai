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


# Round 39 — patterns added for voice notes that lack the explicit "by"
# keyword. Without these, "Remind me today at 3:50pm" fell through to the
# LLM which then hallucinated a date from its training era.
class TestRound39TodayTomorrowAtTime:
    NOW = datetime.fromisoformat("2026-06-05T10:00:00-07:00")
    TZ = "America/Los_Angeles"

    def test_today_at_time(self):
        assert extract("Remind me today at 3:50pm to send email", now=self.NOW, tz=self.TZ) == {
            "due_at": datetime.fromisoformat("2026-06-05T15:50:00-07:00"),
        }

    def test_at_time_today(self):
        assert extract("Send email at 3:50pm today", now=self.NOW, tz=self.TZ) == {
            "due_at": datetime.fromisoformat("2026-06-05T15:50:00-07:00"),
        }

    def test_tomorrow_at_time(self):
        assert extract("Standup tomorrow at 9am", now=self.NOW, tz=self.TZ) == {
            "due_at": datetime.fromisoformat("2026-06-06T09:00:00-07:00"),
        }

    def test_at_time_tomorrow(self):
        assert extract("Standup at 9am tomorrow", now=self.NOW, tz=self.TZ) == {
            "due_at": datetime.fromisoformat("2026-06-06T09:00:00-07:00"),
        }

    def test_bare_today_falls_back_to_end_of_day(self):
        assert extract("Remind me today to call mom", now=self.NOW, tz=self.TZ) == {
            "due_at": datetime.fromisoformat("2026-06-05T23:59:00-07:00"),
        }

    def test_no_time_anchor_no_today_returns_none(self):
        # "remind me to ..." without a time anchor is not a deadline.
        assert extract("remind me to call mom", now=self.NOW, tz=self.TZ) is None
