"""Static introspection tests for the Azure Monitor Workbook template.

These tests guard against accidental breakage of
``infra/observability/workbook-cortex-overview.json`` — the file is consumed by
``az portal workbook create`` (see ``docs/observability.md``) and must remain
parseable JSON with the expected sections.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Resolve relative to the repo root: backend/tests/ -> backend/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKBOOK_PATH = REPO_ROOT / "infra" / "observability" / "workbook-cortex-overview.json"


@pytest.fixture(scope="module")
def workbook() -> dict:
    assert WORKBOOK_PATH.exists(), f"Workbook template missing at {WORKBOOK_PATH}"
    with WORKBOOK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_workbook_template_is_valid_json(workbook: dict) -> None:
    """File must parse as JSON and conform to the Notebook/1.0 envelope."""
    assert isinstance(workbook, dict)
    assert workbook.get("version") == "Notebook/1.0"
    assert isinstance(workbook.get("items"), list)
    assert workbook["items"], "Workbook must contain at least one item"


def test_workbook_has_expected_sections(workbook: dict) -> None:
    """Must include a markdown header (type 1) and >=5 KQL queries (type 3)."""
    items = workbook["items"]
    markdown_items = [i for i in items if i.get("type") == 1]
    kql_items = [i for i in items if i.get("type") == 3]

    assert markdown_items, "Workbook must contain at least one markdown item (type 1)"
    assert any(
        "Cortex" in (i.get("content", {}).get("json", "") or "")
        for i in markdown_items
    ), "Expected a top-level 'Cortex' markdown header"

    assert len(kql_items) >= 5, (
        f"Expected at least 5 KqlItem queries (cost, top-queries, error-rate, "
        f"latency, restarts); found {len(kql_items)}"
    )

    for item in kql_items:
        content = item.get("content", {})
        assert content.get("version") == "KqlItem/1.0"
        assert content.get("query"), "Every KqlItem must carry a non-empty query"


def test_workbook_kql_references_cortex_metric(workbook: dict) -> None:
    """At least one KQL query must reference the cortex.rag.cost_usd_estimate metric."""
    queries = [
        i["content"]["query"]
        for i in workbook["items"]
        if i.get("type") == 3 and "query" in i.get("content", {})
    ]
    assert any("cortex.rag.cost_usd_estimate" in q for q in queries), (
        "Workbook must surface the cortex.rag.cost_usd_estimate custom metric in "
        "at least one KQL query"
    )


def test_workbook_references_cortexks_ai_resource(workbook: dict) -> None:
    """fallbackResourceIds must point at the cortexks-ai App Insights component."""
    fallback = workbook.get("fallbackResourceIds")
    assert isinstance(fallback, list) and fallback, (
        "Workbook must declare at least one fallbackResourceIds entry"
    )
    assert any(
        "microsoft.insights/components/cortexks-ai" in rid.lower()
        or "microsoft.insights/components/cortexks-ai" in rid
        for rid in fallback
    ), f"Expected fallback resource pointing to cortexks-ai; got {fallback!r}"
