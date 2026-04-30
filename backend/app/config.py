"""
Application configuration via pydantic-settings.
All settings are loaded from environment variables (or a .env file in development).
Production secrets are injected via Azure Container App secret references.
"""
from pydantic_settings import BaseSettings


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

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"

    # App
    CORS_ORIGINS: str = "https://cortex-app.azurestaticapps.net,http://localhost:5173"
    ENVIRONMENT: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a list of origin strings."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
