"""Application settings, read from environment variables or backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="CONNECTLY_", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://connectly:connectly@localhost:5432/connectly"
    # Where downloaded raw files are kept. Never committed to git.
    data_dir: Path = REPO_DIR / "data"
    # Comma-separated origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:3000"
    # Network timeout for dataset downloads, in seconds.
    download_timeout: float = 300.0

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
