"""Application settings, loaded from backend/.env (via pydantic-settings)."""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), ".env"),
        extra="ignore",
        case_sensitive=False,
    )

    # Database — SQLite by default so the app runs with zero setup; set to a
    # postgresql+psycopg://… URL (e.g. a free Neon instance) for multi-user.
    database_url: str = "sqlite:///./recallai.db"

    # Auth / JWT
    secret_key: str = "dev-insecure-change-me"   # override in .env for anything real
    jwt_expire_hours: int = 720                  # 30 days

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Where to send the browser after login
    frontend_url: str = "http://localhost:3000"

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


settings = Settings()
