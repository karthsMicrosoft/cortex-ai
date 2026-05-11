"""
Static introspection tests for the Round 16 seed-data scripts.

These tests run as part of the regular pytest suite and require NO database
connection. They validate the curated JSON corpus and confirm that both
scripts are importable without side effects (i.e., the script bodies live
inside ``if __name__ == "__main__":`` blocks).
"""
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
SEED_JSON = SCRIPTS_DIR / "seed_data" / "notes.json"


@pytest.fixture(scope="module")
def seed_records() -> list[dict]:
    with open(SEED_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def test_seed_notes_json_exists_and_parses(seed_records):
    assert SEED_JSON.exists(), f"Seed JSON missing at {SEED_JSON}"
    assert isinstance(seed_records, list)
    assert len(seed_records) == 75


def test_seed_notes_distribution(seed_records):
    counts = Counter(rec["category"] for rec in seed_records)
    assert counts["Learning"] == 15, counts
    for cat in ("Journal", "Ideas", "Fitness", "Music", "Spiritual"):
        assert counts[cat] == 12, (cat, counts)


def test_seed_notes_themed_clusters(seed_records):
    eric = sum(1 for r in seed_records if "Eric" in r["content"])
    marathon = sum(1 for r in seed_records if "marathon" in r["content"].lower())
    calm_mind = sum(1 for r in seed_records if "The Calm Mind" in r["content"])

    assert eric >= 5, f"Expected >=5 'Eric' notes, got {eric}"
    assert marathon >= 4, f"Expected >=4 'marathon' notes, got {marathon}"
    assert calm_mind >= 3, f"Expected >=3 'The Calm Mind' notes, got {calm_mind}"


def test_seed_notes_have_unique_client_ids(seed_records):
    ids = [r["client_id"] for r in seed_records]
    assert len(ids) == len(set(ids)), "client_id values are not unique"


def test_seed_notes_days_ago_in_range(seed_records):
    for r in seed_records:
        d = r["days_ago"]
        assert isinstance(d, int)
        assert 1 <= d <= 90, f"days_ago out of range for {r['client_id']}: {d}"


def _import_script(module_name: str):
    """Import a script under ``backend/scripts/`` without running its body."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    # Drop any cached import so re-runs reflect file edits.
    sys.modules.pop(f"scripts.{module_name}", None)
    return importlib.import_module(f"scripts.{module_name}")


def test_seed_script_imports_cleanly():
    mod = _import_script("seed_dummy_data")
    assert hasattr(mod, "seed"), "expected seed() coroutine on module"


def test_cleanup_script_imports_cleanly():
    mod = _import_script("cleanup_seed_data")
    assert hasattr(mod, "cleanup"), "expected cleanup() coroutine on module"
