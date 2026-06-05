"""
Application configuration via pydantic-settings.
All settings are loaded from environment variables (or a .env file in development).
Production secrets are injected via Azure Container App secret references.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings

_DEV_JWT_PLACEHOLDER = "change-me-in-production"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"

    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"

    # Azure Speech
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "westus2"

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "cortex-media"

    # Azure AI Vision
    AZURE_VISION_ENDPOINT: str = ""
    AZURE_VISION_KEY: str = ""

    # JWT — no default; must be set via environment variable.
    # In development, JWT_SECRET_KEY may be set to a local value in .env.
    # In production (ENVIRONMENT=production) it must be a strong, unique secret.
    JWT_SECRET_KEY: str = _DEV_JWT_PLACEHOLDER

    # App
    CORS_ORIGINS: str = "https://cortex-app.azurestaticapps.net,http://localhost:5173"
    ENVIRONMENT: str = "development"

    # Web Push (Round 35)
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str | None = None

    # Azure Communication Services Email
    acs_email_connection: str | None = None
    acs_email_sender: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Enforce a strong JWT secret.

        Rules:
        - The dev placeholder is allowed to pass this validator (it is caught at
          startup by check_production_secrets() when ENVIRONMENT=production).
        - Any non-placeholder value must be at least 32 characters.
        """
        if v != _DEV_JWT_PLACEHOLDER and len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters long. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    def check_production_secrets(self) -> None:
        """Call at startup: raises RuntimeError if production settings are insecure.

        Fails immediately if ENVIRONMENT=production and the key is still the dev
        placeholder, preventing accidental use of the well-known weak default.
        """
        if self.ENVIRONMENT == "production" and self.JWT_SECRET_KEY == _DEV_JWT_PLACEHOLDER:
            raise RuntimeError(
                "FATAL: JWT_SECRET_KEY is the insecure dev placeholder in a production "
                "environment. Set a strong, unique JWT_SECRET_KEY before starting. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a list of origin strings."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
# Fail fast if production is using a weak/placeholder key.
settings.check_production_secrets()
