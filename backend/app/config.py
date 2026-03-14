"""
OASIS — Application configuration.

All settings are loaded from environment variables (or .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ──
    app_name: str = "OASIS"
    app_env: str = "development"
    secret_key: str = "change-me-to-a-random-secret-key"
    debug: bool = True

    # ── PostgreSQL ──
    postgres_user: str = "oasis"
    postgres_password: str = "change-me"
    postgres_db: str = "oasis"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Synchronous URL for Alembic migrations."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ──
    redis_url: str = "redis://redis:6379/0"

    # ── AI Providers ──
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    cartesia_api_key: str = ""

    # ── Scaleway (OpenAI-compatible LLM API) ──
    # Uses SCALEWAY_SECRET_KEY as the Bearer token (secret part of the API keypair)
    scaleway_secret_key: str = ""          # maps to SCALEWAY_SECRET_KEY in .env
    scaleway_project_id: str = ""          # maps to SCALEWAY_PROJECT_ID in .env
    scaleway_api_url: str = "https://api.scaleway.ai/v1"

    @property
    def scaleway_api_key(self) -> str:
        """Return the Scaleway secret key for use as a Bearer token."""
        return self.scaleway_secret_key

    # ── Google AI (Gemini Live native audio) ──
    google_api_key: str = ""               # maps to GOOGLE_API_KEY in .env

    # ── Azure OpenAI (self-hosted) ──
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    # ── GCP Vertex AI (self-hosted) ──
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    gcp_api_key: str = ""  # alternative to Application Default Credentials

    # ── Telephony ──
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # ── Authentication ──
    # Set AUTH_ENABLED=true and AUTH_PASSWORD to enable basic auth.
    # Default is OFF — no login required.
    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password: str = ""  # Must be set when auth_enabled=true


settings = Settings()
