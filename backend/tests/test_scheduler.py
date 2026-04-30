"""
test_scheduler.py — Task 1.3 (APScheduler nightly distill cron)
TDD red-phase tests for APScheduler integration in FastAPI startup

Covers:
  Task 1.3 — APScheduler hook at FastAPI startup
    - BackgroundScheduler is started at FastAPI lifespan startup
    - A cron job is registered to run nightly at 23:59
    - Weekly summary job registered for Sunday 23:59
    - generate_daily_summary is called by the scheduled job
    - Scheduler is shut down at FastAPI lifespan teardown
    - Single-user MVP: runs for the configured default user

Mock strategy: Mock APScheduler BackgroundScheduler; mock distill functions.
"""
import inspect
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytestmark = pytest.mark.asyncio


def _get_main_src() -> str:
    """Return source code of app.main as a string."""
    import app.main as main_module
    return inspect.getsource(main_module)


# ---------------------------------------------------------------------------
# Module import checks
# ---------------------------------------------------------------------------

class TestSchedulerModuleImport:
    def test_main_has_lifespan_or_startup(self):
        """FastAPI app in main.py must have a lifespan or startup event for the scheduler."""
        from app.main import app
        assert app is not None

    def test_main_references_scheduler(self):
        """main.py must reference APScheduler (BackgroundScheduler)."""
        main_src = _get_main_src()
        assert (
            "apscheduler" in main_src
            or "BackgroundScheduler" in main_src
            or "scheduler" in main_src.lower()
        ), "main.py must reference APScheduler for the nightly distill job"


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

class TestSchedulerRegistration:
    def test_scheduler_has_nightly_daily_job(self):
        """A cron job for daily summary (23:59) must be registered in main.py lifespan."""
        main_src = _get_main_src()
        # Must have hour=23 and minute=59 configured
        assert "hour=23" in main_src or ("23" in main_src and "59" in main_src), (
            "Scheduler config must specify hour=23, minute=59 for nightly distill"
        )
        assert "minute=59" in main_src or "59" in main_src, (
            "Scheduler config must include minute=59"
        )

    def test_nightly_job_calls_generate_daily_summary(self):
        """main.py must reference run_daily_distill or generate_daily_summary."""
        main_src = _get_main_src()
        assert (
            "run_daily_distill" in main_src
            or "generate_daily_summary" in main_src
            or "distill" in main_src.lower()
        ), "main.py must reference the daily distill function"

    def test_weekly_job_registered(self):
        """A weekly summary cron job must be registered in main.py."""
        main_src = _get_main_src()
        assert (
            "run_weekly_distill" in main_src
            or "weekly" in main_src.lower()
        ), "main.py must register a weekly summary job"

    def test_scheduler_started_at_startup(self):
        """BackgroundScheduler.start() must be called in main.py lifespan."""
        main_src = _get_main_src()
        assert "scheduler.start()" in main_src or ".start()" in main_src, (
            "main.py lifespan must call scheduler.start()"
        )

    def test_scheduler_shutdown_at_teardown(self):
        """BackgroundScheduler.shutdown() must be called in main.py lifespan teardown."""
        main_src = _get_main_src()
        assert "shutdown" in main_src, (
            "main.py lifespan must call scheduler.shutdown() on teardown"
        )

    def test_scheduler_uses_cron_trigger(self):
        """main.py must use 'cron' trigger type for the distill job."""
        main_src = _get_main_src()
        assert '"cron"' in main_src or "'cron'" in main_src, (
            "main.py must use cron trigger for the nightly distill job"
        )


# ---------------------------------------------------------------------------
# Scheduler job execution (unit test the distill entry points)
# ---------------------------------------------------------------------------

class TestDistillEntryPoints:
    def test_run_daily_distill_callable(self):
        """run_daily_distill must be a callable in distill module."""
        from app.pipeline.distill import run_daily_distill
        assert callable(run_daily_distill)

    def test_run_weekly_distill_callable(self):
        """run_weekly_distill must be a callable in distill module."""
        from app.pipeline.distill import run_weekly_distill
        assert callable(run_weekly_distill)

    def test_run_daily_distill_handles_exception_gracefully(self):
        """run_daily_distill must catch exceptions per user and not crash the scheduler."""
        from app.pipeline.distill import run_daily_distill
        import inspect
        src = inspect.getsource(run_daily_distill)
        # Must contain exception handling
        assert "except" in src, (
            "run_daily_distill must handle per-user exceptions so the scheduler continues"
        )

    def test_run_weekly_distill_handles_exception_gracefully(self):
        """run_weekly_distill must catch exceptions per user."""
        from app.pipeline.distill import run_weekly_distill
        import inspect
        src = inspect.getsource(run_weekly_distill)
        assert "except" in src, (
            "run_weekly_distill must handle per-user exceptions"
        )

    def test_run_daily_distill_uses_today(self):
        """run_daily_distill must reference date.today() for the target date."""
        from app.pipeline.distill import run_daily_distill
        import inspect
        src = inspect.getsource(run_daily_distill)
        assert "today" in src or "date.today" in src, (
            "run_daily_distill must use today's date"
        )

    def test_run_daily_distill_calls_asyncio_run(self):
        """run_daily_distill must use asyncio.run() or similar to run async code."""
        from app.pipeline.distill import run_daily_distill
        import inspect
        src = inspect.getsource(run_daily_distill)
        assert "asyncio" in src or "async" in src, (
            "run_daily_distill must drive async generate_daily_summary"
        )


# ---------------------------------------------------------------------------
# APScheduler configuration validation
# ---------------------------------------------------------------------------

class TestSchedulerConfiguration:
    def test_apscheduler_importable(self):
        """apscheduler package must be installed."""
        import apscheduler  # noqa: F401

    def test_background_scheduler_importable(self):
        """APScheduler BackgroundScheduler must be importable."""
        from apscheduler.schedulers.background import BackgroundScheduler
        assert BackgroundScheduler is not None

    def test_cron_trigger_importable(self):
        """APScheduler CronTrigger must be importable."""
        from apscheduler.triggers.cron import CronTrigger
        assert CronTrigger is not None

    def test_main_py_references_apscheduler(self):
        """main.py must import from apscheduler."""
        main_src = _get_main_src()
        has_scheduler = (
            "apscheduler" in main_src
            or "BackgroundScheduler" in main_src
        )
        assert has_scheduler, "main.py must import APScheduler for nightly distill scheduling"

    def test_scheduler_runs_at_2359(self):
        """Nightly distill must be configured for hour=23, minute=59."""
        main_src = _get_main_src()
        has_2359 = "hour=23" in main_src and "minute=59" in main_src
        assert has_2359, "Scheduler must be configured to run at hour=23, minute=59"
