from functools import lru_cache
from typing import Any, Literal

from datasifter import RetrievalConfig
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import SettingsConfigDict

from .utils import ValidatedModel, ValidatedSettings, load_version, parse_cors_origins


class OTLPSettings(ValidatedModel):
    endpoint: str | None = None
    headers: str | None = None
    logs_enabled: bool = False
    traces_enabled: bool = True
    metrics_enabled: bool = True


class ExtractionSettings(ValidatedModel):
    default_model: str = 'openai:gpt-5-mini'
    model_version: str = '2025-01-01'
    max_chunks: int = 6
    top_m: int = 3
    header_boost: float = 0.5
    semantic_weight: float = 1.0
    bm25_weight: float = 0.5
    hints_weight: float = 0.3

    def to_retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            max_chunks=self.max_chunks,
            top_m=self.top_m,
            header_boost=self.header_boost,
            semantic_weight=self.semantic_weight,
            bm25_weight=self.bm25_weight,
            hints_weight=self.hints_weight,
        )


class Settings(ValidatedSettings):
    model_config = SettingsConfigDict(
        env_file='.env',  # let pydantic-settings read .env
        case_sensitive=False,  # typical for envs
        extra='ignore',  # ignore unknown env vars
        env_nested_delimiter='__',
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
    otlp: OTLPSettings = Field(default_factory=OTLPSettings)
    jwt_secret: SecretStr = SecretStr('dev-internal-token')

    metadata_schema: str = 'metadata'
    classification_schema: str = 'classification'
    pg_vector_schema: str = 'vectra'

    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)

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
