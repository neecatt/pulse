from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Docker/Kubernetes secrets: a file /run/secrets/pulse_admin_password sets
# PULSE_ADMIN_PASSWORD, and so on for every setting.
_SECRETS_DIR = Path("/run/secrets")


class Settings(BaseSettings):
    """Runtime configuration, read from ``PULSE_*`` environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="PULSE_",
        env_file=".env",
        extra="ignore",
        secrets_dir=_SECRETS_DIR if _SECRETS_DIR.is_dir() else None,
        # Never echo rejected values (passwords, keys) into error messages and logs.
        hide_input_in_errors=True,
    )

    # Where `pulse serve` listens. Behind a reverse proxy keep 127.0.0.1;
    # the container image sets 0.0.0.0.
    host: str = "127.0.0.1"
    # PULSE_PORT, or PORT as set by container platforms that choose the port.
    port: int = Field(default=8000, validation_alias=AliasChoices("PULSE_PORT", "PORT"))

    # Local state (database, generated SSH key). Created on startup.
    data_dir: Path = Path("data")
    database_url: str = "sqlite+aiosqlite:///./data/pulse.db"
    # Other origins allowed to call the API with the user's cookies (make dev adds
    # the Vite dev server). Empty in production: the web app is served by Pulse itself.
    cors_origins: list[str] = []
    # Built frontend to serve from the API process (e.g. ../frontend/dist).
    static_dir: Path | None = None

    # Authentication. With both set, this admin account is created on startup and
    # its password follows the environment (change it here and restart). Without
    # them, the first visitor creates the admin account in the browser.
    admin_username: str | None = None
    admin_password: SecretStr | None = None
    allow_signup: bool = False  # let anyone with the URL create an account
    # A public site: a landing page and a "Try the demo" button that signs visitors
    # into a temporary guest account with simulated clusters (deleted after a day).
    # Real accounts keep using real Slurm.
    demo: bool = False
    session_days: int = 30
    # "auto": Secure cookies when the request arrived over HTTPS (behind a proxy,
    # set trusted_proxies so the original scheme is known).
    secure_cookies: Literal["auto", "always", "never"] = "auto"
    login_max_failures: int = 10  # per client address and per username...
    login_window_seconds: int = 900  # ...within this window
    # Public address, e.g. https://pulse.example.org. Optional: it pins the
    # domain passkeys are bound to; otherwise each request's own address is used.
    public_url: str | None = None
    # Proxies whose X-Forwarded-For/-Proto headers are trusted ("*" for any).
    trusted_proxies: str = "127.0.0.1"

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

    # Web Push. Unset: Pulse generates a key pair in data_dir on first start.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str | None = None  # contact for push services; defaults to public_url
    # More push service hosts to allow, besides the major browsers' (constants.py).
    push_extra_hosts: list[str] = []
    push_ttl_seconds: int = 6 * 3600  # how long a push service keeps an undelivered alert
    push_timeout_seconds: float = 10.0

    @field_validator("admin_password")
    @classmethod
    def _admin_password_is_strong(cls, value: SecretStr | None) -> SecretStr | None:
        from pulse.constants import PASSWORD_MIN_LENGTH

        if value is not None and len(value.get_secret_value()) < PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"PULSE_ADMIN_PASSWORD must be at least {PASSWORD_MIN_LENGTH} characters"
            )
        return value

    @property
    def ssh_key_file(self) -> Path:
        return self.ssh_key_path or self.data_dir / "pulse_ed25519"


@lru_cache
def get_settings() -> Settings:
    return Settings()
