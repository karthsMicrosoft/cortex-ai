"""
Smoke test for the deployed backend.

Run only when RUN_DEPLOYED_SMOKE=1 is set in the environment and BACKEND_URL
points to the live deployment (e.g. https://cortex-api.<region>.azurecontainerapps.io).

Usage:
    RUN_DEPLOYED_SMOKE=1 BACKEND_URL=https://cortex-api.xyz.azurecontainerapps.io \
        pytest backend/tests/test_deployed_smoke.py -v
"""

import os
import pytest

RUN_DEPLOYED_SMOKE = os.environ.get("RUN_DEPLOYED_SMOKE", "0") == "1"
BACKEND_URL = os.environ.get("BACKEND_URL", "")

pytestmark = pytest.mark.skipif(
    not RUN_DEPLOYED_SMOKE,
    reason="Set RUN_DEPLOYED_SMOKE=1 and BACKEND_URL to run deployed smoke tests",
)


def test_health_endpoint_returns_200():
    """GET /api/health must return HTTP 200 on the live deployment."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed — run: pip install httpx")

    assert BACKEND_URL, "BACKEND_URL env var must be set to the deployed backend URL"

    url = BACKEND_URL.rstrip("/") + "/api/health"
    response = httpx.get(url, timeout=15)
    assert response.status_code == 200, (
        f"Expected 200 from {url}, got {response.status_code}: {response.text}"
    )


def test_health_endpoint_returns_json_with_status():
    """GET /api/health must return a JSON body containing a 'status' key."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed — run: pip install httpx")

    assert BACKEND_URL, "BACKEND_URL env var must be set to the deployed backend URL"

    url = BACKEND_URL.rstrip("/") + "/api/health"
    response = httpx.get(url, timeout=15)
    assert response.status_code == 200
    body = response.json()
    assert "status" in body, f"Expected 'status' key in health response, got: {body}"
