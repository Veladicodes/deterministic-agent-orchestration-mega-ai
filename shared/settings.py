from functools import lru_cache
import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

load_dotenv()


class Settings(BaseModel):
    """Centralized runtime settings loaded from environment variables."""

    app_name: str = "mega-ai"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from the process environment."""

        data = {
            "app_name": os.getenv("APP_NAME", "mega-ai"),
            "app_env": os.getenv("APP_ENV", "local"),
            "app_host": os.getenv("APP_HOST", "0.0.0.0"),
            "app_port": int(os.getenv("APP_PORT", "8000")),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "database_url": os.getenv("DATABASE_URL", ""),
            "redis_url": os.getenv("REDIS_URL", ""),
            "celery_broker_url": os.getenv("CELERY_BROKER_URL", ""),
            "celery_result_backend": os.getenv("CELERY_RESULT_BACKEND", ""),
        }
        settings = cls.model_validate(data)
        settings.validate()
        return settings

    def validate(self) -> None:
        """Run lightweight validation on critical settings.

        Raises ValueError on clearly invalid configuration.
        """
        # Basic checks
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")
        if not (self.database_url.startswith("postgresql") or self.database_url.startswith("sqlite")):
            raise ValueError("DATABASE_URL should be a postgresql or sqlite URL")
        if not self.redis_url:
            raise ValueError("REDIS_URL is required")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
