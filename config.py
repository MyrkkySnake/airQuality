"""
Central configuration — reads from .env via pydantic-settings.
Import `settings` anywhere in the project.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str

    # ── OpenAI ────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

    # ── Database ──────────────────────────────────────────────────────────
    # SQLite example:  sqlite+aiosqlite:///./airquality.db
    # Postgres example: postgresql+asyncpg://user:pass@localhost/airquality
    DATABASE_URL: str = "sqlite+aiosqlite:///./airquality.db"
    DB_ECHO: bool = False            # Set True to log SQL in dev

    # ── API Server ────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_SECRET_KEY: str = "change-me-in-production"

    # ── Map defaults ──────────────────────────────────────────────────────
    MAP_CENTER_LAT: float = 42.4597  # Nukus, Uzbekistan
    MAP_CENTER_LON: float = 59.6093
    MAP_ZOOM: int = 12

    # ── Trend analysis ────────────────────────────────────────────────────
    TREND_HOURS: int = 6             # How many hours back to compare

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
