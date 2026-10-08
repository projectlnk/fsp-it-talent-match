from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://project:local-dev-password@localhost:5432/project"
    fsp_base_url: str = "http://localhost:8001"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    reload: bool = False

    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24
    email_verification_token_expire_hours: int = 24
    app_base_url: str = "http://localhost:8000"
    bcrypt_rounds: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()