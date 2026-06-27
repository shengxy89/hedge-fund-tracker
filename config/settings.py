from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg2://hedge:hedge123@localhost:5432/hedge_fund_db"

    # SEC
    sec_user_agent: str = "YourName your@email.com"
    sec_api_base: str = "https://data.sec.gov"
    forms13f_api_base: str = "https://api.forms13f.com/v1"

    # API Keys
    fmp_api_key: str = ""
    whalewisdom_api_key: str = ""

    # App
    log_level: str = "INFO"
    max_retries: int = 3
    rate_limit_delay: float = 0.15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
