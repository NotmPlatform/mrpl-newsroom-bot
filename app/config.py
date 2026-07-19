from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str
    admin_telegram_id: int = 0

    database_url: str

    deepseek_api_key: str
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    yandex_folder_id: str = ""
    yandex_api_key: str = ""

    wp_url: str = "https://mrpl.ru"
    wp_username: str
    wp_application_password: str
    wp_news_category_id: int = 1

    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    max_photos: int = Field(default=10, ge=1, le=10)
    max_voice_seconds: int = Field(default=300, ge=1, le=300)
    max_image_side: int = Field(default=2200, ge=800, le=4000)
    publish_enabled: bool = False
    temp_dir: Path = Path("/tmp/mrpl-newsroom")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://") and "+asyncpg" not in value:
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("wp_url", "deepseek_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("deepseek_model")
    @classmethod
    def validate_deepseek_model(cls, value: str) -> str:
        allowed = {"deepseek-v4-flash", "deepseek-v4-pro"}
        if value not in allowed:
            raise ValueError(f"DEEPSEEK_MODEL must be one of: {', '.join(sorted(allowed))}")
        return value

    @property
    def speechkit_enabled(self) -> bool:
        return bool(self.yandex_folder_id and self.yandex_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

