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
ASSISTANT_MAX_SESSIONS = 8  # connected cluster accounts per Pulse user
ASSISTANT_MAX_INPUT = 16 * 1024
ASSISTANT_MAX_PATH = 4096
ASSISTANT_CHECK_SECONDS = 15
ASSISTANT_MAX_CONNECTIONS = 64
ASSISTANT_MAX_RPC_BYTES = 4 * 1024 * 1024
ASSISTANT_MAX_TEXT = 64 * 1024
ASSISTANT_MAX_ITEMS = 100
ASSISTANT_MAX_PENDING = 32
ASSISTANT_MAX_STATE_CHARS = 128 * 1024

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
HPARAM_MAX_DEPTH = 8  # nesting levels flattened from a config file
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

# Teams
TEAM_INVITE_TTL_SECONDS = 7 * 24 * 3600
TEAM_MAX_PENDING_INVITES = 20
TEAM_MAX_MEMBERS = 100

# SSH keys. The first account keeps Pulse's original key (data_dir/pulse_ed25519
# or PULSE_SSH_KEY_PATH); every other user gets data_dir/ssh/user-<id>_ed25519.
FIRST_USER_ID = 1
USER_KEYS_DIR = "ssh"
# Node-usage samples and metric-file listings of jobs not seen for this long are dropped.
CACHE_MAX_AGE_SECONDS = 3600

# Request bodies larger than this are refused before they're read, so an
# unauthenticated client can't make the server buffer gigabytes. Agent reports
# carry log tails and metric-file chunks; the agent keeps them under
# AGENT_REPORT_BUDGET_BYTES (in pulse_agent.py, which a test keeps below this).
MAX_REQUEST_BYTES = 1024 * 1024
MAX_AGENT_REPORT_BYTES = 16 * 1024 * 1024
AGENT_REPORT_PATH = "/api/agent/report"

# Web Push
PUSH_EXPIRED_STATUSES = frozenset({404, 410})
# Browsers' push services; a subscription anywhere else is refused, so a user
# can't make the server send requests into its own network. Subdomains count.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Android, Opera, Samsung Internet, Brave
    "push.services.mozilla.com",  # Firefox
    "push.apple.com",  # Safari on macOS, iOS and iPadOS
    "notify.windows.com",  # Edge
)
VAPID_KEYS_FILE = "vapid.json"  # in data_dir, when the keys aren't set in the environment
# Contact sent to push services when neither PULSE_VAPID_SUBJECT nor PULSE_PUBLIC_URL is set.
DEFAULT_VAPID_SUBJECT = "mailto:admin@example.com"

# Security headers. Everything the web app loads is same-origin (fonts are
# bundled); inline styles are allowed because React sets style attributes.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "manifest-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
HSTS_MAX_AGE_SECONDS = 365 * 24 * 3600

# Authentication
SESSION_COOKIE = "pulse_session"
SESSION_RENEW_SECONDS = 3600  # extend a session's expiry at most hourly
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,64}$"
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 256
# Passkeys (WebAuthn)
PASSKEY_RP_NAME = "Pulse"  # shown by the browser when creating a passkey
PASSKEY_CHALLENGE_TTL_SECONDS = 300
# Unauthenticated clients can create these, so their number is capped (memory).
PASSKEY_MAX_PENDING_CHALLENGES = 10_000
RATE_LIMIT_MAX_KEYS = 10_000  # addresses and usernames tracked by a rate limiter
# Each sign-up hashes a password (deliberately slow): limit them per address.
SIGNUPS_PER_ADDRESS = 5
SIGNUP_WINDOW_SECONDS = 3600
# Demo guests: temporary accounts with simulated clusters, deleted after this long.
DEMO_GUEST_TTL_SECONDS = 24 * 3600
DEMO_MAX_GUESTS = 1_000  # alive at once; the oldest make way (bounds the database)
DEMO_GUESTS_PER_ADDRESS = 30  # per SIGNUP_WINDOW_SECONDS; a classroom shares one address
DEMO_GUEST_MAX_ACCOUNTS = 5  # simulated clusters per guest
# New accounts per SIGNUP_WINDOW_SECONDS across all addresses, guests and sign-ups
# counted apart. Behind a proxy that passes on a client's own X-Forwarded-For,
# per-address limits can be dodged; this bounds what that buys.
NEW_ACCOUNTS_PER_WINDOW = 300
# Setting a first password on a passkey-only account needs a sign-in this recent,
# so a stolen session can't be turned into a lasting password.
FRESH_SIGN_IN_SECONDS = 10 * 60
# Connecting a cluster assistant needs a sign-in or confirmation this recent.
# Once connected, the browser's grant covers its chats until the connection ends.
ASSISTANT_VERIFIED_SECONDS = 8 * 60 * 60
# Site stats: days shown, and distinct visitors remembered per day (in memory,
# as salted hashes) before new ones are counted as views only.
SITE_STATS_DAYS = 30
SITE_STATS_MAX_VISITORS_PER_DAY = 100_000
ACTIVE_USER_DAYS = 7
PASSKEY_NAME_MAX_LENGTH = 64
PASSKEY_MAX_PER_USER = 20

# scrypt cost (RFC 7914 interactive-login parameters, ~50 ms, 16 MiB)
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
