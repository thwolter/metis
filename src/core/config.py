from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import SettingsConfigDict

from .utils import ValidatedSettings, load_version, parse_cors_origins


class Settings(ValidatedSettings):
    model_config = SettingsConfigDict(
        env_file='.env',  # let pydantic-settings read .env
        case_sensitive=False,  # typical for envs
        extra='ignore',  # ignore unknown env vars
    )

    required_keys = ['postgres_url', 'redis_url', 'openai_api_key', 'tavily_api_key']

    env: Literal['development', 'production', 'testing'] = 'production'
    app_name: str = 'Metis'
    debug: bool | None = None
    version: str = Field(default_factory=load_version)
    admin_email: str = 'support@riskary.de'

    postgres_url: SecretStr | None = None
    redis_url: SecretStr | None = None

    openai_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

    log_level: Literal['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] = 'INFO'
    otlp_endpoint: str | None = None
    otlp_headers: str | None = None
    otel_logs_enabled: bool = False
    otel_traces_enabled: bool = True
    otel_metrics_enabled: bool = True
    jwt_secret: SecretStr = SecretStr('dev-internal-token')

    metadata_schema: str = 'metadata'
    classification_schema: str = 'classification'
    pg_vector_schema: str = 'vectra'

    cors_allow_origins: tuple[str, ...] = ()

    @field_validator('cors_allow_origins', mode='before')
    @classmethod
    def _normalize_cors_origins(cls, value: Any) -> tuple[str, ...]:
        return parse_cors_origins(value)

    @field_validator('postgres_url', mode='before')
    @classmethod
    def validate_postgres_url(cls, url: str) -> str:
        if not url:
            return url
        if url.startswith('postgres://'):
            return url.replace('postgres://', 'postgresql://', 1)
        return url

    @property
    def async_postgres_url(self) -> SecretStr:
        # Convert postgresql:// to postgresql+asyncpg:// for async engine
        if self.postgres_url is None:
            return SecretStr('')
        url = self.postgres_url.get_secret_value()
        if url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql+asyncpg://', 1)
        return SecretStr(url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[missing-argument]
