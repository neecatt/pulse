from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from ``PULSE_*`` environment variables or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="PULSE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./pulse.db"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Single-user stub until real authentication lands; see api/deps.py.
    default_user_email: str = "dev@pulse.local"

    # Slurm access
    slurm_backend: Literal["mock", "ssh"] = "mock"
    ssh_key_path: str | None = None
    ssh_known_hosts: str | None = None
    ssh_connect_timeout_seconds: float = 10.0
    sacct_lookback_hours: int = 48

    # Poller and alert thresholds
    poll_interval_seconds: int = 30
    poll_concurrency: int = 8
    stall_minutes: int = 15
    time_limit_warning_ratio: float = 0.9

    # Web Push (generate with `pulse gen-vapid`)
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
