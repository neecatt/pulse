from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from ``PULSE_*`` environment variables or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="PULSE_", env_file=".env", extra="ignore")

    # Local state (database, generated SSH key). Created on startup.
    data_dir: Path = Path("data")
    database_url: str = "sqlite+aiosqlite:///./data/pulse.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Built frontend to serve from the API process (e.g. ../frontend/dist).
    static_dir: Path | None = None

    # Single-user stub until real authentication lands; see api/deps.py.
    default_user_email: str = "dev@pulse.local"

    # Slurm access
    slurm_backend: Literal["mock", "ssh"] = "mock"
    # Defaults to a key Pulse generates in data_dir on first start.
    ssh_key_path: Path | None = None
    # Strict host checking against this file; unset means trust-on-first-use per account.
    ssh_known_hosts: str | None = None
    ssh_connect_timeout_seconds: float = 10.0
    ssh_command_timeout_seconds: float = 30.0
    ssh_keepalive_seconds: int = 60
    sacct_lookback_hours: int = 48
    # `find` on shared filesystems is slow; look for new metric files this often.
    metric_discovery_interval_seconds: int = 60
    node_stats_timeout_seconds: int = 20

    # Poller and alert thresholds
    # Poll fast while someone has the app open, slowly otherwise.
    poll_interval_live_seconds: int = 10
    poll_interval_idle_seconds: int = 60
    # Per-node CPU/memory/GPU sampling starts a job step (srun); do it this often at most.
    node_stats_interval_seconds: int = 60
    # Flag an agent account when it hasn't reported for this long.
    agent_stale_seconds: int = 180
    poll_concurrency: int = 8
    stall_minutes: int = 15
    time_limit_warning_ratio: float = 0.9
    diverge_percent: int = 50  # smoothed loss this far above its best
    plateau_minutes: int = 60  # no new best loss for this long

    # Web Push (generate with `pulse gen-vapid`)
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"  # set your own contact in .env
    push_ttl_seconds: int = 6 * 3600  # how long a push service keeps an undelivered alert
    push_timeout_seconds: float = 10.0

    @property
    def ssh_key_file(self) -> Path:
        return self.ssh_key_path or self.data_dir / "pulse_ed25519"


@lru_cache
def get_settings() -> Settings:
    return Settings()
