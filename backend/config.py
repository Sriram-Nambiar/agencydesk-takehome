from functools import lru_cache
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized, type-safe application configuration for AgencyDesk.
    Reads from environment variables and optional .env file with automatic type coercion and validation.
    """

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database Configuration (PostgreSQL)
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "agencydesk"
    DB_USER: str = "postgres"
    DB_PASS: str = "devpass"
    DB_MIN_CONN: int = 2
    DB_MAX_CONN: int = 20

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_SOCKET_TIMEOUT: float = 2.0

    # Security & JWT Token Signing
    SECRET_KEY: str = "dev-only-change-me-before-deploying"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # CORS Allowed Origins (Comma-separated)
    CORS_ORIGINS: str = "http://localhost:5173"

    # Rate Limiting (Requests per 60-second sliding window)
    AUTH_RATE_LIMIT_LOGIN: int = 60
    AUTH_RATE_LIMIT_REGISTER: int = 20

    # Local File Uploads Directory
    UPLOAD_DIR: str = "uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("REDIS_PASSWORD", mode="before")
    @classmethod
    def normalize_empty_password(cls, v):
        if v == "" or v is None:
            return None
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of the validated application settings."""
    settings = Settings()
    if settings.ENVIRONMENT == "production" and (
        not settings.SECRET_KEY or settings.SECRET_KEY == "dev-only-change-me-before-deploying"
    ):
        raise RuntimeError("SECRET_KEY must be configured with a secure random secret in production")
    return settings
