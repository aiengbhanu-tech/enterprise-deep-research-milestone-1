from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    app_name: str = "Enterprise Deep Research Agent"
    app_env: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/v1"
    database_url: str = "postgresql+asyncpg://research:research@localhost:5432/research"
    langgraph_database_url: str = "postgresql://research:research@localhost:5432/research"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    research_max_iterations: int = Field(default=3, ge=1, le=10)
    research_default_budget_usd: float = Field(default=2.0, gt=0)
    research_max_searches: int = Field(default=30, ge=1, le=200)
    research_max_sources: int = Field(default=20, ge=1, le=100)
    research_min_coverage_score: float = Field(default=0.8, ge=0, le=1)
    research_min_source_quality: float = Field(default=0.55, ge=0, le=1)
    research_mode: str = "mock"
    search_provider: str = "mock"
    tavily_api_key: str | None = None
    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    citation_min_support_score: float = Field(default=0.12, ge=0, le=1)
    citation_max_repair_attempts: int = Field(default=2, ge=0, le=5)
    llm_input_cost_per_million: float = Field(default=0.25, ge=0)
    llm_output_cost_per_million: float = Field(default=2.0, ge=0)
    max_search_concurrency: int = Field(default=5, ge=1, le=20)
    max_fetch_concurrency: int = Field(default=5, ge=1, le=20)
    fetch_timeout_seconds: float = Field(default=20, gt=0, le=120)
    max_source_bytes: int = Field(default=5_000_000, ge=10_000, le=50_000_000)
    qdrant_collection: str = "research_evidence"


@lru_cache
def get_settings() -> Settings:
    return Settings()
