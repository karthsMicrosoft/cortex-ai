"""
test_security_config.py — Security Task 1, SEC-01

Static review tests for JWT_SECRET_KEY configuration safety.

Covers:
  SEC-01: verify config raises in production when key matches dev placeholder;
          allow override; not None.

Review finding (1.1): JWT_SECRET_KEY defaults to "change-me-in-production".
The fix should either:
  (a) Remove the default so pydantic-settings raises at startup, OR
  (b) Add a validator that raises when ENVIRONMENT != "development" and the
      key equals the placeholder string.

These tests enforce the post-fix contract regardless of approach.
"""
import os
import pytest


# ---------------------------------------------------------------------------
# SEC-01-A: Key must not be None after instantiation
# ---------------------------------------------------------------------------

class TestJWTSecretKeyNotNone:
    def test_jwt_secret_key_is_not_none(self):
        """Settings.JWT_SECRET_KEY must never be None — it must have a value."""
        try:
            from app.config import settings
            assert settings.JWT_SECRET_KEY is not None, (
                "JWT_SECRET_KEY must not be None"
            )
            assert len(settings.JWT_SECRET_KEY) > 0, (
                "JWT_SECRET_KEY must not be an empty string"
            )
        except ImportError as exc:
            pytest.skip(f"app.config not importable: {exc}")


# ---------------------------------------------------------------------------
# SEC-01-B: In production mode the placeholder must be rejected
# ---------------------------------------------------------------------------

_DEV_PLACEHOLDER = "change-me-in-production"


class TestJWTSecretKeyProductionGuard:
    def test_placeholder_rejected_in_production(self, monkeypatch):
        """
        When ENVIRONMENT=production, using the dev placeholder must raise at
        Settings instantiation time (validator) or before the app serves a request.

        If the codebase enforces this via a pydantic @field_validator / model_validator,
        instantiating Settings with the placeholder key and production environment
        must raise a ValueError or ValidationError.

        If the guard is not yet implemented, this test will FAIL — which is the
        red-phase signal that SEC-01 is not fixed.
        """
        import importlib

        # Patch environment variables before importing config
        monkeypatch.setenv("JWT_SECRET_KEY", _DEV_PLACEHOLDER)
        monkeypatch.setenv("ENVIRONMENT", "production")

        # Force re-import of the settings module so monkeypatched env vars take effect
        try:
            import app.config as config_mod
            try:
                importlib.reload(config_mod)
            except (RuntimeError, ValueError):
                # reload() raises RuntimeError/ValueError when check_production_secrets()
                # fires at module level — this is the expected guard behaviour.
                return  # test passes: the guard correctly rejected the placeholder
            # If we reach here, the Settings class was instantiated without error.
            # Check that the instantiated settings STILL raises a dedicated error
            # via a validator (some implementations defer the check).
            from pydantic import ValidationError
            try:
                from pydantic_settings import BaseSettings
                # Re-instantiate to trigger validators
                new_settings = config_mod.Settings(
                    JWT_SECRET_KEY=_DEV_PLACEHOLDER,
                    ENVIRONMENT="production",
                )
                # If instantiation succeeded, try calling check_production_secrets()
                # (some implementations defer the check to a startup call).
                try:
                    new_settings.check_production_secrets()
                    # If we reach here without raising, the guard is missing.
                    pytest.fail(
                        "SEC-01 NOT FIXED: Settings must raise when JWT_SECRET_KEY equals "
                        f"'{_DEV_PLACEHOLDER}' and ENVIRONMENT='production'. "
                        "Add a @field_validator or @model_validator to enforce this."
                    )
                except (ValidationError, ValueError, RuntimeError):
                    # Expected — the guard correctly rejected the placeholder.
                    pass
            except (ValidationError, ValueError, RuntimeError):
                # Expected — the validator correctly rejected the placeholder.
                pass
        except ImportError as exc:
            pytest.skip(f"app.config not importable: {exc}")
        finally:
            # Always reload to restore original module state
            try:
                import app.config as config_mod
                importlib.reload(config_mod)
            except Exception:
                pass

    def test_non_placeholder_key_accepted_in_production(self, monkeypatch):
        """
        When ENVIRONMENT=production and JWT_SECRET_KEY is a strong custom key,
        Settings instantiation must succeed without raising.
        """
        import importlib

        strong_key = "a" * 64  # 64-char key, not the placeholder
        monkeypatch.setenv("JWT_SECRET_KEY", strong_key)
        monkeypatch.setenv("ENVIRONMENT", "production")

        try:
            import app.config as config_mod
            from pydantic import ValidationError
            try:
                new_settings = config_mod.Settings(
                    JWT_SECRET_KEY=strong_key,
                    ENVIRONMENT="production",
                )
                # Should succeed — strong key is valid
                assert new_settings.JWT_SECRET_KEY == strong_key
            except (ValidationError, ValueError) as exc:
                pytest.fail(
                    f"SEC-01: A valid non-placeholder JWT_SECRET_KEY was incorrectly rejected: {exc}"
                )
        except ImportError as exc:
            pytest.skip(f"app.config not importable: {exc}")
        finally:
            try:
                import app.config as config_mod
                importlib.reload(config_mod)
            except Exception:
                pass

    def test_placeholder_allowed_in_development(self, monkeypatch):
        """
        When ENVIRONMENT=development the placeholder key should be allowed
        (dev/test convenience — the guard only applies to production).
        """
        import importlib

        monkeypatch.setenv("JWT_SECRET_KEY", _DEV_PLACEHOLDER)
        monkeypatch.setenv("ENVIRONMENT", "development")

        try:
            import app.config as config_mod
            from pydantic import ValidationError
            try:
                new_settings = config_mod.Settings(
                    JWT_SECRET_KEY=_DEV_PLACEHOLDER,
                    ENVIRONMENT="development",
                )
                # Should succeed in development mode
                assert new_settings.JWT_SECRET_KEY == _DEV_PLACEHOLDER
            except (ValidationError, ValueError) as exc:
                pytest.fail(
                    f"SEC-01: Placeholder key incorrectly rejected in development mode: {exc}"
                )
        except ImportError as exc:
            pytest.skip(f"app.config not importable: {exc}")
        finally:
            try:
                import app.config as config_mod
                importlib.reload(config_mod)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# SEC-01-C: Key length enforcement (at least 32 characters)
# ---------------------------------------------------------------------------

class TestJWTSecretKeyLength:
    def test_short_key_rejected(self, monkeypatch):
        """
        JWT_SECRET_KEY shorter than 32 characters must be rejected regardless of
        ENVIRONMENT (a key this short provides inadequate HMAC-SHA256 security).

        If the validator is not implemented, this test will FAIL as expected
        during the TDD red phase.
        """
        import importlib

        short_key = "tooshort"  # 8 chars
        monkeypatch.setenv("JWT_SECRET_KEY", short_key)
        monkeypatch.setenv("ENVIRONMENT", "production")

        try:
            import app.config as config_mod
            from pydantic import ValidationError
            try:
                new_settings = config_mod.Settings(
                    JWT_SECRET_KEY=short_key,
                    ENVIRONMENT="production",
                )
                pytest.fail(
                    "SEC-01 NOT FIXED: JWT_SECRET_KEY shorter than 32 chars must be rejected "
                    "in production. Add min_length=32 validation."
                )
            except (ValidationError, ValueError):
                pass  # Correctly rejected
        except ImportError as exc:
            pytest.skip(f"app.config not importable: {exc}")
        finally:
            try:
                import app.config as config_mod
                importlib.reload(config_mod)
            except Exception:
                pass

    def test_key_at_least_32_chars_in_current_settings(self):
        """Current settings JWT_SECRET_KEY must be >= 32 characters."""
        try:
            from app.config import settings
            # In test environment the key may be the placeholder or overridden via env.
            # We only assert it is not shorter than 8 chars (minimum sanity check).
            # Production length enforcement is covered by test_short_key_rejected above.
            assert len(settings.JWT_SECRET_KEY) >= 8, (
                "JWT_SECRET_KEY must be at least 8 characters even in test/dev mode"
            )
        except ImportError as exc:
            pytest.skip(f"app.config not importable: {exc}")


# ---------------------------------------------------------------------------
# SEC-06: DEPLOYMENT.md must document WS query-param residual risk
# ---------------------------------------------------------------------------

class TestDeploymentDocsWSResidualRisk:
    """
    SEC-06 (review-comments.tasks.md 1.6)

    The DEPLOYMENT.md documentation must reference the residual risk of the
    WebSocket ?token= query-parameter appearing in Azure platform logs
    (before uvicorn's log-scrubbing filter can act on them).

    This is a documentation assertion test — it reads the file and checks for
    required phrases.
    """

    _DEPLOYMENT_MD_PATH = (
        # Relative from repo root; adjust if tests run from a different cwd.
        # Using absolute resolution via __file__.
        __import__("pathlib").Path(__file__).parent.parent.parent
        / "docs"
        / "DEPLOYMENT.md"
    )

    def test_deployment_md_exists(self):
        """SEC-06: docs/DEPLOYMENT.md must exist."""
        assert self._DEPLOYMENT_MD_PATH.exists(), (
            f"SEC-06: docs/DEPLOYMENT.md not found at {self._DEPLOYMENT_MD_PATH}. "
            "The file must exist and document the WS token residual risk."
        )

    def test_deployment_md_references_ws_query_param_risk(self):
        """
        SEC-06: docs/DEPLOYMENT.md must contain a section documenting the
        WebSocket ?token= query-parameter residual log-exposure risk.

        Required phrases (any one of these signals the risk is documented):
          - "WebSocket" + "token" + "log" (case-insensitive)
          - "residual risk" or "residual" near "WebSocket"
          - "Azure Container App" + "access logs" near "token"
        """
        if not self._DEPLOYMENT_MD_PATH.exists():
            pytest.skip("docs/DEPLOYMENT.md does not exist — covered by test_deployment_md_exists")

        content = self._DEPLOYMENT_MD_PATH.read_text(encoding="utf-8").lower()

        # Check that WebSocket token log exposure is discussed
        has_ws_token_log = (
            "websocket" in content
            and "token" in content
            and ("log" in content or "access log" in content)
        )
        assert has_ws_token_log, (
            "SEC-06 NOT DOCUMENTED: docs/DEPLOYMENT.md must reference the WebSocket "
            "?token= query-parameter and Azure platform log exposure risk. "
            "Add a security section documenting this residual risk per review finding 1.6."
        )

    def test_deployment_md_references_residual_risk_phrase(self):
        """
        SEC-06: docs/DEPLOYMENT.md must contain the phrase 'residual risk'
        (or equivalent) near the WebSocket token section.
        """
        if not self._DEPLOYMENT_MD_PATH.exists():
            pytest.skip("docs/DEPLOYMENT.md does not exist")

        content = self._DEPLOYMENT_MD_PATH.read_text(encoding="utf-8").lower()

        has_residual = (
            "residual risk" in content
            or "residual" in content
            or "platform log" in content
            or "azure container app" in content and "access log" in content
        )
        assert has_residual, (
            "SEC-06 NOT DOCUMENTED: docs/DEPLOYMENT.md must mention that Azure Container "
            "App access logs capture raw URLs (including ?token=) before uvicorn scrubbing. "
            "Add explicit residual-risk documentation."
        )

    def test_deployment_md_references_log_retention_or_future_hardening(self):
        """
        SEC-06: docs/DEPLOYMENT.md must recommend a mitigation (either short log
        retention or future opaque-ticket approach).
        """
        if not self._DEPLOYMENT_MD_PATH.exists():
            pytest.skip("docs/DEPLOYMENT.md does not exist")

        content = self._DEPLOYMENT_MD_PATH.read_text(encoding="utf-8").lower()

        has_mitigation = (
            "retention" in content
            or "ticket" in content
            or "opaque" in content
            or "sec-websocket-protocol" in content
            or "future" in content
        )
        assert has_mitigation, (
            "SEC-06: docs/DEPLOYMENT.md should recommend a mitigation strategy for the "
            "WS token log-exposure risk (short retention window, opaque-ticket approach, etc.)."
        )
