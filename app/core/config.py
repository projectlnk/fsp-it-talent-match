from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = "postgresql+psycopg://project:local-dev-password@localhost:5432/project"
    fsp_base_url: str = "http://localhost:8001"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = "noreply@fsp-it-talent.local"
    smtp_from_name: str = "FSP IT Talent Match"
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    reload: bool = False

    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24
    email_verification_token_expire_hours: int = 24
    app_base_url: str = "http://localhost:8000"
    bcrypt_rounds: int = 12


    @model_validator(mode="after")
    def validate_smtp(self):
        if self.smtp_starttls and self.smtp_ssl:
            raise ValueError("SMTP_STARTTLS и SMTP_SSL нельзя включать одновременно")
        if bool(self.smtp_username) != bool(self.smtp_password.get_secret_value()):
            raise ValueError("SMTP_USERNAME и SMTP_PASSWORD задаются вместе")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()