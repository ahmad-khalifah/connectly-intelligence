"""Application settings, read from environment variables or backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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

    # "development" or "production". Production refuses to start without a secret key.
    environment: str = "development"
    # Signs session tokens. At least 32 characters; generate with
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str | None = None
    # How long a sign-in lasts, in minutes.
    access_token_minutes: int = 480
    # Account lock after repeated wrong passwords.
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    # Sign-in attempts allowed per client address in the window below (all accounts).
    login_ip_limit: int = 30
    login_ip_window_seconds: int = 600
    # Optional language model for narrative summaries. "none" (default) keeps everything
    # deterministic. "ollama" uses a local Ollama server; "openai_compatible" any server with
    # the /v1/chat/completions API (llama.cpp, vLLM, LM Studio...). Only free, self-hosted
    # servers are intended; hosted APIs may charge.
    ai_provider: str = "none"
    ai_base_url: str = "http://localhost:11434"
    ai_model: str = "llama3.1:8b"
    ai_api_key: str | None = None
    ai_timeout: float = 120.0
    # Google Gemini API (Google AI Studio), FREE TIER ONLY. See docs/research.md.
    # The key must come from a Google Cloud project with NO billing account linked: Google's
    # free tier cannot be charged, and linking billing is what moves a project to paid use.
    gemini_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    # Live web research with Google Search grounding. On the free tier only Gemini 2.5 Flash
    # and Flash-Lite include Search (500 requests/day shared, per Google's pricing page).
    gemini_search_model: str = "gemini-2.5-flash"
    # Extraction from sources and summaries (no Search).
    gemini_text_model: str = "gemini-2.5-flash"
    # Connectly's own limits, kept below Google's free limits so the app stops first.
    # Days are counted in Pacific time, when Google resets daily quotas.
    gemini_daily_search_limit: int = 200
    gemini_daily_request_limit: int = 200
    gemini_per_minute_limit: int = 5
    gemini_timeout: float = 90.0
    # How long cached extraction results are reused (Search results are never cached).
    gemini_cache_days: int = 30
    # Trust X-Forwarded-For from a reverse proxy when recording client addresses.
    trust_proxy_headers: bool = False

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
