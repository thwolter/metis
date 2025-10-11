from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',  # let pydantic-settings read .env
        case_sensitive=False,  # typical for envs
        extra='ignore',  # ignore unknown env vars
    )

    env: Literal['development', 'production', 'testing'] = 'production'
    app_name: str = 'FastAPI'
    debug: bool | None = None
    version: str = '0.1.0'
    admin_email: str = 'support@riskary.de'

    postgres_url: SecretStr
    redis_url: SecretStr

    openai_api_key: SecretStr
    tavily_api_key: SecretStr

    log_level: Literal['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] = 'INFO'
    otlp_endpoint: str | None = None
    otlp_headers: str | None = None

    @property
    def pg_vector_url(self) -> SecretStr:
        """Returns the PostgreSQL database URL for PGVector.
        Converts 'postgres://' to 'postgresql://' if needed.
        """
        url = self.postgres_url.get_secret_value()
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql://', 1)
        return SecretStr(url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[missing-argument]
