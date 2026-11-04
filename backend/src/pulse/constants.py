"""Fixed limits and contracts shared across the backend.

Where values live:

- Secrets and anything deployment-specific or worth tuning: ``config.Settings``
  (environment variables / ``.env``).
- Fixed limits and naming contracts: this module.
- Grammar that only one parser interprets (sacct columns, regexes, protobuf
  field numbers): next to that parser.

The login-node agent keeps its own copy of the metric-file rules below because
it must stay a single standalone file; ``tests/test_agent.py`` keeps them equal.
"""

# Metric files in a job's working directory (mirrored in pulse/agent/pulse_agent.py)
CHUNK_BYTES = 256 * 1024  # max new bytes read per file per poll
CONFIG_MAX_BYTES = 64 * 1024
MAX_METRIC_FILES = 8  # newest first, per job
MAX_CONFIG_FILES = 4
SEARCH_DEPTH = 4
PRUNE_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", ".cache")
CONFIG_NAMES = (
    "hparams.yaml",
    "hparams.json",
    "config.yaml",
    "config.yml",
    "config.json",
    "params.json",
    "args.json",
)

# Hyperparameters kept per job
HPARAM_MAX_KEYS = 200
HPARAM_MAX_VALUE_LENGTH = 200

# Metric naming: system metrics are kept apart from training metrics
SYSTEM_METRICS = ("gpu_util", "gpu_mem")  # job-wide averages
SYSTEM_PREFIX = "sys/"  # per node: sys/<node>/cpu, .../mem, .../gpu, .../gpu_mem

# Metric summaries and alerts
EMA_WEIGHT = 0.9
IMPROVEMENT_RATIO = 1e-3  # a new best must beat the old one by 0.1%
MIN_POINTS_FOR_ALERTS = 20  # don't judge a curve on its first few points

# Job output
LOG_TAIL_LINES = 40

# API response sizes
TREND_POINTS = 40  # sparkline in the jobs list
SERIES_POINTS = 500  # system-metric series on the job page
CHART_POINTS = 1000  # per training metric; plenty for a chart, small enough for a phone
ACCOUNT_PALETTE_SIZE = 6  # account colours defined in the frontend

# Live updates
STREAM_KEEPALIVE_SECONDS = 15
STREAM_QUEUE_SIZE = 32  # per connected client; a slow client skips updates

# Scheduling
POLL_TICK_SECONDS = 5  # how often the poller checks which accounts are due

# Web Push
PUSH_EXPIRED_STATUSES = frozenset({404, 410})

# Authentication
SESSION_COOKIE = "pulse_session"
SESSION_RENEW_SECONDS = 3600  # extend a session's expiry at most hourly
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,64}$"
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 256
# scrypt cost (RFC 7914 interactive-login parameters, ~50 ms, 16 MiB)
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
