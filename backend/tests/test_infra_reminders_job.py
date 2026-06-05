"""Round 35 — Reminders Container Apps Job guard rail.

Pins the contract that ``infra/main.bicep`` and
``infra/modules/container-app-job.bicep`` declare the reminders job:

  * Resource type ``Microsoft.App/jobs``
  * Trigger type ``Schedule`` with cron ``* * * * *``
  * Entrypoint command ``python -m scripts.dispatch_reminders``
  * Mounts the optional VAPID + ACS Email secrets
  * Job name follows the ``${appName}-reminders`` pattern

Why this exists: a future Bicep refactor or env-var rename could silently
break the reminders pipeline. These tests fail loudly if the wiring changes.
"""

from pathlib import Path

import pytest

INFRA_ROOT = Path(__file__).resolve().parents[2] / "infra"
MAIN_BICEP = INFRA_ROOT / "main.bicep"
JOB_MODULE = INFRA_ROOT / "modules" / "container-app-job.bicep"


def _read(path: Path) -> str:
    assert path.exists(), f"Expected file does not exist: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def main_bicep() -> str:
    return _read(MAIN_BICEP)


@pytest.fixture(scope="module")
def job_module() -> str:
    return _read(JOB_MODULE)


class TestJobModuleExists:
    def test_module_file_exists(self):
        assert JOB_MODULE.exists(), (
            "infra/modules/container-app-job.bicep must exist (Round 35)"
        )

    def test_declares_jobs_resource(self, job_module: str):
        assert "Microsoft.App/jobs" in job_module, (
            "Module must declare a Microsoft.App/jobs resource"
        )

    def test_uses_schedule_trigger(self, job_module: str):
        assert "triggerType: 'Schedule'" in job_module, (
            "Reminders must use the Schedule trigger (not Manual / Event)"
        )

    def test_cron_default_every_minute(self, job_module: str):
        assert "'* * * * *'" in job_module, (
            "Default cron must be '* * * * *' (every minute)"
        )

    def test_entrypoint_is_dispatch_script(self, job_module: str):
        assert "'scripts.dispatch_reminders'" in job_module, (
            "Job entrypoint must run python -m scripts.dispatch_reminders"
        )

    def test_vapid_secrets_declared(self, job_module: str):
        for needle in ("vapid-public-key", "vapid-private-key", "VAPID_PUBLIC_KEY",
                       "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"):
            assert needle in job_module, (
                f"Job module must wire VAPID secret '{needle}' so push notifications work"
            )

    def test_acs_email_secrets_declared(self, job_module: str):
        for needle in ("acs-email-connection", "ACS_EMAIL_CONNECTION", "ACS_EMAIL_SENDER"):
            assert needle in job_module, (
                f"Job module must wire ACS email secret '{needle}' for the email fallback"
            )

    def test_database_url_wired(self, job_module: str):
        assert "DATABASE_URL" in job_module and "database-url" in job_module, (
            "Job must have DATABASE_URL wired to the same secret the API uses"
        )

    def test_openai_endpoint_wired(self, job_module: str):
        # The dispatcher itself doesn't call OpenAI, but the backfill / future
        # extensions may; keep parity with the API container so reminders can
        # safely import any service module.
        assert "AZURE_OPENAI_ENDPOINT" in job_module


class TestMainBicepInstantiatesJob:
    def test_main_references_job_module(self, main_bicep: str):
        assert "./modules/container-app-job.bicep" in main_bicep, (
            "main.bicep must include the container-app-job module"
        )

    def test_main_passes_environment(self, main_bicep: str):
        assert "containerEnvId: containerEnv.id" in main_bicep

    def test_main_passes_vapid(self, main_bicep: str):
        for needle in ("vapidPublicKey:", "vapidPrivateKey:", "vapidSubject:"):
            assert needle in main_bicep, (
                f"main.bicep must forward VAPID param '{needle}' to the job module"
            )

    def test_main_passes_acs(self, main_bicep: str):
        for needle in ("acsEmailConnection:", "acsEmailSender:"):
            assert needle in main_bicep

    def test_main_outputs_job_name(self, main_bicep: str):
        assert "remindersJobName" in main_bicep, (
            "main.bicep must expose remindersJobName output so deploy scripts can target it"
        )


class TestApiContainerAlsoGetsRemindersSecrets:
    """The API container ALSO needs VAPID + ACS env vars so endpoints like
    POST /api/push/subscribe can return the public key, and so PATCH /api/notes/{id}
    can update reminder state. Otherwise the API container couldn't validate or
    serve the reminder fields."""

    def test_api_container_has_vapid_env(self, main_bicep: str):
        # The main.bicep inline container template (not the module) wires the API.
        # Look for VAPID env vars in main.bicep specifically.
        assert "VAPID_PUBLIC_KEY" in main_bicep, (
            "API container in main.bicep must also expose VAPID_PUBLIC_KEY so "
            "GET /api/push/vapid-public-key can serve the key"
        )

    def test_api_container_has_acs_env(self, main_bicep: str):
        assert "ACS_EMAIL_CONNECTION" in main_bicep, (
            "API container in main.bicep must also expose ACS_EMAIL_CONNECTION"
        )
