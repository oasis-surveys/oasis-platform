"""
Tests for application configuration and settings.

Pure unit tests — no external services needed.
"""

import os

import pytest


class TestConfig:
    def test_settings_loaded(self):
        from app.config import settings

        assert settings.app_name == "OASIS"
        assert settings.debug is True  # Default

    def test_database_url_format(self):
        from app.config import settings

        url = settings.database_url
        assert url.startswith("postgresql+asyncpg://")
        assert settings.postgres_user in url

    def test_database_url_sync_format(self):
        from app.config import settings

        url = settings.database_url_sync
        assert url.startswith("postgresql://")

    def test_redis_url_default(self):
        from app.config import settings

        assert "redis://" in settings.redis_url

    def test_auth_default_disabled(self):
        from app.config import settings

        assert settings.auth_enabled is False

    def test_scaleway_api_key_property(self):
        from app.config import settings

        # scaleway_api_key is a property that returns scaleway_secret_key
        assert settings.scaleway_api_key == settings.scaleway_secret_key

    def test_gcp_defaults(self):
        from app.config import settings

        assert settings.gcp_location == "us-central1"
