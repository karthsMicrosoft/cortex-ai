"""Static introspection tests for deploy workflow concurrency groups.

Round 19 (DECISIONS § 22ae): the Deploy Backend and Deploy Frontend
workflows must declare workflow-level concurrency groups so that two
deploys queued within ~3 minutes do not race the
ContainerAppOperationInProgress / SWA deployment lock. We require
``cancel-in-progress: false`` so an in-flight deploy is never killed
mid-rollout (which could leave the container/app in a bad state); new
runs simply queue and wait.
"""
from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"workflow file missing: {path}"
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_deploy_backend_has_concurrency_group():
    data = _load("deploy-backend.yml")
    assert "concurrency" in data, "deploy-backend.yml must declare a concurrency block"
    concurrency = data["concurrency"]
    assert concurrency.get("group") == "deploy-backend"
    assert concurrency.get("cancel-in-progress") is False


def test_deploy_frontend_has_concurrency_group():
    data = _load("deploy-frontend.yml")
    assert "concurrency" in data, "deploy-frontend.yml must declare a concurrency block"
    concurrency = data["concurrency"]
    assert concurrency.get("group") == "deploy-frontend"
    assert concurrency.get("cancel-in-progress") is False
