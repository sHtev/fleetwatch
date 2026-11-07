from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg://fleetwatch:fleetwatch@localhost:5432/fleetwatch"


settings = Settings()
