"""
Application configuration using Pydantic Settings.
"""

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Application
    APP_NAME: str = "Twitch Miner Backend"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENABLE_SWAGGER: bool = True
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"

    # Paths
    DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"
    INSTANCES_DIR: Path = Path(__file__).parent.parent.parent / "data" / "instances"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///data/app.db"

    # Twitch Miner
    MINER_REPO_PATH: str = ""

    # Security
    JWT_SECRET: str = "change-me-in-production-use-a-random-64-char-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: List[str] = ["*"]  # Restrict in production!

    # Log streaming
    LOG_HISTORY_LINES: int = 100

    # Instance limits
    MAX_INSTANCES_PER_USER: int = 2  # Maximum instances for "user" role

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("MINER_REPO_PATH")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand ~ to home directory in MINER_REPO_PATH."""
        if v and v.startswith("~"):
            return str(Path(v).expanduser())
        return v


settings = Settings()
