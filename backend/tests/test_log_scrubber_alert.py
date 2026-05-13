"""
Tests for the _ScrubTokenFilter (B12 log-scrubber).

Verifies that JWT tokens appearing as ?token=<jwt> or &token=<jwt> in log
records are redacted to token=REDACTED, and that non-token content passes
through unchanged.
"""

import logging

import pytest

from app.main import _ScrubTokenFilter, _TOKEN_RE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def scrub_filter():
    return _ScrubTokenFilter()


@pytest.fixture()
def make_record():
    """Factory that creates a LogRecord with the given message and args."""
    logger = logging.getLogger("test.scrub")

    def _make(msg: str, args=None):
        record = logger.makeRecord(
            name="test.scrub",
            level=logging.INFO,
            fn="test",
            lno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )
        return record

    return _make


# ---------------------------------------------------------------------------
# Basic redaction
# ---------------------------------------------------------------------------

class TestScrubTokenFilter:
    """_ScrubTokenFilter correctly redacts tokens from log records."""

    def test_redacts_token_in_query_string(self, scrub_filter, make_record):
        record = make_record("GET /api/notes?token=eyJhbGciOiJIUzI1NiJ9.payload.sig 200")
        scrub_filter.filter(record)
        assert "eyJ" not in record.msg
        assert "?token=REDACTED" in record.msg

    def test_redacts_token_with_ampersand(self, scrub_filter, make_record):
        record = make_record("GET /api/notes?page=1&token=eyJhbGciOiJIUzI1NiJ9.payload.sig 200")
        scrub_filter.filter(record)
        assert "eyJ" not in record.msg
        assert "&token=REDACTED" in record.msg
        assert "?page=1" in record.msg

    def test_redacts_multiple_tokens(self, scrub_filter, make_record):
        record = make_record(
            "ws /api/voice/stream?token=eyJ1.a.b "
            "redirect /api/notes?token=eyJ2.c.d"
        )
        scrub_filter.filter(record)
        assert record.msg.count("token=REDACTED") == 2
        assert "eyJ" not in record.msg

    def test_case_insensitive(self, scrub_filter, make_record):
        """re.IGNORECASE matches ?Token= but replacement normalises to lowercase."""
        record = make_record("GET /x?Token=eyJhbGci.pay.sig 200")
        scrub_filter.filter(record)
        assert "eyJ" not in record.msg
        assert "token=REDACTED" in record.msg


# ---------------------------------------------------------------------------
# Non-token content is preserved
# ---------------------------------------------------------------------------

class TestNonTokenContent:
    """_ScrubTokenFilter does NOT redact non-token content."""

    def test_plain_message_unchanged(self, scrub_filter, make_record):
        msg = "Application startup complete"
        record = make_record(msg)
        scrub_filter.filter(record)
        assert record.msg == msg

    def test_url_without_token_unchanged(self, scrub_filter, make_record):
        msg = "GET /api/notes?page=2&limit=50 200"
        record = make_record(msg)
        scrub_filter.filter(record)
        assert record.msg == msg

    def test_token_word_in_prose_unchanged(self, scrub_filter, make_record):
        msg = "The token bucket rate limiter is active"
        record = make_record(msg)
        scrub_filter.filter(record)
        assert record.msg == msg

    def test_filter_always_returns_true(self, scrub_filter, make_record):
        """Filter never suppresses records (returns True)."""
        record = make_record("anything")
        assert scrub_filter.filter(record) is True


# ---------------------------------------------------------------------------
# Edge cases — args tuple and args dict
# ---------------------------------------------------------------------------

class TestArgsHandling:
    """Token redaction works in record.args (tuple and dict forms)."""

    def test_args_tuple_redacted(self, scrub_filter, make_record):
        record = make_record(
            "%s %s %s",
            ("GET", "/api/notes?token=eyJhbGci.pay.sig", "200"),
        )
        scrub_filter.filter(record)
        assert all("eyJ" not in str(a) for a in record.args)
        assert any("token=REDACTED" in str(a) for a in record.args)

    def test_args_tuple_non_string_preserved(self, scrub_filter, make_record):
        record = make_record("%s %d", ("GET /api?token=eyJ.x.y", 200))
        scrub_filter.filter(record)
        assert record.args[1] == 200  # int untouched
        assert "token=REDACTED" in record.args[0]

    def test_args_dict_redacted(self, scrub_filter, make_record):
        record = make_record(
            "%(method)s %(url)s",
            {"method": "GET", "url": "/api/notes?token=eyJhbGci.pay.sig"},
        )
        scrub_filter.filter(record)
        assert "eyJ" not in record.args["url"]
        assert "token=REDACTED" in record.args["url"]

    def test_args_dict_non_string_preserved(self, scrub_filter, make_record):
        record = make_record(
            "%(url)s %(status)d",
            {"url": "/api?token=eyJ.x.y", "status": 200},
        )
        scrub_filter.filter(record)
        assert record.args["status"] == 200
        assert "token=REDACTED" in record.args["url"]

    def test_no_args(self, scrub_filter, make_record):
        record = make_record("no args here")
        scrub_filter.filter(record)
        assert record.msg == "no args here"
        assert record.args is None


# ---------------------------------------------------------------------------
# Regex pattern unit tests
# ---------------------------------------------------------------------------

class TestTokenRegex:
    """The _TOKEN_RE pattern matches expected strings."""

    @pytest.mark.parametrize("input_str,expected", [
        ("?token=eyJhbGciOiJIUzI1NiJ9.payload.sig", "?token=REDACTED"),
        ("&token=eyJhbGciOiJIUzI1NiJ9.payload.sig", "&token=REDACTED"),
        ("?Token=eyJABC", "?token=REDACTED"),  # IGNORECASE match; replacement is lowercase
        ("?token=short", "?token=REDACTED"),
    ])
    def test_pattern_matches(self, input_str, expected):
        result = _TOKEN_RE.sub(r"\1token=REDACTED", input_str)
        assert result == expected

    @pytest.mark.parametrize("input_str", [
        "no token here",
        "?page=1&limit=50",
        "token_bucket is full",
    ])
    def test_pattern_does_not_match(self, input_str):
        result = _TOKEN_RE.sub(r"\1token=REDACTED", input_str)
        assert result == input_str
