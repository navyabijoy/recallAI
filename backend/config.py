"""Application settings, loaded from backend/.env (via pydantic-settings)."""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "dev-insecure-change-me"


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
    secret_key: str = _INSECURE_DEFAULT_SECRET   # override in .env for anything real
    jwt_expire_hours: int = 720                  # 30 days

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Where to send the browser after login
    frontend_url: str = "http://localhost:3000"

    # CORS — comma-separated list of allowed frontend origins. Falls back to
    # frontend_url alone when unset.
    allowed_origins: str = ""

    # Error tracking (Sentry) — no-op if unset.
    sentry_dsn: str = ""

    # Set to "1" to allow the insecure default secret key (local dev only).
    allow_insecure_secret_key: bool = False

    # Set to "1" to let sync sources fall back to fabricated mock data when no
    # real credential is configured (local dev / demo only — never in production,
    # it would silently write invented practice history into a real user's model).
    allow_mock_sync: bool = False

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins:
            return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return [self.frontend_url]


settings = Settings()

if settings.secret_key == _INSECURE_DEFAULT_SECRET and not settings.allow_insecure_secret_key:
    raise RuntimeError(
        "SECRET_KEY is unset or using the insecure default. Set a strong SECRET_KEY in "
        "backend/.env (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`), "
        "or set ALLOW_INSECURE_SECRET_KEY=1 for local development only."
    )
