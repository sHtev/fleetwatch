from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg://fleetwatch:fleetwatch@localhost:5432/fleetwatch"
    rounds_file: str = str(Path(__file__).parent.parent.parent / "data" / "york_rounds.json")


settings = Settings()
