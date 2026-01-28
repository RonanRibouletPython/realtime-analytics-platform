from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App config
    PROJECT_NAME: str = "Ingestion Service"
    API_V1: str = "api/v1"
    ENV: Literal["development", "production"] = "development"

    # DB config (Postgres)
    POSTGRES_USER: str = "analytics"
    POSTGRES_PASSWORD: str = "analytics"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "analytics"

    # Redis config
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Kafka config
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_METRICS: str = "metrics_ingestion"

    @property
    def DB_URL(
        self,
    ) -> str:
        db_url = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return db_url

    @property
    def REDIS_URL(
        self,
    ) -> str:
        redis_url = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return redis_url

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


settings = Settings()
