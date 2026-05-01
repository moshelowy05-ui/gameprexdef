from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://gameprex:gameprex_dev@localhost:5432/gameprexdef"
    events_database_url: str = "postgresql+asyncpg://gameprex:gameprex_dev@localhost:5433/gameprex_events"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"

    # Session
    session_cookie_name: str = "gameprex_session"
    session_max_age: int = 86400 * 7  # 7 days

    # Simulation defaults
    default_tick_duration_seconds: int = 5  # real seconds per game tick in real-time mode
    ticks_per_game_hour: int = 1


settings = Settings()
