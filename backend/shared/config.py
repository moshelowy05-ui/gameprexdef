from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://gameprex:gameprex_dev@localhost:5432/gameprexdef"
    events_database_url: str = "postgresql+asyncpg://gameprex:gameprex_dev@localhost:5433/gameprex_events"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"

    # CORS — comma-separated allowed origins; empty = same-origin only
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Default login credentials (override via env in production)
    default_username: str = "nca"
    default_password: str = "gameprex2024"

    # Session
    session_cookie_name: str = "gameprex_session"
    session_max_age: int = 86400 * 7  # 7 days

    # Simulation defaults
    default_tick_duration_seconds: int = 5
    ticks_per_game_hour: int = 1

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
