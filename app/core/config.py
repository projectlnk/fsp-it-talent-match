from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://project:local-dev-password@localhost:5432/project"
    fsp_base_url: str = "http://localhost:8001"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    reload: bool = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
