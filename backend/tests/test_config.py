import pytest
from config import Settings, get_settings


class TestApplicationConfig:
    def test_default_settings_values(self):
        settings = Settings()
        assert settings.ENVIRONMENT == "development"
        assert settings.DB_HOST == "localhost"
        assert settings.DB_PORT == 5432
        assert settings.REDIS_PORT == 6379
        assert settings.ALGORITHM == "HS256"
        assert settings.AUTH_RATE_LIMIT_LOGIN == 60
        assert settings.AUTH_RATE_LIMIT_REGISTER == 20

    def test_cors_origins_list_parsing(self):
        custom_settings = Settings(CORS_ORIGINS="http://localhost:3000, https://agencydesk.app,  http://localhost:5173  ")
        origins = custom_settings.cors_origins_list
        assert origins == ["http://localhost:3000", "https://agencydesk.app", "http://localhost:5173"]

    def test_redis_empty_password_normalizes_to_none(self):
        settings_empty = Settings(REDIS_PASSWORD="")
        assert settings_empty.REDIS_PASSWORD is None

        settings_none = Settings(REDIS_PASSWORD=None)
        assert settings_none.REDIS_PASSWORD is None

        settings_actual = Settings(REDIS_PASSWORD="secure-redis-pass")
        assert settings_actual.REDIS_PASSWORD == "secure-redis-pass"

    def test_environment_variable_override(self, monkeypatch):
        monkeypatch.setenv("DB_PORT", "5439")
        monkeypatch.setenv("AUTH_RATE_LIMIT_LOGIN", "120")
        settings = Settings()
        assert settings.DB_PORT == 5439
        assert settings.AUTH_RATE_LIMIT_LOGIN == 120

    def test_production_secret_key_guard(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "dev-only-change-me-before-deploying")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="SECRET_KEY must be configured"):
            get_settings()
        get_settings.cache_clear()
